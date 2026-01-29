import sys
import os
import shutil
from datetime import datetime, time, timedelta
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextEdit, QSpinBox, QTimeEdit, QGroupBox, QFormLayout,
    QFileDialog, QMessageBox
)
from PyQt5.QtCore import QTimer, QThread, pyqtSignal, QTime
from PyQt5.QtGui import QFont, QPalette, QColor

class FileMoverThread(QThread):
    log_signal = pyqtSignal(str)
    count_signal = pyqtSignal(int, int)  # path_index, count

    def __init__(self, paths, interval_minutes, start_time, end_time):
        super().__init__()
        self.paths = paths  # list of (input_dir, output_dir)
        self.interval_minutes = interval_minutes
        self.start_time = start_time
        self.end_time = end_time
        self.counts = [0, 0]  # counts for each path

    def run(self):
        while not self.isInterruptionRequested():
            now = datetime.now().time()
            if self.start_time <= now <= self.end_time:
                for i, (input_dir, output_dir) in enumerate(self.paths):
                    if os.path.exists(input_dir) and os.path.exists(output_dir):
                        try:
                            files = [f for f in os.listdir(input_dir) if os.path.isfile(os.path.join(input_dir, f))]
                        except PermissionError as e:
                            self.log_signal.emit(f"Ошибка доступа к директории {input_dir}: {str(e)}")
                            continue
                        for file in files:
                            src = os.path.join(input_dir, file)
                            dst = os.path.join(output_dir, file)
                            try:
                                shutil.move(src, dst)
                                self.counts[i] += 1
                                self.log_signal.emit(f"Перемещен файл: {file} из {input_dir} в {output_dir}")
                            except Exception as e:
                                self.log_signal.emit(f"Ошибка перемещения {file}: {str(e)}")
                        self.count_signal.emit(i, self.counts[i])
            # Sleep for interval with interruption check
            for _ in range(self.interval_minutes * 60):
                if self.isInterruptionRequested():
                    break
                self.msleep(1000)  # sleep 1 second at a time

class FileMoverApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("File Mover")
        self.setGeometry(100, 100, 800, 600)
        self.setStyleSheet("""
            QWidget {
                background-color: #f0f0f0;
                font-family: Arial;
            }
            QGroupBox {
                font-weight: bold;
                border: 1px solid #cccccc;
                border-radius: 5px;
                margin-top: 1ex;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3e8e41;
            }
            QLineEdit, QSpinBox, QTimeEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
                padding: 4px;
            }
            QTextEdit {
                border: 1px solid #cccccc;
                border-radius: 4px;
            }
        """)

        self.paths = [("", ""), ("", "")]  # (input, output) for two paths
        self.thread = None
        self.is_running = False
        self.start_time = None  # to track when started

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Status section
        status_group = QGroupBox("Статус")
        status_layout = QHBoxLayout()
        self.status_label = QLabel("Остановлен")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.status_label)
        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        # Paths section
        paths_group = QGroupBox("Пути")
        paths_layout = QVBoxLayout()

        for i in range(2):
            path_layout = QHBoxLayout()
            path_layout.addWidget(QLabel(f"Путь {i+1}:"))

            input_edit = QLineEdit()
            input_edit.setPlaceholderText("Входная директория")
            path_layout.addWidget(input_edit)

            input_btn = QPushButton("Выбрать")
            input_btn.clicked.connect(lambda _, idx=i: self.select_dir(idx, 0))
            path_layout.addWidget(input_btn)

            output_edit = QLineEdit()
            output_edit.setPlaceholderText("Выходная директория")
            path_layout.addWidget(output_edit)

            output_btn = QPushButton("Выбрать")
            output_btn.clicked.connect(lambda _, idx=i: self.select_dir(idx, 1))
            path_layout.addWidget(output_btn)

            count_label = QLabel("Перемещено: 0")
            path_layout.addWidget(count_label)

            paths_layout.addLayout(path_layout)

            # Store references
            if not hasattr(self, 'input_edits'):
                self.input_edits = []
                self.output_edits = []
                self.count_labels = []
            self.input_edits.append(input_edit)
            self.output_edits.append(output_edit)
            self.count_labels.append(count_label)

        paths_group.setLayout(paths_layout)
        layout.addWidget(paths_group)

        # Settings section
        settings_group = QGroupBox("Настройки")
        settings_layout = QFormLayout()

        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 60)
        self.interval_spin.setValue(1)
        self.interval_spin.setSuffix(" мин")
        settings_layout.addRow("Интервал перемещения:", self.interval_spin)

        self.start_time_edit = QTimeEdit()
        self.start_time_edit.setTime(QTime(1, 0))
        settings_layout.addRow("Время начала:", self.start_time_edit)

        self.end_time_edit = QTimeEdit()
        self.end_time_edit.setTime(QTime(3, 0))
        settings_layout.addRow("Время окончания:", self.end_time_edit)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        # Timers section
        timers_group = QGroupBox("Таймеры")
        timers_layout = QHBoxLayout()
        self.remaining_work_label = QLabel("До начала работы: --:--:--")
        timers_layout.addWidget(self.remaining_work_label)
        self.next_move_label = QLabel("Следующее перемещение через: --:--:--")
        timers_layout.addWidget(self.next_move_label)
        timers_group.setLayout(timers_layout)
        layout.addWidget(timers_group)

        # Control buttons
        control_layout = QHBoxLayout()
        self.start_btn = QPushButton("Старт")
        self.start_btn.clicked.connect(self.start_moving)
        control_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Стоп")
        self.stop_btn.clicked.connect(self.stop_moving)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)

        layout.addLayout(control_layout)

        # Logs section
        logs_group = QGroupBox("Логи")
        logs_layout = QVBoxLayout()
        self.logs_text = QTextEdit()
        self.logs_text.setReadOnly(True)
        logs_layout.addWidget(self.logs_text)
        logs_group.setLayout(logs_layout)
        layout.addWidget(logs_group)

        self.setLayout(layout)

        # Timer for updating timers
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_timers)
        self.timer.start(1000)  # every second

    def select_dir(self, path_idx, dir_type):
        dir_path = QFileDialog.getExistingDirectory(self, "Выбрать директорию")
        if dir_path:
            if dir_type == 0:
                self.input_edits[path_idx].setText(dir_path)
                self.paths[path_idx] = (dir_path, self.paths[path_idx][1])
            else:
                self.output_edits[path_idx].setText(dir_path)
                self.paths[path_idx] = (self.paths[path_idx][0], dir_path)

    def start_moving(self):
        if not self.thread or not self.thread.isRunning():
            self.paths = [(self.input_edits[i].text(), self.output_edits[i].text()) for i in range(2)]
            if any(not inp or not out for inp, out in self.paths):
                QMessageBox.warning(self, "Ошибка", "Все пути должны быть указаны.")
                return
            interval = self.interval_spin.value()
            start_time = self.start_time_edit.time().toPyTime()
            end_time = self.end_time_edit.time().toPyTime()
            if start_time >= end_time:
                QMessageBox.warning(self, "Ошибка", "Время начала должно быть раньше времени окончания.")
                return

            self.thread = FileMoverThread(self.paths, interval, start_time, end_time)
            self.thread.log_signal.connect(self.add_log)
            self.thread.count_signal.connect(self.update_count)

            self.thread.start()
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.is_running = True
            self.start_time = datetime.now()
            self.status_label.setText("Запущен")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            self.add_log("Процесс запущен")

    def stop_moving(self):
        if self.thread and self.thread.isRunning():
            self.thread.requestInterruption()
            # Wait for thread to finish, but with a timeout to avoid hanging
            if not self.thread.wait(5000):  # wait up to 5 seconds
                self.add_log("Предупреждение: поток не завершился вовремя")
            self.start_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.is_running = False
            self.start_time = None
            self.status_label.setText("Остановлен")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            self.add_log("Процесс остановлен")

    def add_log(self, message):
        self.logs_text.append(message)
        if self.logs_text.document().lineCount() >= 100:
            self.logs_text.clear()
            self.logs_text.append("Логи очищены")

    def update_count(self, path_idx, count):
        self.count_labels[path_idx].setText(f"Перемещено: {count}")

    def update_timers(self):
        if not self.is_running:
            self.remaining_work_label.setText("До начала работы: --:--:--")
            self.next_move_label.setText("Следующее перемещение через: --:--:--")
            return

        now = datetime.now()
        start = self.start_time_edit.time().toPyTime()
        end = self.end_time_edit.time().toPyTime()
        start_dt = datetime.combine(now.date(), start)
        end_dt = datetime.combine(now.date(), end)

        if start_dt <= now <= end_dt:
            remaining = (end_dt - now).total_seconds()
            self.remaining_work_label.setText(f"Осталось работать: {int(remaining // 3600):02d}:{int((remaining % 3600) // 60):02d}:{int(remaining % 60):02d}")
        else:
            if now < start_dt:
                remaining = (start_dt - now).total_seconds()
                self.remaining_work_label.setText(f"До начала работы: {int(remaining // 3600):02d}:{int((remaining % 3600) // 60):02d}:{int(remaining % 60):02d}")
            else:
                # After end, to start next day
                tomorrow_start = datetime.combine(now.date() + timedelta(days=1), start)
                remaining = (tomorrow_start - now).total_seconds()
                self.remaining_work_label.setText(f"До начала работы: {int(remaining // 3600):02d}:{int((remaining % 3600) // 60):02d}:{int(remaining % 60):02d}")

        # Next move timer
        interval_sec = self.interval_spin.value() * 60
        if self.start_time:
            elapsed = (now - self.start_time).total_seconds()
            next_interval = ((elapsed // interval_sec) + 1) * interval_sec
            next_move = self.start_time + timedelta(seconds=next_interval)
            if next_move > end_dt:
                next_move = datetime.combine(now.date() + timedelta(days=1), start)
        else:
            next_move = start_dt

        remaining_next = (next_move - now).total_seconds()
        if remaining_next < 0:
            remaining_next = 0
        self.next_move_label.setText(f"Следующее перемещение через: {int(remaining_next // 3600):02d}:{int((remaining_next % 3600) // 60):02d}:{int(remaining_next % 60):02d}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileMoverApp()
    window.show()
    sys.exit(app.exec_())