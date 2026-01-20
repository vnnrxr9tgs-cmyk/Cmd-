import sys
import os
import re
import subprocess  # Добавлено для запуска другого скрипта
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QTextEdit,
    QSplitter, QLineEdit, QLabel, QFrame, QPushButton  # Добавлено QPushButton
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class FileViewer(QWidget):
    def __init__(self, directory="432"):
        super().__init__()
        self.directory = directory
        self.file_contents = {}  # Кэш содержимого файлов
        self.initUI()
        self.apply_styles()

    def initUI(self):
        self.setWindowTitle("Файловый просмотрщик")
        self.setGeometry(100, 100, 1000, 800)  # Увеличил высоту для большего пространства снизу

        # Верхняя панель: поисковики вертикально, статистика ниже (компактная)
        top_frame = QFrame()
        top_frame.setFrameShape(QFrame.StyledPanel)
        top_frame.setMaximumHeight(120)  # Ограничиваем высоту для компактности
        top_layout = QVBoxLayout(top_frame)
        top_layout.setSpacing(5)  # Уменьшил отступы
        top_layout.setContentsMargins(5, 5, 5, 5)  # Уменьшил margins

        # Поиск по имени
        name_layout = QHBoxLayout()
        name_label = QLabel("Имя:")
        name_layout.addWidget(name_label)
        self.search_name_edit = QLineEdit()
        self.search_name_edit.setPlaceholderText("Имя файла...")
        self.search_name_edit.textChanged.connect(self.filter_files)
        name_layout.addWidget(self.search_name_edit)
        top_layout.addLayout(name_layout)

        # Поиск по телу
        body_layout = QHBoxLayout()
        body_label = QLabel("Тело:")
        body_layout.addWidget(body_label)
        self.search_body_edit = QLineEdit()
        self.search_body_edit.setPlaceholderText("Текст из файла...")
        self.search_body_edit.textChanged.connect(self.filter_files)
        body_layout.addWidget(self.search_body_edit)
        top_layout.addLayout(body_layout)

        # Статистика и кнопки в одном ряду
        buttons_layout = QHBoxLayout()
        self.stats_label = QLabel("Найдено: 0 групп")
        self.stats_label.setAlignment(Qt.AlignCenter)
        buttons_layout.addWidget(self.stats_label)

        # Кнопка Обновить
        self.refresh_button = QPushButton("Обновить")
        self.refresh_button.clicked.connect(self.refresh_files)
        buttons_layout.addWidget(self.refresh_button)

        # Кнопка Старт
        self.start_button = QPushButton("Старт")
        self.start_button.clicked.connect(self.run_hw_script)
        buttons_layout.addWidget(self.start_button)

        top_layout.addLayout(buttons_layout)

        # Горизонтальный сплиттер для разделения окна
        splitter = QSplitter(Qt.Horizontal)

        # Левая часть: список файлов
        self.file_list = QListWidget()
        self.load_files()
        self.file_list.itemSelectionChanged.connect(
            self.display_file_content)  # Изменено: теперь обновляется при изменении выбора (включая стрелки)

        # Правая часть: текстовый редактор для содержимого
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        self.update_font()  # Применяем шрифт

        # Добавляем виджеты в сплиттер
        splitter.addWidget(self.file_list)
        splitter.addWidget(self.text_edit)

        # Устанавливаем пропорции (список меньше, отображение больше)
        splitter.setSizes([300, 700])

        # Основной layout
        main_layout = QVBoxLayout()
        main_layout.addWidget(top_frame)
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def refresh_files(self):
        """Обновляет список файлов в левом окошке."""
        self.load_files()
        self.filter_files()  # Применяем текущие фильтры после обновления

    def run_hw_script(self):
        """Запускает скрипт hw.py в той же директории."""
        try:
            subprocess.run([sys.executable, 'hw.py'], cwd=os.getcwd())
        except Exception as e:
            print(f"Ошибка при запуске hw.py: {e}")

    def apply_styles(self):
        """Применяет красивые стили."""
        self.setStyleSheet("""
            QWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e0e0e0, stop:1 #c0c0c0);
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 12px;  /* Уменьшил шрифт для компактности */
            }
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f0f0f0);
                border: 2px solid #4CAF50;
                border-radius: 10px;
                padding: 5px;  /* Уменьшил padding */
            }
            QListWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #e8e8e8);
                border: 1px solid #cccccc;
                border-radius: 8px;
                padding: 5px;
                selection-background-color: #4CAF50;
                alternate-background-color: #f9f9f9;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eeeeee;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4CAF50, stop:1 #45a049);
                color: white;
                font-weight: bold;
            }
            QTextEdit {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #f5f5f5);
                border: 1px solid #cccccc;
                border-radius: 8px;
                padding: 10px;
                font-family: 'Consolas', monospace;
                font-size: 18px;
            }
            QLineEdit {
                border: 2px solid #4CAF50;
                border-radius: 5px;
                padding: 5px;  /* Уменьшил padding */
                background: white;
                font-size: 12px;  /* Уменьшил шрифт */
            }
            QLineEdit:focus {
                border-color: #45a049;
                background: #f0fff0;
            }
            QLabel {
                font-weight: bold;
                color: #333333;
                font-size: 12px;  /* Уменьшил шрифт */
            }
            QLabel#stats_label {
                color: #4CAF50;
                font-size: 14px;  /* Немного меньше */
                font-weight: bold;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #e8f5e8, stop:1 #c8e6c9);
                border: 1px solid #4CAF50;
                border-radius: 5px;
                padding: 3px;  /* Уменьшил padding */
            }
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4CAF50, stop:1 #45a049);
                color: white;
                border: 2px solid #4CAF50;
                border-radius: 5px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #45a049, stop:1 #3e8e41);
            }
            QPushButton:pressed {
                background: #3e8e41;
            }
        """)

    def load_files(self):
        """Загружает список файлов из директории и кэширует содержимое."""
        self.file_list.clear()
        self.file_contents.clear()
        if os.path.exists(self.directory):
            files = [f for f in os.listdir(self.directory) if os.path.isfile(os.path.join(self.directory, f))]
            for file in files:
                file_path = os.path.join(self.directory, file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self.file_contents[file] = content
                except:
                    self.file_contents[file] = ""
            self.all_files = files
            self.file_list.addItems(files)
        else:
            self.file_list.addItem("Директория не найдена")

    def count_five_digit_numbers(self, content):
        """Считает количество последовательностей из ровно пяти цифр в тексте."""
        matches = re.findall(r'\b\d{5}\b', content)
        return len(matches)

    def filter_files(self):
        """Фильтрует файлы по имени и/или телу."""
        name_query = self.search_name_edit.text().lower()
        body_query = self.search_body_edit.text().lower()

        self.file_list.clear()
        filtered = []
        for file in self.all_files:
            name_match = name_query in file.lower() if name_query else True
            body_match = body_query in self.file_contents.get(file, "").lower() if body_query else True
            if name_match and body_match:
                filtered.append(file)
        self.file_list.addItems(filtered)

    def display_file_content(self):
        """Отображает содержимое выбранного файла и обновляет статистику."""
        current_item = self.file_list.currentItem()
        if current_item:
            file_name = current_item.text()
            content = self.file_contents.get(file_name, "Ошибка при чтении файла")
            self.text_edit.setPlainText(content)
            # Подсчитываем и отображаем статистику
            count = self.count_five_digit_numbers(content)
            self.stats_label.setText(f"Найдено: {count} групп")

    def update_font(self):
        """Устанавливает фиксированный шрифт в QTextEdit."""
        font = QFont("Consolas", 18)
        self.text_edit.setFont(font)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    viewer = FileViewer()
    viewer.show()
    sys.exit(app.exec_())
