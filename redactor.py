import sys
import json
import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QTextEdit, QPushButton, QLabel,
    QFileDialog, QMessageBox, QSplitter, QToolBar, QAction,
    QStatusBar, QComboBox, QSpinBox, QGroupBox, QFormLayout,
    QCheckBox, QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QIcon, QTextCursor, QColor, QTextCharFormat


class JsonEditor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_file_path = None
        self.current_json_data = None
        self.json_files = []
        self.untitled_counter = 1
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Редактор JSON новостей")
        self.setMinimumSize(1200, 700)

        # Центральный виджет
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Основной горизонтальный layout
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Создаем разделитель
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # ==================== ЛЕВАЯ ПАНЕЛЬ ====================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)

        # Заголовок левой панели
        left_header = QLabel("📁 JSON файлы")
        left_header.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
        left_layout.addWidget(left_header)

        # Кнопки управления файлами
        files_buttons_layout = QHBoxLayout()

        self.open_btn = QPushButton("📂 Открыть")
        self.open_btn.clicked.connect(self.open_json_files)
        files_buttons_layout.addWidget(self.open_btn)

        self.save_btn = QPushButton("💾 Сохранить")
        self.save_btn.clicked.connect(self.save_current_json)
        files_buttons_layout.addWidget(self.save_btn)

        self.save_as_btn = QPushButton("📑 Сохранить как")
        self.save_as_btn.clicked.connect(self.save_json_as)
        files_buttons_layout.addWidget(self.save_as_btn)

        left_layout.addLayout(files_buttons_layout)

        # Список JSON файлов
        self.file_list = QListWidget()
        self.file_list.itemClicked.connect(self.on_file_selected)
        self.file_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 5px;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QListWidget::item:selected {
                background-color: #2c7da0;
                color: white;
            }
            QListWidget::item:hover {
                background-color: #e0eaf3;
            }
        """)
        left_layout.addWidget(self.file_list)

        # Кнопка удаления файла из списка
        self.remove_file_btn = QPushButton("🗑 Удалить из списка")
        self.remove_file_btn.clicked.connect(self.remove_current_file)
        left_layout.addWidget(self.remove_file_btn)

        # ==================== ПРАВАЯ ПАНЕЛЬ ====================
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(5, 5, 5, 5)

        # Верхняя часть правой панели - мета-информация
        meta_group = QGroupBox("Информация о файле")
        meta_layout = QFormLayout(meta_group)

        self.filename_label = QLabel("—")
        self.filename_label.setStyleSheet("font-weight: bold; color: #2c7da0;")
        meta_layout.addRow("Имя файла:", self.filename_label)

        self.processed_date_label = QLabel("—")
        meta_layout.addRow("Дата обработки:", self.processed_date_label)

        self.language_combo = QComboBox()
        self.language_combo.addItems(["ru", "en", "de", "fr", "es", "it", "zh"])
        self.language_combo.currentTextChanged.connect(self.on_language_changed)
        meta_layout.addRow("Язык:", self.language_combo)

        right_layout.addWidget(meta_group)

        # Панель форматирования
        format_group = QGroupBox("Форматирование текста")
        format_layout = QHBoxLayout(format_group)

        # Управление отступами
        indent_layout = QVBoxLayout()
        indent_layout.addWidget(QLabel("Отступ абзаца (px):"))
        self.indent_spin = QSpinBox()
        self.indent_spin.setRange(0, 50)
        self.indent_spin.setValue(20)
        self.indent_spin.valueChanged.connect(self.apply_formatting)
        indent_layout.addWidget(self.indent_spin)
        format_layout.addLayout(indent_layout)

        # Управление межстрочным интервалом
        line_spacing_layout = QVBoxLayout()
        line_spacing_layout.addWidget(QLabel("Межстрочный интервал:"))
        self.line_spacing_combo = QComboBox()
        self.line_spacing_combo.addItems(["1.0", "1.15", "1.5", "2.0"])
        self.line_spacing_combo.setCurrentText("1.5")
        self.line_spacing_combo.currentTextChanged.connect(self.apply_formatting)
        line_spacing_layout.addWidget(self.line_spacing_combo)
        format_layout.addLayout(line_spacing_layout)

        # Пустые строки между темами
        empty_lines_layout = QVBoxLayout()
        empty_lines_layout.addWidget(QLabel("Пустых строк между темами:"))
        self.empty_lines_spin = QSpinBox()
        self.empty_lines_spin.setRange(0, 5)
        self.empty_lines_spin.setValue(2)
        self.empty_lines_spin.valueChanged.connect(self.on_empty_lines_changed)
        empty_lines_layout.addWidget(self.empty_lines_spin)
        format_layout.addLayout(empty_lines_layout)

        # Кнопка применения форматирования к тексту
        self.apply_format_btn = QPushButton("Применить к тексту")
        self.apply_format_btn.clicked.connect(self.reformat_text)
        format_layout.addWidget(self.apply_format_btn)

        right_layout.addWidget(format_group)

        # Текстовый редактор
        editor_group = QGroupBox("Редактор текста")
        editor_layout = QVBoxLayout(editor_group)

        self.text_editor = QTextEdit()
        self.text_editor.setFont(QFont("Segoe UI", 11))
        self.text_editor.textChanged.connect(self.on_text_changed)
        self.text_editor.setStyleSheet("""
            QTextEdit {
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 10px;
                background-color: #fefefe;
            }
        """)
        editor_layout.addWidget(self.text_editor)

        # Кнопки редактирования под текстовым полем
        edit_buttons_layout = QHBoxLayout()

        self.bold_btn = QPushButton("B")
        self.bold_btn.setFixedSize(30, 30)
        self.bold_btn.setStyleSheet("font-weight: bold;")
        self.bold_btn.clicked.connect(self.make_bold)
        edit_buttons_layout.addWidget(self.bold_btn)

        self.italic_btn = QPushButton("I")
        self.italic_btn.setFixedSize(30, 30)
        self.italic_btn.setStyleSheet("font-style: italic;")
        self.italic_btn.clicked.connect(self.make_italic)
        edit_buttons_layout.addWidget(self.italic_btn)

        self.underline_btn = QPushButton("U")
        self.underline_btn.setFixedSize(30, 30)
        self.underline_btn.setStyleSheet("text-decoration: underline;")
        self.underline_btn.clicked.connect(self.make_underline)
        edit_buttons_layout.addWidget(self.underline_btn)

        edit_buttons_layout.addStretch()

        self.find_btn = QPushButton("🔍 Найти")
        self.find_btn.clicked.connect(self.find_text)
        edit_buttons_layout.addWidget(self.find_btn)

        self.replace_btn = QPushButton("🔄 Заменить")
        self.replace_btn.clicked.connect(self.replace_text)
        edit_buttons_layout.addWidget(self.replace_btn)

        editor_layout.addLayout(edit_buttons_layout)

        right_layout.addWidget(editor_group)

        # Кнопки сохранения и отмены изменений
        save_buttons_layout = QHBoxLayout()

        self.save_text_btn = QPushButton("✅ Сохранить изменения")
        self.save_text_btn.setStyleSheet("background-color: #27ae60; color: white; padding: 8px;")
        self.save_text_btn.clicked.connect(self.save_text_changes)
        save_buttons_layout.addWidget(self.save_text_btn)

        self.cancel_btn = QPushButton("❌ Отменить изменения")
        self.cancel_btn.setStyleSheet("background-color: #e74c3c; color: white; padding: 8px;")
        self.cancel_btn.clicked.connect(self.cancel_changes)
        save_buttons_layout.addWidget(self.cancel_btn)

        right_layout.addLayout(save_buttons_layout)

        # Добавляем панели в разделитель
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([350, 850])

        # Строка статуса
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("Готов к работе")

        # Применяем стили
        self.apply_styles()

    def apply_styles(self):
        self.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QPushButton {
                padding: 5px 10px;
                border-radius: 4px;
                background-color: #ecf0f1;
                border: 1px solid #bdc3c7;
            }
            QPushButton:hover {
                background-color: #d5dbdb;
            }
            QPushButton:pressed {
                background-color: #bdc3c7;
            }
            QComboBox, QSpinBox {
                padding: 4px;
                border: 1px solid #ccc;
                border-radius: 4px;
            }
        """)

    def open_json_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите JSON файлы",
            "",
            "JSON files (*.json);;All files (*.*)"
        )

        for file_path in files:
            if file_path not in self.json_files:
                self.json_files.append(file_path)
                self.add_file_to_list(file_path)

        if self.json_files and not self.current_file_path:
            self.load_json_file(self.json_files[0])

        self.statusBar.showMessage(f"Загружено {len(files)} файлов")

    def add_file_to_list(self, file_path):
        filename = os.path.basename(file_path)
        item = QListWidgetItem(f"📄 {filename}")
        item.setData(Qt.UserRole, file_path)
        self.file_list.addItem(item)

    def on_file_selected(self, item):
        file_path = item.data(Qt.UserRole)
        if file_path:
            self.load_json_file(file_path)

    def load_json_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.current_json_data = json.load(f)
                self.current_file_path = file_path

            # Обновляем мета-информацию
            self.filename_label.setText(os.path.basename(file_path))
            self.processed_date_label.setText(self.current_json_data.get("processed_at", "—")[:19])
            self.language_combo.setCurrentText(self.current_json_data.get("language", "ru"))

            # Загружаем текст в редактор
            processed_text = self.current_json_data.get("processed_text", "")
            self.text_editor.setPlainText(processed_text)

            # Применяем форматирование
            self.apply_formatting()

            self.statusBar.showMessage(f"Загружен: {os.path.basename(file_path)}")

            # Выделяем активный элемент в списке
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                if item.data(Qt.UserRole) == file_path:
                    self.file_list.setCurrentItem(item)
                    break

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл:\n{str(e)}")

    def save_current_json(self):
        if not self.current_file_path or not self.current_json_data:
            self.save_json_as()
            return

        self.save_json_to_file(self.current_file_path)

    def save_json_as(self):
        if not self.current_json_data:
            QMessageBox.warning(self, "Предупреждение", "Нет данных для сохранения")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить JSON файл",
            "",
            "JSON files (*.json);;All files (*.*)"
        )

        if file_path:
            self.save_json_to_file(file_path)
            if file_path not in self.json_files:
                self.json_files.append(file_path)
                self.add_file_to_list(file_path)
            self.current_file_path = file_path
            self.filename_label.setText(os.path.basename(file_path))

    def save_json_to_file(self, file_path):
        try:
            # Обновляем данные перед сохранением
            self.current_json_data["language"] = self.language_combo.currentText()
            self.current_json_data["processed_text"] = self.text_editor.toPlainText()

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(self.current_json_data, f, ensure_ascii=False, indent=2)

            self.statusBar.showMessage(f"Сохранено: {os.path.basename(file_path)}")
            QMessageBox.information(self, "Успех", "Файл успешно сохранен")

        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл:\n{str(e)}")

    def on_language_changed(self):
        if self.current_json_data:
            self.current_json_data["language"] = self.language_combo.currentText()
            self.statusBar.showMessage(f"Язык изменен на: {self.language_combo.currentText()}")

    def on_text_changed(self):
        if self.current_json_data:
            # Просто отмечаем, что текст изменен (можно добавить звездочку в заголовок)
            pass

    def save_text_changes(self):
        if self.current_json_data:
            self.current_json_data["processed_text"] = self.text_editor.toPlainText()
            self.statusBar.showMessage("Изменения сохранены в текущем объекте. Не забудьте сохранить файл!")
            QMessageBox.information(self, "Успех", "Текст обновлен. Нажмите 'Сохранить' для записи в файл.")

    def cancel_changes(self):
        if self.current_json_data:
            # Перезагружаем текст из данных
            self.text_editor.setPlainText(self.current_json_data.get("processed_text", ""))
            self.statusBar.showMessage("Изменения отменены")

    def remove_current_file(self):
        current_item = self.file_list.currentItem()
        if current_item:
            file_path = current_item.data(Qt.UserRole)
            if file_path in self.json_files:
                self.json_files.remove(file_path)
            row = self.file_list.row(current_item)
            self.file_list.takeItem(row)

            if self.current_file_path == file_path:
                self.current_file_path = None
                self.current_json_data = None
                self.filename_label.setText("—")
                self.processed_date_label.setText("—")
                self.text_editor.clear()

            self.statusBar.showMessage(f"Удален из списка: {os.path.basename(file_path)}")

    def apply_formatting(self):
        # Применяем стили форматирования к текстовому редактору
        indent = self.indent_spin.value()
        line_spacing = float(self.line_spacing_combo.currentText())

        # Устанавливаем стили через CSS
        self.text_editor.setStyleSheet(f"""
            QTextEdit {{
                border: 1px solid #ccc;
                border-radius: 5px;
                padding: 10px;
                background-color: #fefefe;
            }}
            QTextEdit::viewport {{
                margin: {indent}px;
            }}
        """)

        # Устанавливаем межстрочный интервал
        fmt = QTextCharFormat()
        # Для QTextEdit межстрочный интервал устанавливается через setFont
        font = self.text_editor.font()
        font.setLetterSpacing(QFont.AbsoluteSpacing, line_spacing)
        self.text_editor.setFont(font)

    def reformat_text(self):
        """Переформатирует текст с учетом количества пустых строк между темами"""
        if not self.current_json_data:
            return

        text = self.text_editor.toPlainText()
        empty_lines = self.empty_lines_spin.value()

        # Разделяем текст на блоки по темам (по двойным переносам строк или маркерам тем)
        # Ищем строки, начинающиеся с ** (жирное выделение темы)
        lines = text.split('\n')
        formatted_lines = []
        i = 0

        while i < len(lines):
            line = lines[i].strip()

            # Если строка начинается с ** (заголовок темы)
            if line.startswith('**') or (line and not line.startswith(' ') and len(line) < 100):
                # Добавляем тему
                formatted_lines.append(lines[i])
                i += 1

                # Пропускаем пустые строки после темы
                while i < len(lines) and not lines[i].strip():
                    i += 1

                # Добавляем нужное количество пустых строк
                for _ in range(empty_lines):
                    formatted_lines.append('')

                # Добавляем текст темы
                while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('**'):
                    if lines[i].strip():
                        formatted_lines.append(lines[i])
                    i += 1

                # Добавляем разделитель между темами
                if i < len(lines):
                    formatted_lines.append('')
                    formatted_lines.append('')
            else:
                if line:
                    formatted_lines.append(lines[i])
                elif formatted_lines and formatted_lines[-1] != '':
                    formatted_lines.append('')
                i += 1

        # Собираем отформатированный текст
        formatted_text = '\n'.join(formatted_lines)

        # Очищаем лишние переносы в конце
        while formatted_text.endswith('\n\n'):
            formatted_text = formatted_text[:-1]

        self.text_editor.setPlainText(formatted_text)
        self.statusBar.showMessage("Текст переформатирован")

    def on_empty_lines_changed(self):
        """При изменении количества пустых строк применяем форматирование"""
        self.reformat_text()

    def make_bold(self):
        cursor = self.text_editor.textCursor()
        if cursor.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Bold)
            cursor.mergeCharFormat(fmt)

    def make_italic(self):
        cursor = self.text_editor.textCursor()
        if cursor.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontItalic(True)
            cursor.mergeCharFormat(fmt)

    def make_underline(self):
        cursor = self.text_editor.textCursor()
        if cursor.hasSelection():
            fmt = QTextCharFormat()
            fmt.setFontUnderline(True)
            cursor.mergeCharFormat(fmt)

    def find_text(self):
        from PyQt5.QtWidgets import QInputDialog

        text, ok = QInputDialog.getText(self, "Поиск", "Введите текст для поиска:")
        if ok and text:
            cursor = self.text_editor.textCursor()
            cursor = self.text_editor.document().find(text, cursor)
            if not cursor.isNull():
                self.text_editor.setTextCursor(cursor)
                self.statusBar.showMessage(f"Найдено: {text}")
            else:
                QMessageBox.information(self, "Поиск", "Текст не найден")

    def replace_text(self):
        from PyQt5.QtWidgets import QInputDialog

        find_text, ok = QInputDialog.getText(self, "Замена", "Найти:")
        if ok and find_text:
            replace_text, ok = QInputDialog.getText(self, "Замена", "Заменить на:")
            if ok:
                cursor = self.text_editor.textCursor()
                cursor.beginEditBlock()

                # Заменяем все вхождения
                doc = self.text_editor.document()
                cursor = QTextCursor(doc)

                count = 0
                while True:
                    cursor = doc.find(find_text, cursor)
                    if cursor.isNull():
                        break
                    cursor.insertText(replace_text)
                    count += 1

                cursor.endEditBlock()
                self.statusBar.showMessage(f"Заменено {count} вхождений")

    def closeEvent(self, event):
        """При закрытии программы спрашиваем о сохранении"""
        if self.current_json_data and self.current_json_data.get("processed_text") != self.text_editor.toPlainText():
            reply = QMessageBox.question(
                self,
                "Несохраненные изменения",
                "У вас есть несохраненные изменения. Сохранить перед выходом?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )

            if reply == QMessageBox.Yes:
                self.save_text_changes()
                if self.current_file_path:
                    self.save_json_to_file(self.current_file_path)
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("JSON News Editor")
    app.setApplicationDisplayName("Редактор JSON новостей")

    window = JsonEditor()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()