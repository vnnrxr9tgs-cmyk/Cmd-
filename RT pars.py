import requests
from bs4 import BeautifulSoup
import json
import os
import time

# URL основной страницы
base_url = 'https://russian.rt.com/news'

# Заголовки для имитации браузера
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Папка для сохранения
output_dir = 'news_json'
os.makedirs(output_dir, exist_ok=True)


# Функция для парсинга одной страницы новостей
def parse_news_page(url):
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    news_items = soup.find_all('div', class_='card')
    news_list = []

    for item in news_items:
        # Заголовок и ссылка
        heading_div = item.find('div', class_='card__heading')
        title_tag = heading_div.find('a') if heading_div else None
        title = title_tag.text.strip() if title_tag else 'Без заголовка'
        link = title_tag['href'] if title_tag and 'href' in title_tag.attrs else ''

        # Дата
        date_div = item.find('div', class_='card__date')
        date = date_div.text.strip() if date_div else 'Без даты'

        # Категория
        category_tag = item.find('a', class_='link link_color', href=lambda x: x and not x.startswith('/news'))
        category = category_tag.text.strip() if category_tag else 'Без категории'

        if link:  # Только если есть ссылка
            news_list.append({
                'title': title,
                'link': link,
                'date': date,
                'category': category
            })

    return news_list


# Спарсить 5 страниц
all_news = []
for page in range(1, 6):  # Страницы 1-5
    if page == 1:
        url = base_url
    else:
        # Для дополнительных страниц используем API-подобный URL (на основе data-href)
        url = f'https://russian.rt.com/listing/type.News.tag.novosty-glavnoe/prepare/all-news/15/{page - 1}'

    print(f"Парсим страницу {page}: {url}")
    page_news = parse_news_page(url)
    all_news.extend(page_news)
    time.sleep(1)  # Задержка, чтобы не блокировать

print(f"Всего спарсено {len(all_news)} новостей.")

# Для каждой новости спарсить текст и сохранить в отдельный JSON
for news in all_news:
    link = news['link']
    if not link.startswith('http'):
        link = 'https://russian.rt.com' + link  # Полный URL

    try:
        response = requests.get(link, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Текст новости: обычно в <div class="article__text"> или <p> внутри статьи
        article_div = soup.find('div', class_='article__text') or soup.find('div', class_='article-body')
        if article_div:
            paragraphs = article_div.find_all('p')
            text = '\n'.join([p.text.strip() for p in paragraphs if p.text.strip()])
        else:
            text = 'Текст не найден'

        news['text'] = text

        # Сохранить в отдельный JSON (имя файла по ID новости)
        news_id = link.split('/')[-1].split('-')[0]  # Извлечь ID из ссылки, например 1562392
        filename = f'news_{news_id}.json'
        with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
            json.dump(news, f, ensure_ascii=False, indent=4)

        print(f"Сохранена новость: {filename}")
        time.sleep(0.5)  # Задержка между запросами

    except Exception as e:
        print(f"Ошибка при парсинге {link}: {e}")
        news['text'] = 'Ошибка загрузки текста'
        # Все равно сохранить
        news_id = link.split('/')[-1].split('-')[0] if '/' in link else 'unknown'
        filename = f'news_{news_id}.json'
        with open(os.path.join(output_dir, filename), 'w', encoding='utf-8') as f:
            json.dump(news, f, ensure_ascii=False, indent=4)

print("Парсинг завершен!")