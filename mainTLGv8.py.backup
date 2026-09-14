#!/usr/bin/env python3
"""
Telegram News — клиент Microsoft SQL Server 2008+.

Источник новостей: SQL Server (не JSON).
Импорт JSON → БД: json_to_mssql.py на сервере/ПК с файлами.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import sys
import threading
import time
import traceback
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtMultimedia import QMediaContent, QMediaPlayer
from PyQt5.QtNetwork import QLocalServer, QLocalSocket
from PyQt5.QtWidgets import *

try:
    import pyodbc
except ImportError:
    pyodbc = None  # проверка при старте

# ---------------------------------------------------------------------------
# Paths / constants
# ---------------------------------------------------------------------------


def excepthook(exc_type, exc_value, exc_tb):
    traceback.print_exception(exc_type, exc_value, exc_tb)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = excepthook

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent
    BUNDLE_DIR = BASE_DIR

SETTINGS_DIR = BASE_DIR / "settings"
_EXTERNAL_SOUNDS_DIR = BASE_DIR / "sounds"
SOUNDS_DIR = _EXTERNAL_SOUNDS_DIR if _EXTERNAL_SOUNDS_DIR.exists() else (BUNDLE_DIR / "sounds")
SETTINGS_FILE = SETTINGS_DIR / "settings.xml"
SOUND_FILE = SOUNDS_DIR / "1.mp3"
II_CONFIG_FILE = SETTINGS_DIR / "ii.json"
PROMPTS_FILE = SETTINGS_DIR / "prompts.json"

APP_FONT_FAMILIES: List[str] = []

def load_bundled_fonts():
    """Регистрирует локальные TTF/OTF из sounds (важно для emoji на старых Windows)."""
    APP_FONT_FAMILIES.clear()
    if not SOUNDS_DIR.exists():
        return
    for fp in list(SOUNDS_DIR.glob("*.ttf")) + list(SOUNDS_DIR.glob("*.otf")):
        try:
            fid = QFontDatabase.addApplicationFont(str(fp))
            if fid >= 0:
                APP_FONT_FAMILIES.extend(QFontDatabase.applicationFontFamilies(fid))
        except Exception:
            pass

def emoji_font(size=12, bold=False):
    preferred = next((f for f in APP_FONT_FAMILIES if "emoji" in f.lower()), None)
    f = QFont(preferred or "Segoe UI Emoji", size)
    f.setBold(bold)
    return f

SIDEBAR_WIDTH = 500
CARD_RADIUS = 12
FONT_SIZE_TITLE = 13
FONT_SIZE_CHANNEL = 11
FONT_SIZE_SMALL = 9
CHANNEL_HEIGHT = 120
PAGE_SIZE = 10

# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------


class DarkTheme:
    name = "dark"
    WINDOW = "#17212b"
    SIDEBAR = "#17212b"
    HEADER = "#17212b"
    CARD = "#1a2533"
    CARD_HOVER = "#223041"
    CARD_ACTIVE = "#2a3b4f"
    CARD_UNREAD = "#182331"
    NEWS_CARD = "#232e3c"
    NEWS_CARD_HOVER = "#2b3744"
    NEWS_CARD_GRAD_TOP = "#3a4553"
    NEWS_CARD_GRAD_BOTTOM = "#232e3c"
    BORDER = "#0e1621"
    TEXT = "#e4e8ee"
    SUBTEXT = "#8b9aab"
    BLUE = "#5288c1"
    RED = "#e64a4a"
    UNREAD_BADGE = "#5288c1"
    AVATAR_COLORS = [
        "#e17076", "#7bc862", "#65aadd", "#a695e7", "#ee7aae",
        "#6ec9cb", "#faa774", "#9aa66b", "#d09b6a", "#b8869a",
    ]
    TOAST_GRAD_TOP = "#2b3744"
    TOAST_GRAD_BOTTOM = "#17212b"
    SCROLL_HANDLE = "#5a6275"
    SCROLL_HANDLE_HOVER = "#6f7b8c"
    BG_GRAD_TOP = "#1e2a36"
    BG_GRAD_BOTTOM = "#1c2733"


class LightTheme:
    name = "light"
    WINDOW = "#f0f2f5"
    SIDEBAR = "#ffffff"
    HEADER = "#ffffff"
    CARD = "#ffffff"
    CARD_HOVER = "#e8eef5"
    CARD_ACTIVE = "#d6e4f5"
    CARD_UNREAD = "#eef4fb"
    NEWS_CARD = "#ffffff"
    NEWS_CARD_HOVER = "#f5f8fc"
    NEWS_CARD_GRAD_TOP = "#ffffff"
    NEWS_CARD_GRAD_BOTTOM = "#f4f7fb"
    BORDER = "#d1d9e3"
    TEXT = "#1a2332"
    SUBTEXT = "#6b7a8d"
    BLUE = "#2b7cd3"
    RED = "#d94040"
    UNREAD_BADGE = "#2b7cd3"
    AVATAR_COLORS = [
        "#e17076", "#7bc862", "#65aadd", "#a695e7", "#ee7aae",
        "#6ec9cb", "#faa774", "#9aa66b", "#d09b6a", "#b8869a",
    ]
    TOAST_GRAD_TOP = "#ffffff"
    TOAST_GRAD_BOTTOM = "#eef2f7"
    SCROLL_HANDLE = "#b0b8c4"
    SCROLL_HANDLE_HOVER = "#8e98a8"
    BG_GRAD_TOP = "#f5f7fa"
    BG_GRAD_BOTTOM = "#eef1f5"


Theme = DarkTheme


def apply_theme(cls):
    global Theme
    Theme = cls


def font_s(size=10, bold=False):
    f = QFont("Segoe UI", size)
    f.setBold(bold)
    f.setLetterSpacing(QFont.AbsoluteSpacing, 0.2)
    return f


def human_time(text: str) -> str:
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return text[:5] if len(text) >= 5 else text


def truncate(text, max_len=80):
    return text[:max_len] + "…" if len(text) > max_len else text


def draw_avatar(painter: QPainter, rect: QRect, text: str):
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    idx = int(hashlib.md5(text.encode()).hexdigest(), 16) % len(Theme.AVATAR_COLORS)
    painter.setBrush(QColor(Theme.AVATAR_COLORS[idx]))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(rect)
    words = text.split()
    letters = words[0][:2].upper() if len(words) == 1 else (words[0][0] + words[1][0]).upper()
    painter.setPen(Qt.white)
    painter.setFont(font_s(int(rect.height() * 0.30), True))
    painter.drawText(rect, Qt.AlignCenter, letters)
    painter.restore()


def default_user_id() -> str:
    try:
        return os.getlogin()
    except Exception:
        return os.environ.get("USERNAME") or os.environ.get("USER") or "user"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Settings:
    def __init__(self, filename: Path = SETTINGS_FILE):
        self.filename = Path(filename)
        self.enabled_channels: Dict[str, dict] = {}
        self.font_size = 14
        self.sound_enabled = True
        self.notifications_enabled = True
        self.initialized = False
        self.theme = "dark"
        self.poll_interval_sec = 5
        # MSSQL
        self.mssql_server = ""
        self.mssql_database = "TelegramNews"
        self.mssql_auth = "windows"  # windows | sql
        self.mssql_user = ""
        self.mssql_password = ""
        self.mssql_driver = "SQL Server"
        # Новый профиль должен сам выбрать ник. Существующий user_id читается из settings.xml.
        self.user_id = ""
        self.load()

    def load(self):
        if not self.filename.exists():
            return
        try:
            root = ET.parse(str(self.filename)).getroot()
            self.enabled_channels = {}
            for ch in root.findall("channel"):
                name = ch.get("name")
                self.enabled_channels[name] = {
                    "show": (ch.findtext("show") or "true").lower() == "true",
                    "notify": (ch.findtext("notify") or "true").lower() == "true",
                    "sound": (ch.findtext("sound") or "true").lower() == "true",
                }
            self.font_size = int(root.findtext("font_size") or 14)
            self.sound_enabled = (root.findtext("sound_enabled") or "true").lower() == "true"
            self.notifications_enabled = (root.findtext("notifications_enabled") or "true").lower() == "true"
            self.initialized = (root.findtext("initialized") or "false").lower() == "true"
            self.theme = (root.findtext("theme") or "dark").strip().lower()
            if self.theme not in ("dark", "light"):
                self.theme = "dark"
            try:
                self.poll_interval_sec = int(root.findtext("poll_interval_sec") or 5)
            except ValueError:
                self.poll_interval_sec = 5
            self.mssql_server = root.findtext("mssql_server") or ""
            self.mssql_database = root.findtext("mssql_database") or "TelegramNews"
            self.mssql_auth = (root.findtext("mssql_auth") or "windows").lower()
            self.mssql_user = root.findtext("mssql_user") or ""
            self.mssql_password = root.findtext("mssql_password") or ""
            self.mssql_driver = root.findtext("mssql_driver") or "SQL Server"
            self.user_id = (root.findtext("user_id") or "").strip()
        except Exception:
            pass

    def save(self):
        root = ET.Element("settings")
        for name, data in self.enabled_channels.items():
            ch = ET.SubElement(root, "channel", name=name)
            ET.SubElement(ch, "show").text = str(data.get("show", True)).lower()
            ET.SubElement(ch, "notify").text = str(data.get("notify", True)).lower()
            ET.SubElement(ch, "sound").text = str(data.get("sound", True)).lower()
        ET.SubElement(root, "font_size").text = str(self.font_size)
        ET.SubElement(root, "sound_enabled").text = str(self.sound_enabled).lower()
        ET.SubElement(root, "notifications_enabled").text = str(self.notifications_enabled).lower()
        ET.SubElement(root, "initialized").text = str(self.initialized).lower()
        ET.SubElement(root, "theme").text = self.theme
        ET.SubElement(root, "poll_interval_sec").text = str(self.poll_interval_sec)
        ET.SubElement(root, "mssql_server").text = self.mssql_server
        ET.SubElement(root, "mssql_database").text = self.mssql_database
        ET.SubElement(root, "mssql_auth").text = self.mssql_auth
        ET.SubElement(root, "mssql_user").text = self.mssql_user
        ET.SubElement(root, "mssql_password").text = self.mssql_password
        ET.SubElement(root, "mssql_driver").text = self.mssql_driver
        ET.SubElement(root, "user_id").text = self.user_id
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        ET.ElementTree(root).write(str(self.filename), encoding="utf-8", xml_declaration=True)

    def conn_str(self, driver: Optional[str] = None) -> str:
        d = driver or self.mssql_driver or "SQL Server"
        drv = d if d.startswith("{") else f"{{{d}}}"
        parts = [
            f"DRIVER={drv}",
            f"SERVER={self.mssql_server}",
            f"DATABASE={self.mssql_database}",
            "Connection Timeout=8",
            "Login Timeout=8",
            "TrustServerCertificate=yes",
        ]
        if self.mssql_auth in ("windows", "trusted", "sspi", "domain"):
            parts.append("Trusted_Connection=yes")
        else:
            parts.append(f"UID={self.mssql_user}")
            parts.append(f"PWD={self.mssql_password}")
        return ";".join(parts)

    def candidate_drivers(self) -> List[str]:
        """Порядок перебора ODBC-драйверов (2008 → современные)."""
        preferred = (self.mssql_driver or "SQL Server").strip()
        order = [
            preferred,
            "SQL Server",
            "SQL Server Native Client 10.0",
            "SQL Server Native Client 11.0",
            "ODBC Driver 11 for SQL Server",
            "ODBC Driver 13 for SQL Server",
            "ODBC Driver 17 for SQL Server",
            "ODBC Driver 18 for SQL Server",
        ]
        seen = set()
        out = []
        for d in order:
            if d and d not in seen:
                seen.add(d)
                out.append(d)
        return out

    def is_show(self, name: str) -> bool:
        return self.enabled_channels.get(name, {}).get("show", True)

    def is_notify(self, name: str) -> bool:
        # Скрытый канал никогда не должен давать tray/toast уведомления, включая старые settings.xml.
        return self.is_show(name) and self.enabled_channels.get(name, {}).get("notify", True)

    def is_sound(self, name: str) -> bool:
        return self.enabled_channels.get(name, {}).get("sound", True)

    def set_channel(self, name, show, notify, sound=True):
        self.enabled_channels[name] = {"show": bool(show), "notify": bool(notify) if show else False, "sound": bool(sound)}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class News:
    id: int
    date: str
    channel: str
    text: str
    title: str = ""
    date_ts: float = 0.0
    checksum: str = ""

    def cs(self) -> str:
        return self.checksum or hashlib.md5(
            f"{self.date}{self.channel}{self.title}{self.text}".encode()
        ).hexdigest()


@dataclass
class Channel:
    id: int
    name: str
    last_news: str
    last_date: str
    count: int
    unread_count: int = 0
    notify_enabled: bool = True
    sound_enabled: bool = True


# ---------------------------------------------------------------------------
# MSSQL Storage (каждый вызов — своё соединение; безопасно из QThread)
# ---------------------------------------------------------------------------


class NewsStorage:
    """Синхронный доступ к MSSQL. Не шарить один connection между потоками."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.channels: List[Channel] = []
        self._working_driver: Optional[str] = None

    def connect(self):
        if pyodbc is None:
            raise RuntimeError("pyodbc не установлен. pip install pyodbc")
        if not self.settings.mssql_server:
            raise RuntimeError("Не указан SQL Server (Настройки → Подключение)")

        errors = []
        drivers = []
        if self._working_driver:
            drivers.append(self._working_driver)
        drivers.extend(self.settings.candidate_drivers())

        seen = set()
        for drv in drivers:
            if drv in seen:
                continue
            seen.add(drv)
            try:
                conn = pyodbc.connect(
                    self.settings.conn_str(drv),
                    timeout=8,
                    autocommit=True,
                )
                # Ограничиваем не только установление соединения, но и SQL-команды.
                # Это особенно важно при завершении приложения: зависший запрос не должен
                # удерживать QThread бесконечно. На старых драйверах свойство может быть
                # недоступно, поэтому оставляем безопасный fallback.
                try:
                    conn.timeout = 8
                except Exception:
                    pass
                self._working_driver = drv
                # если в настройках был другой драйвер — запомним рабочий
                if self.settings.mssql_driver != drv:
                    self.settings.mssql_driver = drv
                return conn
            except Exception as e:
                errors.append(f"{drv}: {e}")
                continue
        raise RuntimeError(
            "Не удалось подключиться к SQL Server.\n" + "\n".join(errors[-5:])
        )

    def close(self):
        """Соединения короткие — метод оставлен для совместимости."""
        pass

    def test_connection(self) -> Tuple[bool, str, Optional[str]]:
        try:
            conn = self.connect()
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM dbo.channels")
            ch_cnt = int(cur.fetchone()[0])
            cur.execute("SELECT COUNT(*), ISNULL(MAX(id),0) FROM dbo.news")
            n, max_id = cur.fetchone()
            n, max_id = int(n or 0), int(max_id or 0)
            conn.close()
            drv = self._working_driver or self.settings.mssql_driver
            return (
                True,
                f"OK · driver={drv} · каналов={ch_cnt} · новостей={n} · max_id={max_id}",
                drv,
            )
        except Exception as e:
            return False, str(e), None

    def get_all_channel_names(self) -> List[str]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT name FROM dbo.channels ORDER BY name")
            return [r[0] for r in cur.fetchall()]
        finally:
            conn.close()

    def load_channels(self) -> List[Channel]:
        """Один запрос: каналы + unread (без N+1)."""
        conn = self.connect()
        try:
            cur = conn.cursor()
            user = self.settings.user_id
            cur.execute(
                """
                SELECT
                    c.id,
                    c.name,
                    c.last_date,
                    c.last_text,
                    c.news_count,
                    (
                        SELECT COUNT(*)
                        FROM dbo.news n
                        WHERE n.channel_id = c.id
                          AND n.date_ts > ISNULL(r.last_read_ts, 0)
                    ) AS unread_count
                FROM dbo.channels c
                LEFT JOIN dbo.read_state r
                       ON r.channel_id = c.id AND r.user_id = ?
                ORDER BY c.last_date_ts DESC, c.name
                """,
                (user,),
            )
            channels: List[Channel] = []
            for row in cur.fetchall():
                cid, name, last_date, last_text, news_count, unread = row
                if not self.settings.is_show(name):
                    continue
                channels.append(
                    Channel(
                        id=int(cid),
                        name=name,
                        last_news=last_text or "",
                        last_date=last_date or "",
                        count=int(news_count or 0),
                        unread_count=int(unread or 0),
                        notify_enabled=self.settings.is_notify(name),
                        sound_enabled=self.settings.is_sound(name),
                    )
                )
            self.channels = channels
            return channels
        finally:
            conn.close()

    def news_page(
        self,
        channel_name: Optional[str],
        offset: int = 0,
        limit: int = PAGE_SIZE,
        search: Optional[str] = None,
    ) -> Tuple[List[News], int]:
        """Пагинация через ROW_NUMBER (SQL Server 2008)."""
        conn = self.connect()
        try:
            cur = conn.cursor()
            where = ["1=1"]
            params: list = []

            if channel_name:
                where.append("c.name = ?")
                params.append(channel_name)
            else:
                hidden = [
                    n
                    for n, d in self.settings.enabled_channels.items()
                    if not d.get("show", True)
                ]
                if hidden:
                    ph = ",".join("?" * len(hidden))
                    where.append(f"c.name NOT IN ({ph})")
                    params.extend(hidden)

            if search:
                where.append("(n.body LIKE ? OR ISNULL(n.title, N'') LIKE ?)")
                q = f"%{search}%"
                params.extend([q, q])

            where_sql = " AND ".join(where)

            cur.execute(
                f"""
                SELECT COUNT(*)
                FROM dbo.news n
                INNER JOIN dbo.channels c ON c.id = n.channel_id
                WHERE {where_sql}
                """,
                params,
            )
            total = int(cur.fetchone()[0])

            sql = f"""
                SELECT id, date_str, date_ts, title, body, checksum, channel
                FROM (
                    SELECT n.id, n.date_str, n.date_ts, n.title, n.body, n.checksum,
                           c.name AS channel,
                           ROW_NUMBER() OVER (ORDER BY n.date_ts DESC, n.id DESC) AS rn
                    FROM dbo.news n
                    INNER JOIN dbo.channels c ON c.id = n.channel_id
                    WHERE {where_sql}
                ) t
                WHERE rn BETWEEN ? AND ?
                ORDER BY rn
            """
            cur.execute(sql, params + [offset + 1, offset + limit])
            news = [
                News(
                    id=int(r[0]),
                    date=r[1] or "",
                    channel=r[6],
                    text=r[4] or "",
                    title=r[3] or "",
                    date_ts=float(r[2] or 0),
                    checksum=r[5] or "",
                )
                for r in cur.fetchall()
            ]
            return news, total
        finally:
            conn.close()

    def mark_channel_read(self, channel_name: str) -> None:
        conn = self.connect()
        try:
            cur = conn.cursor()
            user = self.settings.user_id
            cur.execute("SELECT id FROM dbo.channels WHERE name = ?", (channel_name,))
            row = cur.fetchone()
            if not row:
                return
            cid = int(row[0])
            cur.execute(
                """
                SELECT TOP 1 date_str, date_ts FROM dbo.news
                WHERE channel_id = ?
                ORDER BY date_ts DESC, id DESC
                """,
                (cid,),
            )
            last = cur.fetchone()
            if not last:
                return
            date_str, date_ts = last[0], float(last[1] or 0)
            cur.execute(
                """
                IF EXISTS (SELECT 1 FROM dbo.read_state WHERE user_id = ? AND channel_id = ?)
                    UPDATE dbo.read_state
                    SET last_read_ts = ?, last_read_date = ?
                    WHERE user_id = ? AND channel_id = ?
                ELSE
                    INSERT INTO dbo.read_state (user_id, channel_id, last_read_ts, last_read_date)
                    VALUES (?, ?, ?, ?)
                """,
                (user, cid, date_ts, date_str, user, cid, user, cid, date_ts, date_str),
            )
        finally:
            conn.close()

    def mark_all_read(self) -> None:
        """Отметить прочитанными все существующие новости одним пакетным запросом.

        SQL Server 2008 compatible: UPDATE существующих read_state + INSERT отсутствующих.
        Не делаем N+1 запросов по каналам — это важно при сотнях каналов.
        """
        conn = self.connect()
        try:
            cur = conn.cursor()
            user = self.settings.user_id
            cur.execute(
                """
                ;WITH latest AS (
                    SELECT n.channel_id, n.date_ts, n.date_str,
                           ROW_NUMBER() OVER (PARTITION BY n.channel_id ORDER BY n.date_ts DESC, n.id DESC) AS rn
                    FROM dbo.news n
                )
                UPDATE r
                   SET r.last_read_ts = l.date_ts,
                       r.last_read_date = l.date_str
                FROM dbo.read_state r
                INNER JOIN latest l ON l.channel_id = r.channel_id AND l.rn = 1
                WHERE r.user_id = ?;

                ;WITH latest AS (
                    SELECT n.channel_id, n.date_ts, n.date_str,
                           ROW_NUMBER() OVER (PARTITION BY n.channel_id ORDER BY n.date_ts DESC, n.id DESC) AS rn
                    FROM dbo.news n
                )
                INSERT INTO dbo.read_state (user_id, channel_id, last_read_ts, last_read_date)
                SELECT ?, l.channel_id, l.date_ts, l.date_str
                FROM latest l
                WHERE l.rn = 1
                  AND NOT EXISTS (
                      SELECT 1 FROM dbo.read_state r
                      WHERE r.user_id = ? AND r.channel_id = l.channel_id
                  );
                """,
                (user, user, user),
            )
        finally:
            conn.close()

    def max_news_id(self) -> int:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT ISNULL(MAX(id), 0) FROM dbo.news")
            return int(cur.fetchone()[0])
        finally:
            conn.close()

    def news_since_id(self, after_id: int) -> List[News]:
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT n.id, n.date_str, n.date_ts, n.title, n.body, n.checksum, c.name
                FROM dbo.news n
                INNER JOIN dbo.channels c ON c.id = n.channel_id
                WHERE n.id > ?
                ORDER BY n.date_ts DESC, n.id DESC
                """,
                (after_id,),
            )
            return [
                News(
                    id=int(r[0]),
                    date=r[1] or "",
                    channel=r[6],
                    text=r[4] or "",
                    title=r[3] or "",
                    date_ts=float(r[2] or 0),
                    checksum=r[5] or "",
                )
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def news_for_ai(self, channel_names: List[str], since_ts: float, until_ts: float, limit: int = 500) -> List[News]:
        """Новости для ИИ за интервал. Ограничение защищает память на слабых ПК."""
        if not channel_names:
            return []
        names = [n for n in channel_names if self.settings.is_show(n)]
        if not names:
            return []
        conn = self.connect()
        try:
            cur = conn.cursor()
            ph = ",".join("?" * len(names))
            sql = f"""
                SELECT TOP {max(1, min(int(limit), 2000))}
                       n.id, n.date_str, n.date_ts, n.title, n.body, n.checksum, c.name
                FROM dbo.news n
                INNER JOIN dbo.channels c ON c.id = n.channel_id
                WHERE c.name IN ({ph})
                  AND n.date_ts >= ? AND n.date_ts <= ?
                ORDER BY n.date_ts ASC, n.id ASC
            """
            cur.execute(sql, names + [float(since_ts), float(until_ts)])
            return [
                News(
                    id=int(r[0]), date=r[1] or "", date_ts=float(r[2] or 0),
                    title=r[3] or "", text=r[4] or "", checksum=r[5] or "", channel=r[6]
                )
                for r in cur.fetchall()
            ]
        finally:
            conn.close()

    def poll_bundle(self, after_id: int, load_new: bool = True, batch_size: int = 500) -> Tuple[int, List[News], List[Channel]]:
        """Фоновый опрос. Новые записи читаются пакетами, чтобы не раздувать RAM."""
        conn = self.connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT ISNULL(MAX(id), 0) FROM dbo.news")
            max_id = int(cur.fetchone()[0])
            new_items: List[News] = []
            checkpoint_id = max_id
            if load_new and max_id > after_id:
                safe_batch = max(1, min(int(batch_size), 2000))
                cur.execute(
                    f"""
                    SELECT TOP {safe_batch} n.id, n.date_str, n.date_ts, n.title, n.body, n.checksum, c.name
                    FROM dbo.news n
                    INNER JOIN dbo.channels c ON c.id = n.channel_id
                    WHERE n.id > ?
                    ORDER BY n.id ASC
                    """,
                    (after_id,),
                )
                new_items = [
                    News(
                        id=int(r[0]),
                        date=r[1] or "",
                        channel=r[6],
                        text=r[4] or "",
                        title=r[3] or "",
                        date_ts=float(r[2] or 0),
                        checksum=r[5] or "",
                    )
                    for r in cur.fetchall()
                ]
                if new_items:
                    checkpoint_id = new_items[-1].id
            # channels (тот же запрос, что load_channels)
            user = self.settings.user_id
            cur.execute(
                """
                SELECT
                    c.id, c.name, c.last_date, c.last_text, c.news_count,
                    (
                        SELECT COUNT(*) FROM dbo.news n
                        WHERE n.channel_id = c.id
                          AND n.date_ts > ISNULL(r.last_read_ts, 0)
                    ) AS unread_count
                FROM dbo.channels c
                LEFT JOIN dbo.read_state r
                       ON r.channel_id = c.id AND r.user_id = ?
                ORDER BY c.last_date_ts DESC, c.name
                """,
                (user,),
            )
            channels: List[Channel] = []
            for row in cur.fetchall():
                cid, name, last_date, last_text, news_count, unread = row
                if not self.settings.is_show(name):
                    continue
                channels.append(
                    Channel(
                        id=int(cid),
                        name=name,
                        last_news=last_text or "",
                        last_date=last_date or "",
                        count=int(news_count or 0),
                        unread_count=int(unread or 0),
                        notify_enabled=self.settings.is_notify(name),
                        sound_enabled=self.settings.is_sound(name),
                    )
                )
            self.channels = channels
            return checkpoint_id, new_items, channels
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Фоновые задачи БД (QThread) — UI не блокируется
# ---------------------------------------------------------------------------


class DbTask(QThread):
    """
    Универсальный worker.
    op: 'load_channels' | 'news_page' | 'mark_read_and_page' | 'poll' | 'ai_news' | 'test' | 'channel_names' | 'mark_all_read'
    """

    finished_ok = pyqtSignal(str, object)  # op, result
    failed = pyqtSignal(str, str)  # op, error

    def __init__(self, settings: Settings, op: str, params: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._settings = settings
        self.op = op
        self.params = params or {}

    def run(self):
        storage = NewsStorage(self._settings)
        try:
            p = self.params
            if self.op == "load_channels":
                result = storage.load_channels()
            elif self.op == "news_page":
                result = storage.news_page(
                    p.get("channel_name"),
                    int(p.get("offset", 0)),
                    int(p.get("limit", PAGE_SIZE)),
                    p.get("search"),
                )
            elif self.op == "mark_read_and_page":
                storage.mark_channel_read(p["channel_name"])
                channels = storage.load_channels()
                news, total = storage.news_page(
                    p["channel_name"], 0, int(p.get("limit", PAGE_SIZE)), None
                )
                result = (channels, news, total)
            elif self.op == "poll":
                result = storage.poll_bundle(
                    int(p.get("after_id", 0)), bool(p.get("load_new", True)), int(p.get("batch_size", 500))
                )
            elif self.op == "ai_news":
                result = storage.news_for_ai(
                    list(p.get("channels") or []), float(p.get("since_ts", 0)),
                    float(p.get("until_ts", time.time())), int(p.get("limit", 500))
                )
            elif self.op == "test":
                result = storage.test_connection()
            elif self.op == "channel_names":
                result = storage.get_all_channel_names()
            elif self.op == "mark_all_read":
                storage.mark_all_read()
                result = True
            else:
                raise ValueError(f"Unknown op: {self.op}")
            self.finished_ok.emit(self.op, result)
        except Exception as e:
            self.failed.emit(self.op, str(e))


# ---------------------------------------------------------------------------
# Models / delegates (кратко)
# ---------------------------------------------------------------------------


class ChannelListModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._channels: List[Channel] = []
        self._selected = -1

    def rowCount(self, parent=QModelIndex()):
        return len(self._channels)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._channels)):
            return None
        ch = self._channels[index.row()]
        if role == Qt.DisplayRole:
            return ch.name
        if role == Qt.UserRole:
            return ch
        if role == Qt.UserRole + 1:
            return index.row() == self._selected
        return None

    def setChannels(self, channels: List[Channel]):
        self.beginResetModel()
        self._channels = channels
        self._selected = -1
        self.endResetModel()

    def setSelected(self, row: int):
        old = self._selected
        self._selected = row
        if 0 <= old < len(self._channels):
            self.dataChanged.emit(self.index(old), self.index(old), [Qt.UserRole + 1])
        if 0 <= row < len(self._channels):
            self.dataChanged.emit(self.index(row), self.index(row), [Qt.UserRole + 1])


class NewsListModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self._news: List[News] = []
        self._total = 0

    def rowCount(self, parent=QModelIndex()):
        return len(self._news)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._news)):
            return None
        n = self._news[index.row()]
        if role == Qt.DisplayRole:
            return n.title or n.text
        if role == Qt.UserRole:
            return n
        return None

    def reset_page(self, news: List[News], total: int):
        self.beginResetModel()
        self._news = news
        self._total = total
        self.endResetModel()

    def append_page(self, more: List[News]) -> bool:
        if not more:
            return False
        s = len(self._news)
        self.beginInsertRows(QModelIndex(), s, s + len(more) - 1)
        self._news.extend(more)
        self.endInsertRows()
        return len(self._news) < self._total

    def hasMore(self) -> bool:
        return len(self._news) < self._total

    def clear(self):
        self.beginResetModel()
        self._news = []
        self._total = 0
        self.endResetModel()


class ChannelDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        channel = index.data(Qt.UserRole)
        if not channel:
            return
        selected = index.data(Qt.UserRole + 1)
        hover = option.state & QStyle.State_MouseOver
        unread = channel.unread_count
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect.adjusted(4, 4, -4, -4)
        if selected:
            bg = Theme.CARD_ACTIVE
        elif hover:
            bg = Theme.CARD_HOVER
        elif unread > 0:
            bg = Theme.CARD_UNREAD
        else:
            bg = Theme.CARD
        painter.setBrush(QColor(bg))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, CARD_RADIUS, CARD_RADIUS)
        painter.restore()

        av = QRect(rect.left() + 56, rect.top() + (rect.height() - 42) // 2, 42, 42)
        draw_avatar(painter, av, channel.name)
        painter.setFont(font_s(10))
        painter.setPen(QColor(Theme.TEXT if channel.notify_enabled else Theme.SUBTEXT))
        painter.drawText(QRect(rect.left() + 14, rect.top() + 16, 24, 24), Qt.AlignCenter,
                         "🔔" if channel.notify_enabled else "🔕")
        painter.setPen(QColor(Theme.TEXT if channel.sound_enabled else Theme.SUBTEXT))
        painter.drawText(QRect(rect.left() + 14, rect.bottom() - 36, 24, 24), Qt.AlignCenter,
                         "🔊" if channel.sound_enabled else "🔇")

        time_r = QRect(rect.right() - 70, rect.top() + 8, 60, 16)
        name_r = QRect(av.right() + 12, rect.top() + 8, time_r.left() - av.right() - 20, 20)
        painter.setPen(QColor(Theme.TEXT))
        painter.setFont(font_s(FONT_SIZE_CHANNEL, True))
        painter.drawText(name_r, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(channel.name, Qt.ElideRight, name_r.width()))
        painter.setPen(QColor(Theme.SUBTEXT))
        painter.setFont(font_s(FONT_SIZE_SMALL))
        prev = QRect(name_r.left(), name_r.bottom() + 4, rect.right() - name_r.left() - 12, 50)
        fm = painter.fontMetrics()
        lines = [fm.elidedText(l, Qt.ElideRight, prev.width()) for l in (channel.last_news or "").split("\n")]
        max_l = max(1, prev.height() // fm.height())
        if len(lines) > max_l:
            lines = lines[: max_l - 1]
            if lines:
                lines[-1] = fm.elidedText(lines[-1], Qt.ElideRight, prev.width() - fm.width("…")) + "…"
        painter.drawText(prev, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, "\n".join(lines))
        painter.setFont(font_s(8))
        painter.drawText(time_r, Qt.AlignRight | Qt.AlignVCenter, human_time(channel.last_date))
        if unread > 0:
            painter.setBrush(QColor(Theme.BLUE))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRect(rect.left() + 4, rect.top() + 15, 4, rect.height() - 30), 2, 2)
            b = QRect(rect.right() - 24, rect.bottom() - 24, 20, 20)
            painter.setBrush(QColor(Theme.UNREAD_BADGE))
            painter.drawEllipse(b)
            painter.setPen(Qt.white)
            painter.setFont(font_s(9, True))
            painter.drawText(b, Qt.AlignCenter, str(unread))

    def sizeHint(self, option, index):
        return QSize(SIDEBAR_WIDTH - 28, CHANNEL_HEIGHT)


class NewsDelegate(QStyledItemDelegate):
    def __init__(self, font_size=14):
        super().__init__()
        self.font_size = font_size
        self._cache: Dict[str, int] = {}

    def paint(self, painter, option, index):
        news = index.data(Qt.UserRole)
        if not news:
            return
        hover = option.state & QStyle.State_MouseOver
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = option.rect.adjusted(6, 6, -6, -6)
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        if hover:
            g.setColorAt(0, QColor(Theme.NEWS_CARD_HOVER))
            g.setColorAt(1, QColor(Theme.NEWS_CARD))
        else:
            g.setColorAt(0, QColor(Theme.NEWS_CARD_GRAD_TOP))
            g.setColorAt(1, QColor(Theme.NEWS_CARD_GRAD_BOTTOM))
        painter.setBrush(QBrush(g))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, CARD_RADIUS, CARD_RADIUS)
        painter.restore()

        top = QRect(rect.left() + 16, rect.top() + 12, rect.width() - 32, 34)
        av = QRect(top.left(), top.top(), 34, 34)
        draw_avatar(painter, av, news.channel)
        painter.setPen(QColor(Theme.TEXT))
        painter.setFont(font_s(FONT_SIZE_CHANNEL, True))
        painter.drawText(QRect(av.right() + 10, top.top() + 8, 200, 20), Qt.AlignLeft | Qt.AlignVCenter, news.channel)
        painter.setPen(QColor(Theme.SUBTEXT))
        painter.setFont(font_s(FONT_SIZE_SMALL))
        painter.drawText(QRect(top.right() - 100, top.top() + 8, 90, 20), Qt.AlignRight | Qt.AlignVCenter, human_time(news.date))

        if news.title:
            tr = QRect(rect.left() + 16, top.bottom() + 18, rect.width() - 32, 30)
            painter.setPen(QColor(Theme.TEXT))
            painter.setFont(font_s(self.font_size + 2, True))
            painter.drawText(tr, Qt.AlignLeft | Qt.AlignTop,
                             painter.fontMetrics().elidedText(news.title, Qt.ElideRight, tr.width()))
            body_top = tr.bottom() + 26
        else:
            body_top = top.bottom() + 8
        date_y = rect.bottom() - 10 - 18
        body = QRect(rect.left() + 16, body_top, rect.width() - 32, max(0, date_y - 2 - body_top))
        painter.setPen(QColor(Theme.TEXT))
        painter.setFont(font_s(self.font_size))
        painter.drawText(body, Qt.AlignJustify | Qt.AlignTop | Qt.TextWordWrap, news.text)
        painter.setPen(QColor(Theme.SUBTEXT))
        painter.setFont(font_s(FONT_SIZE_SMALL - 1))
        painter.drawText(QRect(rect.left() + 16, date_y, rect.width() - 32, 18), Qt.AlignLeft | Qt.AlignVCenter, news.date)

    def sizeHint(self, option, index):
        news = index.data(Qt.UserRole)
        if not news:
            return QSize(option.rect.width(), 120)
        w = max(100, option.rect.width())
        key = f"{news.cs()}:{w}:{self.font_size}"
        if key in self._cache:
            return QSize(w, self._cache[key])
        fm = QFontMetrics(font_s(self.font_size))
        bh = fm.boundingRect(QRect(0, 0, w - 32, 10000), Qt.TextWordWrap | Qt.AlignJustify, news.text).height()
        th = 0
        if news.title:
            th = QFontMetrics(font_s(self.font_size + 2, True)).boundingRect(
                QRect(0, 0, w - 32, 100), Qt.TextWrapAnywhere | Qt.AlignLeft, news.title
            ).height()
        h = max(100, 12 + 34 + 18 + th + (26 if news.title else 0) + bh + 28 + 20 + 10 + 8)
        self._cache[key] = h
        if len(self._cache) > 600:
            self._cache.clear()
        return QSize(w, h)

    def clear_cache(self):
        self._cache.clear()


# ---------------------------------------------------------------------------
# UI pieces
# ---------------------------------------------------------------------------


class Sidebar(QFrame):
    channelSelected = pyqtSignal(object)
    settingsChanged = pyqtSignal()

    def __init__(self, storage: NewsStorage):
        super().__init__()
        self.storage = storage
        self.setFixedWidth(SIDEBAR_WIDTH)
        self._style()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 16, 14, 14)
        self.title = QLabel("КАНАЛЫ")
        self.title.setFont(font_s(12, True))
        self.title.setStyleSheet(f"color: {Theme.BLUE};")
        lay.addWidget(self.title)
        self.list = QListView()
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setMouseTracking(True)
        self.list.viewport().setAttribute(Qt.WA_Hover, True)
        self.list.setSelectionMode(QAbstractItemView.NoSelection)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self._list_style()
        self.model = ChannelListModel()
        self.list.setModel(self.model)
        self.list.setItemDelegate(ChannelDelegate())
        self.list.clicked.connect(self._click)
        lay.addWidget(self.list)

    def _style(self):
        self.setStyleSheet(f"""
            QFrame {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 {Theme.SIDEBAR}, stop:1 {Theme.WINDOW});
                border: none; border-right: 1px solid {Theme.BORDER}; border-radius: 16px; }}
        """)

    def _list_style(self):
        self.list.setStyleSheet(f"""
            QListView {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ width: 12px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Theme.SCROLL_HANDLE}; border-radius: 6px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def apply_theme(self):
        self._style()
        self._list_style()
        self.title.setStyleSheet(f"color: {Theme.BLUE};")
        self.list.viewport().update()

    def setChannels(self, channels):
        self.model.setChannels(channels)

    def selectNoChannel(self):
        self.model.setSelected(-1)

    def _click(self, index):
        ch = index.data(Qt.UserRole)
        if ch:
            self.model.setSelected(index.row())
            self.channelSelected.emit(ch)

    def _menu(self, pos):
        index = self.list.indexAt(pos)
        if not index.isValid():
            return
        ch = index.data(Qt.UserRole)
        if not ch:
            return
        menu = QMenu()
        menu.setStyleSheet(f"QMenu {{ background: {Theme.CARD}; color: {Theme.TEXT}; border: 1px solid {Theme.BORDER}; border-radius: 10px; padding: 6px; }} QMenu::item:selected {{ background: {Theme.CARD_ACTIVE}; }}")
        for label, field, val in (
            ("Показывать", "show", self.storage.settings.is_show(ch.name)),
            ("Трей уведомление", "notify", ch.notify_enabled),
            ("Звук", "sound", ch.sound_enabled),
        ):
            a = QAction(label, self)
            a.setCheckable(True)
            a.setChecked(val)
            a.triggered.connect(lambda c, ch=ch, f=field: self._tog(ch, f, c))
            menu.addAction(a)
        menu.exec_(self.list.viewport().mapToGlobal(pos))

    def _tog(self, ch, field, checked):
        s = self.storage.settings
        show, notify, sound = s.is_show(ch.name), s.is_notify(ch.name), s.is_sound(ch.name)
        if field == "show":
            show = checked
            if not show:
                notify = False
        elif field == "notify":
            notify = checked
        else:
            sound = checked
        s.set_channel(ch.name, show, notify, sound)
        s.save()
        self.settingsChanged.emit()


class MainContent(QWidget):
    refreshRequested = pyqtSignal()
    searchRequested = pyqtSignal(str)
    settingsRequested = pyqtSignal()
    soundToggleRequested = pyqtSignal()
    themeToggleRequested = pyqtSignal()
    loadMoreRequested = pyqtSignal()
    aiRequested = pyqtSignal()
    markAllReadRequested = pyqtSignal()

    def __init__(self, font_size=14, sound_enabled=True):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.header = QFrame()
        self.header.setFixedHeight(64)
        self._hdr()
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(24, 12, 24, 12)
        self.channel_title = QLabel("Каналы")
        self.channel_title.setFont(font_s(FONT_SIZE_TITLE, True))
        self.channel_title.setStyleSheet(f"color: {Theme.TEXT};")
        hl.addWidget(self.channel_title)
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet(f"color: {Theme.SUBTEXT};")
        hl.addWidget(self.count_label)
        hl.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск...")
        self.search.setFixedWidth(240)
        self.search.setMinimumHeight(36)
        self._search_style()
        self.search.textChanged.connect(self.searchRequested)
        hl.addWidget(self.search)
        self.ai_btn = self._btn("ИИ")
        self.ai_btn.setToolTip("Режим ИИ")
        self.ai_btn.setMinimumWidth(34)
        self.ai_btn.setMaximumWidth(34)
        self.ai_btn.clicked.connect(self.aiRequested.emit)
        hl.addWidget(self.ai_btn)
        self.refresh_btn = self._btn("⟳")
        self.refresh_btn.setToolTip("Обновить")
        self.refresh_btn.clicked.connect(self.refreshRequested)
        hl.addWidget(self.refresh_btn)
        self.mark_all_btn = self._btn("✓✓")
        self.mark_all_btn.setToolTip("Отметить все новости прочитанными")
        self.mark_all_btn.setFont(font_s(10, True))
        self.mark_all_btn.clicked.connect(self.markAllReadRequested.emit)
        hl.addWidget(self.mark_all_btn)
        self.sound_btn = self._btn("")
        self.sound_btn.clicked.connect(self.soundToggleRequested.emit)
        hl.addWidget(self.sound_btn)
        self.set_sound_icon(sound_enabled)
        self.theme_btn = self._btn("☀" if Theme.name == "dark" else "🌙")
        self.theme_btn.clicked.connect(self.themeToggleRequested.emit)
        hl.addWidget(self.theme_btn)
        self.settings_btn = self._btn("⚙")
        self.settings_btn.clicked.connect(self.settingsRequested)
        hl.addWidget(self.settings_btn)
        lay.addWidget(self.header)

        self.news_list = QListView()
        self.news_list.setFrameShape(QFrame.NoFrame)
        self.news_list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.news_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.news_list.setMouseTracking(True)
        self.news_list.viewport().setAttribute(Qt.WA_Hover, True)
        self.news_list.setSelectionMode(QAbstractItemView.NoSelection)
        self._list_style()
        self.news_model = NewsListModel()
        self.news_delegate = NewsDelegate(font_size)
        self.news_list.setModel(self.news_model)
        self.news_list.setItemDelegate(self.news_delegate)
        self.news_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.news_list.customContextMenuRequested.connect(self._news_menu)
        self.news_list.verticalScrollBar().valueChanged.connect(self._scroll)
        lay.addWidget(self.news_list)

        self.placeholder = QLabel("Выберите канал или настройте подключение к SQL Server")
        self.placeholder.setAlignment(Qt.AlignCenter)
        self.placeholder.setFont(font_s(14, True))
        self.placeholder.setStyleSheet(f"color: {Theme.SUBTEXT};")
        self.placeholder.hide()
        lay.addWidget(self.placeholder)
        self._loading = False

    def _btn(self, t):
        b = QPushButton(t)
        # Компактные кнопки: ИИ/обновление не должны занимать лишнее место
        # в заголовке даже при увеличенном системном шрифте.
        b.setFixedSize(34, 34)
        b.setCursor(Qt.PointingHandCursor)
        b.setFont(font_s(12 if t == "ИИ" else 14, t == "ИИ"))
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._btn_style(b)
        return b

    def _btn_style(self, b):
        b.setStyleSheet(f"""
            QPushButton {{ background: {Theme.CARD}; border: 1px solid {Theme.BORDER};
                border-radius: 18px; color: {Theme.TEXT}; }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; }}
        """)

    def _hdr(self):
        self.header.setStyleSheet(f"QFrame {{ background: {Theme.HEADER}; border-bottom: 1px solid {Theme.BORDER}; }}")

    def _search_style(self):
        self.search.setStyleSheet(f"""
            QLineEdit {{ background: {Theme.CARD}; color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER}; border-radius: 18px; padding: 0 16px; }}
            QLineEdit:focus {{ border: 2px solid {Theme.BLUE}; }}
        """)

    def _list_style(self):
        self.news_list.setStyleSheet(f"""
            QListView {{ background: transparent; border: none; }}
            QScrollBar:vertical {{ width: 12px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {Theme.SCROLL_HANDLE}; border-radius: 6px; min-height: 40px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def apply_theme(self):
        self._hdr()
        self._search_style()
        self._list_style()
        self.channel_title.setStyleSheet(f"color: {Theme.TEXT};")
        self.count_label.setStyleSheet(f"color: {Theme.SUBTEXT};")
        self.placeholder.setStyleSheet(f"color: {Theme.SUBTEXT};")
        for b in (self.ai_btn, self.refresh_btn, self.mark_all_btn, self.sound_btn, self.theme_btn, self.settings_btn):
            self._btn_style(b)
        self.theme_btn.setFont(emoji_font(14))
        self.theme_btn.setText("☀" if Theme.name == "dark" else "🌙")
        self.ai_btn.setFont(font_s(12, True))
        self.mark_all_btn.setFont(font_s(10, True))
        self.news_delegate.clear_cache()
        self.news_list.viewport().update()
        self.update()

    def _scroll(self, v):
        if self._loading:
            return
        bar = self.news_list.verticalScrollBar()
        if bar.maximum() > 0 and v >= bar.maximum() * 0.85 and self.news_model.hasMore():
            self._loading = True
            self.loadMoreRequested.emit()
            QTimer.singleShot(150, lambda: setattr(self, "_loading", False))

    def _news_menu(self, pos):
        idx = self.news_list.indexAt(pos)
        if not idx.isValid():
            return
        news = idx.data(Qt.UserRole)
        if not news:
            return
        m = QMenu()
        m.setStyleSheet(f"QMenu {{ background: {Theme.CARD}; color: {Theme.TEXT}; border: 1px solid {Theme.BORDER}; }}")
        a = QAction("Скопировать", self)
        a.triggered.connect(lambda: QApplication.clipboard().setText(f"{news.channel}\n{news.title}\n{news.text}"))
        m.addAction(a)
        m.exec_(self.news_list.viewport().mapToGlobal(pos))

    def set_sound_icon(self, en):
        self.sound_btn.setFont(emoji_font(14))
        self.sound_btn.setText("🔊" if en else "🔇")

    def paintEvent(self, e):
        p = QPainter(self)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, QColor(Theme.BG_GRAD_TOP))
        g.setColorAt(1, QColor(Theme.BG_GRAD_BOTTOM))
        p.fillRect(self.rect(), g)

    def showNewsPage(self, news, total, scroll_top=True):
        self.news_list.show()
        self.placeholder.hide()
        self.news_delegate.clear_cache()
        self.news_model.reset_page(news, total)
        if scroll_top:
            QTimer.singleShot(0, self.news_list.scrollToTop)

    def appendNewsPage(self, more):
        self.news_model.append_page(more)

    def showPlaceholder(self):
        self.news_list.hide()
        self.placeholder.show()
        self.news_model.clear()

    def setChannelInfo(self, name, count):
        self.channel_title.setText(name)
        self.count_label.setText(str(count))

    def set_font_size(self, size):
        self.news_delegate.font_size = size
        self.news_delegate.clear_cache()
        self.news_list.scheduleDelayedItemsLayout()


# ---------------------------------------------------------------------------
# Settings dialog (connection + channels)
# ---------------------------------------------------------------------------


class SettingsDialog(QDialog):
    def __init__(self, channels: List[str], settings: Settings, storage: NewsStorage, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.storage = storage
        self.setWindowTitle("Настройки")
        self.setMinimumSize(640, 560)
        # Единый stylesheet для тёмной/светлой темы (лейблы, чекбоксы, спинбоксы, комбо)
        self.setStyleSheet(f"""
            QDialog {{
                background: {Theme.WINDOW};
                color: {Theme.TEXT};
            }}
            QWidget {{
                color: {Theme.TEXT};
                background: transparent;
            }}
            QLabel {{
                color: {Theme.TEXT};
                background: transparent;
            }}
            QCheckBox {{
                color: {Theme.TEXT};
                background: transparent;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid {Theme.BORDER};
                border-radius: 3px;
                background: {Theme.CARD};
            }}
            QCheckBox::indicator:checked {{
                background: {Theme.BLUE};
                border: 1px solid {Theme.BLUE};
            }}
            QLineEdit, QSpinBox, QComboBox {{
                background: {Theme.CARD};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 6px;
                padding: 6px;
                min-height: 22px;
            }}
            QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
                color: {Theme.SUBTEXT};
                background: {Theme.WINDOW};
            }}
            QComboBox QAbstractItemView {{
                background: {Theme.CARD};
                color: {Theme.TEXT};
                selection-background-color: {Theme.CARD_ACTIVE};
                border: 1px solid {Theme.BORDER};
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                background: {Theme.CARD_HOVER};
                border: none;
                width: 18px;
            }}
            QTabWidget::pane {{
                border: 1px solid {Theme.BORDER};
                background: {Theme.WINDOW};
                top: -1px;
            }}
            QTabBar::tab {{
                background: {Theme.CARD};
                color: {Theme.TEXT};
                padding: 8px 16px;
                border: 1px solid {Theme.BORDER};
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {Theme.CARD_ACTIVE};
                color: {Theme.TEXT};
            }}
            QTabBar::tab:!selected {{
                margin-top: 2px;
                color: {Theme.SUBTEXT};
            }}
            QTableWidget {{
                background: {Theme.CARD};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                gridline-color: {Theme.BORDER};
                outline: none;
            }}
            QTableWidget::item {{
                color: {Theme.TEXT};
                padding: 4px;
            }}
            QHeaderView::section {{
                background: {Theme.CARD_HOVER};
                color: {Theme.SUBTEXT};
                border: none;
                border-bottom: 1px solid {Theme.BORDER};
                padding: 6px;
            }}
            QPushButton {{
                background: {Theme.CARD};
                color: {Theme.TEXT};
                border: 1px solid {Theme.BORDER};
                border-radius: 10px;
                padding: 8px 16px;
            }}
            QPushButton:hover {{
                background: {Theme.CARD_HOVER};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # --- Connection tab ---
        conn_w = QWidget()
        cf = QFormLayout(conn_w)
        cf.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cf.setSpacing(10)
        self.server_edit = QLineEdit(settings.mssql_server)
        self.db_edit = QLineEdit(settings.mssql_database)
        self.auth_combo = QComboBox()
        self.auth_combo.addItems(["Windows (домен / Trusted)", "SQL Server (логин/пароль)"])
        self.auth_combo.setCurrentIndex(0 if settings.mssql_auth == "windows" else 1)
        self.user_edit = QLineEdit(settings.mssql_user)
        self.pass_edit = QLineEdit(settings.mssql_password)
        self.pass_edit.setEchoMode(QLineEdit.Password)
        self.driver_edit = QLineEdit(settings.mssql_driver)
        self.userid_edit = QLineEdit(settings.user_id)
        self.auth_combo.currentIndexChanged.connect(self._auth_changed)

        def _form_label(text: str) -> QLabel:
            lab = QLabel(text)
            lab.setStyleSheet(f"color: {Theme.TEXT}; background: transparent;")
            return lab

        cf.addRow(_form_label("Сервер (IP\\имя):"), self.server_edit)
        cf.addRow(_form_label("База данных:"), self.db_edit)
        cf.addRow(_form_label("Аутентификация:"), self.auth_combo)
        cf.addRow(_form_label("SQL логин:"), self.user_edit)
        cf.addRow(_form_label("Пароль:"), self.pass_edit)
        cf.addRow(_form_label("ODBC Driver:"), self.driver_edit)
        cf.addRow(_form_label("Ваш user_id (прочитано):"), self.userid_edit)
        hint = QLabel(
            "Windows: Trusted_Connection, логин SQL не нужен.\n"
            "SQL: укажите UID/PWD.\n"
            "Driver: «SQL Server» или «SQL Server Native Client 10.0»."
        )
        hint.setStyleSheet(f"color: {Theme.SUBTEXT}; background: transparent;")
        hint.setWordWrap(True)
        cf.addRow(hint)
        test_btn = QPushButton("Проверить подключение")
        test_btn.setStyleSheet(
            f"QPushButton {{ background: {Theme.BLUE}; color: white; border: none; "
            f"border-radius: 8px; padding: 8px 16px; }}"
            f"QPushButton:hover {{ background: #2a7fd4; }}"
        )
        test_btn.clicked.connect(self._test)
        self.test_label = QLabel("")
        self.test_label.setWordWrap(True)
        self.test_label.setStyleSheet(f"color: {Theme.SUBTEXT}; background: transparent;")
        cf.addRow(test_btn)
        cf.addRow(self.test_label)
        self._auth_changed(self.auth_combo.currentIndex())
        tabs.addTab(conn_w, "Подключение")

        # --- Channels tab ---
        ch_w = QWidget()
        chl = QVBoxLayout(ch_w)
        self.ch_search = QLineEdit()
        self.ch_search.setPlaceholderText("Поиск каналов...")
        self.ch_search.textChanged.connect(self._filter_ch)
        chl.addWidget(self.ch_search)
        self.table = QTableWidget(len(channels), 3)
        self.table.setHorizontalHeaderLabels(["Канал", "Показ", "Трей"])
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cb_show, self.cb_notify = {}, {}
        for row, name in enumerate(channels):
            item = QTableWidgetItem(name)
            item.setForeground(QColor(Theme.TEXT))
            self.table.setItem(row, 0, item)
            for col, checked, store in (
                (1, settings.is_show(name), self.cb_show),
                (2, settings.is_notify(name), self.cb_notify),
            ):
                cb = QCheckBox()
                cb.setChecked(checked)
                w = QWidget()
                w.setStyleSheet("background: transparent;")
                l = QHBoxLayout(w)
                l.addWidget(cb)
                l.setAlignment(Qt.AlignCenter)
                l.setContentsMargins(0, 0, 0, 0)
                self.table.setCellWidget(row, col, w)
                store[name] = cb
            self.cb_notify[name].setEnabled(self.cb_show[name].isChecked())
            self.cb_show[name].toggled.connect(
                lambda checked, n=name: self._channel_show_toggled(n, checked)
            )
        chl.addWidget(self.table)
        tabs.addTab(ch_w, "Каналы")

        # --- General ---
        gen = QWidget()
        gl = QVBoxLayout(gen)
        gl.setSpacing(12)
        self.notify_cb = QCheckBox("Трей-уведомления")
        self.notify_cb.setChecked(settings.notifications_enabled)
        self.sound_cb = QCheckBox("Звук")
        self.sound_cb.setChecked(settings.sound_enabled)
        gl.addWidget(self.notify_cb)
        gl.addWidget(self.sound_cb)
        row = QHBoxLayout()
        row.addWidget(_form_label("Тема"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Тёмная", "Светлая"])
        self.theme_combo.setCurrentIndex(0 if settings.theme == "dark" else 1)
        row.addWidget(self.theme_combo)
        row.addStretch()
        gl.addLayout(row)
        row2 = QHBoxLayout()
        row2.addWidget(_form_label("Шрифт"))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(10, 30)
        self.font_spin.setValue(settings.font_size)
        row2.addWidget(self.font_spin)
        row2.addStretch()
        gl.addLayout(row2)
        row3 = QHBoxLayout()
        row3.addWidget(_form_label("Опрос БД (сек)"))
        self.poll_spin = QSpinBox()
        self.poll_spin.setRange(1, 120)
        self.poll_spin.setValue(settings.poll_interval_sec)
        row3.addWidget(self.poll_spin)
        row3.addStretch()
        gl.addLayout(row3)
        gl.addStretch()
        tabs.addTab(gen, "Основные")

        btns = QHBoxLayout()
        btns.addStretch()
        save = QPushButton("Сохранить")
        save.setStyleSheet(
            f"QPushButton {{ background: {Theme.BLUE}; color: white; border: none; "
            f"border-radius: 12px; padding: 8px 20px; }}"
            f"QPushButton:hover {{ background: #2a7fd4; }}"
        )
        save.clicked.connect(self._save)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        btns.addWidget(save)
        btns.addWidget(cancel)
        layout.addLayout(btns)

    def _auth_changed(self, idx):
        sql_mode = idx == 1
        self.user_edit.setEnabled(sql_mode)
        self.pass_edit.setEnabled(sql_mode)

    def _filter_ch(self, text):
        t = text.strip().lower()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            self.table.setRowHidden(row, t not in (item.text().lower() if item else ""))

    def _test(self):
        # временно применить поля, тест в фоне (QThread)
        self._apply_conn_fields()
        self.storage._working_driver = None
        self.test_label.setText("Подключение…")
        self.test_label.setStyleSheet(f"color: {Theme.SUBTEXT}; background: transparent;")

        task = DbTask(self.settings, "test", parent=self)

        def on_ok(_op, result):
            ok, msg, drv = result
            self.test_label.setText(("✓ " if ok else "✗ ") + msg)
            self.test_label.setStyleSheet(
                f"color: {'#4eae5c' if ok else Theme.RED}; background: transparent;"
            )
            if ok and drv:
                self.driver_edit.setText(drv)
                self.settings.mssql_driver = drv
                self.storage._working_driver = drv


        def on_err(_op, msg):
            self.test_label.setText("✗ " + msg)
            self.test_label.setStyleSheet(f"color: {Theme.RED}; background: transparent;")

        task.finished_ok.connect(on_ok)
        task.failed.connect(on_err)
        # QThread нельзя удалять из finished_ok/failed: эти сигналы испускаются
        # ещё внутри run(), то есть рабочий поток в этот момент всё ещё жив.
        def test_finished():
            if self._test_task is task:
                self._test_task = None
            task.deleteLater()

        task.finished.connect(test_finished)
        task.start()
        self._test_task = task

    def _channel_show_toggled(self, name: str, checked: bool):
        notify = self.cb_notify.get(name)
        if notify is not None:
            notify.setEnabled(checked)
            if not checked:
                notify.setChecked(False)

    def _apply_conn_fields(self):
        self.settings.mssql_server = self.server_edit.text().strip()
        self.settings.mssql_database = self.db_edit.text().strip() or "TelegramNews"
        self.settings.mssql_auth = "windows" if self.auth_combo.currentIndex() == 0 else "sql"
        self.settings.mssql_user = self.user_edit.text().strip()
        self.settings.mssql_password = self.pass_edit.text()
        self.settings.mssql_driver = self.driver_edit.text().strip() or "SQL Server"
        self.settings.user_id = self.userid_edit.text().strip()

    def _save(self):
        self._apply_conn_fields()
        if not self.settings.user_id:
            QMessageBox.warning(self, "Имя пользователя", "Укажите свой ник для индивидуальной настройки.")
            self.userid_edit.setFocus()
            return
        for name, cb in self.cb_show.items():
            show = cb.isChecked()
            notify = self.cb_notify[name].isChecked() if show else False
            self.settings.set_channel(name, show, notify, True)
        self.settings.notifications_enabled = self.notify_cb.isChecked()
        self.settings.sound_enabled = self.sound_cb.isChecked()
        self.settings.theme = "dark" if self.theme_combo.currentIndex() == 0 else "light"
        self.settings.font_size = self.font_spin.value()
        self.settings.poll_interval_sec = self.poll_spin.value()
        self.settings.save()
        self.storage.close()
        self.accept()


# ---------------------------------------------------------------------------
# AI mode
# ---------------------------------------------------------------------------


class AIConfig:
    DEFAULTS = {
        "base_url": "http://127.0.0.1:3000",
        "api_path": "/api/chat/completions",
        "token": "",
        "model": "",
        "username": "",
        "timeout_sec": 120,
        "max_news": 500,
        "max_chars": 120000,
    }

    def __init__(self, filename: Path = II_CONFIG_FILE):
        self.filename = Path(filename)
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        if not self.filename.exists():
            return
        try:
            raw = json.loads(self.filename.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for k in self.DEFAULTS:
                    if k in raw:
                        self.data[k] = raw[k]
        except Exception:
            pass

    def save(self):
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.filename.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class PromptStore:
    BUILTIN = {
        "Краткая сводка": (
            "Сделай краткую, структурированную сводку новостей. Объедини дубли, "
            "выдели главное, укажи каналы и не придумывай факты, которых нет в исходных сообщениях."
        ),
        "Важное и риски": (
            "Проанализируй новости, выдели наиболее важные события, потенциальные риски, "
            "что требует внимания в первую очередь. Для каждого вывода укажи, на каких сообщениях он основан."
        ),
    }

    def __init__(self, filename: Path = PROMPTS_FILE):
        self.filename = Path(filename)
        self.custom: Dict[str, str] = {}
        self.load()

    def load(self):
        if not self.filename.exists():
            return
        try:
            raw = json.loads(self.filename.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self.custom = {str(k): str(v) for k, v in raw.items() if str(k).strip()}
        except Exception:
            self.custom = {}

    def save(self):
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        self.filename.write_text(
            json.dumps(self.custom, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def all(self) -> Dict[str, str]:
        out = dict(self.BUILTIN)
        out.update(self.custom)
        return out


class AIRequestTask(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, config: dict, system_prompt: str, user_text: str, parent=None):
        super().__init__(parent)
        self.config = dict(config)
        self.system_prompt = system_prompt
        self.user_text = user_text
        self._cancel_event = threading.Event()
        self._conn = None

    def cancel(self):
        self._cancel_event.set()
        conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def run(self):
        if self._cancel_event.is_set():
            self.cancelled.emit()
            return
        try:
            base = str(self.config.get("base_url", "")).strip().rstrip("/")
            path = str(self.config.get("api_path", "/api/chat/completions")).strip()
            if not path.startswith("/"):
                path = "/" + path
            # Можно указать как http://12345.88:3000, так и 12345.88:3000.
            # Для Open WebUI обычно используется OpenAI-compatible endpoint.
            if "://" not in base:
                base = "http://" + base
                parsed = urlparse(base)
            else:
                parsed = urlparse(base)
            if parsed.scheme not in ("http", "https") or not parsed.hostname:
                raise RuntimeError("Некорректный адрес ИИ-сервера. Пример: http://12345.88:3000")
            prefix = parsed.path.rstrip("/")
            full_path = prefix + path
            timeout = max(5, int(self.config.get("timeout_sec", 120) or 120))
            conn_cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
            self._conn = conn_cls(parsed.hostname, parsed.port, timeout=timeout)

            payload = {
                "model": str(self.config.get("model", "")).strip(),
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": self.user_text},
                ],
                "stream": False,
            }
            if not payload["model"]:
                raise RuntimeError("Не указано имя модели")
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            token = str(self.config.get("token", "")).strip()
            if token:
                headers["Authorization"] = "Bearer " + token
            username = str(self.config.get("username", "")).strip()
            if username:
                headers["X-User-Name"] = username

            self._conn.request("POST", full_path, body=body, headers=headers)
            if self._cancel_event.is_set():
                self.cancelled.emit()
                return
            response = self._conn.getresponse()
            raw = response.read()
            if self._cancel_event.is_set():
                self.cancelled.emit()
                return
            text = raw.decode("utf-8", errors="replace")
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"HTTP {response.status}: {text[:1200]}")
            data = json.loads(text)
            answer = ""
            try:
                answer = data["choices"][0]["message"]["content"]
            except Exception:
                # Open WebUI / Ollama-compatible ответы могут иметь другую форму.
                answer = data.get("response") or data.get("message") or data.get("content") or ""
                if isinstance(answer, dict):
                    answer = answer.get("content") or answer.get("text") or ""
            if not str(answer).strip():
                raise RuntimeError("Сервер вернул ответ без текста")
            self.finished_ok.emit(str(answer))
        except Exception as e:
            if self._cancel_event.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(e))
        finally:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
            self._conn = None


class AIModeDialog(QDialog):
    def __init__(self, storage: NewsStorage, parent=None):
        super().__init__(parent)
        self.storage = storage
        self.config = AIConfig()
        self.prompts = PromptStore()
        self._db_task: Optional[DbTask] = None
        self._ai_task: Optional[AIRequestTask] = None
        self._channel_selection_initialized = False
        self._answer_raw_text = ""
        self._answer_font_size = max(10, min(22, int(self.config.data.get("answer_font_size", 13) or 13)))
        self.setWindowTitle("Режим ИИ")
        self.resize(1100, 760)
        self.setMinimumSize(900, 620)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        # Не даём Qt отрисовать окно промежуточным системным стилем.
        # На первом открытии это особенно заметно в тёмной теме Windows.
        self.setUpdatesEnabled(False)
        self._build_ui()
        self.apply_theme()
        self._load_config_ui()
        self._reload_prompts()
        self._load_channels()
        # Переполируем окно уже после полной установки QSS/palette.
        try:
            self.style().unpolish(self)
            self.style().polish(self)
            self.ensurePolished()
        except Exception:
            pass
        self.setUpdatesEnabled(True)
        self.update()
        self.repaint()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)

        # Левая панель содержит много настроек и не должна обрезаться при
        # уменьшении высоты окна. Раньше QSplitter пытался впихнуть весь
        # вертикальный layout в доступную область, из-за чего нижняя часть
        # блоков/текста визуально обрезалась. Теперь левая часть прокручивается.
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 8, 0)
        ll.setSpacing(10)

        cfg = QGroupBox("Подключение ИИ")
        form = QFormLayout(cfg)
        self.url_edit = QLineEdit()
        self.path_edit = QLineEdit()
        self.model_edit = QLineEdit()
        self.user_edit = QLineEdit()
        self.token_edit = QLineEdit()
        self.token_edit.setEchoMode(QLineEdit.Password)
        form.addRow("Адрес:", self.url_edit)
        form.addRow("API path:", self.path_edit)
        form.addRow("Модель:", self.model_edit)
        form.addRow("Пользователь:", self.user_edit)
        form.addRow("Токен:", self.token_edit)
        self.save_cfg_btn = QPushButton("Сохранить подключение")
        self.save_cfg_btn.clicked.connect(self._save_config_ui)
        form.addRow(self.save_cfg_btn)
        ll.addWidget(cfg)

        # Интервал анализа — отдельный блок, расположенный ВЫШЕ списка каналов.
        # Он больше не является частью области "Новости" и не может залезать на QListWidget.
        interval_box = QGroupBox("Интервал анализа")
        il = QHBoxLayout(interval_box)
        il.setContentsMargins(10, 8, 10, 8)
        il.setSpacing(8)
        il.addWidget(QLabel("Брать новости за последние:"))
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(1, 720)
        self.interval_spin.setValue(1)
        self.interval_spin.setMinimumWidth(80)
        self.interval_unit = QComboBox()
        self.interval_unit.addItems(["минут", "часов", "дней"])
        self.interval_unit.setCurrentIndex(1)
        self.interval_unit.setMinimumWidth(95)
        il.addWidget(self.interval_spin)
        il.addWidget(self.interval_unit)
        il.addStretch(1)
        ll.addWidget(interval_box)

        source = QGroupBox("Новости")
        sl = QVBoxLayout(source)
        self.channel_search = QLineEdit()
        self.channel_search.setPlaceholderText("Поиск канала…")
        self.channel_search.setClearButtonEnabled(True)
        self.channel_search.textChanged.connect(self._filter_channels)
        sl.addWidget(self.channel_search)
        self.channels_list = QListWidget()
        self.channels_list.setMinimumHeight(130)
        self.channels_list.itemChanged.connect(self._channel_selection_changed)
        limit_row = QHBoxLayout()
        limit_note = QLabel("Каналов за один запрос: от 1 до 3")
        limit_note.setStyleSheet(f"color: {Theme.SUBTEXT}; background: transparent;")
        self.channel_count_label = QLabel("0/3")
        self.channel_count_label.setStyleSheet(f"color: {Theme.SUBTEXT}; background: transparent;")
        limit_row.addWidget(limit_note)
        limit_row.addStretch()
        limit_row.addWidget(self.channel_count_label)
        sl.addLayout(limit_row)
        sl.addWidget(self.channels_list)
        ll.addWidget(source, 1)

        prompt_box = QGroupBox("Промт")
        pl = QVBoxLayout(prompt_box)
        pr = QHBoxLayout()
        self.prompt_combo = QComboBox()
        self.prompt_combo.currentTextChanged.connect(self._prompt_selected)
        self.save_prompt_btn = QPushButton("Сохранить как…")
        self.delete_prompt_btn = QPushButton("Удалить свой")
        self.save_prompt_btn.clicked.connect(self._save_prompt)
        self.delete_prompt_btn.clicked.connect(self._delete_prompt)
        pr.addWidget(self.prompt_combo, 1)
        pr.addWidget(self.save_prompt_btn)
        pr.addWidget(self.delete_prompt_btn)
        pl.addLayout(pr)
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setMinimumHeight(150)
        pl.addWidget(self.prompt_edit)
        ll.addWidget(prompt_box, 1)

        actions = QHBoxLayout()
        self.run_btn = QPushButton("Запустить")
        self.cancel_btn = QPushButton("Отмена")
        self.cancel_btn.setEnabled(False)
        self.run_btn.clicked.connect(self._run)
        self.cancel_btn.clicked.connect(self._cancel)
        actions.addWidget(self.run_btn)
        actions.addWidget(self.cancel_btn)
        actions.addStretch()
        ll.addLayout(actions)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(QLabel("Ответ ИИ"))
        top.addStretch()
        self.font_minus_btn = QPushButton("A−")
        self.font_plus_btn = QPushButton("A+")
        self.font_minus_btn.setToolTip("Уменьшить шрифт ответа")
        self.font_plus_btn.setToolTip("Увеличить шрифт ответа")
        self.font_minus_btn.clicked.connect(lambda: self._change_answer_font(-1))
        self.font_plus_btn.clicked.connect(lambda: self._change_answer_font(1))
        self.copy_btn = QPushButton("Копировать")
        self.reset_btn = QPushButton("Сброс")
        self.copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self._answer_raw_text or self.answer.toPlainText()))
        self.reset_btn.clicked.connect(self._reset)
        top.addWidget(self.font_minus_btn)
        top.addWidget(self.font_plus_btn)
        top.addWidget(self.copy_btn)
        top.addWidget(self.reset_btn)
        rl.addLayout(top)
        self.answer = QTextBrowser()
        self.answer.setOpenExternalLinks(False)
        self.answer.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        self.answer.setWordWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        rl.addWidget(self.answer, 1)
        self.status = QLabel("Готово")
        self.status.setWordWrap(True)
        rl.addWidget(self.status)

        # Скроллируем только левую панель. Правая область с ответом ИИ
        # всегда получает всё оставшееся место и сама корректно ужимается.
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        left_scroll.setWidget(left)

        splitter.addWidget(left_scroll)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([430, 670])
        root.addWidget(splitter, 1)

    def _set_ai_palette(self, widget: QWidget, text: Optional[str] = None):
        """Принудительно задаёт палитру конкретному виджету.

        Одного QSS недостаточно на Windows: QGroupBox::title, текст QComboBox,
        элементы popup и некоторые QPushButton могут брать foreground из системной
        палитры. Поэтому для AI-окна одновременно задаём QSS и QPalette.
        """
        pal = widget.palette()
        pal.setColor(QPalette.Window, QColor(Theme.WINDOW))
        pal.setColor(QPalette.Base, QColor(Theme.CARD))
        pal.setColor(QPalette.AlternateBase, QColor(Theme.CARD_HOVER))
        pal.setColor(QPalette.Button, QColor(Theme.CARD))
        pal.setColor(QPalette.Text, QColor(text or Theme.TEXT))
        pal.setColor(QPalette.WindowText, QColor(text or Theme.TEXT))
        pal.setColor(QPalette.ButtonText, QColor(text or Theme.TEXT))
        pal.setColor(QPalette.Highlight, QColor(Theme.CARD_ACTIVE))
        pal.setColor(QPalette.HighlightedText, QColor(Theme.TEXT))
        pal.setColor(QPalette.PlaceholderText, QColor(Theme.SUBTEXT))
        pal.setColor(QPalette.Disabled, QPalette.Text, QColor(Theme.SUBTEXT))
        pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(Theme.SUBTEXT))
        pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(Theme.SUBTEXT))
        widget.setPalette(pal)

    def apply_theme(self):
        """Полностью фиксирует тему AI-окна, включая Windows/system palette."""
        text = Theme.TEXT
        subtext = Theme.SUBTEXT
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background: {Theme.WINDOW}; color: {text}; }}
            QDialog * {{ color: {text}; }}
            QLabel {{ color: {text}; background: transparent; }}
            QGroupBox {{
                color: {text}; background: transparent;
                border: 1px solid {Theme.BORDER}; border-radius: 8px;
                margin-top: 10px;
            }}
            QGroupBox::title {{
                color: {text}; background: {Theme.WINDOW};
                subcontrol-origin: margin; left: 10px; padding: 0 5px;
            }}
            QFormLayout QLabel {{ color: {text}; }}
            QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser {{
                background: {Theme.CARD}; color: {text};
                selection-background-color: {Theme.BLUE};
                selection-color: #ffffff;
                border: 1px solid {Theme.BORDER}; border-radius: 8px; padding: 6px;
            }}
            QComboBox, QSpinBox {{
                background: {Theme.CARD}; color: {text};
                selection-background-color: {Theme.CARD_ACTIVE};
                selection-color: {text};
                border: 1px solid {Theme.BORDER}; border-radius: 8px; padding: 5px 7px;
            }}
            QComboBox QAbstractItemView {{
                background: {Theme.CARD}; color: {text};
                selection-background-color: {Theme.CARD_ACTIVE};
                selection-color: {text};
                border: 1px solid {Theme.BORDER};
            }}
            QAbstractItemView::item {{
                color: {text}; background: {Theme.CARD};
            }}
            QAbstractItemView::item:selected {{
                color: {text}; background: {Theme.CARD_ACTIVE};
            }}
            QMenu {{
                background: {Theme.CARD}; color: {text};
                border: 1px solid {Theme.BORDER};
            }}
            QMenu::item:selected {{
                background: {Theme.CARD_ACTIVE}; color: {text};
            }}
            QListWidget {{
                background: {Theme.CARD}; color: {text};
                border: 1px solid {Theme.BORDER};
            }}
            QListWidget::item:selected {{
                background: {Theme.CARD_ACTIVE}; color: {text};
            }}
            QPushButton {{
                background: {Theme.CARD}; color: {text};
                border: 1px solid {Theme.BORDER}; border-radius: 8px; padding: 6px 10px;
            }}
            QPushButton:hover {{ background: {Theme.CARD_HOVER}; color: {text}; }}
            QPushButton:pressed {{ background: {Theme.CARD_ACTIVE}; color: {text}; }}
            QPushButton:disabled {{ color: {subtext}; }}
        """)

        # Сначала применяем палитру к каждому реальному виджету. Это устраняет
        # чёрный системный текст даже там, где Windows/Qt игнорирует QSS.
        for child in self.findChildren(QWidget):
            self._set_ai_palette(child)

        # GroupBox title не является дочерним QLabel — отдельно закрепляем его
        # через QSS и палитру самого QGroupBox.
        for group in self.findChildren(QGroupBox):
            self._set_ai_palette(group)

        # Явные типы, которые особенно часто сохраняют старый foreground.
        for child in self.findChildren(QLabel):
            child.setStyleSheet(f"color: {text}; background: transparent;")
            self._set_ai_palette(child)

        for child in (
            self.url_edit, self.path_edit, self.model_edit, self.user_edit,
            self.token_edit, self.prompt_edit, self.answer, self.channels_list,
            self.channel_search, self.channel_count_label, self.prompt_combo,
            self.interval_spin, self.interval_unit, self.save_cfg_btn,
            self.save_prompt_btn, self.delete_prompt_btn, self.run_btn,
            self.cancel_btn, self.font_minus_btn, self.font_plus_btn,
            self.copy_btn, self.reset_btn,
        ):
            self._set_ai_palette(child)

        self.status.setStyleSheet(f"color: {subtext}; background: transparent;")
        self._set_ai_palette(self.status, subtext)

    def _load_config_ui(self):
        d = self.config.data
        self.url_edit.setText(str(d.get("base_url", "")))
        self.path_edit.setText(str(d.get("api_path", "/api/chat/completions")))
        self.model_edit.setText(str(d.get("model", "")))
        self.user_edit.setText(str(d.get("username", "")))
        self.token_edit.setText(str(d.get("token", "")))

    def _save_config_ui(self):
        self.config.data.update({
            "base_url": self.url_edit.text().strip(),
            "api_path": self.path_edit.text().strip() or "/api/chat/completions",
            "model": self.model_edit.text().strip(),
            "username": self.user_edit.text().strip(),
            "token": self.token_edit.text().strip(),
            "answer_font_size": self._answer_font_size,
        })
        self.config.save()
        self.status.setText(f"Настройки сохранены: {II_CONFIG_FILE}")

    def _load_channels(self):
        # Повторное открытие AI-окна не должно сбрасывать выбор пользователя.
        selected_before = set(self._selected_channels()) if self._channel_selection_initialized else set()
        self.channels_list.blockSignals(True)
        self.channels_list.clear()
        visible_names = [
            ch.name for ch in self.storage.channels
            if self.storage.settings.is_show(ch.name)
        ]
        for idx, name in enumerate(visible_names):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            if self._channel_selection_initialized:
                checked = name in selected_before
            else:
                checked = idx < 3
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self.channels_list.addItem(item)
        self.channels_list.blockSignals(False)
        self._channel_selection_initialized = True
        self._filter_channels(self.channel_search.text() if hasattr(self, "channel_search") else "")
        self._update_channel_count()

    def _filter_channels(self, text: str):
        needle = (text or "").strip().casefold()
        for i in range(self.channels_list.count()):
            item = self.channels_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

    def _update_channel_count(self):
        count = len(self._selected_channels())
        self.channel_count_label.setText(f"{count}/3")

    def _reload_prompts(self, select_name: Optional[str] = None):
        self.prompt_combo.blockSignals(True)
        self.prompt_combo.clear()
        for name in self.prompts.all().keys():
            self.prompt_combo.addItem(name)
        if select_name:
            i = self.prompt_combo.findText(select_name)
            if i >= 0:
                self.prompt_combo.setCurrentIndex(i)
        self.prompt_combo.blockSignals(False)
        self._prompt_selected(self.prompt_combo.currentText())

    def _prompt_selected(self, name: str):
        text = self.prompts.all().get(name, "")
        self.prompt_edit.setPlainText(text)
        self.delete_prompt_btn.setEnabled(name in self.prompts.custom)

    def _save_prompt(self):
        text = self.prompt_edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "Промт", "Промт пустой.")
            return
        name, ok = QInputDialog.getText(self, "Сохранить промт", "Название:")
        name = name.strip()
        if not ok or not name:
            return
        if name in PromptStore.BUILTIN:
            QMessageBox.warning(self, "Промт", "Это имя занято стандартным промтом.")
            return
        self.prompts.custom[name] = text
        self.prompts.save()
        self._reload_prompts(name)

    def _delete_prompt(self):
        name = self.prompt_combo.currentText()
        if name not in self.prompts.custom:
            return
        del self.prompts.custom[name]
        self.prompts.save()
        self._reload_prompts()

    def _channel_selection_changed(self, changed_item):
        if changed_item.checkState() == Qt.Checked:
            checked = [
                self.channels_list.item(i)
                for i in range(self.channels_list.count())
                if self.channels_list.item(i).checkState() == Qt.Checked
            ]
            if len(checked) > 3:
                self.channels_list.blockSignals(True)
                changed_item.setCheckState(Qt.Unchecked)
                self.channels_list.blockSignals(False)
                self.status.setText("Можно выбрать не более 3 каналов.")
        self._update_channel_count()

    def _selected_channels(self) -> List[str]:
        out = []
        for i in range(self.channels_list.count()):
            item = self.channels_list.item(i)
            if item.checkState() == Qt.Checked:
                out.append(item.text())
        return out

    def _interval_seconds(self) -> int:
        mult = (60, 3600, 86400)[self.interval_unit.currentIndex()]
        return self.interval_spin.value() * mult

    def _set_busy(self, busy: bool, status: str = ""):
        self.run_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        if status:
            self.status.setText(status)

    def _run(self):
        if self._db_task or self._ai_task:
            return
        channels = self._selected_channels()
        prompt = self.prompt_edit.toPlainText().strip()
        if not channels:
            QMessageBox.warning(self, "Режим ИИ", "Выберите хотя бы один канал.")
            return
        if not prompt:
            QMessageBox.warning(self, "Режим ИИ", "Введите промт.")
            return
        self._save_config_ui()
        if not self.config.data.get("base_url") or not self.config.data.get("model"):
            QMessageBox.warning(self, "Режим ИИ", "Укажите адрес сервера и модель.")
            return
        now = time.time()
        self._set_busy(True, "Получаю новости из БД…")
        task = DbTask(
            self.storage.settings,
            "ai_news",
            {
                "channels": channels,
                "since_ts": now - self._interval_seconds(),
                "until_ts": now,
                "limit": int(self.config.data.get("max_news", 500) or 500),
            },
            parent=self,
        )
        self._db_task = task

        def ok(_op, news):
            if not news:
                self._set_busy(False, "За выбранный интервал новостей нет.")
                return
            max_chars = max(10000, int(self.config.data.get("max_chars", 120000) or 120000))
            chunks = []
            used = 0
            for n in news:
                block = f"[{n.date}] [{n.channel}]\n{n.title}\n{n.text}\n"
                if used + len(block) > max_chars:
                    break
                chunks.append(block)
                used += len(block)
            user_text = (
                f"Ниже новости за выбранный интервал. Сообщений загружено: {len(news)}. "
                f"В запрос вошло: {len(chunks)}.\n\n" + "\n---\n".join(chunks)
            )
            self._start_ai(prompt, user_text)

        def err(_op, msg):
            self._set_busy(False, "Ошибка БД: " + msg)

        task.finished_ok.connect(ok)
        task.failed.connect(err)
        def db_finished():
            if self._db_task is task:
                self._db_task = None
            task.deleteLater()
        task.finished.connect(db_finished)
        task.start()

    def _start_ai(self, prompt: str, user_text: str):
        self._set_busy(True, "Отправляю запрос ИИ…")
        self.answer.clear()
        task = AIRequestTask(self.config.data, prompt, user_text, parent=self)
        self._ai_task = task

        def done(text):
            self._answer_raw_text = text or ""
            self._render_answer()
            self.status.setText("Ответ получен.")
            self._set_busy(False)

        def failed(msg):
            self.status.setText("Ошибка ИИ: " + msg)
            self._set_busy(False)

        def cancelled():
            self.status.setText("Операция отменена.")
            self._set_busy(False)

        task.finished_ok.connect(done)
        task.failed.connect(failed)
        task.cancelled.connect(cancelled)
        # Удаление только после QThread.finished — после возврата из run().
        def ai_finished():
            if self._ai_task is task:
                self._ai_task = None
            task.deleteLater()

        task.finished.connect(ai_finished)
        task.start()

    def _cancel(self):
        if self._db_task is not None:
            # pyodbc нельзя безопасно terminate(). Отменяем обработку результата,
            # но НЕ удаляем QThread, пока run() не вернулся.
            task = self._db_task
            try:
                task.finished_ok.disconnect()
                task.failed.disconnect()
            except Exception:
                pass
            task.finished.connect(lambda: setattr(self, "_db_task", None))
            self._set_busy(False, "Получение данных отменено; текущий SQL-запрос завершится в фоне.")
            return
        if self._ai_task is not None:
            self.status.setText("Отменяю запрос…")
            self._ai_task.cancel()

    def _change_answer_font(self, delta: int):
        self._answer_font_size = max(10, min(22, self._answer_font_size + int(delta)))
        self.config.data["answer_font_size"] = self._answer_font_size
        try:
            self.config.save()
        except Exception:
            pass
        self._render_answer()
        self.status.setText(f"Размер шрифта ответа: {self._answer_font_size}")

    @staticmethod
    def _is_list_or_code_paragraph(text: str) -> bool:
        stripped = text.lstrip()
        prefixes = ("- ", "* ", "• ", "> ", "```", "    ")
        if stripped.startswith(prefixes):
            return True
        # Нумерованные списки: 1. / 1)
        head = stripped[:6]
        return any(head.startswith(f"{n}.") or head.startswith(f"{n})") for n in range(1, 10))

    def _render_answer(self):
        """Отрисовать ответ как читаемый документ без зависимости от Markdown API Qt."""
        text = (self._answer_raw_text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        self.answer.clear()
        if not text:
            return
        doc = self.answer.document()
        doc.setDocumentMargin(14)
        cursor = QTextCursor(doc)
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for idx, para in enumerate(paragraphs):
            # Одинарные переводы внутри абзаца сохраняем — полезно для списков/структурированных ответов.
            block = QTextBlockFormat()
            block.setTopMargin(2 if idx == 0 else 7)
            block.setBottomMargin(7)
            block.setLineHeight(135, QTextBlockFormat.ProportionalHeight)
            is_list = self._is_list_or_code_paragraph(para) or "\n- " in para or "\n• " in para
            short_heading = "\n" not in para and len(para) <= 70 and (para.endswith(":") or para.startswith("#"))
            if is_list or short_heading:
                block.setAlignment(Qt.AlignLeft)
                block.setTextIndent(0)
            else:
                block.setAlignment(Qt.AlignJustify)
                block.setTextIndent(22)
            cursor.setBlockFormat(block)
            char = QTextCharFormat()
            char.setForeground(QColor(Theme.TEXT))
            char.setFontPointSize(self._answer_font_size)
            if short_heading:
                char.setFontWeight(QFont.DemiBold)
            cursor.setCharFormat(char)
            clean = para.lstrip("# ") if short_heading else para
            cursor.insertText(clean)
            if idx < len(paragraphs) - 1:
                cursor.insertBlock()
        self.answer.moveCursor(QTextCursor.Start)

    def _reset(self):
        self._answer_raw_text = ""
        self.answer.clear()
        self.status.setText("Готово")

    def closeEvent(self, event):
        # Обычное закрытие только скрывает диалог (WA_DeleteOnClose=False),
        # поэтому живой QThread не уничтожается вместе с окном.
        if self._ai_task is not None:
            self._ai_task.cancel()
        event.accept()

    def wait_for_workers(self, timeout_ms=10000):
        """Безопасно дождаться завершения фоновых QThread перед выходом процесса."""
        tasks = [t for t in (self._db_task, self._ai_task) if t is not None]
        for task in tasks:
            if task.isRunning():
                if task is self._ai_task:
                    task.cancel()
                task.wait(timeout_ms)
        return all(not t.isRunning() for t in tasks)


# ---------------------------------------------------------------------------
# Main window / Toast / Tray
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self, storage: NewsStorage, tray_app=None):
        super().__init__()
        self.storage = storage
        self.tray_app = tray_app
        self.current_channel = None
        self.selected_channel_name = None
        self._search = ""
        self._page_offset = 0
        self._first = True
        self._workers: List[DbTask] = []
        self._busy = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(350)
        self._search_timer.timeout.connect(self._execute_search)
        self._pending_search = ""
        self._search_generation = 0
        self._ai_window = None

        self.setWindowTitle("Telegram News (SQL Server)")
        self.setGeometry(120, 80, 1180, 740)
        self.setMinimumSize(920, 620)
        self.setStyleSheet(f"background: {Theme.WINDOW};")
        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        self.sidebar = Sidebar(storage)
        lay.addWidget(self.sidebar)
        self.content = MainContent(storage.settings.font_size, storage.settings.sound_enabled)
        lay.addWidget(self.content)

        self.sidebar.channelSelected.connect(self.onChannelSelected)
        self.sidebar.settingsChanged.connect(self.refresh)
        self.content.refreshRequested.connect(self.refresh)
        self.content.searchRequested.connect(self.onSearch)
        self.content.settingsRequested.connect(self.open_settings)
        self.content.soundToggleRequested.connect(self.toggle_sound)
        self.content.themeToggleRequested.connect(self.toggle_theme)
        self.content.loadMoreRequested.connect(self.on_load_more)
        self.content.aiRequested.connect(self.open_ai_mode)
        self.content.markAllReadRequested.connect(self.mark_all_read)
        self.content.showPlaceholder()

    def _run_db(self, op: str, params: Optional[dict] = None, on_ok=None, on_err=None):
        """Запуск DbTask; результат приходит в UI-потоке через signal."""
        task = DbTask(self.storage.settings, op, params, parent=self)

        def _ok(o, result):
            if on_ok:
                on_ok(result)

        def _err(o, msg):
            if on_err:
                on_err(msg)
            else:
                self.content.placeholder.setText(f"Ошибка БД: {msg}")
                self.content.showPlaceholder()

        task.finished_ok.connect(_ok)
        task.failed.connect(_err)
        # finished испускается после выхода из run(), поэтому здесь удалять поток безопасно.
        task.finished.connect(lambda t=task: self._cleanup_worker(t))
        self._workers.append(task)
        task.start()

    def _cleanup_worker(self, task: DbTask):
        # Этот слот вызывается ТОЛЬКО из QThread.finished. К этому моменту
        # run() уже завершён, поэтому удаление QObject безопасно.
        try:
            self._workers.remove(task)
        except ValueError:
            pass
        if not task.isRunning():
            task.deleteLater()

    def apply_theme(self):
        self.setStyleSheet(f"background: {Theme.WINDOW};")
        self.sidebar.apply_theme()
        self.content.apply_theme()

    def showEvent(self, e):
        if self._first:
            self._first = False
            self.setWindowOpacity(0)
            a = QPropertyAnimation(self, b"windowOpacity")
            a.setDuration(250)
            a.setStartValue(0)
            a.setEndValue(1)
            a.start()
            self._anim = a
        super().showEvent(e)

    def refresh(self):
        def ok(channels):
            self.storage.channels = channels
            self.sidebar.setChannels(channels)
            if self.selected_channel_name:
                self._reload_async(preserve=True)
            else:
                self.content.showPlaceholder()
                self.sidebar.selectNoChannel()

        self._run_db("load_channels", on_ok=ok)

    def _reload_async(self, preserve=False):
        name = self.selected_channel_name
        search = self._search or None
        need = PAGE_SIZE
        if preserve:
            need = max(PAGE_SIZE, self.content.news_model.rowCount())

        def ok(result):
            news, total = result
            self.content.showNewsPage(news, total, scroll_top=not preserve)
            self.content.setChannelInfo("Поиск" if search else (name or "—"), total)
            self._page_offset = len(news)
            idx = next((i for i, c in enumerate(self.storage.channels) if c.name == name), -1)
            if idx >= 0:
                self.sidebar.model.setSelected(idx)

        self._run_db(
            "news_page",
            {"channel_name": name, "offset": 0, "limit": need, "search": search},
            on_ok=ok,
        )

    def onChannelSelected(self, channel: Channel):
        self._search = ""
        self.content.search.blockSignals(True)
        self.content.search.clear()
        self.content.search.blockSignals(False)
        self.selected_channel_name = channel.name

        def ok(result):
            channels, news, total = result
            self.storage.channels = channels
            self.sidebar.setChannels(channels)
            updated = next((c for c in channels if c.name == channel.name), None)
            if not updated:
                self.current_channel = None
                self.selected_channel_name = None
                self.content.showPlaceholder()
                return
            self.current_channel = updated
            self.selected_channel_name = updated.name
            self.content.showNewsPage(news, total)
            self.content.setChannelInfo(updated.name, total)
            self._page_offset = len(news)
            idx = next((i for i, c in enumerate(channels) if c.name == updated.name), -1)
            if idx >= 0:
                self.sidebar.model.setSelected(idx)

        def err(msg):
            QMessageBox.warning(self, "БД", msg)

        self._run_db(
            "mark_read_and_page",
            {"channel_name": channel.name, "limit": PAGE_SIZE},
            on_ok=ok,
            on_err=err,
        )

    def on_load_more(self):
        if self._busy:
            return
        self._busy = True
        offset = self._page_offset
        name = self.selected_channel_name
        search = self._search or None

        def ok(result):
            self._busy = False
            more, _ = result
            if more:
                self.content.appendNewsPage(more)
                self._page_offset += len(more)

        def err(msg):
            self._busy = False

        self._run_db(
            "news_page",
            {"channel_name": name, "offset": offset, "limit": PAGE_SIZE, "search": search},
            on_ok=ok,
            on_err=err,
        )

    def onSearch(self, text):
        # Debounce: не создаём QThread на каждый введённый символ.
        self._pending_search = text.strip()
        self._search_generation += 1
        self._search_timer.start()

    def _execute_search(self):
        self._search = self._pending_search
        generation = self._search_generation
        if not self._search:
            self._reload_async(preserve=False) if self.selected_channel_name else self.refresh()
            return
        name = self.current_channel.name if self.current_channel else None
        query = self._search

        def ok(result):
            if generation != self._search_generation or query != self._search:
                return
            news, total = result
            self.content.showNewsPage(news, total)
            self.content.setChannelInfo("Поиск", total)
            self._page_offset = len(news)

        self._run_db(
            "news_page",
            {"channel_name": name, "offset": 0, "limit": PAGE_SIZE, "search": query},
            on_ok=ok,
        )

    def mark_all_read(self):
        """Асинхронно отметить все существующие новости прочитанными."""
        if not self.content.mark_all_btn.isEnabled():
            return
        self.content.mark_all_btn.setEnabled(False)
        self.content.mark_all_btn.setToolTip("Отмечаю все новости прочитанными…")

        def ok(_result):
            def channels_ok(channels):
                self.storage.channels = channels
                self.sidebar.setChannels(channels)
                if self.selected_channel_name:
                    self._reload_async(preserve=True)
                self.content.mark_all_btn.setEnabled(True)
                self.content.mark_all_btn.setToolTip("Все новости отмечены прочитанными")
                if self.tray_app:
                    self.tray_app.update_tray_icon()
                QTimer.singleShot(1800, lambda: self.content.mark_all_btn.setToolTip("Отметить все новости прочитанными"))

            def channels_err(msg):
                self.content.mark_all_btn.setEnabled(True)
                self.content.mark_all_btn.setToolTip("Отметить все новости прочитанными")
                QMessageBox.warning(self, "Прочитано", "Не удалось обновить список каналов:\n" + msg)

            self._run_db("load_channels", on_ok=channels_ok, on_err=channels_err)

        def err(msg):
            self.content.mark_all_btn.setEnabled(True)
            self.content.mark_all_btn.setToolTip("Отметить все новости прочитанными")
            QMessageBox.warning(self, "Прочитано", "Не удалось отметить новости:\n" + msg)

        self._run_db("mark_all_read", on_ok=ok, on_err=err)

    def open_ai_mode(self):
        if self._ai_window is None:
            self._ai_window = AIModeDialog(self.storage, self)
        else:
            self._ai_window._load_channels()
        self._ai_window.apply_theme()
        self._ai_window.show()
        self._ai_window.raise_()
        self._ai_window.activateWindow()

    def toggle_sound(self):
        self.storage.settings.sound_enabled = not self.storage.settings.sound_enabled
        self.storage.settings.save()
        self.content.set_sound_icon(self.storage.settings.sound_enabled)
        if self.tray_app:
            self.tray_app.sound_action.setChecked(self.storage.settings.sound_enabled)

    def toggle_theme(self):
        if self.storage.settings.theme == "dark":
            self.storage.settings.theme = "light"
            apply_theme(LightTheme)
        else:
            self.storage.settings.theme = "dark"
            apply_theme(DarkTheme)
        self.storage.settings.save()
        self.apply_theme()
        if self._ai_window is not None:
            self._ai_window.apply_theme()
            self._ai_window._render_answer()

    def open_settings(self):
        def open_with_names(names):
            dlg = SettingsDialog(names or [], self.storage.settings, self.storage, self)
            if dlg.exec_() == QDialog.Accepted:
                apply_theme(LightTheme if self.storage.settings.theme == "light" else DarkTheme)
                self.apply_theme()
                self.content.set_font_size(self.storage.settings.font_size)
                self.content.set_sound_icon(self.storage.settings.sound_enabled)
                self.storage._working_driver = None  # сброс кэша драйвера
                self.refresh()
                if self.tray_app:
                    self.tray_app.restart_poll_timer()
                    self.tray_app.sound_action.setChecked(self.storage.settings.sound_enabled)
                    self.tray_app.notify_action.setChecked(self.storage.settings.notifications_enabled)

        def ok(names):
            open_with_names(names)

        def err(_msg):
            open_with_names(list(self.storage.settings.enabled_channels.keys()))

        if self.storage.settings.mssql_server:
            self._run_db("channel_names", on_ok=ok, on_err=err)
        else:
            open_with_names([])


class ToastNotification(QWidget):
    readRequested = pyqtSignal(str)

    def __init__(self, channel: str, full_text: str, sound_enabled: bool = True):
        super().__init__()
        self.channel = channel
        self._closing = False
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 {Theme.TOAST_GRAD_TOP}, stop:1 {Theme.TOAST_GRAD_BOTTOM});
                border-radius: 16px; border: none; }}
        """)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(24, 16, 24, 16)
        top = QHBoxLayout()
        lab = QLabel(truncate(channel, 35))
        lab.setFont(font_s(12, True))
        lab.setStyleSheet(f"color: {Theme.BLUE}; background: transparent;")
        top.addWidget(lab)
        top.addStretch()
        cx = QPushButton("✕")
        cx.setFixedSize(30, 30)
        cx.setStyleSheet(f"QPushButton {{ background: transparent; border: none; color: {Theme.SUBTEXT}; }}")
        cx.clicked.connect(self.close_animation)
        top.addWidget(cx)
        fl.addLayout(top)
        prev = QLabel(full_text)
        prev.setWordWrap(True)
        prev.setFont(font_s(12))
        prev.setStyleSheet(f"color: {Theme.TEXT}; background: transparent;")
        prev.setMaximumHeight(140)
        fl.addWidget(prev, 1)
        br = QHBoxLayout()
        br.addStretch()
        close_b = QPushButton("Закрыть")
        close_b.setStyleSheet(f"QPushButton {{ background: {Theme.CARD}; border: 1px solid {Theme.BORDER}; border-radius: 16px; color: {Theme.TEXT}; padding: 8px 20px; }}")
        close_b.clicked.connect(self.close_animation)
        read_b = QPushButton("Прочитать")
        read_b.setStyleSheet(f"QPushButton {{ background: {Theme.BLUE}; border: none; border-radius: 16px; color: white; padding: 8px 20px; }}")
        read_b.clicked.connect(lambda: (self.close_animation(), self.readRequested.emit(self.channel)))
        br.addWidget(close_b)
        br.addWidget(read_b)
        fl.addLayout(br)
        main.addWidget(frame)
        self.setFixedSize(520, 280)
        screen = QApplication.primaryScreen().availableGeometry()
        self.tx = screen.right() - 544
        self.ty = screen.bottom() - 310
        self.move(self.tx, screen.bottom() + 40)
        self.setWindowOpacity(0)
        self.show()
        pos = QPropertyAnimation(self, b"pos")
        pos.setDuration(400)
        pos.setStartValue(QPoint(self.tx, screen.bottom() + 40))
        pos.setEndValue(QPoint(self.tx, self.ty))
        pos.setEasingCurve(QEasingCurve.OutBack)
        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(300)
        fade.setStartValue(0)
        fade.setEndValue(1)
        g = QParallelAnimationGroup()
        g.addAnimation(pos)
        g.addAnimation(fade)
        g.start()
        self._anim = g
        self.auto = QTimer()
        self.auto.setSingleShot(True)
        self.auto.timeout.connect(self.close_animation)
        self.auto.start(18000)

    def close_animation(self):
        if self._closing:
            return
        self._closing = True
        self.auto.stop()
        fade = QPropertyAnimation(self, b"windowOpacity")
        fade.setDuration(250)
        fade.setStartValue(self.windowOpacity())
        fade.setEndValue(0)
        slide = QPropertyAnimation(self, b"pos")
        slide.setDuration(250)
        slide.setStartValue(self.pos())
        slide.setEndValue(QPoint(self.pos().x(), self.pos().y() + 50))
        g = QParallelAnimationGroup()
        g.addAnimation(fade)
        g.addAnimation(slide)
        g.finished.connect(self.close)
        self._c = g
        g.start()


class TrayApp(QApplication):
    INSTANCE_NAME = "TelegramNewsMSSQL_single_instance_v2"

    def __init__(self, argv):
        super().__init__(argv)
        self._secondary_instance = False
        self._instance_server = None
        self._pending_instance_show = False
        if self._activate_existing_instance():
            self._secondary_instance = True
            QTimer.singleShot(0, self.quit)
            return

        load_bundled_fonts()
        if pyodbc is None:
            QMessageBox.critical(
                None,
                "Ошибка",
                "Установите pyodbc:\npip install pyodbc\nи ODBC Driver for SQL Server.",
            )
            sys.exit(1)

        self.settings = Settings()
        if not self.settings.user_id.strip():
            nick, ok = QInputDialog.getText(
                None,
                "Первый запуск",
                "Придумай свой ник (в свободной форме) для индивидуальной настройки:",
            )
            nick = nick.strip()
            while ok and not nick:
                QMessageBox.warning(None, "Ник", "Ник не должен быть пустым.")
                nick, ok = QInputDialog.getText(
                    None, "Первый запуск",
                    "Придумай свой ник (в свободной форме) для индивидуальной настройки:"
                )
                nick = nick.strip()
            if not ok:
                self.quit()
                raise SystemExit(0)
            self.settings.user_id = nick
            self.settings.save()

        apply_theme(LightTheme if self.settings.theme == "light" else DarkTheme)
        self.storage = NewsStorage(self.settings)
        self.current_toast = None
        self.player = QMediaPlayer(self)
        self.loading_complete = False
        self._last_max_id = 0
        self._poll_busy = False
        self._workers: List[DbTask] = []

        self.main_window = MainWindow(self.storage, self)
        self.main_window.setVisible(False)
        self.setup_tray()
        if self._pending_instance_show:
            QTimer.singleShot(0, self.show_window)

        self.poll_timer = QTimer(self)
        self.poll_timer.setTimerType(Qt.PreciseTimer)
        self.poll_timer.timeout.connect(self.poll_db)
        self.restart_poll_timer()

        QTimer.singleShot(800, self.finish_loading)

    def _activate_existing_instance(self) -> bool:
        socket = QLocalSocket(self)
        socket.connectToServer(self.INSTANCE_NAME, QIODevice.WriteOnly)
        if socket.waitForConnected(250):
            socket.write(b"SHOW\n")
            socket.flush()
            socket.waitForBytesWritten(250)
            socket.disconnectFromServer()
            return True

        # Нет живого процесса: удаляем только stale endpoint и становимся сервером.
        QLocalServer.removeServer(self.INSTANCE_NAME)
        server = QLocalServer(self)
        if server.listen(self.INSTANCE_NAME):
            server.newConnection.connect(self._instance_message)
            self._instance_server = server
        return False

    def _instance_message(self):
        if self._instance_server is None:
            return
        while self._instance_server.hasPendingConnections():
            sock = self._instance_server.nextPendingConnection()
            try:
                sock.waitForReadyRead(100)
                _ = bytes(sock.readAll())
            except Exception:
                pass
            sock.disconnectFromServer()
        if hasattr(self, "main_window"):
            self.show_window()
        else:
            self._pending_instance_show = True

    def _run_db(self, op: str, params: Optional[dict] = None, on_ok=None, on_err=None):
        task = DbTask(self.settings, op, params, parent=self)

        def _ok(o, result):
            if on_ok:
                on_ok(result)

        def _err(o, msg):
            if on_err:
                on_err(msg)

        task.finished_ok.connect(_ok)
        task.failed.connect(_err)
        task.finished.connect(lambda t=task: self._cleanup(t))
        self._workers.append(task)
        task.start()

    def _cleanup(self, task: DbTask):
        # Этот слот подключён к QThread.finished, никогда не к finished_ok/failed.
        try:
            self._workers.remove(task)
        except ValueError:
            pass
        if not task.isRunning():
            task.deleteLater()

    def restart_poll_timer(self):
        self.poll_timer.stop()
        interval_ms = max(250, int(self.settings.poll_interval_sec * 1000))
        self.poll_timer.setInterval(interval_ms)
        self.poll_timer.start()

    def finish_loading(self):
        self.loading_complete = True
        self.main_window.show()
        if not self.settings.mssql_server:
            self.main_window.open_settings()
            self.update_tray_icon()
            return

        def after_init(_):
            def got_max(max_id):
                # poll_bundle returns tuple; for max only use simple path
                pass

            def on_poll_init(result):
                max_id, _new, channels = result
                self._last_max_id = max_id
                self.storage.channels = channels
                self.main_window.sidebar.setChannels(channels)
                self.main_window.refresh()
                self.update_tray_icon()

            def on_err(msg):
                QMessageBox.warning(
                    self.main_window,
                    "Подключение",
                    f"Не удалось открыть БД:\n{msg}\n\nПроверьте настройки.",
                )
                self.main_window.open_settings()
                self.update_tray_icon()

            self._run_db("poll", {"after_id": 0, "load_new": False}, on_ok=on_poll_init, on_err=on_err)

        if not self.settings.initialized:
            def marked(_):
                self.settings.initialized = True
                self.settings.save()
                after_init(None)

            self._run_db("mark_all_read", on_ok=marked, on_err=lambda m: after_init(None))
        else:
            after_init(None)

    def poll_db(self):
        if not self.settings.mssql_server or not self.loading_complete or self._poll_busy:
            return
        self._poll_busy = True
        after_id = self._last_max_id

        def ok(result):
            self._poll_busy = False
            max_id, new_items, channels = result
            self.storage.channels = channels
            self.main_window.sidebar.setChannels(channels)
            if max_id > self._last_max_id:
                self._last_max_id = max_id
                if self.main_window.selected_channel_name:
                    self.main_window._reload_async(preserve=True)
                self.update_tray_icon()
                if self.settings.notifications_enabled and new_items:
                    notifiable = [n for n in new_items if self.settings.is_notify(n.channel)]
                    if notifiable:
                        by = defaultdict(int)
                        for n in notifiable:
                            by[n.channel] += 1
                        if len(by) == 1:
                            ch, cnt = next(iter(by.items()))
                            if cnt == 1:
                                self.show_toast(
                                    ch, notifiable[0].text, notifiable[0].title,
                                    self.settings.is_sound(ch),
                                )
                            else:
                                self.show_toast(
                                    ch, f"Новых новостей: {cnt}", ch,
                                    self.settings.is_sound(ch),
                                )
                        else:
                            lines = [
                                f"{c}: {n}"
                                for c, n in sorted(by.items(), key=lambda x: -x[1])[:5]
                            ]
                            self.show_toast(
                                "Несколько каналов",
                                "Новые:\n" + "\n".join(lines),
                                sound_enabled_for_channel=all(
                                    self.settings.is_sound(c) for c in by
                                ),
                            )
            else:
                self.update_tray_icon()

        def err(_msg):
            self._poll_busy = False

        self._run_db("poll", {"after_id": after_id}, on_ok=ok, on_err=err)

    def play_sound(self):
        if not self.settings.sound_enabled:
            return
        if SOUND_FILE.exists():
            self.player.stop()
            self.player.setMedia(QMediaContent(QUrl.fromLocalFile(str(SOUND_FILE))))
            self.player.setVolume(100)
            self.player.play()
        else:
            QApplication.beep()

    def show_toast(self, channel, message, title="", sound_enabled_for_channel=None):
        if self.current_toast:
            try:
                self.current_toast.close()
            except Exception:
                pass
        if sound_enabled_for_channel is None:
            sound_enabled_for_channel = self.settings.is_sound(channel)
        final = self.settings.sound_enabled and sound_enabled_for_channel
        if final:
            self.play_sound()
        full = f"{title}\n\n{message}" if title else message
        self.current_toast = ToastNotification(channel, full, final)
        self.current_toast.readRequested.connect(self.open_from_toast)

    def open_from_toast(self, channel_name):
        self.show_window(refresh=False)
        if channel_name == "Несколько каналов":
            self.main_window.refresh()
            return

        def select_target():
            for ch in self.storage.channels:
                if ch.name == channel_name:
                    self.main_window.onChannelSelected(ch)
                    return
            # На случай, если список каналов обновился одновременно с уведомлением.
            def loaded(channels):
                self.storage.channels = channels
                self.main_window.sidebar.setChannels(channels)
                for ch in channels:
                    if ch.name == channel_name:
                        self.main_window.onChannelSelected(ch)
                        break
            self._run_db("load_channels", on_ok=loaded)

        QTimer.singleShot(80, select_target)

    def update_tray_icon(self):
        pix = QPixmap(64, 64)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor("#2288dd"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(8, 8, 48, 48)
        p.setPen(QColor(255, 255, 255))
        p.setFont(QFont("Segoe UI", 26, QFont.Bold))
        p.drawText(pix.rect(), Qt.AlignCenter, "N")
        p.end()
        self.tray.setIcon(QIcon(pix))

    def setup_tray(self):
        self.tray = QSystemTrayIcon(self)
        self.update_tray_icon()
        self.tray.setToolTip("Telegram News")
        menu = QMenu()
        menu.setStyleSheet(f"QMenu {{ background: {Theme.CARD}; color: {Theme.TEXT}; border: 1px solid {Theme.BORDER}; }}")
        menu.addAction(QAction("Открыть", self, triggered=self.show_window))
        self.sound_action = QAction("Звук", self)
        self.sound_action.setCheckable(True)
        self.sound_action.setChecked(self.settings.sound_enabled)
        self.sound_action.triggered.connect(self._tog_sound)
        menu.addAction(self.sound_action)
        self.notify_action = QAction("Уведомления", self)
        self.notify_action.setCheckable(True)
        self.notify_action.setChecked(self.settings.notifications_enabled)
        self.notify_action.triggered.connect(self._tog_notify)
        menu.addAction(self.notify_action)
        menu.addAction(QAction("Настройки", self, triggered=lambda: self.main_window.open_settings()))
        menu.addSeparator()
        menu.addAction(QAction("Выход", self, triggered=self.quit_app))
        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.activated.connect(
            lambda r: self.show_window() if r in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger) else None
        )

    def _tog_sound(self, c):
        self.settings.sound_enabled = c
        self.settings.save()
        self.main_window.content.set_sound_icon(c)

    def _tog_notify(self, c):
        self.settings.notifications_enabled = c
        self.settings.save()

    def show_window(self, refresh=True):
        if self.main_window.isMinimized():
            self.main_window.showNormal()
        else:
            self.main_window.show()
        self.main_window.setWindowState(
            (self.main_window.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive
        )
        self.main_window.raise_()
        self.main_window.activateWindow()
        if refresh:
            self.main_window.refresh()

    def _all_running_workers(self):
        """Собрать все живые QThread приложения, не теряя ссылки при выходе."""
        workers = []
        seen = set()

        def add(task):
            if task is None:
                return
            ident = id(task)
            if ident in seen:
                return
            seen.add(ident)
            try:
                if task.isRunning():
                    workers.append(task)
            except RuntimeError:
                # QObject уже корректно удалён Qt.
                pass

        for task in list(getattr(self, "_workers", [])):
            add(task)

        main = getattr(self, "main_window", None)
        if main is not None:
            for task in list(getattr(main, "_workers", [])):
                add(task)
            ai = getattr(main, "_ai_window", None)
            if ai is not None:
                add(getattr(ai, "_db_task", None))
                add(getattr(ai, "_ai_task", None))
        return workers

    def quit_app(self):
        """Выход из трея без уничтожения работающих QThread."""
        if getattr(self, "_shutting_down", False):
            return
        self._shutting_down = True

        try:
            self.settings.save()
        except Exception:
            pass

        # Больше не создаём новые фоновые запросы.
        try:
            self.poll_timer.stop()
        except Exception:
            pass

        # AI-поток можно прервать закрытием HTTP-соединения.
        main = getattr(self, "main_window", None)
        ai = getattr(main, "_ai_window", None) if main is not None else None
        if ai is not None:
            ai_task = getattr(ai, "_ai_task", None)
            if ai_task is not None:
                try:
                    ai_task.cancel()
                except Exception:
                    pass

        # Скрываем интерфейс сразу: пользователь уже нажал «Выход».
        try:
            if self.current_toast:
                self.current_toast.close()
        except Exception:
            pass
        try:
            self.tray.hide()
        except Exception:
            pass
        try:
            if main is not None:
                main.hide()
        except Exception:
            pass
        try:
            if ai is not None:
                ai.hide()
        except Exception:
            pass

        # DbTask использует короткие соединения; connect/query timeout ограничен выше.
        # Ждём завершения ВСЕХ потоков: TrayApp, MainWindow и AI-диалога.
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            running = self._all_running_workers()
            if not running:
                break
            for task in running:
                try:
                    task.wait(100)
                except RuntimeError:
                    pass
            QCoreApplication.processEvents()

        running = self._all_running_workers()
        if running:
            # Не вызываем QThread.terminate(): он способен повредить pyodbc/Qt.
            # Вместо возврата в обычный режим продолжаем завершение автоматически,
            # как только последний поток действительно закончит работу.
            self._exit_pending_threads = list(running)
            for task in self._exit_pending_threads:
                try:
                    task.finished.connect(self._finish_quit_when_ready, Qt.UniqueConnection)
                except (TypeError, RuntimeError):
                    pass
            QTimer.singleShot(100, self._finish_quit_when_ready)
            return

        self._final_quit()

    def _finish_quit_when_ready(self):
        if not getattr(self, "_shutting_down", False):
            return
        if self._all_running_workers():
            QTimer.singleShot(100, self._finish_quit_when_ready)
            return
        self._final_quit()

    def _final_quit(self):
        if getattr(self, "_quit_finalized", False):
            return
        self._quit_finalized = True
        try:
            self.storage.close()
        except Exception:
            pass
        server = getattr(self, "_instance_server", None)
        if server is not None:
            try:
                server.close()
            except Exception:
                pass
        self.quit()



if __name__ == "__main__":
    app = TrayApp(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    if getattr(app, "_secondary_instance", False):
        sys.exit(app.exec_())
    try:
        sys.exit(app.exec_())
    except Exception as e:
        print("Критическая ошибка:", e)
        sys.exit(1)
