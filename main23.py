from flask import Flask, render_template, abort
import json
import os

app = Flask(__name__)
ARTICLES_DIR = "articles_data_old"

def load_articles():
    articles = []
    if not os.path.exists(ARTICLES_DIR):
        return articles
    for file in os.listdir(ARTICLES_DIR):
        if file.endswith(".json"):
            try:
                with open(os.path.join(ARTICLES_DIR, file), "r", encoding="utf-8") as f:
                    article_data = json.load(f)
                    # Извлекаем site из названия файла (предполагаем формат: site_id.json, например habr_40.json)
                    site = file.split('_')[0] if '_' in file else 'unknown'
                    article_data['site'] = site
                    articles.append(article_data)
            except:
                continue
    # Сортировка по дате
    articles.sort(key=lambda x: x['pubDate'], reverse=True)
    return articles

@app.route("/")
def index():
    articles = load_articles()
    # Фильтруем по сайту для вкладок
    habr_articles = [a for a in articles if a['site'] == 'habr']
    tproger_articles = [a for a in articles if a['site'] == 'tproger']
    return render_template("index.html", habr_articles=habr_articles, tproger_articles=tproger_articles)

@app.route("/article/<site>/<int:article_id>")
def article_page(site, article_id):
    articles_data = load_articles()
    article = next((a for a in articles_data if a['site'] == site and a['id'] == article_id), None)
    if not article:
        abort(404)
    return render_template("article.html", article=article)

if __name__ == "__main__":
    app.run(debug=True)