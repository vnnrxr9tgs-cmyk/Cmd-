import mysql.connector
import requests
import json

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "deepseek-r1:8b"

def get_mysql_variables(host, user, password):
    """Получаем системные настройки MySQL"""
    conn = mysql.connector.connect(
        host=host,
        user=user,
        password=password
    )
    cur = conn.cursor()

    cur.execute("SHOW GLOBAL VARIABLES;")
    variables = dict(cur.fetchall())

    cur.execute("SHOW GLOBAL STATUS;")
    status = dict(cur.fetchall())

    cur.close()
    conn.close()

    return variables, status


def analyze_with_llm(variables, status):
    """Передаем данные в Ollama и получаем аналитический отчёт"""

    prompt = f"""
Ты эксперт MySQL DBA. Тебе переданы системные настройки MySQL и текущая статистика. 
Проанализируй их и составь краткий отчёт:

1. Основные параметры, на которые стоит обратить внимание  
2. Возможные проблемы  
3. Рекомендации по оптимизации конфигурации  
4. Что улучшить, если MySQL используется под высокую нагрузку

Настройки:
{json.dumps(variables, indent=2, ensure_ascii=False)}

Статус:
{json.dumps(status, indent=2, ensure_ascii=False)}
"""

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": MODEL,
            "prompt": prompt,
            "stream": False
        }
    )

    data = response.json()
    return data.get("response", "Нет ответа от модели")


def main():
    variables, status = get_mysql_variables(
        host="localhost",
        user="root",
        password="123456"
    )

    report = analyze_with_llm(variables, status)

    print("\n===== ОТЧЁТ MySQL =====\n")
    print(report)
    print("\n========================\n")


if __name__ == "__main__":
    main()

import json
import time
from pathlib import Path
import requests

# ====== Настройки ======
OLLAMA_URL = "http://localhost:11434/api/generate"
INPUT_DIR = Path("1")
OUTPUT_DIR = Path("2")

# ====== Промпт для перевода ======
PROMPT = """Ты профессиональный переводчик. Нужен только перевод без лишнего текста.
Переведи следующий текст на русский язык:

{text}"""


# ====== Функция перевода ======
def translate(text):
    time.sleep(0.5)
    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "deepseek-r1:8b",
            "prompt": PROMPT.format(text=text),
            "stream": False
        }
    )
    return response.json()["response"]


# ====== Основной цикл ======
def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    for txt_file in INPUT_DIR.glob("*.txt"):
        print(f"Перевод: {txt_file.name}")

        try:
            text = txt_file.read_text(encoding="utf-8")
            translated = translate(text)

            # Сохраняем в тот же файл в новой директории
            output_file = OUTPUT_DIR / txt_file.name
            output_file.write_text(translated, encoding="utf-8")

            print(f"✅ Сохранено: {output_file}")

        except Exception as e:
            print(f"❌ Ошибка: {txt_file.name} - {e}")


if __name__ == "__main__":
    main()