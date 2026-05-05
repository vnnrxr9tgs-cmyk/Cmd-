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
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

# ========== КОНФИГУРАЦИЯ СЕРВЕРОВ LM STUDIO ==========
# Ключ - имя модели (ID), значение - базовый URL сервера (до /v1)
LM_SERVERS = {
    "qwen3-8b": "http://localhost:1234/v1",           # локальный ПК
    "qwen3vl-2b-instruct": "http://localhost:1234/v1",       # удалённый ПК с Vision
    "mistral-7b": "http://192.168.1.101:1234/v1",
    # Добавьте сюда свои модели и их URL
}

# Какие модели поддерживают изображения (Vision)
VISION_SUPPORT = {
    "qwen3-8b": False,
    "qwen3vl-2b-instruct": True,
    "mistral-7b": False,
}
# ===================================================

RATE_LIMIT_SECONDS = 3
MAX_TOKENS_LIMIT = 4096

# Таймауты для запросов (для удалённых серверов)
REQUEST_TIMEOUT_CONNECT = 30
REQUEST_TIMEOUT_READ = 600   # 10 минут

CANCEL_LIMIT_WINDOW = 30
CANCEL_MAX_ATTEMPTS = 2
CANCEL_BLOCK_DURATION = 60

MAX_IMAGE_SIZE_MB = 5
MAX_IMAGE_SIZE_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
MAX_IMAGE_WIDTH = 4096
MAX_IMAGE_HEIGHT = 4096
ALLOWED_IMAGE_FORMATS = ['jpeg', 'jpg', 'png', 'webp']
ALLOWED_MIME_TYPES = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']

cancel_attempts = {}
cancel_blocked_until = {}
last_request_time = {}
active_requests = {}
user_sessions = {}

def validate_image_safe(base64_string, client_mime_type):
    # (оставляем без изменений – ваша существующая реализация)
    base64_size = len(base64_string)
    estimated_bytes = int(base64_size * 0.75)
    if estimated_bytes > MAX_IMAGE_SIZE_BYTES:
        return False, f"Изображение слишком большое. Максимум {MAX_IMAGE_SIZE_MB}MB", None
    try:
        image_bytes = base64.b64decode(base64_string)
    except Exception as e:
        return False, f"Некорректные данные изображения: {str(e)}", None
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        return False, f"Изображение слишком большое после декодирования. Максимум {MAX_IMAGE_SIZE_MB}MB", None
    if len(image_bytes) < 100:
        return False, "Файл изображения слишком маленький или пустой", None
    detected_format = imghdr.what(None, h=image_bytes)
    if not detected_format:
        if len(image_bytes) > 4:
            if image_bytes[0:3] == b'\xff\xd8\xff':
                detected_format = 'jpeg'
            elif image_bytes[0:8] == b'\x89PNG\r\n\x1a\n':
                detected_format = 'png'
            elif len(image_bytes) > 12 and image_bytes[0:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
                detected_format = 'webp'
    if not detected_format:
        return False, "Файл не является изображением или формат не поддерживается", None
    if detected_format not in ALLOWED_IMAGE_FORMATS:
        return False, f"Формат изображения '{detected_format}' не поддерживается. Разрешены: {', '.join(ALLOWED_IMAGE_FORMATS)}", None
    if detected_format == 'jpg' or detected_format == 'jpeg':
        validated_mime = 'image/jpeg'
    elif detected_format == 'png':
        validated_mime = 'image/png'
    elif detected_format == 'webp':
        validated_mime = 'image/webp'
    else:
        validated_mime = f'image/{detected_format}'
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            if img.width > MAX_IMAGE_WIDTH or img.height > MAX_IMAGE_HEIGHT:
                return False, f"Изображение слишком большое: {img.width}x{img.height}. Максимум {MAX_IMAGE_WIDTH}x{MAX_IMAGE_HEIGHT}", None
            img.verify()
    except Exception as e:
        return False, f"Ошибка обработки изображения: {str(e)}", None
    return True, None, validated_mime

def extract_text_from_content(content):
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
    if not text:
        return 0
    return len(text) // 2

def check_token_limit(messages, system_prompt, user_message):
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
            return jsonify({'error': 'Предыдущий запрос еще обрабатывается. Пожалуйста, подождите или нажмите "Стоп".'}), 429
        if user_id in last_request_time:
            elapsed = now - last_request_time[user_id]
            if elapsed < RATE_LIMIT_SECONDS:
                wait_time = round(RATE_LIMIT_SECONDS - elapsed, 1)
                return jsonify({'error': f'Слишком много запросов. Подождите {wait_time} секунд.', 'wait_time': wait_time}), 429
        last_request_time[user_id] = now
        return f(*args, **kwargs)
    return decorated_function

@app.route('/cancel', methods=['POST'])
def cancel_request():
    user_id = request.remote_addr
    is_allowed, error_message = check_cancel_limit(user_id)
    if not is_allowed:
        return jsonify({'error': error_message, 'blocked': True, 'block_duration': CANCEL_BLOCK_DURATION}), 429
    if user_id in active_requests:
        active_requests[user_id] = False
        return jsonify({'status': 'cancelled', 'message': 'Генерация отменена'})
    return jsonify({'status': 'no_active_request'})

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    user_id = request.remote_addr
    session_id = request.json.get('session_id', '')
    user_sessions[user_id] = {'session_id': session_id, 'last_heartbeat': time.time(), 'active': True}
    return jsonify({'status': 'ok'})

@app.route('/cleanup_session', methods=['POST'])
def cleanup_session():
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
    """Вернуть список разрешённых моделей с их свойствами"""
    models_list = []
    for model_id in LM_SERVERS.keys():
        models_list.append({
            "id": model_id,
            "supports_vision": VISION_SUPPORT.get(model_id, False)
        })
    return jsonify({'models': models_list, 'server_busy': False})

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

        # 1. Проверка модели
        if not model_name or model_name not in LM_SERVERS:
            active_requests[user_id] = False
            return jsonify({'error': f'Модель "{model_name}" не найдена или не настроена. Выберите модель из списка.'}), 400

        # 2. Определяем URL сервера
        base_url = LM_SERVERS[model_name]
        lm_studio_url = base_url + "/chat/completions"

        # 3. Обработка изображения
        image_data = data.get('image', None)
        image_mime_type = data.get('image_mime_type', 'image/jpeg')
        validated_image_data = None
        validated_mime_type = None

        if image_data:
            is_valid, error_msg, validated_mime = validate_image_safe(image_data, image_mime_type)
            if not is_valid:
                active_requests[user_id] = False
                return jsonify({'error': f'Ошибка валидации изображения: {error_msg}'}), 400
            validated_image_data = image_data
            validated_mime_type = validated_mime or image_mime_type

        # 4. Параметры
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
        for msg in conversation_history:
            messages.append({"role": msg['role'], "content": msg['content']})

        if validated_image_data:
            user_content = []
            if user_message:
                user_content.append({"type": "text", "text": user_message})
            else:
                user_content.append({"type": "text", "text": "Что на этом изображении? Опиши подробно, распознай весь текст."})
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{validated_mime_type};base64,{validated_image_data}"}
            })
            messages.append({"role": "user", "content": user_content})
        else:
            messages.append({"role": "user", "content": user_message})

        # Проверка токенов
        if validated_image_data:
            is_valid, token_result = check_token_limit(messages, system_prompt, user_content)
        else:
            is_valid, token_result = check_token_limit(messages, system_prompt, user_message)
        if not is_valid:
            active_requests[user_id] = False
            return jsonify({'error': token_result}), 400

        # 5. Полезная нагрузка
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
                response = requests.post(
                    lm_studio_url,
                    json=payload,
                    stream=True,
                    timeout=(REQUEST_TIMEOUT_CONNECT, REQUEST_TIMEOUT_READ)
                )
                if response.status_code != 200:
                    error_text = response.text[:200]
                    yield f"data: {json.dumps({'error': f'Ошибка LM Studio ({response.status_code}): {error_text}'})}\n\n"
                    return

                if validated_image_data:
                    yield f"data: {json.dumps({'content': '🖼️ **Обработка изображения...** Это может занять 1-2 минуты...', 'full': ''})}\n\n"

                for line in response.iter_lines():
                    if user_id in user_sessions and not user_sessions[user_id].get('active', True):
                        response.close()
                        yield f"data: {json.dumps({'cancelled': True, 'partial': full_response, 'reason': 'session_closed'})}\n\n"
                        return
                    if not active_requests.get(user_id, False):
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
                yield f"data: {json.dumps({'error': f'Превышено время ожидания ответа от сервера {model_name} ({REQUEST_TIMEOUT_READ}с).'})}\n\n"
            except requests.exceptions.ConnectionError:
                yield f"data: {json.dumps({'error': f'Не удалось подключиться к серверу для модели {model_name}. Проверьте что LM Studio запущена и доступна по адресу {base_url}'})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                active_requests[user_id] = False

        return Response(
            stream_with_context(generate()),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'}
        )
    except Exception as e:
        active_requests[user_id] = False
        return jsonify({'error': f'Внутренняя ошибка: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)