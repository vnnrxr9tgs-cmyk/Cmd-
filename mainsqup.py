import re
import time
import shutil
import logging
from pathlib import Path
from datetime import datetime


# ============================================================
# НАСТРОЙКИ
# ============================================================

# Откуда берём файлы
SOURCE_DIR = Path("in")

# Куда перемещаем выбранные файлы
DEST_DIR = Path("out")

# Интервал запуска обработки
CHECK_INTERVAL = 30  # секунд

# Обрабатывать только файлы старше 4 минут
MIN_FILE_AGE = 4 * 60  # 240 секунд

# Максимальный диапазон времени внутри одной группы
GROUP_INTERVAL = 20  # секунд


# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# ============================================================
# PARSE FILE NAME
# ============================================================

FILE_PATTERN = re.compile(
    r"^.*?_(?P<unique_id>\d+)_"
    r"(?P<date>\d{4}_\d{2}_\d{2})__"
    r"(?P<time>\d{2}_\d{2}_\d{2})"
    r"(?:_.*)?$"
)


def parse_filename(file_path: Path):
    """
    Разбирает имя файла.

    Пример:

        abc_cvb_3456__2026_09_01__02_04_07_1

    Получаем:

        unique_id = "3456"
        datetime = 2026-09-01 02:04:07

    Возвращает:
        (unique_id, datetime)

    или None, если имя не соответствует формату.
    """

    match = FILE_PATTERN.match(file_path.stem)

    if not match:
        return None

    unique_id = match.group("unique_id")

    date_string = match.group("date")
    time_string = match.group("time")

    datetime_string = f"{date_string}__{time_string}"

    try:
        file_datetime = datetime.strptime(
            datetime_string,
            "%Y_%m_%d__%H_%M_%S",
        )
    except ValueError:
        return None

    return unique_id, file_datetime


# ============================================================
# GET FILES
# ============================================================

def get_files():
    """
    Возвращает файлы, которые:

    1. являются обычными файлами;
    2. имеют правильное имя;
    3. находятся в директории больше 4 минут.
    """

    current_time = time.time()

    result = []

    try:
        entries = list(SOURCE_DIR.iterdir())
    except Exception:
        logging.exception(
            "Не удалось прочитать директорию: %s",
            SOURCE_DIR,
        )
        return result

    for file_path in entries:

        # Только файлы
        try:
            if not file_path.is_file():
                continue
        except OSError:
            continue

        # Разбираем имя
        parsed = parse_filename(file_path)

        if parsed is None:
            logging.warning(
                "Пропускаем файл с неправильным именем: %s",
                file_path.name,
            )
            continue

        unique_id, file_datetime = parsed

        # Получаем информацию о файле
        try:
            stat = file_path.stat()
        except FileNotFoundError:
            # Файл мог исчезнуть между iterdir() и stat()
            continue
        except OSError:
            logging.exception(
                "Не удалось получить информацию о файле: %s",
                file_path,
            )
            continue

        # Возраст файла по mtime
        file_age = current_time - stat.st_mtime

        # Файл ещё слишком новый
        if file_age < MIN_FILE_AGE:
            continue

        result.append(
            {
                "path": file_path,
                "unique_id": unique_id,
                "datetime": file_datetime,
                "size": stat.st_size,
                "mtime": stat.st_mtime,
            }
        )

    return result


# ============================================================
# GROUP FILES
# ============================================================

def create_groups(files):
    """
    Формирует группы.

    Главное правило:

        max(datetime группы) - min(datetime группы) <= 20 секунд

    То есть сравниваем каждый новый файл НЕ с предыдущим,
    а с первым файлом текущей группы.

    Пример:

        02:00:00
        02:00:10
        02:00:20
        02:00:30

    Получаем:

        Группа 1:
            02:00:00
            02:00:10
            02:00:20

        Группа 2:
            02:00:30

    Дополнительно unique_id должен совпадать.
    """

    # --------------------------------------------------------
    # Сначала разбиваем по unique_id
    # --------------------------------------------------------

    files_by_id = {}

    for file_info in files:

        unique_id = file_info["unique_id"]

        if unique_id not in files_by_id:
            files_by_id[unique_id] = []

        files_by_id[unique_id].append(file_info)

    # --------------------------------------------------------
    # Формируем группы отдельно для каждого unique_id
    # --------------------------------------------------------

    groups = []

    for unique_id, unique_files in files_by_id.items():

        # Сортировка по времени из имени файла
        unique_files.sort(
            key=lambda item: item["datetime"]
        )

        current_group = []
        group_start_time = None

        for file_info in unique_files:

            # ------------------------------------------------
            # Начинаем новую группу
            # ------------------------------------------------

            if not current_group:

                current_group = [file_info]
                group_start_time = file_info["datetime"]

                continue

            # ------------------------------------------------
            # Считаем разницу от ПЕРВОГО файла группы
            # ------------------------------------------------

            difference = (
                file_info["datetime"] - group_start_time
            ).total_seconds()

            # ------------------------------------------------
            # Файл помещается в текущую группу
            # ------------------------------------------------

            if difference <= GROUP_INTERVAL:

                current_group.append(file_info)

            # ------------------------------------------------
            # Файл уже не помещается
            # ------------------------------------------------

            else:

                groups.append(current_group)

                current_group = [file_info]

                group_start_time = file_info["datetime"]

        # ----------------------------------------------------
        # Добавляем последнюю группу
        # ----------------------------------------------------

        if current_group:
            groups.append(current_group)

    return groups


# ============================================================
# SAFE MOVE
# ============================================================

def move_file(source: Path, destination_dir: Path):
    """
    Безопасно перемещает файл.

    Если файл с таким именем уже существует в destination,
    добавляет числовой суффикс, чтобы не затереть существующий.
    """

    if not source.exists():
        logging.warning(
            "Файл уже отсутствует: %s",
            source,
        )
        return False

    destination = destination_dir / source.name

    # --------------------------------------------------------
    # Если файл с таким именем уже существует
    # --------------------------------------------------------

    if destination.exists():

        stem = source.stem
        suffix = source.suffix

        counter = 1

        while True:

            new_name = f"{stem}_{counter}{suffix}"
            candidate = destination_dir / new_name

            if not candidate.exists():
                destination = candidate
                break

            counter += 1

    try:

        shutil.move(
            str(source),
            str(destination),
        )

        logging.info(
            "MOVE: %s -> %s",
            source.name,
            destination,
        )

        return True

    except FileNotFoundError:

        logging.warning(
            "Файл исчез во время перемещения: %s",
            source,
        )

    except Exception:

        logging.exception(
            "Ошибка перемещения: %s",
            source,
        )

    return False


# ============================================================
# PROCESS ONE GROUP
# ============================================================

def process_group(group):
    """
    Обрабатывает одну группу.

    Из группы:
        - самый большой файл -> move
        - второй самый большой -> move
        - остальные -> delete

    Если файл один:
        - он перемещается.
    """

    if not group:
        return

    # --------------------------------------------------------
    # Сортируем от самого большого к самому маленькому
    # --------------------------------------------------------

    group.sort(
        key=lambda item: item["size"],
        reverse=True,
    )

    files_to_move = group[:2]
    files_to_delete = group[2:]

    # --------------------------------------------------------
    # Информация о группе
    # --------------------------------------------------------

    unique_id = group[0]["unique_id"]

    start_time = min(
        item["datetime"]
        for item in group
    )

    end_time = max(
        item["datetime"]
        for item in group
    )

    group_duration = (
        end_time - start_time
    ).total_seconds()

    logging.info(
        "Группа: ID=%s | файлов=%d | "
        "время=%s - %s | диапазон=%s сек",
        unique_id,
        len(group),
        start_time,
        end_time,
        group_duration,
    )

    # --------------------------------------------------------
    # Перемещаем 2 самых больших
    # --------------------------------------------------------

    for file_info in files_to_move:

        source = file_info["path"]

        move_file(
            source,
            DEST_DIR,
        )

    # --------------------------------------------------------
    # Удаляем остальные
    # --------------------------------------------------------

    for file_info in files_to_delete:

        file_path = file_info["path"]

        try:

            if not file_path.exists():
                continue

            file_path.unlink()

            logging.info(
                "DELETE: %s | size=%d bytes",
                file_path.name,
                file_info["size"],
            )

        except FileNotFoundError:

            logging.warning(
                "Файл уже отсутствует: %s",
                file_path,
            )

        except Exception:

            logging.exception(
                "Ошибка удаления файла: %s",
                file_path,
            )


# ============================================================
# ONE PROCESSING CYCLE
# ============================================================

def process_files():

    logging.info(
        "========================================"
    )

    logging.info(
        "Начало цикла обработки"
    )

    # --------------------------------------------------------
    # Получаем подходящие файлы
    # --------------------------------------------------------

    files = get_files()

    if not files:

        logging.info(
            "Нет файлов старше %d секунд",
            MIN_FILE_AGE,
        )

        return

    logging.info(
        "Найдено файлов для обработки: %d",
        len(files),
    )

    # --------------------------------------------------------
    # Создаём группы
    # --------------------------------------------------------

    groups = create_groups(files)

    logging.info(
        "Сформировано групп: %d",
        len(groups),
    )

    # --------------------------------------------------------
    # Обрабатываем группы
    # --------------------------------------------------------

    for group in groups:

        process_group(group)

    logging.info(
        "Цикл обработки завершён"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    # --------------------------------------------------------
    # Создаём директории, если их нет
    # --------------------------------------------------------

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    DEST_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    logging.info(
        "========================================"
    )

    logging.info(
        "Сервис запущен"
    )

    logging.info(
        "SOURCE_DIR: %s",
        SOURCE_DIR,
    )

    logging.info(
        "DEST_DIR:   %s",
        DEST_DIR,
    )

    logging.info(
        "Проверка каждые %d секунд",
        CHECK_INTERVAL,
    )

    logging.info(
        "Минимальный возраст файла: %d секунд",
        MIN_FILE_AGE,
    )

    logging.info(
        "Максимальный диапазон группы: %d секунд",
        GROUP_INTERVAL,
    )

    logging.info(
        "========================================"
    )

    # --------------------------------------------------------
    # Бесконечный цикл
    # --------------------------------------------------------

    while True:

        try:

            process_files()

        except KeyboardInterrupt:

            logging.info(
                "Получен сигнал остановки"
            )

            break

        except Exception:

            # Ошибка не должна остановить сервис
            logging.exception(
                "Критическая ошибка цикла"
            )

        # ----------------------------------------------------
        # Ждём 30 секунд
        # ----------------------------------------------------

        time.sleep(CHECK_INTERVAL)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()