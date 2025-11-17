import sys
import json
import socket
import base64
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLineEdit, QTextEdit, QCheckBox, QRadioButton, QLabel, QMessageBox,
    QGroupBox, QGridLayout, QProgressBar, QSplitter, QComboBox
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject, QThread


class WorkerSignals(QObject):
    finished = pyqtSignal()
    error = pyqtSignal(tuple)
    result = pyqtSignal(tuple)
    progress = pyqtSignal(int)


class CommandWorker(QThread):
    def __init__(self, ip, command, mode, encoding):
        super().__init__()
        self.ip = ip
        self.command = command
        self.mode = mode
        self.encoding = encoding
        self.signals = WorkerSignals()

    def run(self):
        try:
            result = self.send_command(self.ip, self.command, self.mode, self.encoding)
            self.signals.result.emit((self.ip, result))
        except Exception as e:
            self.signals.error.emit((self.ip, str(e)))

    def send_command(self, ip, command, mode, encoding):
        """Отправка команды на агент"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((ip, 5050))

            payload = json.dumps({
                "command": command,
                "mode": mode
            }, ensure_ascii=False)

            sock.sendall(payload.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)

            data = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                data += chunk
                if len(data) > 65535:
                    break

            sock.close()

            if not data:
                raise ValueError("Empty response")

            response = json.loads(data.decode("utf-8"))

            # Декодируем stdout/stderr с выбранной кодировкой
            stdout = base64.b64decode(response["stdout"]).decode(encoding, "ignore")
            stderr = base64.b64decode(response["stderr"]).decode(encoding, "ignore")

            return {
                "stdout": stdout,
                "stderr": stderr,
                "returncode": response["returncode"]
            }

        except socket.timeout:
            return {
                "stdout": "",
                "stderr": "Connection timeout (10s)",
                "returncode": 1
            }
        except ConnectionRefusedError:
            return {
                "stdout": "",
                "stderr": "Connection refused - agent not running",
                "returncode": 1
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": f"Connection error: {str(e)}",
                "returncode": 1
            }


class StatusChecker(QThread):
    def __init__(self, ip):
        super().__init__()
        self.ip = ip

    def run(self):
        online = self.check_online(self.ip)
        return self.ip, online

    def check_online(self, ip):
        """Проверка доступности агента"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((ip, 5050))
            sock.close()
            return True
        except:
            return False


class Controller(QWidget):
    def __init__(self):
        super().__init__()
        self.workers = []
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Remote Command Center v2.0")
        self.resize(1000, 700)

        main_layout = QVBoxLayout()

        # Панель управления
        control_layout = self.create_control_panel()
        main_layout.addLayout(control_layout)

        # Сплиттер для основного контента
        splitter = QSplitter(Qt.Horizontal)

        # Левая панель - компьютеры
        left_panel = self.create_computers_panel()
        splitter.addWidget(left_panel)

        # Правая панель - вывод
        right_panel = self.create_output_panel()
        splitter.addWidget(right_panel)

        splitter.setSizes([300, 700])
        main_layout.addWidget(splitter)

        # Прогресс бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        main_layout.addWidget(self.progress_bar)

        self.setLayout(main_layout)

        # Запускаем проверку статусов
        QTimer.singleShot(1000, self.update_statuses)

    def create_control_panel(self):
        layout = QVBoxLayout()  # Основной вертикальный layout

        # Первая строка: Команды
        commands_layout = QHBoxLayout()
        commands_layout.addWidget(QLabel("Команды:"))
        self.command_combo = QComboBox()
        self.command_combo.addItems([
            "Выберите команду...",
            "ipconfig",
            "dir",
            "whoami",
            "netstat",
            "tasklist",
            "systeminfo",
            "ping 8.8.8.8",
            "tracert google.com",
            "net user",
            "hostname",
            "ver"
        ])
        self.command_combo.currentTextChanged.connect(self.on_command_selected)
        commands_layout.addWidget(self.command_combo)
        layout.addLayout(commands_layout)

        # Вторая строка: Поле ввода команды (ниже)
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Команда:"))
        self.input = QLineEdit()
        self.input.setPlaceholderText("Введите команду...")
        self.input.returnPressed.connect(self.on_send)
        input_layout.addWidget(self.input)
        layout.addLayout(input_layout)

        # Третья строка: Кодировка и режим
        options_layout = QHBoxLayout()
        options_layout.addWidget(QLabel("Кодировка:"))
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(["cp1251", "cp866", "utf-8"])
        self.encoding_combo.setCurrentText("cp1251")
        options_layout.addWidget(self.encoding_combo)

        options_layout.addWidget(QLabel("Режим:"))
        self.rb_cmd = QRadioButton("CMD")
        self.rb_cmd.setChecked(True)
        self.rb_ps = QRadioButton("PowerShell")
        self.rb_auto = QRadioButton("Auto")
        options_layout.addWidget(self.rb_cmd)
        options_layout.addWidget(self.rb_ps)
        options_layout.addWidget(self.rb_auto)
        layout.addLayout(options_layout)

        # Четвёртая строка: Кнопки
        buttons_layout = QHBoxLayout()
        send_btn = QPushButton("Выполнить")
        send_btn.clicked.connect(self.on_send)
        buttons_layout.addWidget(send_btn)

        refresh_btn = QPushButton("Обновить статусы")
        refresh_btn.clicked.connect(self.update_statuses)
        buttons_layout.addWidget(refresh_btn)

        clear_btn = QPushButton("Очистить")
        clear_btn.clicked.connect(self.clear_logs)
        buttons_layout.addWidget(clear_btn)
        layout.addLayout(buttons_layout)

        return layout

    def create_computers_panel(self):
        panel = QGroupBox("Клиентские компьютеры")
        layout = QVBoxLayout()

        # Предустановленные компьютеры
        self.pc_data = [
            {"ip": "192.168.0.105", "name": "PC-01"},
            {"ip": "192.168.1.15", "name": "PC-02"},
            {"ip": "192.168.1.20", "name": "PC-03"},
            {"ip": "127.0.0.1", "name": "localhost"},
        ]

        self.checkboxes = []
        self.status_labels = []
        self.execution_labels = []  # Новый список для статусов выполнения

        grid = QGridLayout()
        grid.addWidget(QLabel("IP"), 0, 0)
        grid.addWidget(QLabel("Имя"), 0, 1)
        grid.addWidget(QLabel("Статус"), 0, 2)
        grid.addWidget(QLabel("Выполнение"), 0, 3)  # Новый столбец

        for i, pc in enumerate(self.pc_data, 1):
            cb = QCheckBox()
            cb.setChecked(True)
            self.checkboxes.append(cb)

            ip_label = QLabel(pc["ip"])
            name_label = QLabel(pc["name"])
            status_label = QLabel("🔴")
            self.status_labels.append(status_label)
            execution_label = QLabel("")  # Изначально пустой
            self.execution_labels.append(execution_label)

            grid.addWidget(cb, i, 0)
            grid.addWidget(ip_label, i, 1)
            grid.addWidget(name_label, i, 2)
            grid.addWidget(status_label, i, 3)
            grid.addWidget(execution_label, i, 4)  # Добавляем в новый столбец

        layout.addLayout(grid)

        # Кнопки выбора
        select_buttons = QHBoxLayout()
        select_all_btn = QPushButton("Выбрать все")
        select_all_btn.clicked.connect(self.select_all)
        select_none_btn = QPushButton("Снять все")
        select_none_btn.clicked.connect(self.select_none)

        select_buttons.addWidget(select_all_btn)
        select_buttons.addWidget(select_none_btn)
        layout.addLayout(select_buttons)

        panel.setLayout(layout)
        return panel

    def create_output_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # Вкладки для вывода
        self.output_tabs = QTextEdit()
        self.output_tabs.setReadOnly(True)
        self.output_tabs.setPlaceholderText("Здесь будут отображаться результаты выполнения команд...")

        layout.addWidget(QLabel("Результаты выполнения:"))
        layout.addWidget(self.output_tabs)

        return panel

    def on_command_selected(self, text):
        if text != "Выберите команду...":
            self.input.setText(text)

    def select_all(self):
        for cb in self.checkboxes:
            cb.setChecked(True)

    def select_none(self):
        for cb in self.checkboxes:
            cb.setChecked(False)

    def clear_logs(self):
        self.output_tabs.clear()
        # Очистить статусы выполнения
        for label in self.execution_labels:
            label.setText("")

    def get_selected_ips(self):
        """Получить выбранные IP адреса"""
        return [
            self.pc_data[i]["ip"]
            for i, cb in enumerate(self.checkboxes)
            if cb.isChecked()
        ]

    def get_execution_mode(self):
        """Получить режим выполнения"""
        if self.rb_ps.isChecked():
            return "powershell"
        elif self.rb_cmd.isChecked():
            return "cmd"
        else:
            return "auto"

    def on_send(self):
        command = self.input.text().strip()
        if not command:
            QMessageBox.warning(self, "Ошибка", "Введите команду!")
            return

        ips = self.get_selected_ips()
        mode = self.get_execution_mode()
        encoding = self.encoding_combo.currentText()

        if not ips:
            QMessageBox.warning(self, "Ошибка", "Выберите хотя бы один компьютер!")
            return

        self.execute_commands(ips, command, mode, encoding)

    def execute_commands(self, ips, command, mode, encoding):
        """Выполнение команд на выбранных компьютерах"""
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, len(ips))
        self.progress_bar.setValue(0)

        self.output_tabs.append(f"\n🔧 Выполнение команды: {command}")
        self.output_tabs.append(f"📡 Целевые компьютеры: {', '.join(ips)}")
        self.output_tabs.append("=" * 50)

        # Устанавливаем индикатор выполнения для выбранных IP
        for ip in ips:
            idx = next(i for i, pc in enumerate(self.pc_data) if pc["ip"] == ip)
            self.execution_labels[idx].setText("⏳")  # Индикатор загрузки

        completed_count = 0
        for ip in ips:
            worker = CommandWorker(ip, command, mode, encoding)
            worker.signals.result.connect(self.on_command_result)
            worker.signals.error.connect(self.on_command_error)
            worker.start()
            self.workers.append(worker)

        # Прогресс бар будет обновляться в обработчиках сигналов

    def on_command_result(self, result_data):
        ip, result = result_data

        # Найти индекс IP
        idx = next(i for i, pc in enumerate(self.pc_data) if pc["ip"] == ip)

        # Обновить статус выполнения
        if result["returncode"] == 0:
            self.execution_labels[idx].setText("OK")
        else:
            self.execution_labels[idx].setText("FAIL")

        output_text = f"\n🎯 [{ip}] Результат выполнения:\n"

        if result["stdout"]:
            output_text += f"✅ Вывод:\n{result['stdout']}\n"

        if result["stderr"]:
            output_text += f"❌ Ошибки:\n{result['stderr']}\n"

        output_text += f"🔢 Код возврата: {result['returncode']}\n"
        output_text += "-" * 30

        self.output_tabs.append(output_text)

        # Прокрутка к низу
        cursor = self.output_tabs.textCursor()
        cursor.movePosition(cursor.End)
        self.output_tabs.setTextCursor(cursor)

        # Обновить прогресс бар
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        if self.progress_bar.value() == self.progress_bar.maximum():
            QTimer.singleShot(1000, self.hide_progress_bar)

    def on_command_error(self, error_data):
        ip, error = error_data

        # Найти индекс IP
        idx = next(i for i, pc in enumerate(self.pc_data) if pc["ip"] == ip)

        # Обновить статус выполнения
        self.execution_labels[idx].setText("FAIL")

        self.output_tabs.append(f"\n💥 [{ip}] Ошибка: {error}")

        # Обновить прогресс бар
        self.progress_bar.setValue(self.progress_bar.value() + 1)
        if self.progress_bar.value() == self.progress_bar.maximum():
            QTimer.singleShot(1000, self.hide_progress_bar)

    def hide_progress_bar(self):
        """Скрыть прогресс бар после завершения"""
        self.progress_bar.setVisible(False)

    def update_statuses(self):
        """Обновление статусов компьютеров"""
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ip = {
                executor.submit(self.check_single_status, pc["ip"]): i
                for i, pc in enumerate(self.pc_data)
            }

            for future in as_completed(future_to_ip):
                i = future_to_ip[future]
                try:
                    ip, online = future.result()
                    status = "🟢" if online else "🔴"
                    self.status_labels[i].setText(status)
                except Exception as e:
                    self.status_labels[i].setText("❓")

    def check_single_status(self, ip):
        """Проверка статуса одного компьютера"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            sock.connect((ip, 5050))
            sock.close()
            return ip, True
        except:
            return ip, False


def main():
    app = QApplication(sys.argv)

    # Устанавливаем стиль
    app.setStyle('Fusion')
    window = Controller()
    window.show()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()


###########
import socket
import subprocess
import json
import base64

HOST = "0.0.0.0"
PORT = 5050

print(f"[AGENT] Listening on {HOST}:{PORT}")

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((HOST, PORT))
s.listen(5)

while True:
    conn, addr = s.accept()
    print(f"[AGENT] Connection from {addr}")
    raw = conn.recv(65535).decode("utf-8")

    try:
        info = json.loads(raw)
        command = info["command"]
        mode = info["mode"]

        if mode == "powershell":
            cmd = ["powershell", "-NoProfile", "-Command", command]
        else:
            cmd = ["cmd", "/c", command]

        result = subprocess.run(cmd, capture_output=True, timeout=10)

        stdout = base64.b64encode(result.stdout).decode()
        stderr = base64.b64encode(result.stderr).decode()

        # Если команда ошибочная (returncode != 0), не выводить stderr (очистить его)
        if result.returncode != 0:
            stderr = ""

        response = {
            "stdout": stdout,
            "stderr": stderr,
            "returncode": result.returncode
        }

        # Отправляем ответ только если команда успешная, иначе закрываем без ответа
        if result.returncode == 0:
            conn.send(json.dumps(response).encode("utf-8"))
        # Для ошибочных команд не отправляем ответ, чтобы "не висело" на клиенте (клиент получит empty response и обработает как ошибку)

    except subprocess.TimeoutExpired:
        # Для таймаута не отправляем ответ
        pass
    except Exception as e:
        # Для других исключений не отправляем ответ
        pass

    conn.close()