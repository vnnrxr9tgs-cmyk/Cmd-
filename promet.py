import time
import socket
import psutil
from prometheus_client import start_http_server, Gauge

# Имя процесса
TARGET_PROCESS = "qwerty.exe"

# Имя хоста
HOSTNAME = socket.gethostname()

# Метрика времени работы процесса
process_uptime = Gauge(
    "process_uptime_seconds",
    "Время работы процесса",
    ["host", "process", "pid"]
)


def collect_metrics():
    now = time.time()

    # Очищаем старые значения (важно!)
    process_uptime.clear()

    for proc in psutil.process_iter(['pid', 'name', 'create_time']):
        try:
            if proc.info['name'] == TARGET_PROCESS:
                uptime = now - proc.info['create_time']

                process_uptime.labels(
                    host=HOSTNAME,
                    process=proc.info['name'],
                    pid=str(proc.info['pid'])
                ).set(uptime)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


if __name__ == "__main__":
    start_http_server(8000)
    print("Exporter started on port 8000")

    while True:
        collect_metrics()
        time.sleep(5)

# Имя хоста
HOSTNAME = socket.gethostname()

process_uptime = Gauge(
    "process_uptime_seconds",
    "Время работы процесса",
    ["host", "process", "pid"]
)

def collect_metrics():
    now = time.time()
    process_uptime.clear()

    for proc in psutil.process_iter(['pid', 'name', 'create_time']):
        try:
            name = proc.info['name']

            if name in TARGET_PROCESSES:
                uptime = now - proc.info['create_time']

                process_uptime.labels(
                    host=HOSTNAME,
                    process=name,
                    pid=str(proc.info['pid'])
                ).set(uptime)

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


if __name__ == "__main__":
    start_http_server(8000)
    print("Exporter started on port 8000")

    while True:
        collect_metrics()
        time.sleep(5)

pyinstaller --onefile --clean --noconsole exporter.py

process_uptime_seconds
