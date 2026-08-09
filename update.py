import sqlite3
from collections import deque

python -m PyInstaller --onefile --hidden-import psutil --hidden-import requests --name MonitorAgent monitor_agent.py


# Хранилище метрик (последние 1000 записей в памяти + БД)
metrics_buffer = deque(maxlen=1000)

def init_metrics_db():
    """Создание таблицы для метрик"""
    conn = sqlite3.connect('metrics.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hostname TEXT,
            process_name TEXT,
            timestamp TEXT,
            cpu_percent REAL,
            memory_mb REAL,
            uptime_seconds INTEGER,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_metrics_db()

@app.route('/api/metrics', methods=['POST'])
def api_receive_metrics():
    """Приём метрик от агентов"""
    data = request.get_json()
    data['received_at'] = datetime.now().isoformat()
    metrics_buffer.append(data)

    # Сохраняем в БД
    conn = sqlite3.connect('metrics.db')
    cursor = conn.cursor()
    for proc in data.get('processes', []):
        cursor.execute('''
            INSERT INTO metrics (hostname, process_name, timestamp, cpu_percent, memory_mb, uptime_seconds, status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            data['hostname'],
            proc['process_name'],
            data['timestamp'],
            proc['cpu_percent'],
            proc['memory_mb'],
            proc['uptime_seconds'],
            proc['status']
        ))
    conn.commit()
    conn.close()

    return jsonify({'ok': True})


@app.route('/metrics_view')
@login_required
@role_required_from_config()
def metrics_view():
    return render_template('metrics_view.html',
                           username=session.get('username'),
                           user_role=session.get('user_role'),
                           user_name=session.get('user_name'))


@app.route('/api/metrics/latest')
@login_required
def api_metrics_latest():
    """Последние метрики для отображения"""
    # Отдаём последний пакет из буфера
    if metrics_buffer:
        return jsonify(metrics_buffer[-1])
    return jsonify({'processes': []})


@app.route('/api/metrics/history')
@login_required
def api_metrics_history():
    """История для графиков (последние 100 записей)"""
    process = request.args.get('process', '')
    conn = sqlite3.connect('metrics.db')
    cursor = conn.cursor()

    if process:
        cursor.execute('''
            SELECT timestamp, cpu_percent, memory_mb, status 
            FROM metrics 
            WHERE process_name = ? 
            ORDER BY id DESC LIMIT 100
        ''', [process])
    else:
        cursor.execute('''
            SELECT timestamp, cpu_percent, memory_mb, status 
            FROM metrics 
            ORDER BY id DESC LIMIT 100
        ''')

    rows = cursor.fetchall()
    conn.close()

    return jsonify({
        'data': [
            {'timestamp': r[0], 'cpu': r[1], 'memory': r[2], 'status': r[3]}
            for r in reversed(rows)
        ]
    })