import json
import time
from datetime import datetime, timedelta
import mysql.connector
import logging

# ---------------- CONFIG ----------------
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "password",
    "database": "test_db"
}

TASK_FILE = "tasks.json"
CHECK_INTERVAL = 5  # проверяем каждые 5 секунд
TIME_WINDOW = 60    # окно выполнения (сек)
# ---------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

executed_tasks = set()

def load_tasks():
    with open(TASK_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def connect_db():
    return mysql.connector.connect(**DB_CONFIG)

def get_task_datetime(task, now):
    task_time = datetime.strptime(task["time"], "%H:%M:%S").time()
    return now.replace(
        hour=task_time.hour,
        minute=task_time.minute,
        second=task_time.second,
        microsecond=0
    )

def should_run(task, now):
    task_dt = get_task_datetime(task, now)

    # ключ уникальности
    task_key = f"{task['id']}_{task_dt}"

    if task_key in executed_tasks:
        return False

    delta = (now - task_dt).total_seconds()

    # если попали в окно выполнения
    if 0 <= delta <= TIME_WINDOW:
        executed_tasks.add(task_key)
        return True

    return False

def execute_task(task, connection):
    try:
        cursor = connection.cursor()
        cursor.execute(task["query"], task["params"])
        connection.commit()
        logging.info(f"Задача {task['id']} выполнена")
    except Exception as e:
        logging.error(f"Ошибка задачи {task['id']}: {e}")

def cleanup_executed(now):
    """Удаляем старые ключи (чтобы память не росла)"""
    to_remove = []
    for key in executed_tasks:
        _, dt_str = key.split("_", 1)
        dt = datetime.fromisoformat(dt_str)
        if now - dt > timedelta(days=1):
            to_remove.append(key)

    for k in to_remove:
        executed_tasks.remove(k)

def scheduler():
    connection = connect_db()

    while True:
        now = datetime.now()

        try:
            tasks = load_tasks()

            for task in tasks:
                if should_run(task, now):
                    execute_task(task, connection)

            cleanup_executed(now)

        except Exception as e:
            logging.error(f"Ошибка цикла: {e}")

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    logging.info("Планировщик запущен")
    scheduler()