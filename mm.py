import sys
import json
import time
import socket
import os
import subprocess
from functools import partial

from PyQt5.QtWidgets import *
from PyQt5.QtCore import QTimer, Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor, QFont


TOKEN = "12345"
UPDATE_INTERVAL = 5000
HOSTS_CONFIG = []
EXCLUDED_IPS = set()


# ====================== СЕТЬ ======================
def send_cmd(ip, port, cmd):
    try:
        with socket.create_connection((ip, port), timeout=5) as sock:
            sock.sendall((json.dumps(cmd) + "\n").encode("utf-8"))
            data = sock.recv(65536).decode("utf-8", errors="ignore").strip()
            return ip, json.loads(data)
    except Exception as e:
        return ip, {"error": str(e)}


# ====================== WORKER ======================
class Worker(QThread):
    finished = pyqtSignal(list)

    def run(self):
        results = []
        for h in HOSTS_CONFIG:
            if h["ip"] in EXCLUDED_IPS:
                continue

            cmd = {
                "cmd": "list",
                "token": TOKEN,
                "processes": h.get("monitor_processes", [])
            }

            results.append(send_cmd(h["ip"], h["port"], cmd))

        self.finished.emit(results)


# ====================== UI ======================
class MonitorWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Process Monitor")
        self.resize(1150, 650)
        self.setFont(QFont("Segoe UI", 9))

        self.worker = None

        self.load_config()
        self.init_ui()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.start_update)
        self.timer.start(UPDATE_INTERVAL)

    def init_ui(self):
        layout = QVBoxLayout(self)

        top = QHBoxLayout()

        self.last_update_label = QLabel("Последнее обновление: —")
        self.last_update_label.setStyleSheet("font-weight: bold;")
        top.addWidget(self.last_update_label)

        btn = QPushButton("Обновить")
        btn.clicked.connect(self.start_update)
        top.addWidget(btn)

        top.addStretch()
        layout.addLayout(top)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "IP", "Описание", "Процесс", "Время", "Kill", "RDP"
        ])

        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)

        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(1, 180)
        self.table.setColumnWidth(2, 200)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 70)
        self.table.setColumnWidth(5, 100)

        layout.addWidget(self.table)

    # ======================
    def start_update(self):
        if self.worker and self.worker.isRunning():
            return

        self.worker = Worker()
        self.worker.finished.connect(self.update_table)
        self.worker.start()

    # ======================
    def update_table(self, results):
        self.table.setRowCount(0)
        self.last_update_label.setText(f"Последнее обновление: {time.strftime('%H:%M:%S')}")

        for ip, data in results:
            host = next((h for h in HOSTS_CONFIG if h["ip"] == ip), {})
            desc = host.get("description", ip)

            if "error" in data:
                self.add_row([ip, desc, "Ошибка", data["error"], "", ""])
                continue

            for name, items in data.get("processes", {}).items():
                for proc in items:
                    self.add_process(ip, desc, name, proc)

            self.add_rdp_row(ip, desc)

    # ======================
    def add_process(self, ip, desc, name, proc):
        row = self.table.rowCount()
        self.table.insertRow(row)

        pid = proc.get("pid")
        uptime = proc.get("uptime", "-")

        self.table.setItem(row, 0, QTableWidgetItem(ip))
        self.table.setItem(row, 1, QTableWidgetItem(desc))
        self.table.setItem(row, 2, QTableWidgetItem(f"{name} [{pid}]"))
        self.table.setItem(row, 3, QTableWidgetItem(uptime))

        btn = QPushButton("Kill")
        btn.setFixedWidth(60)
        btn.clicked.connect(partial(self.kill_process, ip, pid))
        self.table.setCellWidget(row, 4, btn)

    # ======================
    def add_rdp_row(self, ip, desc):
        row = self.table.rowCount()
        self.table.insertRow(row)

        self.table.setItem(row, 0, QTableWidgetItem(ip))
        self.table.setItem(row, 1, QTableWidgetItem(desc))
        self.table.setItem(row, 2, QTableWidgetItem("— RDP —"))

        btn = QPushButton("Connect")
        btn.clicked.connect(partial(self.connect_rdp, ip))
        self.table.setCellWidget(row, 5, btn)

    # ======================
    def connect_rdp(self, ip):
        host = next((h for h in HOSTS_CONFIG if h["ip"] == ip), None)
        if not host:
            return

        user = host.get("rdp_user", "")
        password = host.get("rdp_pass", "")

        try:
            subprocess.run(
                ["cmdkey", f"/generic:TERMSRV/{ip}", f"/user:{user}", f"/pass:{password}"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            subprocess.Popen(["mstsc", f"/v:{ip}"])
        except Exception as e:
            print("RDP error:", e)

    # ======================
    def kill_process(self, ip, pid):
        host = next((h for h in HOSTS_CONFIG if h["ip"] == ip), None)
        if not host:
            return

        send_cmd(ip, host["port"], {
            "cmd": "kill_by_pid",
            "pid": pid,
            "token": TOKEN
        })

        self.start_update()

    # ======================
    def add_row(self, vals):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for i, v in enumerate(vals):
            self.table.setItem(row, i, QTableWidgetItem(str(v)))

    # ======================
    def load_config(self):
        global HOSTS_CONFIG
        path = "hosts.json"
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                HOSTS_CONFIG[:] = json.load(f)

    def closeEvent(self, e):
        if self.worker:
            self.worker.quit()
            self.worker.wait()
        e.accept()


def main():
    app = QApplication(sys.argv)
    w = MonitorWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()