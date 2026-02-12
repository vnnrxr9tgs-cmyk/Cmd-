import sys
import json
import os
import subprocess  # Используем subprocess вместо paramiko
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
            # Формируем базовую команду SSH
            # -o StrictHostKeyChecking=no отключает вопрос о доверии хосту (аналог AutoAddPolicy)
            # -o ConnectTimeout=5 ограничивает время подключения
            ssh_cmd = [
                "ssh",
                "-p", str(self.port),
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=5"
            ]

            # Если указан ключ, добавляем его в команду
            if self.key_path and os.path.exists(self.key_path):
                ssh_cmd.extend(["-i", self.key_path])

            # Добавляем пользователя и хост
            ssh_cmd.append(f"{self.user}@{self.host}")

            # Если есть пароль, пытаемся использовать sshpass (если установлен в системе)
            # Это нужно, т.к. обычный ssh не принимает пароль через аргументы
            use_sshpass = False
            if self.password and not self.key_path:
                # Проверяем, есть ли sshpass в системе
                if os.system("which sshpass > /dev/null 2>&1") == 0:
                    ssh_cmd = ["sshpass", "-p", self.password] + ssh_cmd
                    use_sshpass = True
                else:
                    # Если sshpass нет, ssh попытается спросить пароль в консоли, что в GUI не сработает.
                    # Лучше выбросить ошибку сразу.
                    self.error.emit(
                        "Password authentication requires 'sshpass' utility installed on the client machine. Use SSH keys instead.")
                    return

            # Команды для выполнения (объединяем в одну строку через ";")
            # Экранируем кавычки для оболочки
            # Добавлены MEM, полный CPU usage и упрощенная NETWORK (IP, RX, TX для всех интерфейсов)
            remote_cmd = (
                "echo 'HOSTNAME:'; hostname; "
                "echo '---'; echo 'UPTIME:'; uptime; "
                "echo '---'; echo 'CPU:'; sysctl -n hw.ncpu; echo 'CPU usage:'; ps -axo pcpu | awk '{s+=$1} END {print s \"%\"}'; "
                "echo '---'; echo 'MEM:'; sysctl -n hw.physmem; echo 'Active pages:'; vmstat -s | grep 'pages active'; "
                "echo '---'; echo 'PROCESSES:'; ps ax | wc -l; "
                "echo '---'; echo 'DISK:'; df -h /; "
                "echo '---'; echo 'NETWORK:'; "
                "for iface in $(ifconfig -l); do "
                "  ip=$(ifconfig $iface | grep 'inet ' | awk '{print $2}' | head -1); "
                "  if [ -n \"$ip\" ]; then "
                "    rx=$(netstat -i | grep $iface | awk '{print $5}'); "
                "    tx=$(netstat -i | grep $iface | awk '{print $8}'); "
                "    echo \"$iface: IP=$ip, RX=$rx bytes, TX=$tx bytes\"; "
                "  fi; "
                "done"
            )

            # Добавляем команду bash -c для выполнения составной команды
            ssh_cmd.extend(["bash", "-c", f"'{remote_cmd}'"])

            # Запускаем процесс
            # stderr=subprocess.PIPE позволит перехватить ошибки SSH
            process = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            stdout, stderr = process.communicate()

            if process.returncode != 0:
                # Если была ошибка подключения или выполнения
                err_msg = stderr.strip() if stderr.strip() else "Unknown SSH error"
                # Скрываем лишние предупреждения SSH
                if "Warning: Permanently added" in err_msg:
                    err_msg = "Connection established but remote command failed."
                self.error.emit(f"SSH Error (Code {process.returncode}): {err_msg}")
            else:
                # Успешное выполнение
                # Немного форматируем вывод для красоты, так как мы передали echo в команде
                self.result.emit(stdout.strip())

        except Exception as e:
            self.error.emit(f"System Exception: {str(e)}")

# ---------- MAIN WINDOW ---------- (без изменений)
class Monitor(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FreeBSD Monitor (Subprocess SSH)")
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
        self.browse_key_btn = QPushButton("Browse Key")

        self.start_btn.clicked.connect(self.start_monitoring)
        self.stop_btn.clicked.connect(self.stop_monitoring)
        self.update_btn.clicked.connect(self.update_metrics)
        self.test_btn.clicked.connect(self.test_connection)
        self.browse_key_btn.clicked.connect(self.browse_key)

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
        grid.addWidget(self.browse_key_btn, 3, 2)

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

        # Проверка порта
        try:
            port = int(self.port_edit.text().strip())
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
        self.update_metrics()

    def display_result(self, text):
        self.output.setText(text)
        self.status_bar.showMessage("Updated successfully")

    def display_error(self, err):
        self.output.append(f"\nERROR: {err}")
        self.status_bar.showMessage("Error occurred")

    def closeEvent(self, event):
        self.stop_monitoring()
        if self.worker and self.worker.isRunning():
            self.worker.wait()
        event.accept()

# ---------- RUN ----------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = Monitor()
    win.show()
    sys.exit(app.exec_())

# import sys
# import json
# import os
# import subprocess
# import tempfile
# from PyQt5.QtCore import QThread, pyqtSignal, QTimer
# from PyQt5.QtWidgets import (
#     QApplication, QWidget, QLabel, QLineEdit,
#     QPushButton, QTextEdit, QGridLayout, QVBoxLayout,
#     QGroupBox, QMessageBox, QStatusBar, QCheckBox, QFileDialog
# )
#
#
# # ---------- SSH WORKER THREAD ----------
# class SSHWorker(QThread):
#     result = pyqtSignal(str)
#     error = pyqtSignal(str)
#
#     def __init__(self, host, port, user, password, key_path=None):
#         super().__init__()
#         self.host = host
#         self.port = port
#         self.user = user
#         self.password = password
#         self.key_path = key_path
#
#     def run(self):
#         try:
#             commands = {
#                 "hostname": "hostname",
#                 "uptime": "uptime",
#                 "cpu": "sysctl -n hw.ncpu && ps -axo pcpu | awk '{s+=$1} END {print \"CPU usage:\", s \"%\"}'",
#                 "mem": "sysctl -n hw.physmem && vmstat -s | grep 'pages active'",
#                 "proc": "ps ax | wc -l",
#                 "disk": "df -h /"
#             }
#
#             output = []
#
#             for name, remote_cmd in commands.items():
#                 result = self.execute_ssh_command(remote_cmd)
#                 output.append(f"{name.upper()}:\n{result}")
#
#             self.result.emit("\n\n".join(output))
#
#         except Exception as e:
#             self.error.emit(str(e))
#
#     def execute_ssh_command(self, command):
#         """Выполняет SSH команду используя системный ssh клиент"""
#         try:
#             # Базовые аргументы ssh
#             ssh_cmd = [
#                 'ssh',
#                 '-o', 'ConnectTimeout=5',
#                 '-o', 'StrictHostKeyChecking=no',  # Не рекомендуется для продакшена!
#                 '-o', 'UserKnownHostsFile=/dev/null',
#                 '-p', str(self.port),
#                 f'{self.user}@{self.host}',
#                 command
#             ]
#
#             # Добавляем путь к ключу, если указан
#             if self.key_path:
#                 ssh_cmd.insert(1, '-i')
#                 ssh_cmd.insert(2, self.key_path)
#
#             # Используем sshpass для автоматического ввода пароля
#             if self.password and not self.key_path:
#                 # Проверяем наличие sshpass
#                 try:
#                     subprocess.run(['which', 'sshpass'], check=True, capture_output=True)
#                     ssh_cmd = ['sshpass', '-p', self.password] + ssh_cmd
#                 except subprocess.CalledProcessError:
#                     # Если sshpass не установлен, используем pexpect (если доступен)
#                     return self.ssh_with_password_pexpect(command)
#
#             # Выполняем команду
#             result = subprocess.run(
#                 ssh_cmd,
#                 capture_output=True,
#                 text=True,
#                 timeout=10
#             )
#
#             if result.returncode != 0:
#                 error_msg = result.stderr.strip()
#                 if "Permission denied" in error_msg:
#                     return "Error: Permission denied. Check credentials."
#                 elif "Connection timed out" in error_msg:
#                     return "Error: Connection timeout. Check host and port."
#                 else:
#                     return f"Error: {error_msg}"
#
#             return result.stdout.strip() or "No output"
#
#         except subprocess.TimeoutExpired:
#             return "Error: Command timeout"
#         except FileNotFoundError:
#             return "Error: SSH client not found. Please install OpenSSH client."
#         except Exception as e:
#             return f"Error: {str(e)}"
#
#     def ssh_with_password_pexpect(self, command):
#         """Альтернативный метод с использованием pexpect (если доступен)"""
#         try:
#             import pexpect
#
#             ssh_cmd = f'ssh -o StrictHostKeyChecking=no -p {self.port} {self.user}@{self.host} {command}'
#
#             child = pexpect.spawn(ssh_cmd, timeout=10)
#
#             # Ожидаем запрос пароля
#             i = child.expect(['password:', pexpect.EOF, pexpect.TIMEOUT], timeout=5)
#
#             if i == 0:  # Запрос пароля
#                 child.sendline(self.password)
#                 child.expect(pexpect.EOF, timeout=10)
#                 return child.before.decode('utf-8', errors='ignore').strip()
#             else:
#                 return child.before.decode('utf-8', errors='ignore').strip()
#
#         except ImportError:
#             return "Error: Neither sshpass nor pexpect is available. Install sshpass or pexpect."
#         except Exception as e:
#             return f"Error with pexpect: {str(e)}"
#
#
# # Вариант 2: Использование модуля paramiko с fallback (сохраняем для совместимости)
# try:
#     import paramiko
#
#     PARAMIKO_AVAILABLE = True
# except ImportError:
#     PARAMIKO_AVAILABLE = False
#     print("Paramiko not available, using system SSH client")
#
#
# # Альтернативный SSHWorker с поддержкой обоих методов
# class FlexibleSSHWorker(QThread):
#     result = pyqtSignal(str)
#     error = pyqtSignal(str)
#
#     def __init__(self, host, port, user, password, key_path=None):
#         super().__init__()
#         self.host = host
#         self.port = port
#         self.user = user
#         self.password = password
#         self.key_path = key_path
#
#     def run(self):
#         try:
#             if PARAMIKO_AVAILABLE:
#                 self.ssh_via_paramiko()
#             else:
#                 self.ssh_via_system()
#         except Exception as e:
#             self.error.emit(str(e))
#
#     def ssh_via_paramiko(self):
#         """Метод с использованием paramiko"""
#         try:
#             client = paramiko.SSHClient()
#             client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#
#             if self.key_path:
#                 client.connect(
#                     hostname=self.host,
#                     port=self.port,
#                     username=self.user,
#                     key_filename=self.key_path,
#                     timeout=5
#                 )
#             else:
#                 client.connect(
#                     hostname=self.host,
#                     port=self.port,
#                     username=self.user,
#                     password=self.password,
#                     timeout=5
#                 )
#
#             commands = {
#                 "hostname": "hostname",
#                 "uptime": "uptime",
#                 "cpu": "sysctl -n hw.ncpu && ps -axo pcpu | awk '{s+=$1} END {print \"CPU usage:\", s \"%\"}'",
#                 "mem": "sysctl -n hw.physmem && vmstat -s | grep 'pages active'",
#                 "proc": "ps ax | wc -l",
#                 "disk": "df -h /"
#             }
#
#             output = []
#             for name, cmd in commands.items():
#                 stdin, stdout, stderr = client.exec_command(cmd)
#                 result = stdout.read().decode().strip()
#                 error = stderr.read().decode().strip()
#                 if error:
#                     output.append(f"{name.upper()}:\nError: {error}")
#                 else:
#                     output.append(f"{name.upper()}:\n{result}")
#
#             client.close()
#             self.result.emit("\n\n".join(output))
#
#         except Exception as e:
#             raise Exception(f"Paramiko error: {str(e)}")
#
#     def ssh_via_system(self):
#         """Метод с использованием системного SSH"""
#         try:
#             commands = {
#                 "hostname": "hostname",
#                 "uptime": "uptime",
#                 "cpu": "sysctl -n hw.ncpu && ps -axo pcpu | awk '{s+=$1} END {print \"CPU usage:\", s \"%\"}'",
#                 "mem": "sysctl -n hw.physmem && vmstat -s | grep 'pages active'",
#                 "proc": "ps ax | wc -l",
#                 "disk": "df -h /"
#             }
#
#             output = []
#
#             # Создаем временный скрипт для команд
#             with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
#                 for name, cmd in commands.items():
#                     f.write(f'echo "=== {name} ===\n"\n')
#                     f.write(f'{cmd}\n')
#                     f.write(f'echo "\n"\n')
#                 temp_script = f.name
#
#             try:
#                 # Базовые аргументы ssh
#                 ssh_cmd = [
#                     'ssh',
#                     '-o', 'ConnectTimeout=5',
#                     '-o', 'StrictHostKeyChecking=no',
#                     '-o', 'UserKnownHostsFile=/dev/null',
#                     '-p', str(self.port),
#                     f'{self.user}@{self.host}',
#                     'bash -s'  # Читаем скрипт из stdin
#                 ]
#
#                 if self.key_path:
#                     ssh_cmd.insert(1, '-i')
#                     ssh_cmd.insert(2, self.key_path)
#
#                 if self.password and not self.key_path:
#                     try:
#                         subprocess.run(['which', 'sshpass'], check=True, capture_output=True)
#                         ssh_cmd = ['sshpass', '-p', self.password] + ssh_cmd
#                     except subprocess.CalledProcessError:
#                         pass
#
#                 # Выполняем команды
#                 with open(temp_script, 'r') as f:
#                     result = subprocess.run(
#                         ssh_cmd,
#                         stdin=f,
#                         capture_output=True,
#                         text=True,
#                         timeout=15
#                     )
#
#                 if result.returncode == 0:
#                     # Парсим результат
#                     sections = result.stdout.split('=== ')
#                     for section in sections:
#                         if section.strip():
#                             lines = section.strip().split('\n', 1)
#                             if len(lines) == 2:
#                                 name, content = lines
#                                 content = content.replace('===', '').strip()
#                                 output.append(f"{name}:\n{content}")
#
#                     self.result.emit("\n\n".join(output))
#                 else:
#                     self.error.emit(f"SSH error: {result.stderr}")
#
#             finally:
#                 # Удаляем временный файл
#                 os.unlink(temp_script)
#
#         except Exception as e:
#             self.error.emit(f"System SSH error: {str(e)}")
#
#
# # ---------- MAIN WINDOW ----------
# class Monitor(QWidget):
#     def __init__(self):
#         super().__init__()
#         self.setWindowTitle("FreeBSD Monitor (SSH Client)")
#         self.resize(800, 600)
#
#         self.timer = QTimer()
#         self.timer.setInterval(15000)
#         self.timer.timeout.connect(self.update_metrics)
#
#         self.worker = None
#         self.config_file = "monitor_config.json"
#         self.load_config()
#
#         self.init_ui()
#
#         # Проверяем доступность SSH клиента
#         self.check_ssh_availability()
#
#     def init_ui(self):
#         layout = QVBoxLayout()
#
#         # ---- CONNECTION PANEL ----
#         conn_box = QGroupBox("SSH Connection")
#         grid = QGridLayout()
#
#         self.ip_edit = QLineEdit(self.config.get("ip", ""))
#         self.port_edit = QLineEdit(str(self.config.get("port", 22)))
#         self.user_edit = QLineEdit(self.config.get("user", ""))
#         self.pass_edit = QLineEdit(self.config.get("password", ""))
#         self.pass_edit.setEchoMode(QLineEdit.Password)
#         self.key_checkbox = QCheckBox("Use SSH Key")
#         self.key_edit = QLineEdit(self.config.get("key_path", ""))
#         self.key_edit.setEnabled(False)
#         self.key_checkbox.toggled.connect(lambda: self.key_edit.setEnabled(self.key_checkbox.isChecked()))
#
#         self.start_btn = QPushButton("Start Monitoring")
#         self.stop_btn = QPushButton("Stop Monitoring")
#         self.update_btn = QPushButton("Update Now")
#         self.test_btn = QPushButton("Test Connection")
#         self.browse_key_btn = QPushButton("Browse Key")
#
#         self.start_btn.clicked.connect(self.start_monitoring)
#         self.stop_btn.clicked.connect(self.stop_monitoring)
#         self.update_btn.clicked.connect(self.update_metrics)
#         self.test_btn.clicked.connect(self.test_connection)
#         self.browse_key_btn.clicked.connect(self.browse_key)
#
#         grid.addWidget(QLabel("IP:"), 0, 0)
#         grid.addWidget(self.ip_edit, 0, 1)
#         grid.addWidget(QLabel("Port:"), 0, 2)
#         grid.addWidget(self.port_edit, 0, 3)
#         grid.addWidget(QLabel("User:"), 1, 0)
#         grid.addWidget(self.user_edit, 1, 1)
#         grid.addWidget(QLabel("Password:"), 2, 0)
#         grid.addWidget(self.pass_edit, 2, 1)
#         grid.addWidget(self.key_checkbox, 3, 0)
#         grid.addWidget(self.key_edit, 3, 1)
#         grid.addWidget(self.browse_key_btn, 3, 2)
#
#         grid.addWidget(self.start_btn, 0, 4)
#         grid.addWidget(self.stop_btn, 1, 4)
#         grid.addWidget(self.update_btn, 2, 4)
#         grid.addWidget(self.test_btn, 3, 4)
#
#         conn_box.setLayout(grid)
#
#         # ---- OUTPUT ----
#         self.output = QTextEdit()
#         self.output.setReadOnly(True)
#
#         # ---- STATUS BAR ----
#         self.status_bar = QStatusBar()
#         self.status_bar.showMessage("Ready")
#
#         layout.addWidget(conn_box)
#         layout.addWidget(self.output)
#         layout.addWidget(self.status_bar)
#         self.setLayout(layout)
#
#     def check_ssh_availability(self):
#         """Проверяет доступность SSH клиента"""
#         try:
#             subprocess.run(['ssh', '-V'], capture_output=True, check=True)
#             self.status_bar.showMessage("SSH client available")
#         except (subprocess.CalledProcessError, FileNotFoundError):
#             msg = "WARNING: SSH client not found. Please install OpenSSH client."
#             self.output.setText(msg)
#             self.status_bar.showMessage(msg)
#
#     def browse_key(self):
#         file, _ = QFileDialog.getOpenFileName(self, "Select SSH Key", "", "All Files (*)")
#         if file:
#             self.key_edit.setText(file)
#
#     def load_config(self):
#         if os.path.exists(self.config_file):
#             with open(self.config_file, "r") as f:
#                 self.config = json.load(f)
#         else:
#             self.config = {}
#
#     def save_config(self):
#         self.config = {
#             "ip": self.ip_edit.text().strip(),
#             "port": int(self.port_edit.text().strip() or 22),
#             "user": self.user_edit.text().strip(),
#             "password": self.pass_edit.text(),
#             "key_path": self.key_edit.text().strip() if self.key_checkbox.isChecked() else ""
#         }
#         with open(self.config_file, "w") as f:
#             json.dump(self.config, f)
#
#     def validate_inputs(self):
#         ip = self.ip_edit.text().strip()
#         port = self.port_edit.text().strip()
#         user = self.user_edit.text().strip()
#         password = self.pass_edit.text()
#         key_path = self.key_edit.text().strip() if self.key_checkbox.isChecked() else None
#
#         if not ip:
#             QMessageBox.warning(self, "Error", "IP address is required")
#             return False
#         if not user:
#             QMessageBox.warning(self, "Error", "Username is required")
#             return False
#         if not password and not key_path:
#             QMessageBox.warning(self, "Error", "Password or SSH key is required")
#             return False
#         try:
#             port = int(port)
#             if not (1 <= port <= 65535):
#                 raise ValueError
#         except ValueError:
#             QMessageBox.warning(self, "Error", "Invalid port")
#             return False
#         return True
#
#     def start_monitoring(self):
#         if not self.validate_inputs():
#             return
#         self.save_config()
#         if not self.timer.isActive():
#             self.update_metrics()
#             self.timer.start()
#             self.status_bar.showMessage("Monitoring started")
#
#     def stop_monitoring(self):
#         self.timer.stop()
#         self.status_bar.showMessage("Monitoring stopped")
#
#     def update_metrics(self):
#         if not self.validate_inputs():
#             return
#         if self.worker and self.worker.isRunning():
#             self.status_bar.showMessage("Previous update in progress, skipping...")
#             return
#
#         ip = self.ip_edit.text().strip()
#         port = int(self.port_edit.text().strip())
#         user = self.user_edit.text().strip()
#         password = self.pass_edit.text()
#         key_path = self.key_edit.text().strip() if self.key_checkbox.isChecked() else None
#
#         # Используем FlexibleSSHWorker для поддержки обоих методов
#         self.worker = FlexibleSSHWorker(ip, port, user, password, key_path)
#         self.worker.result.connect(self.display_result)
#         self.worker.error.connect(self.display_error)
#         self.worker.start()
#         self.status_bar.showMessage("Updating...")
#
#     def test_connection(self):
#         if not self.validate_inputs():
#             return
#         self.update_metrics()
#
#     def display_result(self, text):
#         self.output.setText(text)
#         self.status_bar.showMessage("Updated successfully")
#
#     def display_error(self, err):
#         self.output.append(f"\nERROR: {err}")
#         self.status_bar.showMessage("Error occurred")
#
#     def closeEvent(self, event):
#         self.stop_monitoring()
#         if self.worker and self.worker.isRunning():
#             self.worker.wait()
#         event.accept()
#
#
# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     win = Monitor()
#     win.show()
#     sys.exit(app.exec_())
# # import sys
# # import json
# # import os
# # import subprocess  # Замена pexpect/paramiko
# # from PyQt5.QtCore import QThread, pyqtSignal, QTimer
# # from PyQt5.QtWidgets import (
# #     QApplication, QWidget, QLabel, QLineEdit,
# #     QPushButton, QTextEdit, QGridLayout, QVBoxLayout,
# #     QGroupBox, QMessageBox, QStatusBar, QCheckBox, QFileDialog
# # )
# #
# #
# # # ---------- SSH WORKER THREAD ----------
# # class SSHWorker(QThread):
# #     result = pyqtSignal(str)
# #     error = pyqtSignal(str)
# #
# #     def __init__(self, host, port, user, password, key_path=None):
# #         super().__init__()
# #         self.host = host
# #         self.port = port
# #         self.user = user
# #         self.password = password
# #         self.key_path = key_path
# #
# #     def run(self):
# #         try:
# #             # Команды адаптированы для FreeBSD (sysctl для CPU/MEM, df для диска)
# #             commands = {
# #                 "hostname": "hostname",
# #                 "uptime": "uptime",
# #                 "cpu": "sysctl -n hw.ncpu && ps -axo pcpu | awk '{s+=$1} END {print \"CPU usage:\", s \"%\"}'",
# #                 # Примерный CPU usage
# #                 "mem": "sysctl -n hw.physmem && vmstat -s | grep 'pages active'",  # Память
# #                 "proc": "ps ax | wc -l",
# #                 "disk": "df -h /"  # Дисковое пространство
# #             }
# #
# #             output = []
# #             for name, cmd in commands.items():
# #                 # Формируем команду SSH
# #                 if self.key_path:
# #                     # Для ключей: ssh -p port -i key_path user@host "command"
# #                     ssh_cmd = ['ssh', '-p', str(self.port), '-i', self.key_path, '-o', 'StrictHostKeyChecking=no',
# #                                f'{self.user}@{self.host}', cmd]
# #                 else:
# #                     # Для паролей: sshpass -p password ssh -p port user@host "command"
# #                     # Требует sshpass; если нет, используйте ключи
# #                     ssh_cmd = ['sshpass', '-p', self.password, 'ssh', '-p', str(self.port), '-o',
# #                                'StrictHostKeyChecking=no', f'{self.user}@{self.host}', cmd]
# #
# #                 # Запускаем команду
# #                 result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=10)
# #
# #                 if result.returncode == 0:
# #                     output.append(f"{name.upper()}:\n{result.stdout.strip()}")
# #                 else:
# #                     output.append(f"{name.upper()}:\nError: {result.stderr.strip()}")
# #
# #             self.result.emit("\n\n".join(output))  # Разделители для читаемости
# #
# #         except subprocess.TimeoutExpired:
# #             self.error.emit("SSH command timed out")
# #         except FileNotFoundError as e:
# #             if 'sshpass' in str(e):
# #                 self.error.emit("sshpass not found. Install it (pkg install sshpass) or use SSH keys only.")
# #             else:
# #                 self.error.emit(f"SSH command not found: {e}")
# #         except Exception as e:
# #             self.error.emit(str(e))
# #
# #
# # # ---------- MAIN WINDOW ---------- (без изменений)
# # class Monitor(QWidget):
# #     def __init__(self):
# #         super().__init__()
# #         self.setWindowTitle("FreeBSD Monitor")
# #         self.resize(800, 600)
# #
# #         self.timer = QTimer()
# #         self.timer.setInterval(15000)
# #         self.timer.timeout.connect(self.update_metrics)
# #
# #         self.worker = None
# #         self.config_file = "monitor_config.json"
# #         self.load_config()
# #
# #         self.init_ui()
# #
# #     def init_ui(self):
# #         layout = QVBoxLayout()
# #
# #         # ---- CONNECTION PANEL ----
# #         conn_box = QGroupBox("SSH Connection")
# #         grid = QGridLayout()
# #
# #         self.ip_edit = QLineEdit(self.config.get("ip", ""))
# #         self.port_edit = QLineEdit(str(self.config.get("port", 22)))
# #         self.user_edit = QLineEdit(self.config.get("user", ""))
# #         self.pass_edit = QLineEdit(self.config.get("password", ""))
# #         self.pass_edit.setEchoMode(QLineEdit.Password)
# #         self.key_checkbox = QCheckBox("Use SSH Key")
# #         self.key_edit = QLineEdit(self.config.get("key_path", ""))
# #         self.key_edit.setEnabled(False)
# #         self.key_checkbox.toggled.connect(lambda: self.key_edit.setEnabled(self.key_checkbox.isChecked()))
# #
# #         self.start_btn = QPushButton("Start Monitoring")
# #         self.stop_btn = QPushButton("Stop Monitoring")
# #         self.update_btn = QPushButton("Update Now")
# #         self.test_btn = QPushButton("Test Connection")
# #         self.browse_key_btn = QPushButton("Browse Key")  # Создаём кнопку как переменную
# #
# #         self.start_btn.clicked.connect(self.start_monitoring)
# #         self.stop_btn.clicked.connect(self.stop_monitoring)
# #         self.update_btn.clicked.connect(self.update_metrics)
# #         self.test_btn.clicked.connect(self.test_connection)
# #         self.browse_key_btn.clicked.connect(self.browse_key)  # Подключаем сигнал
# #
# #         grid.addWidget(QLabel("IP:"), 0, 0)
# #         grid.addWidget(self.ip_edit, 0, 1)
# #         grid.addWidget(QLabel("Port:"), 0, 2)
# #         grid.addWidget(self.port_edit, 0, 3)
# #         grid.addWidget(QLabel("User:"), 1, 0)
# #         grid.addWidget(self.user_edit, 1, 1)
# #         grid.addWidget(QLabel("Password:"), 2, 0)
# #         grid.addWidget(self.pass_edit, 2, 1)
# #         grid.addWidget(self.key_checkbox, 3, 0)
# #         grid.addWidget(self.key_edit, 3, 1)
# #         grid.addWidget(self.browse_key_btn, 3, 2)  # Добавляем кнопку в grid
# #
# #         grid.addWidget(self.start_btn, 0, 4)
# #         grid.addWidget(self.stop_btn, 1, 4)
# #         grid.addWidget(self.update_btn, 2, 4)
# #         grid.addWidget(self.test_btn, 3, 4)
# #
# #         conn_box.setLayout(grid)
# #
# #         # ---- OUTPUT ----
# #         self.output = QTextEdit()
# #         self.output.setReadOnly(True)
# #
# #         # ---- STATUS BAR ----
# #         self.status_bar = QStatusBar()
# #         self.status_bar.showMessage("Ready")
# #
# #         layout.addWidget(conn_box)
# #         layout.addWidget(self.output)
# #         layout.addWidget(self.status_bar)
# #         self.setLayout(layout)
# #
# #     def browse_key(self):
# #         file, _ = QFileDialog.getOpenFileName(self, "Select SSH Key", "", "All Files (*)")
# #         if file:
# #             self.key_edit.setText(file)
# #
# #     def load_config(self):
# #         if os.path.exists(self.config_file):
# #             with open(self.config_file, "r") as f:
# #                 self.config = json.load(f)
# #         else:
# #             self.config = {}
# #
# #     def save_config(self):
# #         self.config = {
# #             "ip": self.ip_edit.text().strip(),
# #             "port": int(self.port_edit.text().strip() or 22),
# #             "user": self.user_edit.text().strip(),
# #             "password": self.pass_edit.text(),
# #             "key_path": self.key_edit.text().strip() if self.key_checkbox.isChecked() else ""
# #         }
# #         with open(self.config_file, "w") as f:
# #             json.dump(self.config, f)
# #
# #     def validate_inputs(self):
# #         ip = self.ip_edit.text().strip()
# #         port = self.port_edit.text().strip()
# #         user = self.user_edit.text().strip()
# #         password = self.pass_edit.text()
# #         key_path = self.key_edit.text().strip() if self.key_checkbox.isChecked() else None
# #
# #         if not ip:
# #             QMessageBox.warning(self, "Error", "IP address is required")
# #             return False
# #         if not user:
# #             QMessageBox.warning(self, "Error", "Username is required")
# #             return False
# #         if not password and not key_path:
# #             QMessageBox.warning(self, "Error", "Password or SSH key is required")
# #             return False
# #         try:
# #             port = int(port)
# #             if not (1 <= port <= 65535):
# #                 raise ValueError
# #         except ValueError:
# #             QMessageBox.warning(self, "Error", "Invalid port")
# #             return False
# #         return True
# #
# #     # ---------- LOGIC ----------
# #     def start_monitoring(self):
# #         if not self.validate_inputs():
# #             return
# #         self.save_config()
# #         if not self.timer.isActive():
# #             self.update_metrics()
# #             self.timer.start()
# #             self.status_bar.showMessage("Monitoring started")
# #
# #     def stop_monitoring(self):
# #         self.timer.stop()
# #         self.status_bar.showMessage("Monitoring stopped")
# #
# #     def update_metrics(self):
# #         if not self.validate_inputs():
# #             return
# #         if self.worker and self.worker.isRunning():
# #             self.status_bar.showMessage("Previous update in progress, skipping...")
# #             return
# #
# #         ip = self.ip_edit.text().strip()
# #         port = int(self.port_edit.text().strip())
# #         user = self.user_edit.text().strip()
# #         password = self.pass_edit.text()
# #         key_path = self.key_edit.text().strip() if self.key_checkbox.isChecked() else None
# #
# #         self.worker = SSHWorker(ip, port, user, password, key_path)
# #         self.worker.result.connect(self.display_result)
# #         self.worker.error.connect(self.display_error)
# #         self.worker.start()
# #         self.status_bar.showMessage("Updating...")
# #
# #     def test_connection(self):
# #         if not self.validate_inputs():
# #             return
# #         self.update_metrics()  # Просто запускаем обновление как тест
# #
# #     def display_result(self, text):
# #         self.output.setText(text)
# #         self.status_bar.showMessage("Updated successfully")
# #
# #     def display_error(self, err):
# #         self.output.append(f"\nERROR: {err}")
# #         self.status_bar.showMessage("Error occurred")
# #
# #     def closeEvent(self, event):
# #         self.stop_monitoring()
# #         if self.worker and self.worker.isRunning():
# #             self.worker.wait()  # Ждём завершения
# #         event.accept()
# #
# #
# # # ---------- RUN ----------
# # if __name__ == "__main__":
# #     app = QApplication(sys.argv)
# #     win = Monitor()
# #     win.show()
# #     sys.exit(app.exec_())