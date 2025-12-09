import requests
import xml.etree.ElementTree as ET
import json
from bs4 import BeautifulSoup
import os
import zipfile
import shutil
from datetime import datetime

# RSS ленты
RSS_FEEDS = {
    "habr": "https://habr.com/ru/rss/all/all/",
}

OUTPUT_DIR = "habr_data"
os.makedirs(OUTPUT_DIR, exist_ok=True)

headers = {"User-Agent": "Mozilla/5.0"}
articles = []
article_id = 1

for site_name, RSS_URL in RSS_FEEDS.items():
    print(f"\nСкачиваем RSS с {site_name}...")
    try:
        rss_resp = requests.get(RSS_URL, headers=headers)
        rss_resp.raise_for_status()
        root = ET.fromstring(rss_resp.text)
        items = root.find("channel").findall("item")
    except Exception as e:
        print(f"❌ Ошибка загрузки RSS {site_name}: {e}")
        continue

    for item in items:
        title = item.findtext("title")
        link = item.findtext("link") or item.findtext("guid")
        pubDate_raw = item.findtext("pubDate")
        author = item.findtext("{http://purl.org/dc/elements/1.1/}creator")

        # Дата в формате YYYY-MM-DD HH:MM:SS
        if pubDate_raw:
            pubDate_fixed = pubDate_raw.replace("GMT", "+0000")
            try:
                pubDate_dt = datetime.strptime(pubDate_fixed, "%a, %d %b %Y %H:%M:%S %z")
                pubDate = pubDate_dt.strftime("%Y-%m-%d %H:%M:%S")
                # Форматируем дату для имени файла: YYYY_MM_DD_HHMMSS
                file_date_str = pubDate_dt.strftime("%Y_%m_%d_%H%M%S")
            except Exception:
                pubDate = pubDate_raw
                file_date_str = "nodate"
        else:
            pubDate = ""
            file_date_str = "nodate"

        print(f"{article_id}. {title}")

        if not link:
            continue

        try:
            page_resp = requests.get(link, headers=headers)
            page_resp.raise_for_status()
            html = page_resp.text
        except Exception as e:
            print(f"❌ Ошибка при загрузке статьи: {e}")
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Парсер для тела статьи
        body_div = None
        if site_name == "habr":
            body_div = soup.find("div", class_="tm-article-body") \
                       or soup.find("div", class_="article-formatted-body") \
                       or soup.find("div", class_="post__text")
        elif site_name == "tproger":
            body_div = soup.find("div", class_="post-content") \
                       or soup.find("div", class_="entry-content")

        if body_div:
            # Убираем картинки
            for img in body_div.find_all("img"):
                img.decompose()
            body_html = str(body_div)
        else:
            meta_desc = soup.find("meta", attrs={"name": "description"})
            body_html = meta_desc["content"] if meta_desc else ""

        article_data = {
            "id": article_id,
            "site": site_name,
            "title": title,
            "author": author,
            "pubDate": pubDate,
            "link": link,
            "bodyHtml": body_html
        }

        # Сохраняем в отдельный файл с именем habr_YYYY_MM_DD_HHMMSS.json
        filename = os.path.join(OUTPUT_DIR, f"habr_{file_date_str}.json")

        # Если файл с такой датой уже существует (маловероятно, но на всякий случай)
        counter = 1
        original_filename = filename
        while os.path.exists(filename):
            # Добавляем суффикс только если действительно есть конфликт
            filename = original_filename.replace(".json", f"_{counter}.json")
            counter += 1

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(article_data, f, ensure_ascii=False, indent=4)

        articles.append(article_data)
        article_id += 1

print(f"\nГотово! Сохранено статей: {len(articles)}")
print(f"Файлы находятся в директории: {os.path.abspath(OUTPUT_DIR)}")

# Архивируем папку
zip_filename = f"{OUTPUT_DIR}.zip"
print(f"\nСоздаем архив: {zip_filename}")

try:
    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(OUTPUT_DIR):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, start=OUTPUT_DIR)
                zipf.write(file_path, arcname)

    print(f"✓ Архив успешно создан: {zip_filename}")

    # Удаляем исходную папку
    shutil.rmtree(OUTPUT_DIR)
    print(f"✓ Папка {OUTPUT_DIR} удалена")

except Exception as e:
    print(f"❌ Ошибка при создании архива: {e}")

print("\nРабота завершена!")