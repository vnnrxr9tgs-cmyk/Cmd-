"""
Агент мониторинга процессов Windows
Собирает метрики и отправляет на Flask-сервер
"""
import psutil
import time
import requests
import json
import logging
from datetime import datetime

# ===== ЗАГРУЗКА КОНФИГА =====
try:
    with open('monitor_config.json', 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    print("❌ Файл monitor_config.json не найден!")
    exit(1)

SERVER_URL = CONFIG['server_url']  # http://192.168.1.100:5000
PROCESS_NAMES = CONFIG['processes']  # ["python.exe", "notepad.exe", "chrome.exe"]
INTERVAL = CONFIG.get('interval', 2)  # секунды между замерами
HOSTNAME = CONFIG.get('hostname', 'server-1')  # имя этого сервера

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    handlers=[logging.FileHandler('monitor_agent.log', encoding='utf-8')]
)
logger = logging.getLogger(__name__)

def get_system_metrics():
    """Общая загрузка системы"""
    return {
        'cpu_total': round(psutil.cpu_percent(interval=0.5), 1),
        'ram_total_percent': round(psutil.virtual_memory().percent, 1),
        'ram_total_mb': round(psutil.virtual_memory().total / 1024 / 1024),
        'ram_used_mb': round(psutil.virtual_memory().used / 1024 / 1024),
        'ram_free_mb': round(psutil.virtual_memory().available / 1024 / 1024),
        'cpu_cores': psutil.cpu_count(),
        'cpu_freq': round(psutil.cpu_freq().current, 1) if psutil.cpu_freq() else 0
    }

def get_process_metrics(process_name):
    """Сбор метрик для конкретного процесса"""
    metrics = {
        'process_name': process_name,
        'running': False,
        'cpu_percent': 0.0,
        'memory_mb': 0.0,
        'uptime_seconds': 0,
        'status': 'not_found',
        'pid': None
    }

    for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_info', 'create_time', 'status']):
        try:
            if proc.info['name'].lower() == process_name.lower():
                metrics['running'] = True
                metrics['pid'] = proc.info['pid']
                metrics['cpu_percent'] = round(proc.cpu_percent(interval=0.5), 1)
                metrics['memory_mb'] = round(proc.info['memory_info'].rss / 1024 / 1024, 1)
                metrics['uptime_seconds'] = int(time.time() - proc.info['create_time'])

                # Статус: running, sleeping, not_responding
                status = str(proc.info['status'])
                if status == 'running':
                    metrics['status'] = 'active'
                elif status == 'sleeping':
                    metrics['status'] = 'idle'
                else:
                    metrics['status'] = status

                # Проверка на зависание (не отвечает > 30 сек)
                try:
                    if not proc.is_running():
                        metrics['status'] = 'not_responding'
                except:
                    metrics['status'] = 'not_responding'

                break
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return metrics


def send_metrics(data):
    """Отправка метрик на сервер"""
    try:
        response = requests.post(
            f"{SERVER_URL}/api/metrics",
            json=data,
            timeout=3
        )
        if response.status_code == 200:
            logger.info(f"✅ Отправлено: {len(data['processes'])} процессов")
        else:
            logger.warning(f"⚠️ Сервер ответил: {response.status_code}")
    except requests.exceptions.ConnectionError:
        logger.error(f"❌ Нет соединения с сервером {SERVER_URL}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки: {e}")


def main():
    print(f"🚀 Агент мониторинга запущен")
    print(f"📡 Сервер: {SERVER_URL}")
    print(f"📋 Процессы: {', '.join(PROCESS_NAMES)}")
    print(f"⏱️  Интервал: {INTERVAL} сек")
    print("-" * 50)

    while True:
        try:
            payload = {
                'hostname': HOSTNAME,
                'timestamp': datetime.now().isoformat(),
                'system': get_system_metrics(),
                'processes': []
            }

            for proc_name in PROCESS_NAMES:
                metrics = get_process_metrics(proc_name)
                payload['processes'].append(metrics)


            send_metrics(payload)
            time.sleep(INTERVAL)

        except KeyboardInterrupt:
            print("\n⏹️ Агент остановлен")
            break
        except Exception as e:
            logger.error(f"❌ Ошибка: {e}")
            time.sleep(INTERVAL)


if __name__ == '__main__':
    main()