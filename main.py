from flask import Flask, render_template, request, jsonify, Response, stream_with_context, session
import requests
import time
import json
import uuid
from functools import wraps
from datetime import datetime, timedelta
import threading
import base64
import imghdr
import io
from PIL import Image
import secrets

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.config['SESSION_PERMANENT'] = False
app.config['SESSION_TYPE'] = 'filesystem'
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB максимальный размер запроса

# ========== УВЕЛИЧЕННЫЕ ТАЙМАУТЫ ДЛЯ VISION МОДЕЛЕЙ ==========
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
RATE_LIMIT_SECONDS = 3
MAX_TOKENS_LIMIT = 4096

# УВЕЛИЧЕННЫЕ ТАЙМАУТЫ (для обработки изображений)
REQUEST_TIMEOUT_CONNECT = 30  # 30 секунд на подключение
REQUEST_TIMEOUT_READ = 600  # 10 МИНУТ на чтение ответа (было 120 секунд)

# Ограничения для отмены генерации
CANCEL_LIMIT_WINDOW = 30
CANCEL_MAX_ATTEMPTS = 2
CANCEL_BLOCK_DURATION = 60

# Ограничения для изображений
MAX_IMAGE_SIZE_MB = 5  # 5 MB
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
MAX_IMAGE_WIDTH = 4096
MAX_IMAGE_HEIGHT = 4096
ALLOWED_IMAGE_FORMATS = ['jpeg', 'jpg', 'png', 'webp']
ALLOWED_MIME_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']

# Хранилище для отслеживания отмен
cancel_attempts = {}
cancel_blocked_until = {}

last_request_time = {}
active_requests = {}
user_sessions = {}


def validate_image_safe(base64_string, client_mime_type):
    """
    Многоуровневая проверка изображения на сервере
    Возвращает (is_valid, error_message, validated_mime_type)
    """
    # 1. Проверка размера base64 строки
    base64_size = len(base64_string)
    estimated_bytes = int(base64_size * 0.75)  # base64 примерно на 33% больше бинарных данных

    if estimated_bytes > MAX_IMAGE_SIZE_BYTES:
        return False, f"Изображение слишком большое. Максимум {MAX_IMAGE_SIZE_MB}MB", None

    # 2. Проверка, что base64 валидный
    try:
        image_bytes = base64.b64decode(base64_string)
    except Exception as e:
        return False, f"Некорректные данные изображения: {str(e)}", None

    # 3. Проверка реального размера декодированных данных
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        return False, f"Изображение слишком большое после декодирования. Максимум {MAX_IMAGE_SIZE_MB}MB", None

    # 4. Проверка минимального размера (не пустой файл)
    if len(image_bytes) < 100:  # Минимум 100 байт
        return False, "Файл изображения слишком маленький или пустой", None

    # 5. Определение реального типа файла через imghdr (не доверяем клиенту)
    detected_format = imghdr.what(None, h=image_bytes)

    if not detected_format:
        # Пробуем определить через магические байты вручную
        if len(image_bytes) > 4:
            # JPEG
            if image_bytes[0:3] == b'\xff\xd8\xff':
                detected_format = 'jpeg'
            # PNG
            elif image_bytes[0:8] == b'\x89PNG\r\n\x1a\n':
                detected_format = 'png'
            # WEBP
            elif len(image_bytes) > 12 and image_bytes[0:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
                detected_format = 'webp'

    if not detected_format:
        return False, "Файл не является изображением или формат не поддерживается", None

    # 6. Проверка, что формат разрешен
    if detected_format not in ALLOWED_IMAGE_FORMATS:
        return False, f"Формат изображения '{detected_format}' не поддерживается. Разрешены: {', '.join(ALLOWED_IMAGE_FORMATS)}", None

    # 7. Нормализуем mime тип
    if detected_format == 'jpg' or detected_format == 'jpeg':
        validated_mime = 'image/jpeg'
    elif detected_format == 'png':
        validated_mime = 'image/png'
    elif detected_format == 'webp':
        validated_mime = 'image/webp'
    else:
        validated_mime = f'image/{detected_format}'

    # 8. Проверка через PIL (самая надежная) с ограничением размера
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # Проверка размеров изображения
            if img.width > MAX_IMAGE_WIDTH or img.height > MAX_IMAGE_HEIGHT:
                return False, f"Изображение слишком большое: {img.width}x{img.height}. Максимум {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}", None

            # Проверка целостности
            img.verify()

            # Если изображение использует палитру, это безопасно, но мы можем предупредить
            print(f"✅ Изображение валидно: формат={detected_format}, размер={img.width}x{img.height}, режим={img.mode}")

    except Exception as e:
        return False, f"Ошибка обработки изображения: {str(e)}", None

    return True, None, validated_mime


def extract_text_from_content(content):
    """Извлекает текст из содержимого сообщения (может быть строкой или списком для vision)"""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'text':
                texts.append(item.get('text', ''))
        return ' '.join(texts)
    return str(content)


def count_tokens(text):
    """Приблизительный подсчет токенов"""
    if not text:
        return 0
    return len(text) // 2


def check_token_limit(messages, system_prompt, user_message):
    """Проверяет общее количество токенов во входных данных"""
    total_text = system_prompt

    if isinstance(user_message, list):
        user_text = extract_text_from_content(user_message)
    else:
        user_text = user_message

    total_text += user_text

    for msg in messages:
        content = msg.get('content', '')
        total_text += extract_text_from_content(content)

    token_count = count_tokens(total_text)

    if token_count > MAX_TOKENS_LIMIT:
        return False, f"Превышен лимит токенов: {token_count}/{MAX_TOKENS_LIMIT}. Уменьшите историю диалога."

    return True, token_count


def check_cancel_limit(user_id):
    """Проверяет, не превышен ли лимит отмен генерации"""
    now = datetime.now()

    if user_id in cancel_blocked_until:
        if now < cancel_blocked_until[user_id]:
            remaining = int((cancel_blocked_until[user_id] - now).total_seconds())
            return False, f"Вы превысили лимит отмен (2 за 30 сек). Блокировка на {remaining} секунд."
        else:
            del cancel_blocked_until[user_id]
            cancel_attempts[user_id] = []

    if user_id not in cancel_attempts:
        cancel_attempts[user_id] = []

    cutoff = now - timedelta(seconds=CANCEL_LIMIT_WINDOW)
    cancel_attempts[user_id] = [ts for ts in cancel_attempts[user_id] if ts > cutoff]

    if len(cancel_attempts[user_id]) >= CANCEL_MAX_ATTEMPTS:
        cancel_blocked_until[user_id] = now + timedelta(seconds=CANCEL_BLOCK_DURATION)
        return False, f"Слишком много отмен ({CANCEL_MAX_ATTEMPTS} за {CANCEL_LIMIT_WINDOW} сек). Подождите {CANCEL_BLOCK_DURATION} секунд."

    cancel_attempts[user_id].append(now)
    return True, None


def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user_id = request.remote_addr
        now = time.time()

        if user_id in active_requests and active_requests[user_id]:
            return jsonify({
                'error': 'Предыдущий запрос еще обрабатывается. Пожалуйста, подождите или нажмите "Стоп".'
            }), 429

        if user_id in last_request_time:
            elapsed = now - last_request_time[user_id]
            if elapsed < RATE_LIMIT_SECONDS:
                wait_time = round(RATE_LIMIT_SECONDS - elapsed, 1)
                return jsonify({
                    'error': f'Слишком много запросов. Подождите {wait_time} секунд.',
                    'wait_time': wait_time
                }), 429

        last_request_time[user_id] = now
        return f(*args, **kwargs)

    return decorated_function


@app.route('/cancel', methods=['POST'])
def cancel_request():
    """Отменить текущий запрос с проверкой лимита"""
    user_id = request.remote_addr

    is_allowed, error_message = check_cancel_limit(user_id)

    if not is_allowed:
        return jsonify({
            'error': error_message,
            'blocked': True,
            'block_duration': CANCEL_BLOCK_DURATION
        }), 429

    if user_id in active_requests:
        active_requests[user_id] = False
        return jsonify({
            'status': 'cancelled',
            'message': 'Генерация отменена'
        })

    return jsonify({'status': 'no_active_request'})


@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    """Получение сигнала о том, что страница активна"""
    user_id = request.remote_addr
    session_id = request.json.get('session_id', '')

    user_sessions[user_id] = {
        'session_id': session_id,
        'last_heartbeat': time.time(),
        'active': True
    }

    return jsonify({'status': 'ok'})


@app.route('/cleanup_session', methods=['POST'])
def cleanup_session():
    """Очистка при закрытии страницы"""
    user_id = request.remote_addr

    if user_id in active_requests:
        active_requests[user_id] = False

    if user_id in user_sessions:
        user_sessions[user_id]['active'] = False

    return jsonify({'status': 'cleaned'})


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/get_models', methods=['GET'])
def get_models():
    """Получить список доступных моделей из LM Studio"""
    try:
        response = requests.get("http://localhost:1234/v1/models", timeout=5)
        if response.status_code == 200:
            models = response.json()
            model_names = [model['id'] for model in models.get('data', [])]
            return jsonify({'models': model_names, 'server_busy': False})
        else:
            return jsonify({'models': [], 'server_busy': True})
    except:
        return jsonify({'models': [], 'server_busy': True})


@app.route('/chat', methods=['POST'])
@rate_limit
def chat():
    user_id = request.remote_addr
    request_id = str(uuid.uuid4())

    active_requests[user_id] = True

    try:
        data = request.json
        user_message = data.get('message', '').strip()
        conversation_history = data.get('history', [])
        model_name = data.get('model', '')

        # ПРОВЕРКА: выбрана ли модель
        if not model_name or model_name == '':
            active_requests[user_id] = False
            return jsonify({'error': 'Пожалуйста, выберите модель в настройках. Модель не выбрана.'}), 400

        if not user_message and not data.get('image'):
            active_requests[user_id] = False
            return jsonify({'error': 'Введите сообщение или загрузите изображение'}), 400

        # ========== НОВАЯ ПРОВЕРКА ИЗОБРАЖЕНИЯ НА СЕРВЕРЕ ==========
        image_data = data.get('image', None)
        image_mime_type = data.get('image_mime_type', 'image/jpeg')
        validated_image_data = None
        validated_mime_type = None

        if image_data:
            # Проверяем изображение
            is_valid, error_msg, validated_mime = validate_image_safe(image_data, image_mime_type)

            if not is_valid:
                active_requests[user_id] = False
                print(f"[{request_id}] ❌ Ошибка валидации изображения от {user_id}: {error_msg}")
                return jsonify({'error': f'Ошибка валидации изображения: {error_msg}'}), 400

            # Используем проверенные данные
            validated_image_data = image_data
            validated_mime_type = validated_mime or image_mime_type
            print(f"[{request_id}] ✅ Изображение успешно проверено. MIME: {validated_mime_type}")
        # ========================================================

        temperature = float(data.get('temperature', 0.7))
        top_p = float(data.get('top_p', 0.9))
        top_k = int(data.get('top_k', 50))
        presence_penalty = float(data.get('presence_penalty', 0.0))
        frequency_penalty = float(data.get('frequency_penalty', 0.0))
        repeat_penalty = float(data.get('repeat_penalty', 1.0))
        system_prompt = data.get('system_prompt', 'Ты полезный ассистент.')
        max_tokens = int(data.get('max_tokens', 8000))
        stop_sequences = data.get('stop_sequences', [])
        seed = data.get('seed', None)

        messages = [{"role": "system", "content": system_prompt}]

        # Добавляем историю диалога
        for msg in conversation_history:
            messages.append({
                "role": msg['role'],
                "content": msg['content']
            })

        # Формируем сообщение пользователя с возможным изображением
        if validated_image_data:  # Используем проверенные данные
            # Для Vision моделей используем формат с изображением
            user_content = []

            # Добавляем текст, если есть
            if user_message:
                user_content.append({
                    "type": "text",
                    "text": user_message
                })
            else:
                user_content.append({
                    "type": "text",
                    "text": "Что на этом изображении? Опиши подробно, распознай весь текст."
                })

            # Добавляем изображение (используем проверенные данные)
            user_content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{validated_mime_type};base64,{validated_image_data}"
                }
            })

            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": user_message})

        # Проверка токенов (немного изменена для работы с изображениями)
        if validated_image_data:
            user_content_for_tokens = user_content if 'user_content' in locals() else user_message
            is_valid, token_result = check_token_limit(messages, system_prompt, user_content_for_tokens)
        else:
            is_valid, token_result = check_token_limit(messages, system_prompt, user_message)

        if not is_valid:
            active_requests[user_id] = False
            return jsonify({'error': token_result}), 400

        print(f"[{request_id}] Токенов во входных данных: ~{token_result}/{MAX_TOKENS_LIMIT}")
        if validated_image_data:
            print(
                f"[{request_id}] 🖼️ ЗАПРОС С ИЗОБРАЖЕНИЕМ - Таймауты: connect={REQUEST_TIMEOUT_CONNECT}с, read={REQUEST_TIMEOUT_READ}с (10 минут)")

        payload = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "max_tokens": max_tokens,
            "stream": True
        }

        if presence_penalty != 0.0:
            payload["presence_penalty"] = presence_penalty
        if frequency_penalty != 0.0:
            payload["frequency_penalty"] = frequency_penalty
        if repeat_penalty != 1.0:
            payload["repeat_penalty"] = repeat_penalty
        if stop_sequences:
            payload["stop"] = stop_sequences
        if seed is not None:
            payload["seed"] = seed

        def generate():
            full_response = ""
            try:
                # УВЕЛИЧЕННЫЕ ТАЙМАУТЫ ЗДЕСЬ
                response = requests.post(
                    LM_STUDIO_URL,
                    json=payload,
                    stream=True,
                    timeout=(REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ)
                )

                if response.status_code != 200:
                    error_text = response.text[:200]
                    yield f"data: {json.dumps({'error': f'Ошибка LM Studio ({response.status_code}): {error_text}'})}\n\n"
                    return

                # Отправляем уведомление о начале обработки для изображений
                if validated_image_data:
                    yield f"data: {json.dumps({'content': '🖼️ **Обработка изображения...** Это может занять 1-2 минуты...', 'full': ''})}\n\n"

                for line in response.iter_lines():
                    if user_id in user_sessions and not user_sessions[user_id].get('active', True):
                        print(f"[{request_id}] Сессия закрыта")
                        response.close()
                        yield f"data: {json.dumps({'cancelled': True, 'partial': full_response, 'reason': 'session_closed'})}\n\n"
                        return

                    if not active_requests.get(user_id, False):
                        print(f"[{request_id}] Запрос отменен")
                        response.close()
                        yield f"data: {json.dumps({'cancelled': True, 'partial': full_response})}\n\n"
                        return

                    if line:
                        line = line.decode('utf-8')
                        if line.startswith('data: '):
                            data_str = line[6:]
                            if data_str == '[DONE]':
                                break
                            try:
                                chunk = json.loads(data_str)
                                if 'choices' in chunk and len(chunk['choices']) > 0:
                                    delta = chunk['choices'][0].get('delta', {})
                                    content = delta.get('content', '')
                                    if content:
                                        full_response += content
                                        yield f"data: {json.dumps({'content': content, 'full': full_response})}\n\n"
                            except json.JSONDecodeError:
                                continue

                yield f"data: {json.dumps({'done': True, 'full': full_response})}\n\n"

            except requests.exceptions.Timeout:
                print(f"[{request_id}] ❌ ТАЙМАУТ! Превышено время ожидания ({REQUEST_TIMEOUT_READ}с)")
                yield f"data: {json.dumps({'error': f'Превышено время ожидания ответа от LM Studio (10 минут). Для обработки изображения:'})}\n\n"
                yield f"data: {json.dumps({'error': '1. Уменьшите размер изображения\\n2. Используйте изображения меньшего разрешения\\n3. Попробуйте более легкую модель'})}\n\n"
            except requests.exceptions.ConnectionError:
                print(f"[{request_id}] ❌ Ошибка подключения к LM Studio")
                yield f"data: {json.dumps({'error': 'Не удалось подключиться к LM Studio. Проверьте что сервер запущен на порту 1234.'})}\n\n"
            except Exception as e:
                print(f"[{request_id}] ❌ Ошибка: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                active_requests[user_id] = False
                print(f"[{request_id}] Streaming завершен")

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no',
                'Connection': 'keep-alive'
            }
        )

    except Exception as e:
        active_requests[user_id] = False
        print(f"[{request_id}] Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Внутренняя ошибка: {str(e)}'}), 500


if __name__ == '__main__':
    # ПРАВИЛЬНЫЙ ЗАПУСК - без timeout параметра
    app.run(debug=False, host="0.0.0.0", port=5000, threaded=True)