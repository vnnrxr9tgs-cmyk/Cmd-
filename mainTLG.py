import sys
import os
import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Set, Optional
from collections import defaultdict
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

import traceback

def excepthook(exc_type, exc_value, exc_tb):
    traceback.print_exception(exc_type, exc_value, exc_tb)
    sys.__excepthook__(exc_type, exc_value, exc_tb)

sys.excepthook = excepthook

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SETTINGS_DIR = os.path.join(BASE_DIR, "settings")
SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")

READ_STATE_FILE = os.path.join(SETTINGS_DIR, "read_state.json")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.xml")
SOUND_FILE = os.path.join(SOUNDS_DIR, "1.mp3")

SIDEBAR_WIDTH = 500
CARD_RADIUS = 12
FONT_SIZE_TITLE = 13
FONT_SIZE_CHANNEL = 11
FONT_SIZE_SMALL = 9
CHANNEL_HEIGHT = 120

class Theme:
    WINDOW = "#17212b"
    SIDEBAR = "#17212b"
    HEADER = "#17212b"
    CARD = "#1a2533"
    CARD_HOVER = "#223041"
    CARD_ACTIVE = "#2a3b4f"
    CARD_UNREAD = "#182331"
    NEWS_CARD = "#232e3c"
    NEWS_CARD_HOVER = "#2b3744"
    NEWS_CARD_GRAD_TOP = "#3a4553"  # светлый сине-серый
    NEWS_CARD_GRAD_BOTTOM = "#232e3c"   # тёмный сине-серый
    BORDER = "#0e1621"
    TEXT = "#e4e8ee"
    SUBTEXT = "#8b9aab"
    BLUE = "#5288c1"
    GREEN = "#4eae5c"
    RED = "#e64a4a"
    UNREAD_BADGE = "#5288c1"
    AVATAR_COLORS = [
        "#e17076", "#7bc862", "#65aadd", "#a695e7", "#ee7aae",
        "#6ec9cb", "#faa774", "#9aa66b", "#d09b6a", "#b8869a"
    ]
    TOAST_GRAD_TOP = "#2b3744"
    TOAST_GRAD_BOTTOM = "#17212b"

def font_s(size=10, bold=False):
    f = QFont("Segoe UI", size)
    f.setBold(bold)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 0.2)  # лёгкое разрежение (необязательно)
    return f

def human_time(text):
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.strftime("%H:%M")
        except:
            continue
    return text[:5] if len(text) >= 5 else text

def truncate(text, max_len=80):
    return text[:max_len] + "…" if len(text) > max_len else text

def draw_avatar(painter: QPainter, rect: QRect, text: str):
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    color_index = int(hashlib.md5(text.encode()).hexdigest(), 16) % len(Theme.AVATAR_COLORS)
    painter.setBrush(QColor(Theme.AVATAR_COLORS[color_index]))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(rect)
    words = text.split()
    if len(words) == 1:
        letters = words[0][:2].upper()
    else:
        letters = (words[0][0] + words[1][0]).upper()
    painter.setPen(Qt.white)
    font = font_s(int(rect.height() * 0.30), True)
    painter.setFont(font)
    painter.drawText(rect, Qt.AlignCenter, letters)
    painter.restore()

class Settings:
    def __init__(self, filename=SETTINGS_FILE):
        self.filename = filename
        self.enabled_channels = {}
        self.font_size = 14
        self.sound_enabled = True
        self.notifications_enabled = True
        self.initialized = False
        self.data_dir = os.path.join(BASE_DIR, "data")
        self.load()

    def load(self):
        if not os.path.exists(self.filename):
            self.enabled_channels = {}
            return
        try:
            tree = ET.parse(self.filename)
            root = tree.getroot()
            self.enabled_channels = {}
            for ch in root.findall("channel"):
                name = ch.get("name")
                show = ch.find("show").text.lower() == "true"
                notify = ch.find("notify").text.lower() == "true"
                sound_elem = ch.find("sound")
                sound = True if sound_elem is None else sound_elem.text.lower() == "true"
                self.enabled_channels[name] = {"show": show, "notify": notify, "sound": sound}
            font_elem = root.find("font_size")
            if font_elem is not None and font_elem.text:
                self.font_size = int(font_elem.text)
            sound_elem = root.find("sound_enabled")
            if sound_elem is not None and sound_elem.text:
                self.sound_enabled = sound_elem.text.lower() == "true"
            notifications_elem = root.find("notifications_enabled")
            if notifications_elem is not None and notifications_elem.text:
                self.notifications_enabled = notifications_elem.text.lower() == "true"
            init_elem = root.find("initialized")
            if init_elem is not None and init_elem.text:
                self.initialized = init_elem.text.lower() == "true"
            data_dir_elem = root.find("data_dir")
            if data_dir_elem is not None and data_dir_elem.text:
                self.data_dir = data_dir_elem.text
        except:
            self.enabled_channels = {}

    def save(self):
        root = ET.Element("settings")
        for name, data in self.enabled_channels.items():
            ch = ET.SubElement(root, "channel", name=name)
            show = ET.SubElement(ch, "show")
            show.text = str(data["show"]).lower()
            notify = ET.SubElement(ch, "notify")
            notify.text = str(data["notify"]).lower()
            sound = ET.SubElement(ch, "sound")
            sound.text = str(data.get("sound", True)).lower()
        font_elem = ET.SubElement(root, "font_size")
        font_elem.text = str(self.font_size)
        sound_elem = ET.SubElement(root, "sound_enabled")
        sound_elem.text = str(self.sound_enabled).lower()
        notifications_elem = ET.SubElement(root, "notifications_enabled")
        notifications_elem.text = str(self.notifications_enabled).lower()
        init_elem = ET.SubElement(root, "initialized")
        init_elem.text = str(self.initialized).lower()
        data_dir_elem = ET.SubElement(root, "data_dir")
        data_dir_elem.text = self.data_dir
        tree = ET.ElementTree(root)
        tree.write(self.filename, encoding="utf-8", xml_declaration=True)

    def is_show(self, channel_name):
        return self.enabled_channels.get(channel_name, {}).get("show", True)

    def is_notify(self, channel_name):
        return self.enabled_channels.get(channel_name, {}).get("notify", True)

    def is_sound(self, channel_name):
        return self.enabled_channels.get(channel_name, {}).get("sound", True)

    def set_channel(self, name, show, notify, sound=True):
        self.enabled_channels[name] = {"show": show, "notify": notify, "sound": sound}

@dataclass
class News:
    date: str
    channel: str
    text: str
    title: str = ""

    @property
    def dt(self):
        if not self.date:
            return datetime.min
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M"):
            try:
                return datetime.strptime(self.date, fmt)
            except:
                continue
        return datetime.min

    def checksum(self):
        return hashlib.md5(f"{self.date}{self.channel}{self.title}{self.text}".encode()).hexdigest()

@dataclass
class Channel:
    name: str
    last_news: str
    last_date: str
    count: int
    unread_count: int = 0
    notify_enabled: bool = True
    sound_enabled: bool = True

class ChannelListModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._channels = []
        self._selected_index = -1

    def rowCount(self, parent=QModelIndex()):
        return len(self._channels)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._channels)):
            return None
        channel = self._channels[index.row()]
        if role == Qt.DisplayRole:
            return channel.name
        elif role == Qt.UserRole:
            return channel
        elif role == Qt.UserRole + 1:
            return index.row() == self._selected_index
        elif role == Qt.UserRole + 2:
            return channel.unread_count
        return None

    def setChannels(self, channels: List[Channel]):
        self.beginResetModel()
        self._channels = channels
        self._selected_index = -1
        self.endResetModel()

    def channel_at(self, row):
        if 0 <= row < len(self._channels):
            return self._channels[row]
        return None

    def setSelected(self, row):
        old_row = self._selected_index
        self._selected_index = row
        if old_row >= 0 and old_row < len(self._channels):
            self.dataChanged.emit(self.index(old_row), self.index(old_row), [Qt.UserRole + 1])
        if row >= 0 and row < len(self._channels):
            self.dataChanged.emit(self.index(row), self.index(row), [Qt.UserRole + 1])

class NewsListModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._news = []

    def rowCount(self, parent=QModelIndex()):
        return len(self._news)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._news)):
            return None
        news = self._news[index.row()]
        if role == Qt.DisplayRole:
            return news.title if news.title else news.text
        elif role == Qt.UserRole:
            return news
        return None

    def setNews(self, news_list: List[News]):
        self.beginResetModel()
        self._news = news_list
        self.endResetModel()

class ChannelDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        channel = index.data(Qt.UserRole)
        if not channel:
            return

        is_selected = index.data(Qt.UserRole + 1)
        is_hover = option.state & QStyle.State_MouseOver
        unread = channel.unread_count

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect.adjusted(4, 4, -4, -4)

        if is_selected:
            bg_color = QColor(Theme.CARD_ACTIVE)
        elif is_hover:
            bg_color = QColor(Theme.CARD_HOVER)
        elif unread > 0:
            bg_color = QColor(Theme.CARD_UNREAD)
        else:
            bg_color = QColor(Theme.CARD)

        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, CARD_RADIUS, CARD_RADIUS)
        painter.restore()

        avatar_left = rect.left() + 56
        avatar_rect = QRect(avatar_left, rect.top() + (rect.height() - 42) // 2, 42, 42)
        draw_avatar(painter, avatar_rect, channel.name)

        icon_x = rect.left() + 14
        icon_y_top = rect.top() + 16
        icon_y_bottom = rect.bottom() - 36
        font_icon = font_s(10)

        notify_icon = "🔔" if channel.notify_enabled else "🔕"
        painter.setPen(QColor(Theme.TEXT if channel.notify_enabled else Theme.SUBTEXT))
        painter.setFont(font_icon)
        painter.drawText(QRect(icon_x, icon_y_top, 24, 24), Qt.AlignCenter, notify_icon)

        sound_icon = "🔊" if channel.sound_enabled else "🔇"
        painter.setPen(QColor(Theme.TEXT if channel.sound_enabled else Theme.SUBTEXT))
        painter.drawText(QRect(icon_x, icon_y_bottom, 24, 24), Qt.AlignCenter, sound_icon)

        text_rect = QRect(avatar_rect.right() + 12, rect.top() + 8,
                          rect.width() - avatar_rect.width() - 60, rect.height() - 16)
        painter.setPen(QColor(Theme.TEXT))
        painter.setFont(font_s(FONT_SIZE_CHANNEL, True))

        time_rect = QRect(rect.right() - 70, rect.top() + 8, 60, 16)
        name_rect = QRect(text_rect.left(), text_rect.top(),
                          time_rect.left() - text_rect.left() - 8, 20)
        elided_name = painter.fontMetrics().elidedText(channel.name, Qt.ElideRight, name_rect.width())
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_name)

        painter.setPen(QColor(Theme.SUBTEXT))
        painter.setFont(font_s(FONT_SIZE_SMALL))
        preview_rect = QRect(text_rect.left(), name_rect.bottom() + 4, text_rect.width(), 50)

        fm = painter.fontMetrics()
        lines = []
        for line in channel.last_news.split('\n'):
            elided = fm.elidedText(line, Qt.ElideRight, preview_rect.width())
            lines.append(elided)

        line_height = fm.height()
        max_lines = preview_rect.height() // line_height

        if len(lines) > max_lines:
            lines = lines[:max_lines - 1]
            last_line = lines[-1] if lines else ""
            if not last_line.endswith("…"):
                last_line = fm.elidedText(last_line, Qt.ElideRight, preview_rect.width() - fm.width("…"))
                if not last_line:
                    last_line = "…"
                else:
                    last_line += "…"
            lines[-1] = last_line

        final_text = "\n".join(lines)
        painter.drawText(preview_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, final_text)

        painter.setPen(QColor(Theme.SUBTEXT))
        painter.setFont(font_s(8))
        painter.drawText(time_rect, Qt.AlignRight | Qt.AlignVCenter, human_time(channel.last_date))

        if unread > 0:
            # Вертикальная полоска слева для выделения канала
            indicator_rect = QRect(rect.left() + 4, rect.top() + 15, 4, rect.height() - 30)
            painter.setBrush(QColor(Theme.BLUE))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(indicator_rect, 2, 2)

            badge_rect = QRect(rect.right() - 24, rect.bottom() - 24, 20, 20)
            painter.setBrush(QColor(Theme.UNREAD_BADGE))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(badge_rect)
            painter.setPen(Qt.white)
            painter.setFont(font_s(9, True))
            painter.drawText(badge_rect, Qt.AlignCenter, str(unread))

    def sizeHint(self, option, index):
        return QSize(SIDEBAR_WIDTH - 28, CHANNEL_HEIGHT)

class NewsDelegate(QStyledItemDelegate):
    BOTTOM_MARGIN = 10

    def __init__(self, font_size=14):
        super().__init__()
        self.font_size = font_size

    def paint(self, painter, option, index):
        news = index.data(Qt.UserRole)
        if not news:
            return

        is_hover = option.state & QStyle.State_MouseOver

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect.adjusted(6, 6, -6, -6)

        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if is_hover:
            gradient.setColorAt(0, QColor(Theme.NEWS_CARD_HOVER))
            gradient.setColorAt(1, QColor(Theme.NEWS_CARD))
        else:
            gradient.setColorAt(0, QColor(Theme.NEWS_CARD_GRAD_TOP))
            gradient.setColorAt(1, QColor(Theme.NEWS_CARD_GRAD_BOTTOM))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, CARD_RADIUS, CARD_RADIUS)
        painter.restore()

        top_rect = QRect(rect.left() + 16, rect.top() + 12, rect.width() - 32, 34)
        avatar_rect = QRect(top_rect.left(), top_rect.top(), 34, 34)
        draw_avatar(painter, avatar_rect, news.channel)

        channel_rect = QRect(avatar_rect.right() + 10, top_rect.top() + 8, 200, 20)
        painter.setPen(QColor(Theme.TEXT))
        painter.setFont(font_s(FONT_SIZE_CHANNEL, True))
        painter.drawText(channel_rect, Qt.AlignLeft | Qt.AlignVCenter, news.channel)

        time_rect = QRect(top_rect.right() - 100, top_rect.top() + 8, 90, 20)
        painter.setPen(QColor(Theme.SUBTEXT))
        painter.setFont(font_s(FONT_SIZE_SMALL))
        painter.drawText(time_rect, Qt.AlignRight | Qt.AlignVCenter, human_time(news.date))

        if news.title:
            title_rect = QRect(rect.left() + 16, top_rect.bottom() + 18,
                               rect.width() - 32, 30)
            painter.setPen(QColor(Theme.TEXT))
            painter.setFont(font_s(self.font_size + 2, True))
            elided_title = painter.fontMetrics().elidedText(news.title, Qt.ElideRight, title_rect.width())
            painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignTop, elided_title)
            body_top = title_rect.bottom() + 26
        else:
            body_top = top_rect.bottom() + 8

        date_height = 18
        gap_before_date = 2
        date_y = rect.bottom() - self.BOTTOM_MARGIN - date_height

        body_rect = QRect(rect.left() + 16, body_top,
                          rect.width() - 32,
                          max(0, date_y - gap_before_date - body_top))
        painter.setPen(QColor(Theme.TEXT))
        painter.setFont(font_s(self.font_size))
        painter.drawText(body_rect, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, news.text)

        date_rect = QRect(rect.left() + 16, date_y, rect.width() - 32, date_height)
        painter.setPen(QColor(Theme.SUBTEXT))
        painter.setFont(font_s(FONT_SIZE_SMALL - 1))
        painter.drawText(date_rect, Qt.AlignLeft | Qt.AlignVCenter, news.date)

    def sizeHint(self, option, index):
        news = index.data(Qt.UserRole)
        if not news:
            return QSize(option.rect.width(), 120)

        font = font_s(self.font_size)
        metrics = QFontMetrics(font)
        body_width = option.rect.width() - 32

        body_height = metrics.boundingRect(QRect(0, 0, body_width, 10000),
                                           Qt.TextWordWrap | Qt.AlignLeft,
                                           news.text).height()
        title_height = 0
        if news.title:
            title_font = font_s(self.font_size + 2, True)
            title_metrics = QFontMetrics(title_font)
            title_height = title_metrics.boundingRect(QRect(0, 0, body_width, 100),
                                                      Qt.TextWrapAnywhere | Qt.AlignLeft,
                                                      news.title).height()

        top_margin = 12
        header_height = 34
        gap_after_header = 18
        gap_after_title = 26 if news.title else 0
        date_height = 20
        gap_before_date = 28
        bottom_margin = self.BOTTOM_MARGIN

        total_height = (top_margin + header_height + gap_after_header +
                        title_height + gap_after_title +
                        body_height + gap_before_date + date_height + bottom_margin)
        total_height += 8

        return QSize(option.rect.width(), max(100, int(total_height)))

class Sidebar(QFrame):
    channelSelected = pyqtSignal(object)
    settingsChanged = pyqtSignal()

    def __init__(self, storage):
        super().__init__()
        self.storage = storage
        self.setFixedWidth(SIDEBAR_WIDTH)
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                           stop:0 {Theme.SIDEBAR}, stop:1 {Theme.WINDOW});
                border-radius: 16px;
                border: none;
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

        self.channel_list = QListView()
        self.channel_list.setFrameShape(QFrame.NoFrame)
        self.channel_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.channel_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.channel_list.setMouseTracking(True)
        self.channel_list.viewport().setAttribute(Qt.WA_Hover, True)
        self.channel_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.channel_list.verticalScrollBar().setSingleStep(15)
        self.channel_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.channel_list.customContextMenuRequested.connect(self.show_channel_menu)
        self.channel_list.setStyleSheet(f"""
            QListView {{
                background: transparent;
                border: none;
            }}
            QListView::item {{
                background: transparent;
            }}
            QListView::item:hover {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                width: 12px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #5a6275, stop:1 #454b57);
                border-radius: 6px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #6f7b8c, stop:1 #5a6275);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

        self.channel_model = ChannelListModel()
        self.channel_delegate = ChannelDelegate()
        self.channel_list.setModel(self.channel_model)
        self.channel_list.setItemDelegate(self.channel_delegate)
        self.channel_list.clicked.connect(self.on_channel_clicked)
        layout.addWidget(self.channel_list)

        self._selected_index = -1

    def setChannels(self, channels: List[Channel]):
        self.channel_model.setChannels(channels)
        self._selected_index = -1

    def selectNoChannel(self):
        self.channel_model.setSelected(-1)
        self._selected_index = -1

    def on_channel_clicked(self, index):
        channel = index.data(Qt.UserRole)
        if channel:
            self.channel_model.setSelected(index.row())
            self._selected_index = index.row()
            self.channelSelected.emit(channel)

    def show_channel_menu(self, pos):
        index = self.channel_list.indexAt(pos)
        if not index.isValid():
            return
        channel = index.data(Qt.UserRole)
        if not channel:
            return

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

        show_action = QAction("Показывать", self)
        show_action.setCheckable(True)
        show_action.setChecked(self.storage.settings.is_show(channel.name))
        show_action.triggered.connect(lambda checked, ch=channel: self.toggle_show(ch, checked))

        notify_action = QAction("Трей уведомление", self)
        notify_action.setCheckable(True)
        notify_action.setChecked(channel.notify_enabled)
        notify_action.triggered.connect(lambda checked, ch=channel: self.toggle_notify(ch, checked))

        sound_action = QAction("Звук", self)
        sound_action.setCheckable(True)
        sound_action.setChecked(channel.sound_enabled)
        sound_action.triggered.connect(lambda checked, ch=channel: self.toggle_sound(ch, checked))

        menu.addAction(show_action)
        menu.addAction(notify_action)
        menu.addAction(sound_action)
        menu.exec_(self.channel_list.viewport().mapToGlobal(pos))

    def toggle_show(self, channel, checked):
        self.storage.settings.set_channel(
            channel.name,
            checked,
            channel.notify_enabled,
            channel.sound_enabled
        )
        self.storage.settings.save()
        self.settingsChanged.emit()

    def toggle_notify(self, channel, checked):
        self.storage.settings.set_channel(
            channel.name,
            self.storage.settings.is_show(channel.name),
            checked,
            channel.sound_enabled
        )
        self.storage.settings.save()
        self.settingsChanged.emit()

    def toggle_sound(self, channel, checked):
        self.storage.settings.set_channel(
            channel.name,
            self.storage.settings.is_show(channel.name),
            channel.notify_enabled,
            checked
        )
        self.storage.settings.save()
        self.settingsChanged.emit()

class MainContent(QWidget):
    refreshRequested = pyqtSignal()
    searchRequested = pyqtSignal(str)
    settingsRequested = pyqtSignal()
    soundToggleRequested = pyqtSignal()

    def __init__(self, font_size=14, sound_enabled=True):
        super().__init__()
        self.setStyleSheet(f"background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

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

        self.sound_btn = QPushButton()
        self.sound_btn.setFixedSize(36, 36)
        self.sound_btn.setCursor(Qt.PointingHandCursor)
        self.sound_btn.setFont(font_s(16))
        self.sound_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.CARD};
                border: none;
                border-radius: 18px;
                color: white;
            }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
            QPushButton:pressed {{ background: {Theme.BLUE}; }}
        """)
        self.sound_btn.clicked.connect(self.soundToggleRequested.emit)
        header_layout.addWidget(self.sound_btn)
        self.set_sound_icon(sound_enabled)

        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(36, 36)
        settings_btn.setCursor(Qt.PointingHandCursor)
        settings_btn.setFont(font_s(16))
        settings_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.CARD};
                border: none;
                border-radius: 18px;
                color: white;
            }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
            QPushButton:pressed {{ background: {Theme.BLUE}; }}
        """)
        settings_btn.clicked.connect(self.settingsRequested)
        header_layout.addWidget(settings_btn)

        layout.addWidget(self.header)

        self.news_list = QListView()
        self.news_list.setFrameShape(QFrame.NoFrame)
        self.news_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.news_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.news_list.setMouseTracking(True)
        self.news_list.viewport().setAttribute(Qt.WA_Hover, True)
        self.news_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.news_list.verticalScrollBar().setSingleStep(15)
        self.news_list.setStyleSheet(f"""
            QListView {{
                background: transparent;
                border: none;
            }}
            QListView::item {{
                background: transparent;
            }}
            QListView::item:hover {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                width: 12px;
                background: transparent;
            }}
            QScrollBar::handle:vertical {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #5a6275, stop:1 #454b57);
                border-radius: 6px;
                min-height: 40px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                           stop:0 #6f7b8c, stop:1 #5a6275);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

        self.news_model = NewsListModel()
        self.news_delegate = NewsDelegate(font_size)
        self.news_list.setModel(self.news_model)
        self.news_list.setItemDelegate(self.news_delegate)
        layout.addWidget(self.news_list)

        self.news_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.news_list.customContextMenuRequested.connect(self.show_news_menu)

        self.placeholder = QLabel("Выберите канал для чтения")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setFont(font_s(16, True))
        self.placeholder.setStyleSheet(f"color: {Theme.SUBTEXT}; background: transparent;")
        self.placeholder.hide()
        layout.addWidget(self.placeholder)

        self.font_size = font_size

    def show_news_menu(self, pos):
        index = self.news_list.indexAt(pos)
        if not index.isValid():
            return

        rect = self.news_list.visualRect(index).adjusted(6, 6, -6, -6)
        if not rect.contains(pos):
            return

        news = index.data(Qt.UserRole)
        if not news:
            return

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
        copy_action = QAction("Скопировать новость", self)
        copy_action.triggered.connect(lambda: self.copy_news(news))
        menu.addAction(copy_action)
        menu.exec_(self.news_list.viewport().mapToGlobal(pos))

    def copy_news(self, news):
        text = f"{news.channel}\n{news.title}\n{news.text}"
        QApplication.clipboard().setText(text)

    def set_sound_icon(self, enabled):
        if enabled:
            self.sound_btn.setText("🔊")
            self.sound_btn.setToolTip("Выключить звук")
        else:
            self.sound_btn.setText("🔇")
            self.sound_btn.setToolTip("Включить звук")

    def resizeEvent(self, event):
        if hasattr(self, 'news_list'):
            self.news_list.scheduleDelayedItemsLayout()
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor("#1e2a36"))
        gradient.setColorAt(1, QColor("#1c2733"))
        painter.fillRect(self.rect(), gradient)

    def showNews(self, news_list: List[News], scroll_to_top=True):
        self.news_list.show()
        self.placeholder.hide()
        if scroll_to_top:
            self.news_model.setNews(news_list)
            QTimer.singleShot(0, lambda: self.news_list.scrollToTop())
        else:
            scrollbar = self.news_list.verticalScrollBar()
            pos = scrollbar.value()
            self.news_model.setNews(news_list)
            QTimer.singleShot(0, lambda: scrollbar.setValue(min(pos, scrollbar.maximum())))

    def showPlaceholder(self):
        self.news_list.hide()
        self.placeholder.show()

    def setChannelInfo(self, name: str, count: int):
        self.channel_title.setText(name)
        self.count_label.setText(str(count))

    def set_font_size(self, size):
        self.font_size = size
        self.news_delegate.font_size = size
        self.news_list.scheduleDelayedItemsLayout()
        self.news_list.viewport().update()

class MainWindow(QMainWindow):
    def __init__(self, storage, tray_app=None):
        super().__init__()
        self.storage = storage
        self.tray_app = tray_app
        self.current_channel = None
        self.selected_channel_name = None
        self._first_show = True

        self.setWindowTitle("Telegram News")
        icon_path = os.path.join(BASE_DIR, "sounds/11.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setGeometry(120, 80, 1180, 740)
        self.setMinimumSize(920, 620)
        self.setStyleSheet(f"background: {Theme.WINDOW};")

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.sidebar = Sidebar(storage)
        layout.addWidget(self.sidebar)

        self.content = MainContent(self.storage.settings.font_size,
                                   self.storage.settings.sound_enabled)
        layout.addWidget(self.content)

        self.sidebar.channelSelected.connect(self.onChannelSelected)
        self.sidebar.settingsChanged.connect(self.on_settings_changed)
        self.content.searchRequested.connect(self.onSearch)
        self.content.refreshRequested.connect(self.request_reload)
        self.content.settingsRequested.connect(self.open_settings)
        self.content.soundToggleRequested.connect(self.toggle_sound)

        self.content.showPlaceholder()

    def request_reload(self):
        if self.tray_app:
            self.tray_app.start_async_reload()
        else:
            self.loadData(preserve_selection=True)

    def toggle_sound(self):
        self.storage.settings.sound_enabled = not self.storage.settings.sound_enabled
        self.storage.settings.save()
        self.content.set_sound_icon(self.storage.settings.sound_enabled)
        if hasattr(self, 'tray_app') and self.tray_app:
            self.tray_app.sound_action.setChecked(self.storage.settings.sound_enabled)
            self.tray_app.update_tray_icon()

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
            self._show_anim = anim
        super().showEvent(event)

    def loadData(self, preserve_selection=False):
        try:
            self.storage.load()
        except Exception:
            self.sidebar.setChannels([])
            self.content.showPlaceholder()
            return
        self.refresh_ui(preserve_selection)

    def refresh_ui(self, preserve_selection=False):
        self.sidebar.setChannels(self.storage.channels)

        if preserve_selection and self.selected_channel_name:
            news = self.storage.by_channel(self.selected_channel_name)
            if not news:
                self.selected_channel_name = None
                self.current_channel = None
                self.content.showPlaceholder()
                self.sidebar.selectNoChannel()
                return
            self.content.showNews(news, scroll_to_top=False)
            self.content.setChannelInfo(self.selected_channel_name, len(news))
            # Восстанавливаем выделение в списке каналов
            idx = next((i for i, c in enumerate(self.storage.channels) if c.name == self.selected_channel_name), -1)
            if idx >= 0:
                self.sidebar.channel_model.setSelected(idx)
            return

        if self.selected_channel_name:
            for ch in self.storage.channels:
                if ch.name == self.selected_channel_name:
                    idx = self.storage.channels.index(ch)
                    self.sidebar.channel_model.setSelected(idx)
                    self.onChannelSelected(ch)
                    return
            self.selected_channel_name = None
            self.current_channel = None

        self.content.showPlaceholder()
        self.sidebar.selectNoChannel()

    def on_settings_changed(self):
        self.storage.load()
        self.refresh_ui(preserve_selection=True)
        if self.tray_app:
            self.tray_app.update_tray_icon()

    def onChannelSelected(self, channel: Channel):
        self.storage.mark_channel_read(channel.name)
        self.storage.load()
        self.sidebar.setChannels(self.storage.channels)

        updated_channel = None
        for ch in self.storage.channels:
            if ch.name == channel.name:
                updated_channel = ch
                break

        if updated_channel is None:
            self.current_channel = None
            self.selected_channel_name = None
            self.content.showPlaceholder()
            self.sidebar.selectNoChannel()
            return

        self.current_channel = updated_channel
        self.selected_channel_name = updated_channel.name

        news = self.storage.by_channel(updated_channel.name)
        self.content.showNews(news)
        self.content.setChannelInfo(updated_channel.name, len(news))

        idx = next((i for i, c in enumerate(self.storage.channels) if c.name == updated_channel.name), -1)
        if idx >= 0:
            self.sidebar.channel_model.setSelected(idx)

    def onSearch(self, text: str):
        if not text.strip():
            if self.current_channel:
                self.onChannelSelected(self.current_channel)
            else:
                self.loadData()
            return

        news = self.storage.search(text, self.current_channel.name if self.current_channel else None)
        self.content.showNews(news)
        self.content.setChannelInfo("Результаты поиска", len(news))

    def open_settings(self):
        all_channels = self.storage.get_all_channel_names()
        dlg = SettingsDialog(all_channels, self.storage.settings, self)
        if dlg.exec_() == QDialog.Accepted:
            new_path = dlg.data_dir_edit.text().strip()
            if not os.path.isdir(new_path):
                QMessageBox.warning(self, "Предупреждение", "Выбранная папка не существует.\nНастройки не изменены.")
                return
            self.storage.settings.data_dir = new_path
            self.storage.settings.save()
            self.storage.data_dir = new_path
            self.storage.load()
            self.content.set_font_size(self.storage.settings.font_size)
            self.content.set_sound_icon(self.storage.settings.sound_enabled)
            self.refresh_ui()
            if self.tray_app:
                self.tray_app.update_tray_icon()
                self.tray_app.sound_action.setChecked(self.storage.settings.sound_enabled)
                self.tray_app.notify_action.setChecked(self.storage.settings.notifications_enabled)

class NewsStorage:
    def __init__(self, data_dir: str, settings: Optional[Settings] = None):
        self.data_dir = data_dir
        self.read_state_file = READ_STATE_FILE
        self.settings = settings if settings is not None else Settings()
        self.news: List[News] = []
        self.channels: List[Channel] = []
        self.last_read_by_channel: Dict[str, str] = {}
        self._load_read_state()

    def mark_all_current_as_read(self):
        if not os.path.isdir(self.data_dir):
            return
        for channel in self.get_all_channel_names():
            news_list = self.load_channel_news(channel)
            if news_list:
                latest_date = max(n.date for n in news_list)
                self.last_read_by_channel[channel] = latest_date
        self._save_read_state()
        self.news.clear()
        self.channels.clear()

    def channel_file_path(self, channel_name):
        safe_name = channel_name.replace("/", "_").replace("\\", "_")
        return os.path.join(self.data_dir, f"{safe_name}.json")

    def load_channel_news(self, channel_name):
        path = self.channel_file_path(channel_name)
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            news_list = []
            for item in data:
                date = item.get("dateTime") or item.get("date", "")
                text = item.get("text") or item.get("body", "")
                if not text:
                    continue
                news_list.append(News(date=date, channel=channel_name, text=text))
            return news_list
        except Exception as e:
            print(f"Ошибка загрузки {path}: {e}")
            return []

    def save_channel_news(self, channel_name, news_list):
        path = self.channel_file_path(channel_name)
        data = [{"dateTime": n.date, "text": n.text} for n in news_list]
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except:
            pass

    def get_all_channel_names(self):
        if not os.path.isdir(self.data_dir):
            return []
        names = set()
        try:
            for filename in os.listdir(self.data_dir):
                if filename.endswith(".json"):
                    names.add(filename[:-5])
        except:
            pass
        return sorted(names)

    def load(self):
        self.news, self.channels, self.last_read_by_channel = self.load_news_data(
            self.data_dir, self.settings, self.last_read_by_channel
        )

    @staticmethod
    def load_news_data(data_dir, settings, last_read_by_channel):
        if not os.path.isdir(data_dir):
            return [], [], {}

        all_channel_names = NewsStorage._get_all_channel_names(data_dir)
        news = []
        last_read = dict(last_read_by_channel)

        for channel in all_channel_names:
            if not settings.is_show(channel):
                continue
            news_list = NewsStorage._load_channel_news(data_dir, channel)
            news.extend(news_list)
            if channel not in last_read:
                last_read[channel] = datetime.min.strftime("%Y-%m-%dT%H:%M:%S")

        news.sort(key=lambda x: x.dt, reverse=True)

        cache = {}
        for item in news:
            if item.channel not in cache:
                cache[item.channel] = {"last": item.text or "", "date": item.date, "count": 0}
            cache[item.channel]["count"] += 1

        channels = []
        for name, data in cache.items():
            channel_news = [n for n in news if n.channel == name]
            unread = NewsStorage._unread_count_for_channel(name, channel_news, last_read)
            channels.append(Channel(
                name=name,
                last_news=data["last"],
                last_date=data["date"],
                count=data["count"],
                unread_count=unread,
                notify_enabled=settings.is_notify(name),
                sound_enabled=settings.is_sound(name)
            ))

        channels.sort(key=lambda x: x.last_date, reverse=True)
        return news, channels, last_read

    @staticmethod
    def _get_all_channel_names(data_dir):
        if not os.path.isdir(data_dir):
            return []
        names = set()
        for filename in os.listdir(data_dir):
            if filename.endswith(".json"):
                names.add(filename[:-5])
        return sorted(names)

    @staticmethod
    def _load_channel_news(data_dir, channel_name):
        safe_name = channel_name.replace("/", "_").replace("\\", "_")
        path = os.path.join(data_dir, f"{safe_name}.json")
        if not os.path.exists(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, list):
                return []
            news_list = []
            for item in data:
                date = item.get("dateTime") or item.get("date", "")
                text = item.get("text") or item.get("body", "")
                if not text:
                    continue
                news_list.append(News(date=date, channel=channel_name, text=text))
            return news_list
        except Exception:
            return []

    @staticmethod
    def _unread_count_for_channel(channel_name, channel_news, last_read_by_channel):
        if not channel_news:
            return 0
        last_read_date_str = last_read_by_channel.get(channel_name)
        if not last_read_date_str:
            return 0
        last_read_dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M"):
            try:
                last_read_dt = datetime.strptime(last_read_date_str, fmt)
                break
            except:
                continue
        if last_read_dt is None:
            return 0
        return sum(1 for n in channel_news if n.dt > last_read_dt)

    def checksum(self):
        if not self.news:
            return ""
        last = self.news[0]
        return last.checksum()

    def all_news(self):
        return self.news[:]

    def by_channel(self, name):
        return [n for n in self.news if n.channel == name]

    def search(self, text, channel=None):
        text = text.lower().strip()
        data = self.news if not channel else self.by_channel(channel)
        return [n for n in data if text in n.text.lower()]

    def _load_read_state(self):
        if os.path.exists(self.read_state_file):
            try:
                with open(self.read_state_file, 'r', encoding='utf-8') as f:
                    self.last_read_by_channel = json.load(f)
            except:
                self.last_read_by_channel = {}

    def _save_read_state(self):
        try:
            os.makedirs(os.path.dirname(self.read_state_file), exist_ok=True)
            with open(self.read_state_file, 'w', encoding='utf-8') as f:
                json.dump(self.last_read_by_channel, f, ensure_ascii=False, indent=2)
        except:
            pass

    def mark_channel_read(self, channel_name: str):
        channel_news = [n for n in self.news if n.channel == channel_name]
        if channel_news:
            latest = channel_news[0]
            self.last_read_by_channel[channel_name] = latest.date
            self._save_read_state()

    def unread_count_for_channel(self, channel_name: str) -> int:
        channel_news = [n for n in self.news if n.channel == channel_name]
        if not channel_news:
            return 0
        return self._unread_count_for_channel(channel_name, channel_news, self.last_read_by_channel)

class NewsLoaderThread(QThread):
    finished_with_result = pyqtSignal(object)

    def __init__(self, data_dir, settings, last_read_by_channel):
        super().__init__()
        self.data_dir = data_dir
        self.settings = settings
        self.last_read = last_read_by_channel.copy()

    def run(self):
        try:
            news, channels, updated_last_read = NewsStorage.load_news_data(
                self.data_dir, self.settings, self.last_read
            )
            self.finished_with_result.emit((news, channels, updated_last_read))
        except Exception as e:
            print(f"Ошибка асинхронной загрузки: {e}")
            self.finished_with_result.emit(None)

class SettingsDialog(QDialog):
    def __init__(self, channels, settings, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle("Настройки каналов")
        self.setMinimumWidth(600)
        self.setMinimumHeight(450)
        self.setStyleSheet(f"background: {Theme.WINDOW}; color: {Theme.TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        title = QLabel("Настройка каналов")
        title.setFont(font_s(14, True))
        title.setStyleSheet(f"color: {Theme.TEXT};")
        layout.addWidget(title)

        data_layout = QHBoxLayout()
        data_label = QLabel("Папка с новостями:")
        data_label.setFont(font_s(11))
        data_label.setStyleSheet("color: white;")
        self.data_dir_edit = QLineEdit(settings.data_dir)
        self.data_dir_edit.setFont(font_s(11))
        self.data_dir_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {Theme.CARD};
                color: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 6px;
            }}
        """)
        self.browse_btn = QPushButton("Обзор...")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        self.browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.CARD};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                color: white;
                padding: 6px 12px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
        """)
        self.browse_btn.clicked.connect(self.browse_folder)
        data_layout.addWidget(data_label)
        data_layout.addWidget(self.data_dir_edit)
        data_layout.addWidget(self.browse_btn)
        layout.addLayout(data_layout)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Поиск каналов...")
        self.search_edit.setFont(font_s(11))
        self.search_edit.setStyleSheet(f"""
            QLineEdit {{
                background: {Theme.CARD};
                color: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 8px;
            }}
            QLineEdit:focus {{
                border: 1px solid {Theme.BLUE};
            }}
        """)
        self.search_edit.textChanged.connect(self.filter_channels)
        layout.addWidget(self.search_edit)

        select_all_btn = QPushButton("Выделить все")
        deselect_all_btn = QPushButton("Снять все")
        for btn in (select_all_btn, deselect_all_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {Theme.CARD};
                    border: 1px solid {Theme.BORDER};
                    border-radius: 6px;
                    color: white;
                    padding: 6px 12px;
                    font-size: 11px;
                }}
                QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
            """)
        select_all_btn.clicked.connect(self.select_all_channels)
        deselect_all_btn.clicked.connect(self.deselect_all_channels)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(deselect_all_btn)
        layout.addLayout(btn_row)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Канал", "Отображать", "Трей уведомление"])
        self.table.setRowCount(len(channels))
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setMinimumHeight(250)
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background: {Theme.CARD};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 8px;
            }}
            QTableWidget::item {{
                padding: 6px 10px;
            }}
            QHeaderView::section {{
                background: {Theme.CARD};
                color: {Theme.SUBTEXT};
                padding: 6px 10px;
                border: none;
                border-bottom: 1px solid {Theme.BORDER};
                font-weight: bold;
            }}
        """)

        self.checkboxes_show = {}
        self.checkboxes_notify = {}
        for row, channel in enumerate(channels):
            item_name = QTableWidgetItem(channel)
            item_name.setForeground(QColor(Theme.TEXT))
            item_name.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.table.setItem(row, 0, item_name)

            cb_show = QCheckBox()
            cb_show.setChecked(settings.is_show(channel))
            cb_show.setStyleSheet("background: transparent;")
            container_show = QWidget()
            lay_show = QHBoxLayout(container_show)
            lay_show.addWidget(cb_show)
            lay_show.setAlignment(Qt.AlignCenter)
            lay_show.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 1, container_show)
            self.checkboxes_show[channel] = cb_show

            cb_notify = QCheckBox()
            cb_notify.setChecked(settings.is_notify(channel))
            cb_notify.setStyleSheet("background: transparent;")
            container_notify = QWidget()
            lay_notify = QHBoxLayout(container_notify)
            lay_notify.addWidget(cb_notify)
            lay_notify.setAlignment(Qt.AlignCenter)
            lay_notify.setContentsMargins(0, 0, 0, 0)
            self.table.setCellWidget(row, 2, container_notify)
            self.checkboxes_notify[channel] = cb_notify

            cb_notify.setEnabled(settings.is_show(channel))
            cb_show.stateChanged.connect(lambda state, ch=channel: self._update_notify_state(ch, state))

        layout.addWidget(self.table)

        global_group = QGroupBox("Основные")
        global_group.setFont(font_s(11, True))
        global_group.setStyleSheet(f"""
            QGroupBox {{
                color: {Theme.SUBTEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                margin-top: 8px;
                padding-top: 12px;
                background: rgba(255,255,255,0.02);
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
        """)
        global_layout = QVBoxLayout(global_group)
        global_layout.setContentsMargins(12, 16, 12, 12)
        global_layout.setSpacing(12)

        notify_layout = QHBoxLayout()
        notify_label = QLabel("Трей уведомления")
        notify_label.setFont(font_s(11))
        notify_label.setStyleSheet("color: white;")
        self.notify_checkbox = QCheckBox()
        self.notify_checkbox.setChecked(settings.notifications_enabled)
        self.notify_checkbox.setStyleSheet("background: transparent;")
        notify_layout.addWidget(notify_label)
        notify_layout.addWidget(self.notify_checkbox)
        notify_layout.addStretch()
        global_layout.addLayout(notify_layout)

        sound_layout = QHBoxLayout()
        sound_label = QLabel("Звук")
        sound_label.setFont(font_s(11))
        sound_label.setStyleSheet("color: white;")
        self.sound_checkbox = QCheckBox()
        self.sound_checkbox.setChecked(settings.sound_enabled)
        self.sound_checkbox.setStyleSheet("background: transparent;")
        sound_layout.addWidget(sound_label)
        sound_layout.addWidget(self.sound_checkbox)
        sound_layout.addStretch()
        global_layout.addLayout(sound_layout)

        layout.addWidget(global_group)

        font_layout = QHBoxLayout()
        font_label = QLabel("Размер шрифта новостей:")
        font_label.setFont(font_s(11))
        font_label.setStyleSheet("color: white;")
        self.font_spin = QSpinBox()
        self.font_spin.setRange(10, 30)
        self.font_spin.setValue(settings.font_size)
        self.font_spin.setFont(font_s(11))
        self.font_spin.setStyleSheet(f"""
            QSpinBox {{
                background: {Theme.CARD};
                color: white;
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 4px;
            }}
        """)
        font_layout.addWidget(font_label)
        font_layout.addWidget(self.font_spin)
        font_layout.addStretch()
        layout.addLayout(font_layout)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        save_btn = QPushButton("Сохранить")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.BLUE};
                border: none;
                border-radius: 14px;
                color: white;
                padding: 8px 20px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: #2a7fd4; }}
        """)
        save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton("Отмена")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.CARD};
                border: 1px solid {Theme.BORDER};
                border-radius: 14px;
                color: white;
                padding: 8px 20px;
                font-size: 11px;
            }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(save_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)

    def filter_channels(self, text):
        search_text = text.strip().lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item is not None:
                channel_name = item.text().lower()
                self.table.setRowHidden(row, search_text not in channel_name)

    def select_all_channels(self):
        for ch, cb_show in self.checkboxes_show.items():
            cb_show.setChecked(True)
            cb_notify = self.checkboxes_notify[ch]
            cb_notify.setChecked(True)
            cb_notify.setEnabled(True)

    def deselect_all_channels(self):
        for ch, cb_show in self.checkboxes_show.items():
            cb_show.setChecked(False)
            cb_notify = self.checkboxes_notify[ch]
            cb_notify.setChecked(False)
            cb_notify.setEnabled(False)

    def browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку с новостями", self.data_dir_edit.text())
        if folder:
            self.data_dir_edit.setText(folder)

    def _update_notify_state(self, channel, show_state):
        cb_notify = self.checkboxes_notify[channel]
        if show_state == Qt.Checked:
            cb_notify.setEnabled(True)
        else:
            cb_notify.setChecked(False)
            cb_notify.setEnabled(False)

    def save(self):
        for channel, cb_show in self.checkboxes_show.items():
            show = cb_show.isChecked()
            notify = self.checkboxes_notify[channel].isChecked() if show else False
            self.settings.set_channel(channel, show, notify, True)
        self.settings.font_size = self.font_spin.value()
        self.settings.sound_enabled = self.sound_checkbox.isChecked()
        self.settings.notifications_enabled = self.notify_checkbox.isChecked()
        self.settings.save()
        self.accept()

class ToastNotification(QWidget):
    readRequested = pyqtSignal(str)

    def __init__(self, channel: str, full_text: str, sound_enabled: bool = True):
        super().__init__()
        self.channel = channel
        self.full_text = full_text
        self._closing = False
        self.sound_enabled = sound_enabled

        self.toast_width = 520
        self.toast_height = 280

        self._anim_show = None
        self._anim_close = None

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.frame = QFrame()
        self.frame.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 {Theme.TOAST_GRAD_TOP}, stop:1 {Theme.TOAST_GRAD_BOTTOM});
                border-radius: 16px;
                border: none;
            }}
        """)
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(24, 16, 24, 16)
        frame_layout.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(12)

        ch_display = truncate(channel, 35)
        ch_label = QLabel(ch_display)
        ch_label.setFont(font_s(12, True))
        ch_label.setStyleSheet(f"color: {Theme.BLUE}; background: transparent;")
        top.addWidget(ch_label)
        top.addStretch()

        if not self.sound_enabled:
            sound_off_label = QLabel("🔇")
            sound_off_label.setFont(font_s(16))
            sound_off_label.setStyleSheet(f"color: {Theme.RED}; background: transparent;")
            sound_off_label.setToolTip("Звук выключен")
            top.addWidget(sound_off_label)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none; color: {Theme.SUBTEXT}; font-size: 16px; }}
            QPushButton:hover {{ color: #ffffff; }}
        """)
        close_btn.clicked.connect(self.close_animation)
        top.addWidget(close_btn)
        frame_layout.addLayout(top)

        self.preview_label = QLabel(full_text)
        self.preview_label.setWordWrap(True)
        self.preview_label.setFont(font_s(12))
        self.preview_label.setStyleSheet(f"color: {Theme.TEXT}; background: transparent;")
        self.preview_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.preview_label.setMinimumHeight(60)
        self.preview_label.setMaximumHeight(140)
        frame_layout.addWidget(self.preview_label, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(16)
        btn_layout.addStretch()

        self.close_btn = QPushButton("Закрыть")
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.CARD};
                border: 1px solid {Theme.BORDER};
                border-radius: 16px;
                color: white;
                padding: 8px 24px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
        """)
        self.close_btn.clicked.connect(self.close_animation)
        btn_layout.addWidget(self.close_btn)

        self.read_btn = QPushButton("Прочитать")
        self.read_btn.setCursor(Qt.PointingHandCursor)
        self.read_btn.setStyleSheet(f"""
            QPushButton {{
                background: {Theme.BLUE};
                border: none;
                border-radius: 16px;
                color: white;
                padding: 8px 24px;
                font-size: 13px;
            }}
            QPushButton:hover {{ background: #2a7fd4; }}
        """)
        self.read_btn.clicked.connect(self.read_clicked)
        btn_layout.addWidget(self.read_btn)

        frame_layout.addLayout(btn_layout)
        main_layout.addWidget(self.frame)

        self.setFixedSize(self.toast_width, self.toast_height)

        screen = QApplication.primaryScreen().availableGeometry()
        self.target_x = screen.right() - self.toast_width - 24
        self.target_y = screen.bottom() - self.toast_height - 30
        self.move(self.target_x, screen.bottom() + 40)

        self.setWindowOpacity(0.0)
        self.show()

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

    def read_clicked(self):
        self.close_animation()
        self.readRequested.emit(self.channel)

    def close_animation(self):
        if self._closing:
            return
        self._closing = True
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

class LoadingScreen(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setFixedSize(400, 200)
        self.setStyleSheet(f"""
            QDialog {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                                           stop:0 {Theme.TOAST_GRAD_TOP}, stop:1 {Theme.TOAST_GRAD_BOTTOM});
                border: 2px solid {Theme.BORDER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        title = QLabel("Telegram News")
        title.setFont(font_s(18, True))
        title.setStyleSheet("color: white; background: transparent;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                background: {Theme.CARD};
                border: none;
                border-radius: 3px;
            }}
            QProgressBar::chunk {{
                background: {Theme.BLUE};
                border-radius: 3px;
            }}
        """)
        layout.addWidget(self.progress)

        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2,
                  screen.center().y() - self.height() // 2)

class TrayApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)

        self.settings = Settings()

        self._data_available = os.path.isdir(self.settings.data_dir)
        if not self._data_available:
            QMessageBox.warning(
                None,
                "Внимание",
                f"Папка с новостями не найдена.\nПуть: {self.settings.data_dir}\n\nВы можете изменить путь в настройках."
            )

        self.storage = NewsStorage(self.settings.data_dir, settings=self.settings)

        if self._data_available and not self.settings.initialized:
            self.storage.mark_all_current_as_read()
            self.settings.initialized = True
            self.settings.save()

        self.current_toast = None
        self.loading_complete = False
        self.last_confirmed_checksums: Set[str] = None
        self._reload_timer = QTimer()
        self._reload_timer.setSingleShot(True)
        self._reload_timer.timeout.connect(self.start_async_reload)

        self._reload_in_progress = False
        self.loader_thread = None
        self._loader_finished = False  # новый флаг

        self.main_window = MainWindow(self.storage, tray_app=self)
        self.main_window.setVisible(False)

        self.file_watcher = QFileSystemWatcher()
        self.file_watcher.directoryChanged.connect(self.update_watched_files)
        self.file_watcher.fileChanged.connect(self.on_file_changed)
        if self._data_available:
            self.file_watcher.addPath(self.storage.data_dir)

        self.setup_tray()

        self.splash = LoadingScreen()
        self.splash.show()

        self.watchdog_timer = QTimer()
        self.watchdog_timer.timeout.connect(self.check_data_dir)
        self.watchdog_timer.start(5000)

        QTimer.singleShot(4000, self.finish_loading)

    def update_tray_icon(self):
        any_sound_off = (not self.settings.sound_enabled) or any(
            not ch.sound_enabled for ch in self.storage.channels
        )
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setBrush(QColor("#2288dd"))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(8, 8, 48, 48)

        if any_sound_off:
            painter.setPen(QPen(QColor("white"), 3))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(22, 26, 6, 12)
            painter.drawLine(28, 27, 38, 18)
            painter.drawLine(28, 37, 38, 46)
            painter.drawArc(30, 20, 12, 12, -60 * 16, 120 * 16)
            painter.drawArc(34, 16, 20, 20, -50 * 16, 100 * 16)
            painter.setPen(QPen(QColor("#e64a4a"), 4))
            painter.drawLine(16, 48, 48, 16)
        else:
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI", 26, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "N")

        painter.end()
        self.tray.setIcon(QIcon(pixmap))

    def check_data_dir(self):
        try:
            if os.path.isdir(self.storage.data_dir):
                if not self._data_available:
                    self._data_available = True
                    self.file_watcher.addPath(self.storage.data_dir)
                    self.update_watched_files()
                    self.start_async_reload()
            else:
                if self._data_available:
                    self._data_available = False
                    self._reload_timer.stop()
                    try:
                        paths = self.file_watcher.files() + self.file_watcher.directories()
                        if paths:
                            self.file_watcher.removePaths(paths)
                    except:
                        pass
                    self.storage.news.clear()
                    self.storage.channels.clear()
                    self.main_window.selected_channel_name = None
                    self.main_window.current_channel = None
                    self.main_window.sidebar.setChannels([])
                    self.main_window.content.showPlaceholder()
        except Exception as e:
            print(f"Ошибка в check_data_dir: {e}")

    def finish_loading(self):
        self.splash.close()
        self.loading_complete = True
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        if self._data_available:
            self.update_watched_files()
            self.start_async_reload()
        else:
            self.main_window.loadData(preserve_selection=False)
        self.update_tray_icon()

    def update_watched_files(self):
        if not hasattr(self, 'file_watcher') or not self._data_available:
            return
        if not os.path.isdir(self.storage.data_dir):
            return
        try:
            old_files = self.file_watcher.files()
            if old_files:
                self.file_watcher.removePaths(old_files)
            for channel_file in os.listdir(self.storage.data_dir):
                if channel_file.endswith(".json"):
                    self.file_watcher.addPath(os.path.join(self.storage.data_dir, channel_file))
        except:
            pass

    def on_file_changed(self, path):
        if self._data_available:
            self._reload_timer.start(800)

    def start_async_reload(self):
        if self._reload_in_progress or not self._data_available:
            return
        if not os.path.isdir(self.storage.data_dir):
            return
        self._reload_in_progress = True
        self._loader_finished = False

        self.loader_thread = NewsLoaderThread(self.storage.data_dir, self.settings, self.storage.last_read_by_channel)
        self.loader_thread.finished_with_result.connect(self.handle_loaded_data)
        self.loader_thread.finished.connect(self.on_loader_finished)
        self.loader_thread.start()

    def on_loader_finished(self):
        # Новый метод
        self._reload_in_progress = False
        self._loader_finished = True
        if self.loader_thread:
            self.loader_thread.deleteLater()
            self.loader_thread = None
    def handle_loaded_data(self, result):
        # Не сбрасываем _reload_in_progress и не обнуляем loader_thread здесь,
        # ждём завершения потока в on_loader_finished
        if result is None:
            return

        news, channels, updated_last_read = result
        self.storage.news = news
        self.storage.channels = channels
        self.storage.last_read_by_channel = updated_last_read

        self.main_window.refresh_ui(preserve_selection=True)

        current_checksums = {n.checksum() for n in self.storage.news}
        if self.last_confirmed_checksums is None:
            self.last_confirmed_checksums = current_checksums
            self.update_tray_icon()
            return

        new_news = [n for n in self.storage.news if n.checksum() not in self.last_confirmed_checksums]
        self.last_confirmed_checksums = current_checksums

        if not new_news:
            self.update_tray_icon()
            return

        new_news.sort(key=lambda x: x.dt, reverse=True)
        self.update_tray_icon()

        if not self.settings.notifications_enabled:
            return

        notifiable_new_news = [n for n in new_news if self.settings.is_notify(n.channel)]
        if not notifiable_new_news:
            return

        channels = defaultdict(int)
        for n in notifiable_new_news:
            channels[n.channel] += 1

        if len(channels) == 1:
            ch, count = next(iter(channels.items()))
            if count == 1:
                last = notifiable_new_news[0]
                self.show_toast(last.channel, last.text, last.title,
                                sound_enabled_for_channel=self.settings.is_sound(last.channel))
            else:
                self.show_toast(ch, f"Новых новостей: {count}", title=ch,
                                sound_enabled_for_channel=self.settings.is_sound(ch))
        else:
            sorted_channels = sorted(channels.items(), key=lambda x: -x[1])
            all_sound_enabled = all(self.settings.is_sound(ch) for ch in channels.keys())
            if len(sorted_channels) > 3:
                first_three = sorted_channels[:3]
                others = len(sorted_channels) - 3
                lines = [f"{ch}: {cnt}" for ch, cnt in first_three]
                message = "Новые:\n" + "\n".join(lines) + f"\nи ещё {others} каналов"
            else:
                lines = [f"{ch}: {cnt}" for ch, cnt in sorted_channels]
                message = "Новые:\n" + "\n".join(lines)
            self.show_toast("Несколько каналов", message,
                            sound_enabled_for_channel=all_sound_enabled)

    def play_sound(self):
        if not self.settings.sound_enabled:
            return
        if os.path.exists(SOUND_FILE):
            self.player = QMediaPlayer()
            url = QUrl.fromLocalFile(SOUND_FILE)
            content = QMediaContent(url)
            self.player.setMedia(content)
            self.player.setVolume(100)
            self.player.play()
        else:
            QApplication.beep()

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

        self.sound_action = QAction("Звук", self)
        self.sound_action.setCheckable(True)
        self.sound_action.setChecked(self.settings.sound_enabled)
        self.sound_action.triggered.connect(self.toggle_sound_tray)
        menu.addAction(self.sound_action)

        self.notify_action = QAction("Трей уведомления", self)
        self.notify_action.setCheckable(True)
        self.notify_action.setChecked(self.settings.notifications_enabled)
        self.notify_action.triggered.connect(self.toggle_notifications_tray)
        menu.addAction(self.notify_action)

        settings_action = QAction("Настройки", self)
        settings_action.triggered.connect(self.open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()
        exit_act = QAction("Выход", self)
        exit_act.triggered.connect(self.quit_app)
        menu.addAction(exit_act)

        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.activated.connect(self.on_tray_activated)

    def toggle_sound_tray(self, checked):
        self.settings.sound_enabled = checked
        self.settings.save()
        if hasattr(self, 'main_window') and self.main_window:
            self.main_window.content.set_sound_icon(checked)
        self.update_tray_icon()

    def toggle_notifications_tray(self, checked):
        self.settings.notifications_enabled = checked
        self.settings.save()

    def show_window(self):
        if not self.loading_complete:
            return
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.main_window.loadData(preserve_selection=False)

    def on_tray_activated(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.show_window()

    def open_settings(self):
        if not self.loading_complete:
            return
        all_channels = self.storage.get_all_channel_names()
        dlg = SettingsDialog(all_channels, self.settings)
        if dlg.exec_() == QDialog.Accepted:
            new_path = dlg.data_dir_edit.text().strip()
            if not os.path.isdir(new_path):
                QMessageBox.warning(self.main_window, "Предупреждение", "Выбранная папка не существует.\nНастройки не изменены.")
                return
            self.settings.data_dir = new_path
            self.settings.save()
            self.storage.data_dir = new_path
            self._data_available = True
            self.file_watcher.addPath(new_path)
            self.storage.load()
            self.main_window.content.set_font_size(self.settings.font_size)
            self.main_window.content.set_sound_icon(self.settings.sound_enabled)
            self.main_window.refresh_ui()
            self.update_watched_files()
            self.sound_action.setChecked(self.settings.sound_enabled)
            self.notify_action.setChecked(self.settings.notifications_enabled)
            self.update_tray_icon()

    def show_toast(self, channel: str, message: str, title: str = "", sound_enabled_for_channel: Optional[bool] = None):
        if self.current_toast:
            try:
                self.current_toast.close()
            except:
                pass
            self.current_toast = None

        if sound_enabled_for_channel is None:
            sound_enabled_for_channel = self.settings.is_sound(channel)

        final_sound_enabled = self.settings.sound_enabled and sound_enabled_for_channel

        if final_sound_enabled:
            self.play_sound()

        full_text = f"{title}\n\n{message}" if title else message
        self.current_toast = ToastNotification(
            channel, full_text,
            sound_enabled=final_sound_enabled
        )
        self.current_toast.readRequested.connect(self.open_channel_from_toast)

    def open_channel_from_toast(self, channel_name: str):
        self.show_window()
        if channel_name == "Несколько каналов":
            self.main_window.loadData()
            return
        for ch in self.storage.channels:
            if ch.name == channel_name:
                self.main_window.onChannelSelected(ch)
                break

    def quit_app(self):
        # Ожидаем завершения фоновой загрузки, если она активна
        if self.loader_thread and self.loader_thread.isRunning():
            self.loader_thread.wait()  # блокируем до завершения run()
            self.loader_thread.deleteLater()  # безопасно удаляем
            self.loader_thread = None

        self.storage._save_read_state()
        self.settings.save()
        if self.current_toast:
            self.current_toast.close()
        self.tray.hide()
        sys.exit(0)

if __name__ == "__main__":
    app = TrayApp(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    try:
        sys.exit(app.exec_())
    except Exception as e:
        print("Критическая ошибка:", e)
        sys.exit(1)