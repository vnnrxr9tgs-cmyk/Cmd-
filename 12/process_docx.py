import os
import json
import requests
import re
import shutil
from datetime import datetime
from docx import Document
import langdetect

# ================== НАСТРОЙКИ ==================
LM_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "qwen3-8b"  # ← ОБЯЗАТЕЛЬНО замени на точное имя твоей модели

TRANSCRIPTIONS_DIR = "transcriptions"
ARCHIVE_DIR = "archive"
OUTPUTS_DIR = "outputs"

# Создаём необходимые папки
os.makedirs(TRANSCRIPTIONS_DIR, exist_ok=True)
os.makedirs(ARCHIVE_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)


def extract_text(docx_path):
    doc = Document(docx_path)
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip())


def clean_think_tags(text: str) -> str:
    """Агрессивная очистка от <think> блоков и китайского текста"""
    if not text:
        return ""

    # Удаляем блоки <think>...</think>
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', text, flags=re.IGNORECASE)

    # Удаляем незакрытый <think> до конца
    cleaned = re.sub(r'<think>[\s\S]*$', '', cleaned, flags=re.IGNORECASE)

    # Удаляем остатки </think>
    cleaned = re.sub(r'^\s*</think>\s*', '', cleaned, flags=re.IGNORECASE)

    # Удаляем китайские иероглифы (если просочатся)
    cleaned = re.sub(r'[\u4e00-\u9fff]+', '', cleaned)

    # Убираем лишние пустые строки в начале
    cleaned = re.sub(r'^\s*\n+', '', cleaned).strip()

    return cleaned


def process_file(docx_path):
    filename = os.path.basename(docx_path)
    json_path = os.path.join(OUTPUTS_DIR, filename.replace(".docx", ".json"))

    # Если JSON уже существует — файл уже обработан
    if os.path.exists(json_path):
        print(f"⏭ Уже обработан: {filename} → перемещаю в архив")
        shutil.move(docx_path, os.path.join(ARCHIVE_DIR, filename))
        return

    print(f"🔄 Обрабатываю: {filename}")

    text = extract_text(docx_path)
    if not text.strip():
        print("⚠ Пустой файл")
        return

    try:
        lang = langdetect.detect(text[:800])
    except:
        lang = "ru"

    # Читаем промт
    with open("prompt.txt", "r", encoding="utf-8") as f:
        prompt_template = f.read()

    full_prompt = prompt_template.format(text=text, language=lang)

    # Запрос к LM Studio
    payload = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": full_prompt}],
        "temperature": 0.25,
        "max_tokens": 6500
    }

    try:
        response = requests.post(LM_URL, json=payload, timeout=760)

        if response.status_code != 200:
            print(f"❌ Ошибка LM Studio ({response.status_code}): {response.text[:300]}")
            return

        result = response.json()
        raw_content = result["choices"][0]["message"]["content"].strip()

        # Очистка от <think> и китайского
        processed_text = clean_think_tags(raw_content)

        # Fallback: если после очистки почти ничего нет
        if len(processed_text) < 100 and '</think>' in raw_content:
            processed_text = raw_content.split('</think>')[-1].strip()

        if not processed_text:
            processed_text = raw_content

        # Сохраняем результат
        data = {
            "original_filename": filename,
            "processed_at": datetime.now().isoformat(),
            "language": lang,
            "processed_text": processed_text
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # ← Перемещаем оригинальный DOCX в архив
        shutil.move(docx_path, os.path.join(ARCHIVE_DIR, filename))

        print(f"✅ Готово! Результат сохранён → {json_path}")
        print(f"   Файл перемещён в архив → {ARCHIVE_DIR}/")

    except Exception as e:
        print(f"❌ Ошибка при обработке {filename}: {e}")


# ================== ЗАПУСК ==================
if __name__ == "__main__":
    print("🚀 Запуск обработки транскрипций с HF-радио...\n")

    count = 0
    for file in os.listdir(TRANSCRIPTIONS_DIR):
        if file.lower().endswith(".docx"):
            process_file(os.path.join(TRANSCRIPTIONS_DIR, file))
            count += 1

    if count == 0:
        print("В папке 'transcriptions' нет .docx файлов.")
    else:
        print(f"\n🎉 Обработка завершена! Обработано файлов: {count}")
        print(f"   Тезисы сохранены в папке: outputs/")
        print(f"   Оригинальные DOCX перемещены в папку: archive/")