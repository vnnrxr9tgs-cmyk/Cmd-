import os
from datetime import datetime

# Текст статуса (замените на свой, например, "1234")
status_text = "1234"

# Номер базы данных (bd1, bd2 или bd3; замените на нужный)
# db_name = "bd1"

# Директория для сохранения файлов (текущая директория по умолчанию; измените если нужно)
save_dir = "."  # Например, "db_status_files"

# Получаем текущую дату и время
now = datetime.now()
date_str = now.strftime('%Y%m%d_%H%M%S')

# Формируем имя файла
filename = f"{date_str}_bd1.txt"
filepath = os.path.join(save_dir, filename)

# Создаем директорию, если не существует
os.makedirs(save_dir, exist_ok=True)

# Сохраняем текст в файл
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(status_text)

print(f"Статус сохранен в файл: {filepath}")

