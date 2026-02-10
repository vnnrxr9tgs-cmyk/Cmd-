import sys
import json
import os
import paramiko
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QLineEdit,
    QPushButton, QTextEdit, QGridLayout, QVBoxLayout,
    QGroupBox, QMessageBox, QStatusBar, QCheckBox, QFileDialog
)

# ---------- SSH WORKER THREAD ----------
class SSHWorker(QThread):
    result = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, host, port, user, password, key_path=None):
        super().__init__()
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.key_path = key_path

    def run(self):
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())  # Для тестов; в проде используй RejectPolicy и known_hosts
            if self.key_path:
                client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.user,
                    key_filename=self.key_path,
                    timeout=5
                )
            else:
                client.connect(
                    hostname=self.host,
                    port=self.port,
                    username=self.user,
                    password=self.password,
                    timeout=5
                )

            # Команды адаптированы для FreeBSD (sysctl для CPU/MEM, df для диска)
            commands = {
                "hostname": "hostname",
                "uptime": "uptime",
                "cpu": "sysctl -n hw.ncpu && ps -axo pcpu | awk '{s+=$1} END {print \"CPU usage:\", s \"%\"}'",  # Примерный CPU usage
                "mem": "sysctl -n hw.physmem && vmstat -s | grep 'pages active'",  # Память
                "proc": "ps ax | wc -l",
                "disk": "df -h /"  # Дисковое пространство
            }

            output = []
            for name, cmd in commands.items():
                stdin, stdout, stderr = client.exec_command(cmd)
                result = stdout.read().decode().strip()
                error = stderr.read().decode().strip()
                if error:
                    output.append(f"{name.upper()}:\nError: {error}")
                else:
                    output.append(f"{name.upper()}:\n{result}")

            client.close()
            self.result.emit("\n\n".join(output))  # Разделители для читаемости

        except Exception as e:
            self.error.emit(str(e))


# ---------- MAIN WINDOW ----------
class Monitor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FreeBSD Monitor")
        self.resize(800, 600)

        self.timer = QTimer()
        self.timer.setInterval(15000)
        self.timer.timeout.connect(self.update_metrics)

        self.worker = None
        self.config_file = "monitor_config.json"
        self.load_config()

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # ---- CONNECTION PANEL ----
        conn_box = QGroupBox("SSH Connection")
        grid = QGridLayout()

        self.ip_edit = QLineEdit(self.config.get("ip", ""))
        self.port_edit = QLineEdit(str(self.config.get("port", 22)))
        self.user_edit = QLineEdit(self.config.get("user", ""))
        self.pass_edit = QLineEdit(self.config.get("password", ""))
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.key_checkbox = QCheckBox("Use SSH Key")
        self.key_edit = QLineEdit(self.config.get("key_path", ""))
        self.key_edit.setEnabled(False)
        self.key_checkbox.toggled.connect(lambda: self.key_edit.setEnabled(self.key_checkbox.isChecked()))

        self.start_btn = QPushButton("Start Monitoring")
        self.stop_btn = QPushButton("Stop Monitoring")
        self.update_btn = QPushButton("Update Now")
        self.test_btn = QPushButton("Test Connection")
        self.browse_key_btn = QPushButton("Browse Key")  # Создаём кнопку как переменную

        self.start_btn.clicked.connect(self.start_monitoring)
        self.stop_btn.clicked.connect(self.stop_monitoring)
        self.update_btn.clicked.connect(self.update_metrics)
        self.test_btn.clicked.connect(self.test_connection)
        self.browse_key_btn.clicked.connect(self.browse_key)  # Подключаем сигнал

        grid.addWidget(QLabel("IP:"), 0, 0)
        grid.addWidget(self.ip_edit, 0, 1)
        grid.addWidget(QLabel("Port:"), 0, 2)
        grid.addWidget(self.port_edit, 0, 3)
        grid.addWidget(QLabel("User:"), 1, 0)
        grid.addWidget(self.user_edit, 1, 1)
        grid.addWidget(QLabel("Password:"), 2, 0)
        grid.addWidget(self.pass_edit, 2, 1)
        grid.addWidget(self.key_checkbox, 3, 0)
        grid.addWidget(self.key_edit, 3, 1)
        grid.addWidget(self.browse_key_btn, 3, 2)  # Добавляем кнопку в grid

        grid.addWidget(self.start_btn, 0, 4)
        grid.addWidget(self.stop_btn, 1, 4)
        grid.addWidget(self.update_btn, 2, 4)
        grid.addWidget(self.test_btn, 3, 4)

        conn_box.setLayout(grid)

        # ---- OUTPUT ----
        self.output = QTextEdit()
        self.output.setReadOnly(True)

        # ---- STATUS BAR ----
        self.status_bar = QStatusBar()
        self.status_bar.showMessage("Ready")

        layout.addWidget(conn_box)
        layout.addWidget(self.output)
        layout.addWidget(self.status_bar)
        self.setLayout(layout)

    def browse_key(self):
        file, _ = QFileDialog.getOpenFileName(self, "Select SSH Key", "", "All Files (*)")
        if file:
            self.key_edit.setText(file)

    def load_config(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, "r") as f:
                self.config = json.load(f)
        else:
            self.config = {}

    def save_config(self):
        self.config = {
            "ip": self.ip_edit.text().strip(),
            "port": int(self.port_edit.text().strip() or 22),
            "user": self.user_edit.text().strip(),
            "password": self.pass_edit.text(),
            "key_path": self.key_edit.text().strip() if self.key_checkbox.isChecked() else ""
        }
        with open(self.config_file, "w") as f:
            json.dump(self.config, f)

    def validate_inputs(self):
        ip = self.ip_edit.text().strip()
        port = self.port_edit.text().strip()
        user = self.user_edit.text().strip()
        password = self.pass_edit.text()
        key_path = self.key_edit.text().strip() if self.key_checkbox.isChecked() else None

        if not ip:
            QMessageBox.warning(self, "Error", "IP address is required")
            return False
        if not user:
            QMessageBox.warning(self, "Error", "Username is required")
            return False
        if not password and not key_path:
            QMessageBox.warning(self, "Error", "Password or SSH key is required")
            return False
        try:
            port = int(port)
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid port")
            return False
        return True

    # ---------- LOGIC ----------
    def start_monitoring(self):
        if not self.validate_inputs():
            return
        self.save_config()
        if not self.timer.isActive():
            self.update_metrics()
            self.timer.start()
            self.status_bar.showMessage("Monitoring started")

    def stop_monitoring(self):
        self.timer.stop()
        self.status_bar.showMessage("Monitoring stopped")

    def update_metrics(self):
        if not self.validate_inputs():
            return
        if self.worker and self.worker.isRunning():
            self.status_bar.showMessage("Previous update in progress, skipping...")
            return

        ip = self.ip_edit.text().strip()
        port = int(self.port_edit.text().strip())
        user = self.user_edit.text().strip()
        password = self.pass_edit.text()
        key_path = self.key_edit.text().strip() if self.key_checkbox.isChecked() else None

        self.worker = SSHWorker(ip, port, user, password, key_path)
        self.worker.result.connect(self.display_result)
        self.worker.error.connect(self.display_error)
        self.worker.start()
        self.status_bar.showMessage("Updating...")

    def test_connection(self):
        if not self.validate_inputs():
            return
        self.update_metrics()  # Просто запускаем обновление как тест

    def display_result(self, text):
        self.output.setText(text)
        self.status_bar.showMessage("Updated successfully")

    def display_error(self, err):
        self.output.append(f"\nERROR: {err}")
        self.status_bar.showMessage("Error occurred")

    def closeEvent(self, event):
        self.stop_monitoring()
        if self.worker and self.worker.isRunning():
            self.worker.wait()  # Ждём завершения
        event.accept()


# ---------- RUN ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Monitor()
    win.show()
    sys.exit(app.exec_())