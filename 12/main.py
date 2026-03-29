from flask import Flask, render_template
import json, os
from datetime import datetime
import markdown

app = Flask(__name__)

OUTPUTS_DIR = "outputs"

@app.route("/")
def index():
    files = [f for f in os.listdir(OUTPUTS_DIR) if f.endswith(".json")]
    news_list = []

    for f in files:
        with open(os.path.join(OUTPUTS_DIR, f), "r", encoding="utf-8") as file:
            data = json.load(file)

            text = data["processed_text"]

            # анализ
            blocks = [b for b in text.split("\n\n") if b.strip()]
            articles_count = len(blocks)
            chars_count = len(text)

            news_list.append({
                "id": f,
                "title": data["original_filename"].replace(".docx", ""),
                "date": datetime.fromisoformat(data["processed_at"]).strftime("%d.%m.%Y %H:%M"),
                "language": data.get("language", "unknown"),
                "articles_count": articles_count,
                "chars_count": chars_count,
                "full_text": text  # добавляем полный текст для поиска
            })

    news_list.sort(key=lambda x: x["date"], reverse=True)

    return render_template("index.html", news=news_list)

@app.route("/news/<filename>")
def detail(filename):
    path = os.path.join(OUTPUTS_DIR, filename)

    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        html_text = markdown.markdown(data["processed_text"], extensions=["extra"])

        return render_template("detail.html", data=data, html_text=html_text)

    return "Файл не найден", 404

if __name__ == "__main__":
    app.run(debug=True, port=5000)