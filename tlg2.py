import sys
import os
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

NEWS_FILE = "news.txt"

# ──────────────────────────────────────────────────────
# КОНСТАНТЫ
# ──────────────────────────────────────────────────────
SIDEBAR_WIDTH = 390
CARD_RADIUS = 12
FONT_SIZE_TITLE = 13
FONT_SIZE_NEWS = 12
FONT_SIZE_CHANNEL = 11
FONT_SIZE_SMALL = 9
CHANNEL_HEIGHT = 88

# ──────────────────────────────────────────────────────
# ТЕМА
# ──────────────────────────────────────────────────────
class Theme:
    WINDOW = "#1f2329"
    SIDEBAR = "#21262d"
    HEADER = "#1a1e24"
    CARD = "#2a2f38"
    CARD_HOVER = "#323a44"
    CARD_ACTIVE = "#2f6ea5"
    BORDER = "#353c46"
    TEXT = "#ffffff"
    SUBTEXT = "#9ea7b3"
    BLUE = "#3390ec"
    GREEN = "#43d675"
    RED = "#ff6666"
    SHADOW = QColor(0, 0, 0, 100)


def font_s(size=10, bold=False):
    f = QFont("Segoe UI", size)
    f.setBold(bold)
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def apply_shadow(widget, blur=18, offset_y=4):
    effect = QGraphicsDropShadowEffect()
    effect.setBlurRadius(blur)
    effect.setOffset(0, offset_y)
    effect.setColor(Theme.SHADOW)
    widget.setGraphicsEffect(effect)


def human_time(text):
    try:
        dt = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        return dt.strftime("%H:%M")
    except:
        return text[:5] if len(text) >= 5 else text


def truncate(text, max_len=80):
    return text[:max_len] + "…" if len(text) > max_len else text


# ──────────────────────────────────────────────────────
# МОДЕЛИ
# ──────────────────────────────────────────────────────
@dataclass
class News:
    date: str
    channel: str
    text: str

    @property
    def dt(self):
        try:
            return datetime.strptime(self.date, "%Y-%m-%d %H:%M:%S")
        except:
            return datetime.min


@dataclass
class Channel:
    name: str
    last_news: str
    last_date: str
    count: int


# ──────────────────────────────────────────────────────
# АВАТАРКА
# ──────────────────────────────────────────────────────
class AvatarWidget(QWidget):
    COLORS = [
        "#3390ec", "#50b36d", "#ff9800", "#e91e63", "#9c27b0",
        "#03a9f4", "#009688", "#607d8b", "#f44336", "#795548"
    ]

    def __init__(self, text, size=38):
        super().__init__()
        self.text = text
        self.size = size
        self.setFixedSize(size, size)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        color = QColor(self.COLORS[abs(hash(self.text)) % len(self.COLORS)])
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, self.size, self.size)

        words = self.text.split()
        if len(words) == 1:
            letters = words[0][:2].upper()
        else:
            letters = (words[0][0] + words[1][0]).upper()

        p.setPen(Qt.white)
        p.setFont(font_s(int(self.size * 0.42), True))
        p.drawText(self.rect(), Qt.AlignCenter, letters)


# ──────────────────────────────────────────────────────
# ВИДЖЕТ КАНАЛА
# ──────────────────────────────────────────────────────
class ChannelWidget(QFrame):
    clicked = pyqtSignal(object)

    def __init__(self, channel: Channel):
        super().__init__()
        self.channel = channel
        self.selected = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(CHANNEL_HEIGHT)

        self.setStyleSheet(f"""
            QFrame {{
                background: {Theme.CARD};
                border-radius: {CARD_RADIUS}px;
                border: none;
            }}
        """)
        apply_shadow(self, 16, 3)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)

        avatar = AvatarWidget(channel.name, 42)
        layout.addWidget(avatar)

        info = QVBoxLayout()
        info.setSpacing(6)

        title = QLabel(channel.name)
        title.setFont(font_s(FONT_SIZE_CHANNEL, True))
        title.setStyleSheet("color: #ffffff;")
        info.addWidget(title)

        preview = QLabel(truncate(channel.last_news, 48))
        preview.setFont(font_s(FONT_SIZE_SMALL))
        preview.setStyleSheet(f"color: {Theme.SUBTEXT};")
        preview.setWordWrap(True)
        preview.setMaximumHeight(34)
        info.addWidget(preview)

        layout.addLayout(info)
        layout.addStretch()

        time_label = QLabel(human_time(channel.last_date))
        time_label.setFont(font_s(8))
        time_label.setStyleSheet(f"color: {Theme.SUBTEXT};")
        time_label.setAlignment(Qt.AlignRight | Qt.AlignTop)
        layout.addWidget(time_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.channel)

    def setSelected(self, value):
        self.selected = value
        bg = Theme.CARD_ACTIVE if value else Theme.CARD
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-radius: {CARD_RADIUS}px;
                border: none;
            }}
        """)

    def enterEvent(self, event):
        if not self.selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {Theme.CARD_HOVER};
                    border-radius: {CARD_RADIUS}px;
                    border: none;
                }}
            """)

    def leaveEvent(self, event):
        if not self.selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {Theme.CARD};
                    border-radius: {CARD_RADIUS}px;
                    border: none;
                }}
            """)


# ──────────────────────────────────────────────────────
# КАРТОЧКА НОВОСТИ
# ──────────────────────────────────────────────────────
class NewsCard(QFrame):
    def __init__(self, news: News):
        super().__init__()
        self.news = news

        self.setStyleSheet(f"""
            QFrame {{
                background: {Theme.CARD};
                border-radius: {CARD_RADIUS}px;
                border: none;
            }}
        """)
        apply_shadow(self, 22, 4)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        top = QHBoxLayout()
        top.setSpacing(12)

        avatar = AvatarWidget(news.channel, 34)
        top.addWidget(avatar)

        channel_label = QLabel(news.channel)
        channel_label.setFont(font_s(FONT_SIZE_CHANNEL, True))
        channel_label.setStyleSheet("color: #ffffff;")
        top.addWidget(channel_label)

        top.addStretch()

        time_label = QLabel(human_time(news.date))
        time_label.setFont(font_s(FONT_SIZE_SMALL))
        time_label.setStyleSheet(f"color: {Theme.SUBTEXT};")
        top.addWidget(time_label)

        copy_btn = QPushButton("Копировать")
        copy_btn.setFixedSize(82, 28)
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {Theme.BORDER};
                border-radius: 14px;
                color: {Theme.SUBTEXT};
                font-size: 10px;
            }}
            QPushButton:hover {{
                background: {Theme.CARD_HOVER};
                border-color: {Theme.BLUE};
                color: white;
            }}
        """)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(news.text))
        top.addWidget(copy_btn)

        layout.addLayout(top)

        text_label = QLabel(news.text)
        text_label.setWordWrap(True)
        text_label.setFont(font_s(FONT_SIZE_NEWS))
        text_label.setStyleSheet(f"color: {Theme.TEXT}; line-height: 1.45;")
        layout.addWidget(text_label)

        bottom = QHBoxLayout()
        date_full = QLabel(news.date)
        date_full.setFont(font_s(FONT_SIZE_SMALL - 1))
        date_full.setStyleSheet(f"color: {Theme.SUBTEXT};")
        bottom.addWidget(date_full)
        bottom.addStretch()
        layout.addLayout(bottom)

    def enterEvent(self, event):
        self.setStyleSheet(f"""
            QFrame {{
                background: {Theme.CARD_HOVER};
                border-radius: {CARD_RADIUS}px;
                border: none;
            }}
        """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(f"""
            QFrame {{
                background: {Theme.CARD};
                border-radius: {CARD_RADIUS}px;
                border: none;
            }}
        """)
        super().leaveEvent(event)


# ──────────────────────────────────────────────────────
# БОКОВАЯ ПАНЕЛЬ
# ──────────────────────────────────────────────────────
class Sidebar(QFrame):
    channelSelected = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setStyleSheet(f"""
            QFrame {{
                background: {Theme.SIDEBAR};
                border-right: 1px solid {Theme.BORDER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(12)

        title = QLabel("КАНАЛЫ")
        title.setFont(font_s(12, True))
        title.setStyleSheet(f"color: {Theme.BLUE}; letter-spacing: 0.8px;")
        layout.addWidget(title)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical {
                width: 7px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: #454b57;
                border-radius: 3px;
                min-height: 30px;
            }
            QScrollBar::handle:vertical:hover { background: #5a6275; }
        """)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setSpacing(9)
        self.vbox.setContentsMargins(0, 0, 0, 0)
        self.vbox.addStretch()

        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll)

        self.channel_widgets = []

    def clear(self):
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self.channel_widgets.clear()

    def setChannels(self, channels: List[Channel]):
        self.clear()
        for channel in channels:
            w = ChannelWidget(channel)
            w.clicked.connect(self.selectChannel)
            self.channel_widgets.append(w)
            self.vbox.insertWidget(self.vbox.count() - 1, w)

    def selectChannel(self, channel):
        for w in self.channel_widgets:
            w.setSelected(w.channel.name == channel.name)
        self.channelSelected.emit(channel)


# ──────────────────────────────────────────────────────
# ОСНОВНОЙ КОНТЕНТ
# ──────────────────────────────────────────────────────
class MainContent(QWidget):
    refreshRequested = pyqtSignal()
    searchRequested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setStyleSheet(f"background: {Theme.WINDOW};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = QFrame()
        self.header.setFixedHeight(64)
        self.header.setStyleSheet(f"""
            QFrame {{
                background: {Theme.HEADER};
                border-bottom: 1px solid {Theme.BORDER};
            }}
        """)

        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(24, 12, 24, 12)
        header_layout.setSpacing(16)

        self.channel_title = QLabel("Все новости")
        self.channel_title.setFont(font_s(FONT_SIZE_TITLE, True))
        self.channel_title.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(self.channel_title)

        self.count_label = QLabel("0")
        self.count_label.setFont(font_s(FONT_SIZE_SMALL))
        self.count_label.setStyleSheet(f"color: {Theme.SUBTEXT};")
        header_layout.addWidget(self.count_label)

        header_layout.addStretch()

        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по новостям...")
        self.search.setMinimumHeight(36)
        self.search.setFixedWidth(240)
        self.search.setFont(font_s(10))
        self.search.setStyleSheet(f"""
            QLineEdit {{
                background: {Theme.CARD};
                color: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 18px;
                padding: 0 16px;
            }}
            QLineEdit:focus {{
                border: 2px solid {Theme.BLUE};
            }}
        """)
        self.search.textChanged.connect(self.searchRequested)
        header_layout.addWidget(self.search)

        refresh_btn = QPushButton("⟳")
        refresh_btn.setFixedSize(36, 36)
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.setFont(font_s(16))
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.CARD};
                border: none;
                border-radius: 18px;
                color: white;
            }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
            QPushButton:pressed {{ background: {Theme.BLUE}; }}
        """)
        refresh_btn.clicked.connect(self.refreshRequested)
        header_layout.addWidget(refresh_btn)

        layout.addWidget(self.header)

        self.news_area = QScrollArea()
        self.news_area.setWidgetResizable(True)
        self.news_area.setFrameShape(QFrame.NoFrame)
        self.news_area.setStyleSheet(f"""
            QScrollArea {{ background: {Theme.WINDOW}; border: none; }}
            QScrollBar:vertical {{
                width: 9px;
                background: {Theme.WINDOW};
            }}
            QScrollBar::handle:vertical {{
                background: #454b57;
                border-radius: 4px;
                min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{ background: #5f677d; }}
        """)

        self.news_container = QWidget()
        self.news_container.setStyleSheet(f"background: {Theme.WINDOW};")
        self.news_layout = QVBoxLayout(self.news_container)
        self.news_layout.setContentsMargins(20, 20, 20, 20)
        self.news_layout.setSpacing(14)
        self.news_layout.addStretch()

        self.news_area.setWidget(self.news_container)
        layout.addWidget(self.news_area)

    def showNews(self, news_list: List[News]):
        while self.news_layout.count() > 1:
            item = self.news_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        if not news_list:
            empty = QLabel("Новостей не найдено")
            empty.setAlignment(Qt.AlignCenter)
            empty.setFont(font_s(14))
            empty.setStyleSheet(f"color: {Theme.SUBTEXT}; padding: 80px 20px;")
            self.news_layout.insertWidget(0, empty)
        else:
            for news in news_list:
                card = NewsCard(news)
                self.news_layout.insertWidget(self.news_layout.count() - 1, card)

        QTimer.singleShot(30, lambda: self.news_area.verticalScrollBar().setValue(0))

    def setChannelInfo(self, name: str, count: int):
        self.channel_title.setText(name)
        self.count_label.setText(str(count))


# ──────────────────────────────────────────────────────
# ГЛАВНОЕ ОКНО
# ──────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self, storage):
        super().__init__()
        self.storage = storage
        self.current_channel = None
        self._first_show = True

        self.setWindowTitle("Telegram News")
        self.setGeometry(120, 80, 1180, 740)
        self.setMinimumSize(920, 620)
        self.setStyleSheet(f"background: {Theme.WINDOW};")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar()
        layout.addWidget(self.sidebar)

        self.content = MainContent()
        layout.addWidget(self.content)

        self.sidebar.channelSelected.connect(self.onChannelSelected)
        self.content.searchRequested.connect(self.onSearch)
        self.content.refreshRequested.connect(self.loadData)

        self.loadData()

    def showEvent(self, event):
        if self._first_show:
            self._first_show = False
            self.setWindowOpacity(0.0)
            anim = QPropertyAnimation(self, b"windowOpacity")
            anim.setDuration(280)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.start()
            self._show_anim = anim  # сохраняем, чтобы не удалилась
        super().showEvent(event)

    def loadData(self):
        self.storage.load()
        self.sidebar.setChannels(self.storage.channels)

        all_news = self.storage.all_news()
        self.content.showNews(all_news)
        self.content.setChannelInfo("Все новости", len(all_news))

        if self.sidebar.channel_widgets:
            self.sidebar.selectChannel(self.sidebar.channel_widgets[0].channel)

    def onChannelSelected(self, channel: Channel):
        self.current_channel = channel
        news = self.storage.by_channel(channel.name)
        self.content.showNews(news)
        self.content.setChannelInfo(channel.name, len(news))

    def onSearch(self, text: str):
        if not text.strip():
            if self.current_channel:
                self.onChannelSelected(self.current_channel)
            else:
                all_news = self.storage.all_news()
                self.content.showNews(all_news)
                self.content.setChannelInfo("Все новости", len(all_news))
            return

        news = self.storage.search(text, self.current_channel.name if self.current_channel else None)
        self.content.showNews(news)
        self.content.setChannelInfo("Результаты поиска", len(news))

    def showNews(self, news_list):
        self.content.showNews(news_list)


# ──────────────────────────────────────────────────────
# ХРАНИЛИЩЕ
# ──────────────────────────────────────────────────────
class NewsStorage:
    def __init__(self, filename):
        self.filename = filename
        self.news: List[News] = []
        self.channels: List[Channel] = []
        self.ensure_file()

    def ensure_file(self):
        if not os.path.exists(self.filename):
            sample_data = [
                "2026-07-10 09:15:00 | Россия 24 | Правительство одобрило новую программу поддержки IT-отрасли",
                "2026-07-10 10:05:00 | НТВ | В Москве запущен крупнейший в Европе дата-центр",
                "2026-07-10 11:20:00 | Первый канал | Президент провел совещание по экономическим вопросам",
                "2026-07-10 12:40:00 | ТВЦ | Курс рубля укрепился на фоне позитивных новостей",
            ]
            with open(self.filename, 'w', encoding='utf-8') as f:
                for line in sample_data:
                    f.write(line + "\n")

    def load(self):
        self.news.clear()
        self.channels.clear()
        if not os.path.exists(self.filename):
            return

        with open(self.filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|', 2)
                if len(parts) >= 3:
                    self.news.append(News(parts[0].strip(), parts[1].strip(), parts[2].strip()))

        self.news.sort(key=lambda x: x.dt, reverse=True)

        cache = {}
        for item in self.news:
            if item.channel not in cache:
                cache[item.channel] = {"last": item.text, "date": item.date, "count": 0}
            cache[item.channel]["count"] += 1

        for name, data in cache.items():
            self.channels.append(Channel(name, data["last"], data["date"], data["count"]))

        self.channels.sort(key=lambda x: x.last_date, reverse=True)

    def checksum(self):
        if not self.news:
            return ""
        last = self.news[0]
        return hashlib.md5(f"{last.date}{last.channel}{last.text}".encode()).hexdigest()

    def all_news(self):
        return self.news[:]

    def by_channel(self, name):
        return [n for n in self.news if n.channel == name]

    def search(self, text, channel=None):
        text = text.lower().strip()
        data = self.news if not channel else self.by_channel(channel)
        return [n for n in data if text in n.text.lower()]


# ──────────────────────────────────────────────────────
# УВЕДОМЛЕНИЕ (исправлено сохранение анимаций)
# ──────────────────────────────────────────────────────
class ToastNotification(QWidget):
    def __init__(self, channel: str, full_text: str):
        super().__init__()
        self.channel = channel
        self.full_text = full_text
        self.expanded = False

        self.width = 460
        self.compact_height = 160
        self.expanded_height = 420

        # Сохраняем анимации, чтобы не удалились сборщиком мусора
        self._anim_show = None
        self._anim_close = None
        self._anim_expand = None
        self._anim_collapse = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setStyleSheet(f"""
            QFrame {{
                background: {Theme.CARD};
                border-radius: 16px;
                border: 1px solid {Theme.BORDER};
            }}
        """)
        apply_shadow(self.frame, 32, 8)

        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(20, 18, 20, 18)
        frame_layout.setSpacing(14)

        # Верхняя строка
        top = QHBoxLayout()
        top.setSpacing(12)

        ch_label = QLabel(channel)
        ch_label.setFont(font_s(13, True))
        ch_label.setStyleSheet(f"color: {Theme.BLUE};")
        top.addWidget(ch_label)
        top.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {Theme.SUBTEXT}; font-size: 15px; }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        close_btn.clicked.connect(self.close_animation)
        top.addWidget(close_btn)

        frame_layout.addLayout(top)

        # Превью
        self.preview_label = QLabel(truncate(full_text, 140))
        self.preview_label.setWordWrap(True)
        self.preview_label.setFont(font_s(12))
        self.preview_label.setStyleSheet(f"color: {Theme.TEXT};")
        frame_layout.addWidget(self.preview_label)

        # Полный текст
        self.detail_area = QScrollArea()
        self.detail_area.setWidgetResizable(True)
        self.detail_area.setFrameShape(QFrame.NoFrame)
        self.detail_area.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: #3f4754; border-radius: 3px; }}
        """)
        self.detail_content = QLabel(full_text)
        self.detail_content.setWordWrap(True)
        self.detail_content.setFont(font_s(12))
        self.detail_content.setStyleSheet(f"color: {Theme.TEXT}; padding-right: 12px;")
        self.detail_area.setWidget(self.detail_content)
        self.detail_area.setVisible(False)
        frame_layout.addWidget(self.detail_area)

        # Кнопки
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        self.close_btn = QPushButton("Закрыть")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.CARD};
                border: 1px solid {Theme.BORDER};
                border-radius: 14px;
                color: white;
                padding: 7px 18px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
        """)
        self.close_btn.clicked.connect(self.close_animation)
        btn_layout.addWidget(self.close_btn)

        self.expand_btn = QPushButton("Подробнее")
        self.expand_btn.setCursor(Qt.PointingHandCursor)
        self.expand_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.BLUE};
                border: none;
                border-radius: 14px;
                color: white;
                padding: 7px 18px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: #2a7fd4; }}
        """)
        self.expand_btn.clicked.connect(self.toggle_expand)
        btn_layout.addWidget(self.expand_btn)

        frame_layout.addLayout(btn_layout)
        main_layout.addWidget(self.frame)

        self.setFixedSize(self.width, self.compact_height)

        # Позиционирование и анимация
        screen = QApplication.primaryScreen().availableGeometry()
        self.target_x = screen.right() - self.width - 24
        self.target_y = screen.bottom() - self.compact_height - 80
        self.move(self.target_x, screen.bottom() + 40)

        self.setWindowOpacity(0.0)
        self.show()

        # Анимация появления (сохраняем ссылки)
        pos_anim = QPropertyAnimation(self, b"pos")
        pos_anim.setDuration(420)
        pos_anim.setStartValue(QPoint(self.target_x, screen.bottom() + 40))
        pos_anim.setEndValue(QPoint(self.target_x, self.target_y))
        pos_anim.setEasingCurve(QEasingCurve.OutBack)

        fade_anim = QPropertyAnimation(self, b"windowOpacity")
        fade_anim.setDuration(340)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)

        self._anim_show = QParallelAnimationGroup()
        self._anim_show.addAnimation(pos_anim)
        self._anim_show.addAnimation(fade_anim)
        self._anim_show.start()

        self.auto_close = QTimer()
        self.auto_close.setSingleShot(True)
        self.auto_close.timeout.connect(self.close_animation)
        self.auto_close.start(18000)

    def toggle_expand(self):
        if self.expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        if self.expanded:
            return
        self.expanded = True
        self.auto_close.stop()
        self.expand_btn.setText("Свернуть")
        self.preview_label.setVisible(False)
        self.detail_area.setVisible(True)

        current = self.geometry()
        new_h = self.expanded_height
        new_y = current.y() - (new_h - current.height())
        new_y = max(new_y, 40)
        end_geo = QRect(current.x(), new_y, self.width, new_h)

        self._anim_expand = QPropertyAnimation(self, b"geometry")
        self._anim_expand.setDuration(380)
        self._anim_expand.setStartValue(current)
        self._anim_expand.setEndValue(end_geo)
        self._anim_expand.setEasingCurve(QEasingCurve.OutCubic)
        self._anim_expand.finished.connect(lambda: self.setFixedHeight(new_h))
        self._anim_expand.start()

    def collapse(self):
        if not self.expanded:
            return
        self.expanded = False
        self.expand_btn.setText("Подробнее")
        self.detail_area.setVisible(False)
        self.preview_label.setVisible(True)

        current = self.geometry()
        new_h = self.compact_height
        new_y = current.y() + (current.height() - new_h)
        end_geo = QRect(current.x(), new_y, self.width, new_h)

        self._anim_collapse = QPropertyAnimation(self, b"geometry")
        self._anim_collapse.setDuration(380)
        self._anim_collapse.setStartValue(current)
        self._anim_collapse.setEndValue(end_geo)
        self._anim_collapse.setEasingCurve(QEasingCurve.OutCubic)
        self._anim_collapse.finished.connect(self._collapse_finished)
        self._anim_collapse.start()

    def _collapse_finished(self):
        self.setFixedHeight(self.compact_height)
        self.auto_close.start(16000)

    def close_animation(self):
        self.auto_close.stop()

        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(260)
        fade.setStartValue(self.windowOpacity())
        fade.setEndValue(0.0)

        slide = QPropertyAnimation(self, b"pos")
        slide.setDuration(260)
        slide.setStartValue(self.pos())
        slide.setEndValue(QPoint(self.pos().x(), self.pos().y() + 60))
        slide.setEasingCurve(QEasingCurve.InCubic)

        self._anim_close = QParallelAnimationGroup()
        self._anim_close.addAnimation(fade)
        self._anim_close.addAnimation(slide)
        self._anim_close.finished.connect(self.close)
        self._anim_close.start()


# ──────────────────────────────────────────────────────
# ПРИЛОЖЕНИЕ
# ──────────────────────────────────────────────────────
class TrayApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.storage = NewsStorage(NEWS_FILE)
        self.last_hash = None
        self.current_toast = None
        self.notifications_enabled = True

        self.main_window = MainWindow(self.storage)
        # Не скрываем главное окно при запуске, пусть пользователь сам решит
        # self.main_window.hide()  # раскомментировать, если нужно стартовать свёрнуто
        self.main_window.show()

        self.setup_tray()

        self.check_timer = QTimer()
        self.check_timer.timeout.connect(self.check_news)
        self.check_timer.start(2500)

        QTimer.singleShot(1200, self.show_startup_toast)

    def setup_tray(self):
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor("#2288dd"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 48, 48)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 26, QFont.Bold))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, "N")
        painter.end()

        self.tray = QSystemTrayIcon(QIcon(pixmap), self)
        self.tray.setToolTip("Telegram News")

        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background: {Theme.CARD};
                color: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                padding: 6px;
            }}
            QMenu::item {{ padding: 8px 28px 8px 16px; border-radius: 6px; }}
            QMenu::item:selected {{ background: {Theme.CARD_ACTIVE}; }}
        """)

        show_action = QAction("Открыть", self)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)

        self.notify_action = QAction("Оповещения", self)
        self.notify_action.setCheckable(True)
        self.notify_action.setChecked(True)
        self.notify_action.triggered.connect(self.toggle_notifications)
        menu.addAction(self.notify_action)

        menu.addSeparator()
        exit_act = QAction("Выход", self)
        exit_act.triggered.connect(self.quit_app)
        menu.addAction(exit_act)

        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.activated.connect(self.on_tray_activated)

    def show_window(self):
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.main_window.loadData()

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.show_window()

    def toggle_notifications(self, checked):
        self.notifications_enabled = checked

    def check_news(self):
        self.storage.load()
        h = self.storage.checksum()
        if self.last_hash is None:
            self.last_hash = h
            return
        if h != self.last_hash and self.storage.news:
            self.last_hash = h
            if self.notifications_enabled:
                last = self.storage.news[0]
                self.show_toast(last.channel, last.text)
            self.main_window.loadData()

    def show_toast(self, channel: str, message: str):
        if self.current_toast:
            self.current_toast.close_animation()
        self.current_toast = ToastNotification(channel, message)

    def show_startup_toast(self):
        self.storage.load()
        if self.storage.news and self.notifications_enabled:
            last = self.storage.news[0]
            self.show_toast(last.channel, last.text)

    def quit_app(self):
        if self.current_toast:
            self.current_toast.close()
        self.tray.hide()
        sys.exit(0)


if __name__ == "__main__":
    app = TrayApp(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    sys.exit(app.exec_())