from flask import Flask, render_template
import os
import glob
from datetime import datetime

app = Flask(__name__)

# Путь к директории с файлами (измените на свой)
DB_STATUS_DIR = 'db_status_files'


def get_latest_db_status():
    """
    Сканирует директорию и возвращает самые свежие файлы для bd1, bd2, bd3.
    Возвращает словарь: {'bd1': {'date': datetime_object, 'content': 'текст'}, ...} или None если нет файла.
    """
    files = glob.glob(os.path.join(DB_STATUS_DIR, '*_*_bd*.txt'))
    db_status = {'bd1': None, 'bd2': None, 'bd3': None}

    for file in files:
        filename = os.path.basename(file)
        try:
            # Парсим имя файла: YYYYMMDD_HHMMSS_bdX
            parts = filename.split('_')
            if len(parts) == 3 and parts[2].startswith('bd') and parts[2].endswith('.txt'):
                date_str = parts[0] + parts[1]
                db_name = parts[2].replace('.txt', '')
                if db_name in db_status:
                    # Преобразуем в datetime для сравнения
                    file_date = datetime.strptime(date_str, '%Y%m%d%H%M%S')
                    if db_status[db_name] is None or file_date > db_status[db_name]['date']:
                        with open(file, 'r', encoding='utf-8') as f:
                            content = f.read()
                        db_status[db_name] = {'date': file_date, 'content': content}
        except (ValueError, IndexError):
            continue  # Пропускаем некорректные файлы

    return db_status


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/status_db')
def status_db():
    db_status = get_latest_db_status()
    return render_template('status_db.html', db_status=db_status)


if __name__ == '__main__':
    app.run(debug=True)