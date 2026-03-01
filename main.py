import requests
import json

# Настройки подключения
LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
# Важно: В LM Studio в разделе "Server" часто указывают ID модели.
# Если не знаете, что там написано, попробуйте "local-model" или название вашей модели (например, "llama-3-8b")
MODEL_NAME = "t-lite-it-2.1"

# Путь к вашему CSV файлу
CSV_FILE_PATH = "shop1_yesterday.csv"


def send_csv_to_lm_studio(file_path):
    # 1. Читаем CSV файл целиком как текст
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            csv_content = f.read()
    except FileNotFoundError:
        print(f"Файл {file_path} не найден.")
        return

    # 2. Формируем сообщения
    # Системное сообщение: говорим модели, что она должна делать
    system_message = "Ты — эксперт по анализу данных. Твоя задача — проанализировать предоставленный CSV-файл, найти закономерности и выдать краткую выжимку (сводку)."

    # Пользовательское сообщение: прикрепляем содержимое файла
    user_message = f"Вот содержимое CSV файла:\n\n```csv\n{csv_content}\n```"

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.7,  # Настройки генерации
        "stream": False
    }

    print("Отправка данных в LM Studio... Это может занять некоторое время.")

    # 3. Отправляем POST запрос
    try:
        response = requests.post(LM_STUDIO_URL, json=payload, timeout=600)  # timeout 5 минут

        # Проверка на ошибки
        response.raise_for_status()

        # 4. Получаем и выводим ответ
        result = response.json()

        # Структура ответа от OpenAI-совместимого API
        if 'choices' in result and len(result['choices']) > 0:
            ai_response = result['choices'][0]['message']['content']
            print("\n--- Ответ модели ---\n")
            print(ai_response)
        else:
            print("Ошибка в структуре ответа:", result)

    except requests.exceptions.ConnectionError:
        print("Ошибка: Не удалось подключиться к LM Studio.")
        print("Убедитесь, что сервер запущен (вкладка 'Server' в LM Studio) и выбрана модель.")
    except Exception as e:
        print(f"Произошла ошибка: {e}")


if __name__ == "__main__":
    send_csv_to_lm_studio(CSV_FILE_PATH)