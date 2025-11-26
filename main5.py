import os
import shutil
import chardet
import re


def is_word(token):
    """
    Проверяет, что токен содержит хотя бы 60% букв.
    Подходит для любых языков (Unicode).
    """
    letters = sum(1 for c in token if c.isalpha())
    return letters / len(token) >= 0.6 if token else False


def detect_text_blocks(text, min_word_ratio=0.3):
    """
    Разбивает текст на строки и проверяет каждую строку на наличие слов.
    Если хотя бы одна строка содержит достаточное количество слов, считаем текст читаемым.
    """
    lines = text.splitlines()
    for line in lines:
        tokens = re.findall(r'\b\w+\b', line, re.UNICODE)
        if not tokens:
            continue
        readable_tokens = [t for t in tokens if is_word(t)]
        ratio = len(readable_tokens) / len(tokens)
        if ratio >= min_word_ratio:
            return True
    return False


def is_readable_file(file_path):
    try:
        # Читаем бинарно
        with open(file_path, 'rb') as f:
            raw_data = f.read()
    except (OSError, IOError) as e:
        print(f"Ошибка чтения файла {file_path}: {e}")
        return False

    # Определяем кодировку
    result = chardet.detect(raw_data)
    encoding = result['encoding']
    if not encoding:
        return False

    try:
        text = raw_data.decode(encoding)
    except (UnicodeDecodeError, TypeError) as e:
        print(f"Ошибка декодирования файла {file_path}: {e}")
        return False

    # Проверяем блоки текста
    return detect_text_blocks(text)


# Основная функция для сканирования директории и перемещения файлов
def scan_and_move_files(directory_path, dir_A="A", dir_B="B"):
    # Создаем директории A и B, если они не существуют
    try:
        os.makedirs(dir_A, exist_ok=True)
        os.makedirs(dir_B, exist_ok=True)
    except OSError as e:
        print(f"Ошибка создания директорий: {e}")
        return

    # Сканируем директорию
    try:
        files = [f for f in os.listdir(directory_path) if os.path.isfile(os.path.join(directory_path, f))]
    except OSError as e:
        print(f"Ошибка сканирования директории {directory_path}: {e}")
        return

    for file_name in files:
        file_path = os.path.join(directory_path, file_name)
        if is_readable_file(file_path):
            target_dir = dir_A
            print(f"{file_name} содержит осмысленный текст. Перемещаем в {dir_A}.")
        else:
            target_dir = dir_B
            print(f"{file_name} похоже на случайный набор байт. Перемещаем в {dir_B}.")

        try:
            shutil.move(file_path, os.path.join(target_dir, file_name))
        except (OSError, IOError) as e:
            print(f"Ошибка перемещения файла {file_name}: {e}")


# Пример использования: сканируем текущую директорию
scan_and_move_files("С")
