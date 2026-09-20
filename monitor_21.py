#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Монитор Python-скриптов с веб-панелью и журналом.
Светлая тема, 2 колонки, CPU/RAM, JSON-конфиг.
"""

from __future__ import annotations

import sys
import os
import json
import time
import queue
import signal
import shutil
import socket
import shlex
import traceback
import subprocess
import threading
import datetime
from collections import deque
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QProcess, QProcessEnvironment
from PyQt5.QtGui import QFont, QColor, QTextCursor, QTextCharFormat
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QPushButton, QLabel, QTextEdit, QGroupBox, QScrollArea, QSpinBox, QCheckBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QFileDialog, QDialog, QDialogButtonBox,
    QFrame, QToolButton, QAbstractItemView, QSizePolicy,
    QGraphicsDropShadowEffect
)


# ============================================================
#  КОНСТАНТЫ И КОНФИГ
# ============================================================

APP_NAME = "Монитор Python-скриптов"
# Конфиг и логи всегда рядом с самим приложением (не с workdir скрипта)
APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "monitor_config.json"
LOG_DIR = APP_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

MAX_LOG_FILE_SIZE = 5 * 1024 * 1024
MAX_GUI_LOG_LINES = 250
MAX_PENDING_GUI_LINES = 5000
MAX_FILE_BUFFER_LINES = 10000
WEB_JOURNAL_LINES = 30
WEB_MODULE_LOG_LINES = 10
WATCHDOG_STARTUP_GRACE = 30
# Через сколько мс после SIGTERM/terminate эскалируем до SIGKILL, если процесс жив
KILL_ESCALATION_MS = 1500

DEFAULT_CONFIG = {
    "restart_delay": 10,
    "hang_timeout": 300,
    "max_restarts_per_hour": 12,
    "web_enabled": True,
    "web_host": "0.0.0.0",
    "web_port": 8765,
    "web_refresh_sec": 2,
    "modules": [
        {"title": "Hello World", "script": "hello.py", "workdir": "", "args": "", "autostart": False},
        {"title": "Time Now", "script": "time_now.py", "workdir": "", "args": "", "autostart": False},
        {"title": "Hang Demo", "script": "hang_demo.py", "workdir": "", "args": "", "autostart": False},
        {"title": "Crash Demo", "script": "crash_demo.py", "workdir": "", "args": "", "autostart": False},
    ],
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = json.loads(json.dumps(DEFAULT_CONFIG))
            for k, v in data.items():
                if k != "modules":
                    cfg[k] = v
            modules = data.get("modules", [])
            clean = []
            for m in modules:
                if isinstance(m, dict) and m.get("title") and m.get("script"):
                    clean.append({
                        "title": str(m["title"]),
                        "script": str(m["script"]),
                        "workdir": str(m.get("workdir", "")),
                        "args": str(m.get("args", "")),
                        "autostart": bool(m.get("autostart", False)),
                    })
            if clean:
                cfg["modules"] = clean
            return cfg
        except json.JSONDecodeError as e:
            print(f"[ERROR] Конфиг повреждён: {e}", file=sys.stderr)
            try:
                CONFIG_PATH.rename(CONFIG_PATH.with_suffix(".json.bak"))
            except Exception:
                pass
        except Exception as e:
            print(f"[ERROR] Ошибка чтения конфига: {e}", file=sys.stderr)
    return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR] Не удалось сохранить конфиг: {e}", file=sys.stderr)


# ============================================================
#  СИСТЕМНЫЕ РЕСУРСЫ
# ============================================================

class ResourceMonitor:
    """CPU/RAM системы и отдельных процессов (через psutil)."""

    def __init__(self):
        self._proc_cache: dict[int, "psutil.Process"] = {}
        self._sys_cpu = 0.0
        self._sys_ram_percent = 0.0
        self._sys_ram_used_mb = 0.0
        self._sys_ram_total_mb = 0.0
        if psutil:
            # первый вызов cpu_percent всегда 0 — прогреваем
            psutil.cpu_percent(interval=None)

    def tick_system(self):
        if not psutil:
            return
        try:
            self._sys_cpu = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            self._sys_ram_percent = vm.percent
            self._sys_ram_used_mb = vm.used / (1024 * 1024)
            self._sys_ram_total_mb = vm.total / (1024 * 1024)
        except Exception:
            pass

    def system_snapshot(self) -> dict:
        return {
            "cpu_percent": round(self._sys_cpu, 1),
            "ram_percent": round(self._sys_ram_percent, 1),
            "ram_used_mb": round(self._sys_ram_used_mb, 0),
            "ram_total_mb": round(self._sys_ram_total_mb, 0),
            "psutil": psutil is not None,
        }

    def process_stats(self, pid: int) -> dict:
        """cpu_percent, rss_mb для PID. cpu_percent — с момента прошлого вызова."""
        empty = {"cpu_percent": 0.0, "rss_mb": 0.0, "ok": False}
        if not psutil or pid <= 0:
            return empty
        try:
            proc = self._proc_cache.get(pid)
            if proc is None or not proc.is_running() or proc.pid != pid:
                proc = psutil.Process(pid)
                self._proc_cache[pid] = proc
                proc.cpu_percent(interval=None)  # прогрев
                mem = proc.memory_info()
                return {"cpu_percent": 0.0, "rss_mb": round(mem.rss / (1024 * 1024), 1), "ok": True}
            if not proc.is_running():
                self._proc_cache.pop(pid, None)
                return empty
            cpu = proc.cpu_percent(interval=None)
            mem = proc.memory_info()
            return {
                "cpu_percent": round(cpu, 1),
                "rss_mb": round(mem.rss / (1024 * 1024), 1),
                "ok": True,
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            self._proc_cache.pop(pid, None)
            return empty
        except Exception:
            return empty

    def cleanup_pid(self, pid: int):
        self._proc_cache.pop(pid, None)


# ============================================================
#  ЛОГИРОВАНИЕ ПРИЛОЖЕНИЯ
# ============================================================

class AppLogger:
    _instance: "AppLogger | None" = None

    def __init__(self, path: Path = LOG_DIR / "monitor.log"):
        self.path = path
        self.q: "queue.Queue[str | None]" = queue.Queue()
        self.subscribers: list = []
        self.tail: list[str] = []
        self._tail_lock = threading.Lock()
        self._sub_lock = threading.Lock()
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()
        self._load_tail_from_file()

    @classmethod
    def instance(cls) -> "AppLogger":
        if cls._instance is None:
            cls._instance = AppLogger()
        return cls._instance

    def subscribe(self, fn):
        with self._sub_lock:
            self.subscribers.append(fn)

    def unsubscribe(self, fn):
        with self._sub_lock:
            try:
                self.subscribers.remove(fn)
            except ValueError:
                pass

    def _load_tail_from_file(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-80:]
                with self._tail_lock:
                    self.tail = lines
        except Exception:
            pass

    def _rotate_if_needed(self):
        try:
            if self.path.exists() and self.path.stat().st_size > MAX_LOG_FILE_SIZE:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                self.path.rename(LOG_DIR / f"monitor_{ts}.log")
        except Exception as e:
            print(f"[AppLogger] Ошибка ротации: {e}", file=sys.stderr)

    def _worker(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            try:
                self._rotate_if_needed()
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(item + "\n")
            except Exception as e:
                print(f"[AppLogger] Ошибка записи: {e}", file=sys.stderr)

            with self._tail_lock:
                self.tail.append(item)
                if len(self.tail) > 80:
                    self.tail = self.tail[-80:]

            with self._sub_lock:
                subs = list(self.subscribers)
            for fn in subs:
                try:
                    fn(item)
                except Exception:
                    pass

    def log(self, level: str, msg: str):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        tid = threading.get_ident() % 100000
        line = f"[{ts}] [{level:<5}] [t{tid:05d}] {msg}"
        self.q.put(line)
        try:
            print(line, flush=True)
        except Exception:
            pass

    def info(self, msg):  self.log("INFO", msg)
    def warn(self, msg):  self.log("WARN", msg)
    def error(self, msg): self.log("ERROR", msg)

    def exception(self, msg):
        self.log("ERROR", msg + "\n" + traceback.format_exc())

    def get_tail(self) -> list[str]:
        with self._tail_lock:
            return list(self.tail)


def LOG(level: str, msg: str):
    AppLogger.instance().log(level, msg)


# ============================================================
#  МОДЕЛЬ СТАТУСОВ
# ============================================================

STATUS = {
    "running":    {"label": "Работает",    "color": "#1a7f37", "bg": "#dafbe1", "icon": "●",
                   "title_bg": "#2da44e", "title_border": "#1a7f37", "title_fg": "#ffffff"},
    "starting":   {"label": "Запускается", "color": "#0969da", "bg": "#ddf4ff", "icon": "◐",
                   "title_bg": "#c9d1d9", "title_border": "#afb8c1", "title_fg": "#1f2328"},
    "restarting": {"label": "Перезапуск",  "color": "#9a6700", "bg": "#fff8c5", "icon": "↻",
                   "title_bg": "#c9d1d9", "title_border": "#afb8c1", "title_fg": "#1f2328"},
    "hanging":    {"label": "Завис",       "color": "#cf222e", "bg": "#ffebe9", "icon": "!",
                   "title_bg": "#c9d1d9", "title_border": "#afb8c1", "title_fg": "#1f2328"},
    "error":      {"label": "Ошибка",      "color": "#cf222e", "bg": "#ffebe9", "icon": "✕",
                   "title_bg": "#c9d1d9", "title_border": "#afb8c1", "title_fg": "#1f2328"},
    "stopped":    {"label": "Остановлен",  "color": "#57606a", "bg": "#eaeef2", "icon": "○",
                   "title_bg": "#c9d1d9", "title_border": "#afb8c1", "title_fg": "#1f2328"},
    "done":       {"label": "Завершён",    "color": "#0969da", "bg": "#ddf4ff", "icon": "✓",
                   "title_bg": "#c9d1d9", "title_border": "#afb8c1", "title_fg": "#1f2328"},
}


def status_info(key: str) -> dict:
    return STATUS.get(key, STATUS["stopped"])


# ============================================================
#  ОДИН МОДУЛЬ
# ============================================================

class ModuleBox(QGroupBox):
    status_changed = pyqtSignal()

    def __init__(self, title, script, workdir, args,
                 config_provider, resource_monitor: ResourceMonitor, parent=None):
        super().__init__(title, parent)
        self.title_text = title
        self.script = script
        self.workdir = workdir or ""
        self.args_str = args or ""
        self.config_provider = config_provider
        self.resmon = resource_monitor

        self.process = QProcess(self)
        self.status_key = "stopped"
        self.user_stopped = False
        self.error_state = False
        self.start_time = None
        self.last_output_time = None
        self.next_restart_at = None
        self.log_collapsed = False
        self._hang_restart_pending = False
        self._recent_lines: list[str] = []
        self._last_lines_lock = threading.Lock()
        self._log_full_height = 140   # ≈10 строк Consolas 9pt
        self._line_counter = 0
        self._restart_history = deque()
        self._cpu = 0.0
        self._rss_mb = 0.0
        self._last_pid = 0
        # Используется ли setsid (POSIX): позволяет убить всю группу процессов,
        # а не только сам интерпретатор.
        self._used_setsid = False

        # Данные, которые читает веб-сервер из чужого потока. Только простые
        # Python-объекты под локом — обращаться к QWidget (QLabel.text()) из
        # не-GUI потока небезопасно в Qt.
        self._state_lock = threading.Lock()
        self._last_run_text = "—"

        # deque(maxlen=…) сам держит границу, ручные обрезки не нужны
        self._log_file_buffer: deque = deque(maxlen=MAX_FILE_BUFFER_LINES)
        self._log_flush_timer = QTimer(self)
        self._log_flush_timer.setInterval(1000)
        self._log_flush_timer.timeout.connect(self._flush_log_file)
        self._log_flush_timer.start()

        self._pending_gui_lines: deque = deque(maxlen=MAX_PENDING_GUI_LINES)
        self._pending_lock = threading.Lock()
        self._render_timer = QTimer(self)
        self._render_timer.setInterval(200)
        self._render_timer.timeout.connect(self._flush_gui_buffer)
        self._render_timer.start()

        self.restart_timer = QTimer(self)
        self.restart_timer.setSingleShot(True)
        self.restart_timer.timeout.connect(self._do_auto_restart)

        self._setup_process()
        self._build_ui()
        self._set_status("stopped")

    def _setup_process(self):
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._on_ready_read)
        self.process.started.connect(self._on_started)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_error)

    def _build_ui(self):
        self.status_label = QLabel()
        self.status_label.setObjectName("statusPill")
        self.status_label.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        self.last_run = QLabel("—")
        self.last_run.setObjectName("metaValue")
        self.uptime_label = QLabel("—")
        self.uptime_label.setObjectName("metaValue")
        self.cpu_label = QLabel("CPU —")
        self.cpu_label.setObjectName("resLabel")
        self.ram_label = QLabel("RAM —")
        self.ram_label.setObjectName("resLabel")
        self.restart_info = QLabel("")
        self.restart_info.setObjectName("hintLabel")
        self.restart_info.setVisible(False)

        lbl_start = QLabel("Старт:")
        lbl_start.setObjectName("metaKey")
        lbl_up = QLabel("Up:")
        lbl_up.setObjectName("metaKey")

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setUndoRedoEnabled(False)
        self.log.setFixedHeight(self._log_full_height)
        self.log.setFont(QFont("Consolas", 9))
        self.log.setObjectName("logView")
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        self.log.setPlaceholderText("Вывод скрипта появится здесь…")

        # Кнопка «Старт» — серая, чтобы не путаться с зелёной плашкой
        # работающего модуля. Стиль — #btnStart.
        self.btn_start = QPushButton("Старт")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setToolTip("Запустить скрипт")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.setFixedHeight(24)
        self.btn_start.setFixedWidth(72)

        self.btn_stop = QPushButton("Стоп")
        self.btn_stop.setObjectName("btnDanger")
        self.btn_stop.setToolTip("Остановить скрипт")
        self.btn_stop.setCursor(Qt.PointingHandCursor)
        self.btn_stop.setFixedHeight(24)
        self.btn_stop.setFixedWidth(72)

        self.btn_restart = QPushButton("Рестарт")
        self.btn_restart.setObjectName("btnNeutral")
        self.btn_restart.setToolTip("Перезапустить скрипт вручную")
        self.btn_restart.setCursor(Qt.PointingHandCursor)
        self.btn_restart.setFixedHeight(24)
        self.btn_restart.setFixedWidth(82)

        self.autoscroll_chk = QCheckBox("Автопрокрутка")
        self.autoscroll_chk.setObjectName("moduleAutoscroll")
        self.autoscroll_chk.setChecked(True)
        self.autoscroll_chk.setToolTip("Прокручивать лог к последней строке автоматически")
        self.autoscroll_chk.setCursor(Qt.PointingHandCursor)
        self.autoscroll_chk.toggled.connect(self._on_autoscroll_toggled)

        self.btn_clear = QPushButton("Очистить")
        self.btn_clear.setObjectName("btnGhostFlat")
        self.btn_clear.setToolTip("Очистить панель лога")
        self.btn_clear.setCursor(Qt.PointingHandCursor)
        self.btn_clear.setFixedHeight(24)

        self.btn_collapse = QToolButton()
        self.btn_collapse.setText("▾ лог")
        self.btn_collapse.setCheckable(True)
        self.btn_collapse.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.btn_collapse.setObjectName("btnGhost")
        self.btn_collapse.setCursor(Qt.PointingHandCursor)
        self.btn_collapse.setFixedHeight(24)

        self.btn_start.clicked.connect(self.start)
        self.btn_stop.clicked.connect(lambda: self.stop())
        self.btn_restart.clicked.connect(self.restart)
        self.btn_clear.clicked.connect(self.clear_log)
        self.btn_collapse.toggled.connect(self._toggle_log)

        self._meta_frame = QFrame()
        self._meta_frame.setObjectName("metaFrame")
        meta = QHBoxLayout(self._meta_frame)
        meta.setContentsMargins(2, 0, 2, 0)
        meta.setSpacing(8)
        meta.addWidget(lbl_start)
        meta.addWidget(self.last_run)
        meta.addWidget(lbl_up)
        meta.addWidget(self.uptime_label)
        meta.addWidget(self.cpu_label)
        meta.addWidget(self.ram_label)
        meta.addStretch()
        meta.addWidget(self.restart_info)
        meta.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_restart)
        btn_row.addStretch()
        btn_row.addWidget(self.autoscroll_chk)
        btn_row.addWidget(self.btn_clear)
        btn_row.addWidget(self.btn_collapse)

        v = QVBoxLayout(self)
        v.setSpacing(4)
        v.setContentsMargins(8, 6, 8, 6)
        v.addWidget(self._meta_frame)
        v.addLayout(btn_row)
        v.addWidget(self.log)

        self._update_buttons()

    def _on_autoscroll_toggled(self, checked: bool):
        if checked:
            sb = self.log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _toggle_log(self, checked: bool):
        """Сворачивает только лог. Мета (статус/CPU/RAM) остаётся.
        Карточка сама сжимается до естественной высоты за счёт
        QSizePolicy.Maximum + Qt.AlignTop, выставленных снаружи."""
        self.log_collapsed = checked
        if checked:
            self.log.hide()
            self.btn_collapse.setText("▸ лог")
        else:
            self.log.show()
            self.btn_collapse.setText("▾ лог")

        lay = self.layout()
        if lay is not None:
            lay.invalidate()
        self.updateGeometry()

    def _apply_title_style(self, key: str):
        info = status_info(key)
        bg = info["title_bg"]
        border = info["title_border"]
        fg = info["title_fg"]
        accent = info["color"]
        # margin-top увеличен, чтобы плашка заголовка не наезжала на мета-строку.
        self.setStyleSheet(
            f"QGroupBox {{"
            f"  border: 1px solid #d0d7de;"
            f"  border-left: 3px solid {accent};"
            f"  border-radius: 8px;"
            f"  margin-top: 18px;"
            f"  padding-top: 4px;"
            f"  background: #ffffff;"
            f"  font-weight: 600;"
            f"}}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin;"
            f"  subcontrol-position: top left;"
            f"  left: 10px;"
            f"  padding: 1px 8px;"
            f"  background: {bg};"
            f"  color: {fg};"
            f"  border: 1px solid {border};"
            f"  border-radius: 6px;"
            f"  font-weight: 600;"
            f"  font-size: 9pt;"
            f"}}"
        )

    def _set_status(self, key: str, detail: str = ""):
        self.status_key = key
        info = status_info(key)
        text = f"{info['icon']} {info['label']}"
        if detail:
            text += f" · {detail}"
        self.status_label.setText(text)
        self.status_label.setStyleSheet(
            f"color: {info['color']};"
            f"background: {info['bg']};"
            f"border: 1px solid {info['color']}33;"
            f"border-radius: 8px;"
            f"padding: 2px 8px;"
            f"font-weight: 600;"
            f"font-size: 9pt;"
        )
        self._apply_title_style(key)
        self._update_buttons()
        self.status_changed.emit()

    def _update_buttons(self):
        busy = self.process.state() != QProcess.NotRunning
        restart_pending = self.restart_timer.isActive()
        self.btn_start.setEnabled(not busy and not restart_pending)
        can_stop = (
            busy or restart_pending
            or self.status_key in ("starting", "restarting", "hanging")
        )
        self.btn_stop.setEnabled(can_stop)
        # Restart доступен только когда есть что перезапускать:
        # запущенный процесс, ожидание автостарта, либо ошибочное/зависшее состояние.
        self.btn_restart.setEnabled(
            busy or restart_pending
            or self.status_key in ("starting", "restarting", "hanging", "error")
        )

    def _log_to_file(self, text: str):
        """Метка времени — на момент поступления строки, не на момент flush."""
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log_file_buffer.append(f"[{ts}] {text}")

    def _append_log(self, text: str, color: str = "#1f2328"):
        if not text:
            return
        with self._pending_lock:
            self._pending_gui_lines.append((text, color))
        with self._last_lines_lock:
            self._recent_lines.append(text)
            if len(self._recent_lines) > 30:
                self._recent_lines = self._recent_lines[-30:]
        self._log_to_file(text)

    def _flush_gui_buffer(self):
        with self._pending_lock:
            if not self._pending_gui_lines:
                return
            batch = list(self._pending_gui_lines)
            self._pending_gui_lines.clear()

        # Ограничиваем только то, что рендерим за один проход.
        skipped = 0
        if len(batch) > 300:
            skipped = len(batch) - 300
            batch = batch[-300:]

        self.log.setUpdatesEnabled(False)
        try:
            cursor = self.log.textCursor()
            cursor.movePosition(QTextCursor.End)
            for text, color in batch:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor(color))
                cursor.setCharFormat(fmt)
                cursor.insertText(text + "\n")

            if skipped:
                fmt = QTextCharFormat()
                fmt.setForeground(QColor("#8c959f"))
                cursor.setCharFormat(fmt)
                cursor.insertText(f"… ({skipped} строк пропущено)\n")

            doc = self.log.document()
            if doc.blockCount() > MAX_GUI_LOG_LINES:
                cur = QTextCursor(doc.begin())
                cur.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor,
                                 doc.blockCount() - MAX_GUI_LOG_LINES)
                cur.removeSelectedText()

            # Прокручиваем к последней строке только если включена автопрокрутка.
            if self.autoscroll_chk.isChecked():
                self.log.ensureCursorVisible()
        finally:
            self.log.setUpdatesEnabled(True)

    def _flush_log_file(self):
        if not self._log_file_buffer:
            return
        buf = list(self._log_file_buffer)
        self._log_file_buffer.clear()
        try:
            # Логи монитора всегда в APP_DIR/logs — не в workdir скрипта
            safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in self.title_text)
            path = LOG_DIR / f"{safe_name}.log"
            if path.exists() and path.stat().st_size > MAX_LOG_FILE_SIZE:
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                path.rename(LOG_DIR / f"{path.stem}_{ts}.log")
            # Одна операция записи вместо N — заметно меньше нагрузки на диск.
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n".join(buf))
                f.write("\n")
        except Exception as e:
            LOG("ERROR", f"[{self.title_text}] Ошибка записи лога: {e}")

    def _resolve_script(self) -> Path:
        """Абсолютный путь к скрипту. workdir влияет на cwd процесса, не на поиск файла
        если script уже абсолютный."""
        sp = Path(self.script)
        if sp.is_absolute():
            return sp
        if self.workdir:
            return (Path(self.workdir) / sp).resolve()
        return (APP_DIR / sp).resolve()

    def start(self):
        LOG("INFO", f"[{self.title_text}] start()")
        if self.process.state() != QProcess.NotRunning:
            self._append_log("Процесс уже запущен.", "#9a6700")
            return
        if self.restart_timer.isActive():
            self.restart_timer.stop()
            self.next_restart_at = None

        script_path = self._resolve_script()
        if not script_path.exists():
            self._append_log(f"Файл не найден: {script_path}", "#cf222e")
            self._set_status("error", "файл не найден")
            return

        self.user_stopped = False
        self.error_state = False
        self._hang_restart_pending = False
        self.start_time = datetime.datetime.now()
        self.last_output_time = self.start_time
        run_text = self.start_time.strftime("%H:%M:%S")
        self.last_run.setText(run_text)
        with self._state_lock:
            self._last_run_text = run_text
        self._set_status("starting")

        try:
            args = shlex.split(self.args_str) if self.args_str.strip() else []
        except ValueError:
            args = self.args_str.split()

        program = sys.executable
        script_args = ["-u", str(script_path)] + args

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")
        self.process.setProcessEnvironment(env)

        # Рабочая директория процесса:
        # 1) явный workdir из конфига
        # 2) иначе — папка скрипта
        if self.workdir:
            cwd = str(Path(self.workdir).resolve())
        else:
            cwd = str(script_path.parent)
        self.process.setWorkingDirectory(cwd)
        self._append_log(f"cwd: {cwd}", "#57606a")

        # На *nix запускаем через `setsid`, если он доступен: это создаёт
        # новую сессию/группу процессов, и при остановке можно убить всю
        # группу через os.killpg (включая дочерние процессы скрипта), а не
        # только сам интерпретатор Python.
        self._used_setsid = False
        if sys.platform != "win32" and shutil.which("setsid"):
            self._used_setsid = True
            self.process.start("setsid", [program] + script_args)
        else:
            self.process.start(program, script_args)

    def _on_started(self):
        pid = self.process.processId()
        self._last_pid = pid
        self._append_log(f"Запущен (PID {pid})", "#0969da")
        self._set_status("running")

    def stop(self, silent: bool = False):
        LOG("INFO", f"[{self.title_text}] stop()")
        self.restart_timer.stop()
        self.next_restart_at = None
        self.user_stopped = True
        self._hang_restart_pending = False

        if self.process.state() != QProcess.NotRunning:
            self._kill_process_tree()

        if not silent:
            self._append_log("Процесс остановлен.", "#57606a")

        self.start_time = None
        self._cpu = 0.0
        self._rss_mb = 0.0
        self.cpu_label.setText("CPU —")
        self.ram_label.setText("RAM —")
        if self._last_pid:
            self.resmon.cleanup_pid(self._last_pid)
            self._last_pid = 0
        self._set_status("stopped")

    def restart(self):
        self._restart_history.clear()
        self._append_log("Ручной перезапуск.", "#0969da")
        self.restart_timer.stop()
        self.next_restart_at = None
        was_running = self.process.state() != QProcess.NotRunning
        self.user_stopped = True
        self._hang_restart_pending = False
        if was_running:
            self._kill_process_tree()
        # user_stopped НЕ сбрасываем здесь. Если сбросить сразу, асинхронный
        # finished() (может прийти позже — например, после эскалации до
        # SIGKILL) увидит user_stopped == False и запланирует лишний
        # автоперезапуск поверх уже запланированного ниже QTimer.singleShot.
        # start() сам сбросит user_stopped, когда реально стартует.
        QTimer.singleShot(200, self.start)

    def _kill_process_tree(self):
        pid = self.process.processId()
        if pid <= 0:
            self.process.kill()
            return
        if sys.platform == "win32":
            def run_taskkill(p: int):
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(p)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW, timeout=5,
                    )
                except Exception as e:
                    LOG("ERROR", f"[{self.title_text}] taskkill: {e}")
            threading.Thread(target=run_taskkill, args=(pid,), daemon=True).start()
        else:
            try:
                if self._used_setsid:
                    # pid — это и PGID новой сессии (setsid делает exec,
                    # PID не меняется), поэтому SIGTERM всей группе.
                    os.killpg(pid, signal.SIGTERM)
                else:
                    self.process.terminate()
            except ProcessLookupError:
                pass
            except Exception as e:
                LOG("WARN", f"[{self.title_text}] terminate: {e}")
            QTimer.singleShot(KILL_ESCALATION_MS, self._force_kill_if_needed)

    def _force_kill_if_needed(self):
        if self.process.state() == QProcess.NotRunning:
            return
        pid = self.process.processId()
        LOG("WARN", f"[{self.title_text}] SIGTERM не подействовал, отправляю SIGKILL")
        try:
            if sys.platform != "win32" and self._used_setsid and pid > 0:
                os.killpg(pid, signal.SIGKILL)
            else:
                self.process.kill()
        except ProcessLookupError:
            pass
        except Exception:
            try:
                self.process.kill()
            except Exception:
                pass

    def _on_ready_read(self):
        data = self.process.readAllStandardOutput()
        text = bytes(data).decode("utf-8", errors="replace")
        if not text:
            return
        self.last_output_time = datetime.datetime.now()

        lines = [l.rstrip() for l in text.splitlines() if l.strip()]
        self._line_counter += len(lines)
        if self._line_counter >= 2000:
            LOG("INFO", f"[{self.title_text}] получил {self._line_counter} строк, процесс жив")
            self._line_counter = 0
        # Раньше здесь был self._restart_history = deque(), который обнулял
        # счётчик рестартов при ЛЮБОМ выводе — лимит max_restarts_per_hour не
        # срабатывал вообще ни для одного скрипта, который печатает хоть
        # строку перед падением. История теперь живёт своей жизнью и чистится
        # только по времени (см. _restart_limit_state) или вручную.

        if self.status_key == "hanging":
            self._set_status("running")

        batch: list[tuple[str, str]] = []
        for line in lines:
            low = line.lower()
            if any(w in low for w in ("error", "exception", "traceback",
                                       "critical", "fatal", "syntaxerror")):
                self.error_state = True
                batch.append((line, "#cf222e"))
            elif "warning" in low or "warn" in low:
                batch.append((line, "#9a6700"))
            else:
                batch.append((line, "#1f2328"))

        # deque(maxlen=…) сам вытесняет старое — ручные обрезки не нужны.
        with self._pending_lock:
            self._pending_gui_lines.extend(batch)

        with self._last_lines_lock:
            self._recent_lines.extend(line for line, _ in batch)
            if len(self._recent_lines) > 30:
                self._recent_lines = self._recent_lines[-30:]

        # Один таймстамп на весь чанк — все строки пришли в одном readAllStandardOutput().
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._log_file_buffer.extend(f"[{ts}] {line}" for line, _ in batch)

    def _on_finished(self, exit_code, exit_status):
        LOG("INFO", f"[{self.title_text}] finished code={exit_code} "
                    f"status={exit_status} user_stopped={self.user_stopped} "
                    f"hang={self._hang_restart_pending}")
        self.start_time = None
        self._cpu = 0.0
        self._rss_mb = 0.0
        self.cpu_label.setText("CPU —")
        self.ram_label.setText("RAM —")
        if self._last_pid:
            self.resmon.cleanup_pid(self._last_pid)
            self._last_pid = 0
        self._update_buttons()

        if self.user_stopped and not self._hang_restart_pending:
            return

        if self._hang_restart_pending:
            self._append_log("Перезапуск после зависания.", "#cf222e")
            self._hang_restart_pending = False
            self._schedule_restart(hang=True)
            return

        crashed = (exit_status == QProcess.CrashExit) or (exit_code != 0) or self.error_state
        if crashed:
            self._set_status("error", f"код {exit_code}")
            self._schedule_restart(hang=False)
        else:
            self._set_status("done")

    def _on_error(self, error):
        if error == QProcess.FailedToStart:
            self._append_log(f"Ошибка запуска: {self.process.errorString()}", "#cf222e")
            self._set_status("error", "ошибка запуска")

    def _restart_limit_state(self):
        cfg = self.config_provider()
        limit = max(0, int(cfg.get("max_restarts_per_hour", 12)))
        now = time.time()
        while self._restart_history and now - self._restart_history[0] >= 3600:
            self._restart_history.popleft()
        return limit, len(self._restart_history)

    def _schedule_restart(self, hang: bool = False):
        if self.user_stopped and not hang:
            return

        limit, used = self._restart_limit_state()
        if limit > 0 and used >= limit:
            self.next_restart_at = None
            self.user_stopped = True
            self._set_status("error", f"лимит рестартов: {limit}/ч")
            self._append_log(
                f"Автоперезапуск остановлен: достигнут лимит {limit} рестартов за час. "
                "Ручной Рестарт сбрасывает лимит.",
                "#cf222e",
            )
            LOG("WARN", f"[{self.title_text}] restart limit reached: {limit}/hour")
            return

        cfg = self.config_provider()
        delay = max(1, int(cfg.get("restart_delay", 10)))
        self.next_restart_at = time.time() + delay
        self._set_status("restarting", f"через {delay} с")
        self._append_log(f"Автоперезапуск через {delay} с.", "#9a6700")
        self.restart_timer.start(delay * 1000)

    def _do_auto_restart(self):
        self.next_restart_at = None
        if self.user_stopped or self.process.state() != QProcess.NotRunning:
            self._update_buttons()
            return
        self._restart_history.append(time.time())
        self.start()

    def check_hang(self):
        if self.process.state() != QProcess.Running:
            return
        cfg = self.config_provider()
        timeout = cfg.get("hang_timeout", 0)
        if timeout <= 0 or not self.last_output_time:
            return
        if self.start_time:
            startup_age = (datetime.datetime.now() - self.start_time).total_seconds()
            if startup_age < WATCHDOG_STARTUP_GRACE:
                return
        idle = (datetime.datetime.now() - self.last_output_time).total_seconds()
        if idle > timeout and self.status_key != "hanging":
            LOG("WARN", f"[{self.title_text}] зависание {int(idle)} с")
            self._append_log(f"Зависание: нет вывода {int(idle)} с.", "#cf222e")
            self.error_state = True
            self._hang_restart_pending = True
            self._set_status("hanging", f"{int(idle)} с без вывода")
            self._kill_process_tree()

    def get_uptime(self) -> str:
        if self.start_time and self.process.state() == QProcess.Running:
            delta = datetime.datetime.now() - self.start_time
            h, r = divmod(int(delta.total_seconds()), 3600)
            m, s = divmod(r, 60)
            return f"{h:02}:{m:02}:{s:02}"
        return "—"

    def get_uptime_seconds(self) -> int:
        if self.start_time and self.process.state() == QProcess.Running:
            return int((datetime.datetime.now() - self.start_time).total_seconds())
        return 0

    def update_uptime_display(self):
        self.uptime_label.setText(self.get_uptime())
        # ресурсы процесса
        pid = self.process.processId() if self.process.state() != QProcess.NotRunning else 0
        if pid > 0:
            st = self.resmon.process_stats(pid)
            if st["ok"]:
                self._cpu = st["cpu_percent"]
                self._rss_mb = st["rss_mb"]
                self.cpu_label.setText(f"CPU {self._cpu:.0f}%")
                self.ram_label.setText(f"RAM {self._rss_mb:.0f} МБ")
            else:
                self.cpu_label.setText("CPU —")
                self.ram_label.setText("RAM —")
        else:
            self.cpu_label.setText("CPU —")
            self.ram_label.setText("RAM —")

        if self.next_restart_at:
            left = max(0, int(self.next_restart_at - time.time()))
            self.restart_info.setText(f"рестарт {left}с")
            self.restart_info.setVisible(True)
        else:
            self.restart_info.setText("")
            self.restart_info.setVisible(False)
        self._update_buttons()

    def clear_log(self):
        self.log.clear()
        with self._pending_lock:
            self._pending_gui_lines.clear()
        self._log_file_buffer.clear()
        with self._last_lines_lock:
            self._recent_lines.clear()

    def is_running(self) -> bool:
        return self.process.state() == QProcess.Running

    def snapshot(self) -> dict:
        """Срез состояния для веб-сервера.

        Вызывается из потока HTTP-обработчика (ThreadingHTTPServer), а не из
        GUI-потока — поэтому здесь нельзя обращаться к методам QWidget
        (например, QLabel.text(), как было раньше). Используются только
        простые Python-атрибуты, защищённые блокировками.
        """
        with self._last_lines_lock:
            lines = list(self._recent_lines[-WEB_MODULE_LOG_LINES:])
        with self._state_lock:
            last_run_text = self._last_run_text
        limit, used = self._restart_limit_state()
        info = status_info(self.status_key)
        return {
            "title": self.title_text,
            "script": self.script,
            "workdir": self.workdir,
            "status": self.status_key,
            "status_label": info["label"],
            "status_color": info["color"],
            "status_bg": info["bg"],
            "status_icon": info["icon"],
            "last_run": last_run_text,
            "uptime": self.get_uptime(),
            "uptime_seconds": self.get_uptime_seconds(),
            "pid": self.process.processId() if self.process.state() != QProcess.NotRunning else 0,
            "cpu_percent": self._cpu,
            "rss_mb": self._rss_mb,
            "last_output_ago": (
                max(0, int((datetime.datetime.now() - self.last_output_time).total_seconds()))
                if self.last_output_time and self.process.state() == QProcess.Running else 0
            ),
            "restarts_last_hour": used,
            "restart_limit_per_hour": limit,
            "next_restart_in": (
                max(0, int(self.next_restart_at - time.time()))
                if self.next_restart_at else 0
            ),
            "log_tail": lines,
        }


# ============================================================
#  ОКНО ЖУРНАЛА
# ============================================================

class JournalDialog(QDialog):
    append_signal = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Журнал приложения")
        self.resize(900, 520)
        self._build()
        AppLogger.instance().subscribe(self._on_log)
        self.append_signal.connect(self._append)

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        self.view = QTextEdit()
        self.view.setReadOnly(True)
        self.view.setUndoRedoEnabled(False)
        self.view.setFont(QFont("Consolas", 9))
        self.view.setObjectName("journalView")
        self.view.setLineWrapMode(QTextEdit.NoWrap)
        v.addWidget(self.view)

        row = QHBoxLayout()
        self.autoscroll = QCheckBox("Автопрокрутка")
        self.autoscroll.setChecked(True)
        row.addWidget(self.autoscroll)
        row.addStretch()
        btn_clear = QPushButton("Очистить")
        btn_clear.setFixedHeight(26)
        btn_clear.clicked.connect(self.view.clear)
        row.addWidget(btn_clear)
        btn_close = QPushButton("Закрыть")
        btn_close.setFixedHeight(26)
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_close)
        v.addLayout(row)

        for line in AppLogger.instance().get_tail():
            self.view.insertPlainText(line)

    def _on_log(self, line: str):
        self.append_signal.emit(line)

    def _append(self, line: str):
        sb = self.view.verticalScrollBar()
        at_bottom = sb.value() >= sb.maximum() - 4
        self.view.append(line)
        if self.autoscroll.isChecked() or at_bottom:
            sb.setValue(sb.maximum())

    def closeEvent(self, event):
        AppLogger.instance().unsubscribe(self._on_log)
        super().closeEvent(event)


# ============================================================
#  ДИАЛОГИ МОДУЛЕЙ
# ============================================================

class ModuleEditDialog(QDialog):
    def __init__(self, data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Модуль")
        self.setMinimumWidth(520)
        self.data = data or {
            "title": "", "script": "", "workdir": "", "args": "", "autostart": False
        }
        form = QFormLayout(self)
        form.setSpacing(8)
        form.setContentsMargins(14, 14, 14, 14)

        self.title_edit = QLineEdit(self.data["title"])
        self.script_edit = QLineEdit(self.data["script"])
        self.workdir_edit = QLineEdit(self.data.get("workdir", ""))
        self.args_edit = QLineEdit(self.data.get("args", ""))
        self.autostart_chk = QCheckBox("Запускать автоматически")
        self.autostart_chk.setChecked(bool(self.data.get("autostart")))

        btn_browse = QPushButton("…")
        btn_browse.setFixedWidth(32)
        btn_browse.setFixedHeight(26)
        btn_browse.setCursor(Qt.PointingHandCursor)
        btn_browse.clicked.connect(self._browse_script)
        script_row = QHBoxLayout()
        script_row.addWidget(self.script_edit)
        script_row.addWidget(btn_browse)

        btn_dir = QPushButton("…")
        btn_dir.setFixedWidth(32)
        btn_dir.setFixedHeight(26)
        btn_dir.setCursor(Qt.PointingHandCursor)
        btn_dir.clicked.connect(self._browse_dir)
        dir_row = QHBoxLayout()
        dir_row.addWidget(self.workdir_edit)
        dir_row.addWidget(btn_dir)

        hint = QLabel(
            "Скрипт: путь к .py (относительный или абсолютный).\n"
            "Рабочая папка: cwd процесса. Пусто = папка скрипта.\n"
            "Логи монитора всегда пишутся в logs/ рядом с приложением."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #57606a; font-size: 8.5pt;")

        form.addRow("Название:", self.title_edit)
        form.addRow("Скрипт:", script_row)
        form.addRow("Рабочая папка:", dir_row)
        form.addRow("Аргументы:", self.args_edit)
        form.addRow(self.autostart_chk)
        form.addRow(hint)

        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(self._on_accept)
        bbox.rejected.connect(self.reject)
        form.addRow(bbox)

    def _browse_script(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите скрипт", "", "Python (*.py);;Все файлы (*)"
        )
        if path:
            self.script_edit.setText(path)

    def _browse_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Рабочая папка")
        if path:
            self.workdir_edit.setText(path)

    def _on_accept(self):
        # Раньше можно было сохранить модуль с пустым путём к скрипту —
        # в списке появлялась карточка, которую невозможно запустить.
        if not self.script_edit.text().strip():
            QMessageBox.warning(self, "Проверка", "Укажите путь к скрипту.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "title": self.title_edit.text().strip() or "Без названия",
            "script": self.script_edit.text().strip(),
            "workdir": self.workdir_edit.text().strip(),
            "args": self.args_edit.text().strip(),
            "autostart": self.autostart_chk.isChecked(),
        }


class ModulesDialog(QDialog):
    def __init__(self, modules, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Управление модулями")
        self.resize(780, 420)
        self.modules = [m.copy() for m in modules]
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["Название", "Скрипт", "Рабочая папка", "Аргументы", "Автозапуск"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        btns = QHBoxLayout()
        for text, slot in (("Добавить", self._add), ("Изменить", self._edit),
                           ("Удалить", self._delete)):
            b = QPushButton(text)
            b.setFixedHeight(26)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(slot)
            btns.addWidget(b)
        btns.addStretch()
        layout.addLayout(btns)

        bbox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bbox.accepted.connect(self.accept)
        bbox.rejected.connect(self.reject)
        layout.addWidget(bbox)
        self._reload()
        self.table.doubleClicked.connect(lambda _: self._edit())

    def _reload(self):
        self.table.setRowCount(len(self.modules))
        for r, m in enumerate(self.modules):
            self.table.setItem(r, 0, QTableWidgetItem(m["title"]))
            self.table.setItem(r, 1, QTableWidgetItem(m["script"]))
            self.table.setItem(r, 2, QTableWidgetItem(m.get("workdir", "")))
            self.table.setItem(r, 3, QTableWidgetItem(m.get("args", "")))
            chk = QTableWidgetItem()
            chk.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            chk.setCheckState(Qt.Checked if m.get("autostart") else Qt.Unchecked)
            self.table.setItem(r, 4, chk)

    def _add(self):
        dlg = ModuleEditDialog(parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.modules.append(dlg.get_data())
            self._reload()

    def _edit(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        i = rows[0].row()
        dlg = ModuleEditDialog(self.modules[i], parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.modules[i] = dlg.get_data()
            self._reload()

    def _delete(self):
        rows = sorted((r.row() for r in self.table.selectionModel().selectedRows()),
                      reverse=True)
        if not rows:
            return
        # Раньше удаление срабатывало без подтверждения — легко снести
        # модуль случайным кликом.
        if QMessageBox.question(
            self, "Удаление", f"Удалить выбранные модули ({len(rows)})?",
            QMessageBox.Yes | QMessageBox.No
        ) != QMessageBox.Yes:
            return
        for r in rows:
            del self.modules[r]
        self._reload()

    def get_modules(self) -> list:
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 4)
            if item:
                self.modules[r]["autostart"] = item.checkState() == Qt.Checked
        return self.modules


# ============================================================
#  ВЕБ-СЕРВЕР
# ============================================================

WEB_HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Монитор скриптов</title>
<style>
  :root {
    --bg:#f0f3f6; --panel:#ffffff; --border:#d0d7de; --text:#1f2328;
    --muted:#57606a; --accent:#0969da;
  }
  * { box-sizing: border-box; }
  body {
    margin:0; padding:16px 20px;
    background:var(--bg); color:var(--text);
    font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;
    font-size:13px;
  }
  h1 { font-size:18px; font-weight:600; margin:0 0 2px; }
  .sub { color:var(--muted); font-size:11px; }
  .topbar {
    display:flex; justify-content:space-between; align-items:flex-end;
    margin-bottom:12px; gap:12px; flex-wrap:wrap;
  }
  .sys {
    display:flex; gap:14px; flex-wrap:wrap;
    background:var(--panel); border:1px solid var(--border);
    border-radius:8px; padding:8px 12px; margin-bottom:12px;
    font-size:12px; color:var(--muted);
  }
  .sys b { color:var(--text); font-weight:600; }
  .grid {
    display:grid; gap:10px;
    grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
  }
  .card {
    background:var(--panel); border:1px solid var(--border);
    border-radius:8px; padding:12px;
    display:flex; flex-direction:column; gap:8px;
  }
  .card h2 {
    font-size:13px; font-weight:600; margin:0;
    display:inline-block; padding:2px 10px;
    border-radius:6px; border:1px solid;
    width:max-content;
  }
  .card h2.running { background:#2da44e; color:#ffffff; border-color:#1a7f37; }
  .card h2.other   { background:#c9d1d9; color:#1f2328; border-color:#afb8c1; }
  .status {
    display:inline-flex; align-items:center; gap:5px;
    font-weight:600; font-size:11px;
    padding:2px 8px; border-radius:8px;
    width:max-content;
  }
  .dot { width:7px; height:7px; border-radius:50%; display:inline-block; }
  .meta {
    display:flex; gap:12px; flex-wrap:wrap;
    color:var(--muted); font-size:11px;
  }
  .meta b { color:var(--text); font-weight:600; }
  pre.log {
    background:#f6f8fa; border:1px solid var(--border);
    border-radius:6px; padding:8px; margin:0;
    max-height:90px; overflow:auto;
    font-family:ui-monospace,Consolas,monospace; font-size:11px;
    color:#1f2328; white-space:pre-wrap; word-break:break-word;
  }
  .empty { color:var(--muted); font-style:italic; }
  .journal {
    margin-top:16px;
    background:var(--panel); border:1px solid var(--border);
    border-radius:8px; padding:12px;
  }
  .journal h2 { font-size:14px; font-weight:600; margin:0 0 8px; }
  .journal .note { color:var(--muted); font-weight:400; font-size:11px; }
  .journal pre {
    background:#f6f8fa; border:1px solid var(--border);
    border-radius:6px; padding:8px; margin:0;
    max-height:140px; overflow:auto;
    font-family:ui-monospace,Consolas,monospace; font-size:11px;
    color:#1f2328; white-space:pre-wrap; word-break:break-word;
  }
</style>
</head>
<body>
  <div class="topbar">
    <div>
      <h1>Монитор Python-скриптов</h1>
      <div class="sub">Только просмотр · частота настраивается в приложении</div>
    </div>
    <div class="sub" id="ts"></div>
  </div>

  <div class="sys" id="sys">Система: …</div>
  <div class="grid" id="grid"></div>

  <div class="journal">
    <h2>Журнал приложения <span class="note" id="journal-note"></span></h2>
    <pre id="journal">Загрузка…</pre>
  </div>

<script>
async function tick() {
  try {
    const r = await fetch('/api/status', {cache:'no-store'});
    const data = await r.json();
    document.getElementById('ts').textContent =
      'Обновлено: ' + new Date().toLocaleTimeString();
    renderSys(data.system || {});
    render(data.modules || []);
    renderJournal(data.journal || [], data.journal_total || 0);
  } catch(e) {
    document.getElementById('ts').textContent = 'Нет соединения';
  }
}
function esc(s){return (s??'').replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function renderSys(s) {
  const el = document.getElementById('sys');
  if (!s.psutil) {
    el.textContent = 'Система: psutil не установлен — CPU/RAM недоступны';
    return;
  }
  el.innerHTML =
    `<span>CPU: <b>${s.cpu_percent ?? 0}%</b></span>` +
    `<span>RAM: <b>${s.ram_percent ?? 0}%</b> (${s.ram_used_mb ?? 0} / ${s.ram_total_mb ?? 0} МБ)</span>`;
}
function render(mods) {
  const g = document.getElementById('grid');
  g.innerHTML = '';
  for (const m of mods) {
    const card = document.createElement('div');
    card.className = 'card';
    const logLines = (m.log_tail && m.log_tail.length)
      ? m.log_tail.slice().reverse() : [];
    const logHtml = logLines.length
      ? logLines.map(esc).join('\n')
      : '<span class="empty">Нет вывода</span>';
    const restartInfo = m.next_restart_in > 0
      ? `<span>Рестарт через <b>${m.next_restart_in} с</b></span>`
      : '';
    const titleClass = m.status === 'running' ? 'running' : 'other';
    const cpuRam = m.pid > 0
      ? `<span>CPU: <b>${(m.cpu_percent??0).toFixed(0)}%</b></span>
         <span>RAM: <b>${(m.rss_mb??0).toFixed(0)} МБ</b></span>`
      : '';
    card.innerHTML = `
      <h2 class="${titleClass}">${esc(m.title)}</h2>
      <div class="status" style="color:${m.status_color};background:${m.status_bg};border:1px solid ${m.status_color}33">
        <span class="dot" style="background:${m.status_color}"></span>
        ${esc(m.status_label)}
      </div>
      <div class="meta">
        <span>Скрипт: <b>${esc(m.script)}</b></span>
        <span>Запуск: <b>${esc(m.last_run)}</b></span>
        <span>Работает: <b>${esc(m.uptime)}</b></span>
        ${m.pid > 0 ? `<span>PID: <b>${m.pid}</b></span>` : ''}
        ${cpuRam}
        ${m.restart_limit_per_hour > 0 ? `<span>Рестарты: <b>${m.restarts_last_hour}/${m.restart_limit_per_hour} ч</b></span>` : ''}
        ${restartInfo}
      </div>
      <pre class="log">${logHtml}</pre>
    `;
    g.appendChild(card);
  }
}
function renderJournal(lines, total) {
  const el = document.getElementById('journal');
  const note = document.getElementById('journal-note');
  const ordered = lines.slice().reverse();
  el.textContent = ordered.length ? ordered.join('\n') : 'Записей нет';
  note.textContent = total > lines.length ? `(последние ${lines.length})` : '';
  el.scrollTop = 0;
}
const REFRESH_MS = (%%REFRESH_SEC%%) * 1000;
tick();
setInterval(tick, REFRESH_MS);
</script>
</body>
</html>
"""


class WebServer:
    def __init__(self, snapshot_fn, system_fn, host="0.0.0.0", port=8765, refresh_sec=2):
        self.snapshot_fn = snapshot_fn
        self.system_fn = system_fn
        self.host = host
        self.port = port
        self.refresh_sec = max(1, int(refresh_sec))
        self.httpd = None
        self.thread = None
        self.actual_port = None

    def start(self):
        snapshot_fn = self.snapshot_fn
        system_fn = self.system_fn
        refresh_sec = self.refresh_sec

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, ctype, body: bytes):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    html = WEB_HTML.replace("%%REFRESH_SEC%%", str(refresh_sec))
                    self._send(200, "text/html; charset=utf-8", html.encode("utf-8"))
                elif self.path == "/api/status":
                    try:
                        tail = AppLogger.instance().get_tail()
                        data = {
                            "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                            "system": system_fn(),
                            "modules": snapshot_fn(),
                            "journal": tail[-WEB_JOURNAL_LINES:],
                            "journal_total": len(tail),
                        }
                        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                        self._send(200, "application/json; charset=utf-8", body)
                    except Exception as e:
                        # Раньше необработанное исключение здесь рвало соединение
                        # без ответа — клиент видел молчаливый сбой.
                        LOG("ERROR", f"[web] /api/status: {e}")
                        body = json.dumps({"error": str(e)}).encode("utf-8")
                        self._send(500, "application/json; charset=utf-8", body)
                else:
                    self._send(404, "text/plain; charset=utf-8", b"Not found")

        try:
            self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
            self.httpd.daemon_threads = True
            self.actual_port = self.httpd.server_address[1]
            self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self.thread.start()
            return True, None
        except OSError as e:
            return False, str(e)

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None


# ============================================================
#  ГЛАВНОЕ ОКНО
# ============================================================

class Platform(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1100, 780)

        self.config = load_config()
        self.modules: list[ModuleBox] = []
        self.web_server: WebServer | None = None
        self.journal_dialog: JournalDialog | None = None
        self.resmon = ResourceMonitor()

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._save_runtime)

        self._build_ui()
        self._apply_styles()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

        QTimer.singleShot(400, self._autostart_modules)
        QTimer.singleShot(600, self._start_web)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        header = QFrame()
        header.setObjectName("header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 8, 12, 8)

        title = QLabel(APP_NAME)
        title.setObjectName("titleLabel")
        hl.addWidget(title)
        hl.addStretch()

        self.web_label = QLabel("Веб: выключен")
        self.web_label.setObjectName("webLabel")
        self.web_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hl.addWidget(self.web_label)

        self.btn_journal = QPushButton("Журнал")
        self.btn_journal.setFixedHeight(26)
        self.btn_journal.setCursor(Qt.PointingHandCursor)
        self.btn_journal.clicked.connect(self._open_journal)
        hl.addWidget(self.btn_journal)
        root.addWidget(header)

        summary = QFrame()
        summary.setObjectName("summary")
        sl = QHBoxLayout(summary)
        sl.setContentsMargins(12, 6, 12, 6)
        sl.setSpacing(14)
        self.summary_label = QLabel("Модули: 0")
        self.summary_label.setObjectName("summaryLabel")
        sl.addWidget(self.summary_label)
        self.sys_label = QLabel("CPU — · RAM —")
        self.sys_label.setObjectName("sysLabel")
        sl.addWidget(self.sys_label)
        sl.addStretch()
        self.updated_label = QLabel("—")
        self.updated_label.setObjectName("updatedLabel")
        sl.addWidget(self.updated_label)
        root.addWidget(summary)

        panel = QFrame()
        panel.setObjectName("panel")
        ph = QHBoxLayout(panel)
        ph.setContentsMargins(10, 6, 10, 6)
        ph.setSpacing(6)

        ph.addWidget(QLabel("Задержка:"))
        self.spin_delay = QSpinBox()
        self.spin_delay.setRange(1, 3600)
        self.spin_delay.setValue(self.config.get("restart_delay", 10))
        self.spin_delay.setFixedWidth(64)
        self.spin_delay.setFixedHeight(26)
        self.spin_delay.setToolTip("Пауза перед автоперезапуском, с")
        self.spin_delay.valueChanged.connect(lambda: self._save_timer.start(1000))
        ph.addWidget(self.spin_delay)

        ph.addWidget(QLabel("Hang:"))
        self.spin_hang = QSpinBox()
        self.spin_hang.setRange(0, 86400)
        self.spin_hang.setValue(self.config.get("hang_timeout", 300))
        self.spin_hang.setFixedWidth(70)
        self.spin_hang.setFixedHeight(26)
        self.spin_hang.setToolTip("Таймаут зависания, с (0 = выкл)")
        self.spin_hang.valueChanged.connect(lambda: self._save_timer.start(1000))
        ph.addWidget(self.spin_hang)

        ph.addWidget(QLabel("Лимит/ч:"))
        self.spin_restart_limit = QSpinBox()
        self.spin_restart_limit.setRange(0, 120)
        self.spin_restart_limit.setValue(self.config.get("max_restarts_per_hour", 12))
        self.spin_restart_limit.setFixedWidth(56)
        self.spin_restart_limit.setFixedHeight(26)
        self.spin_restart_limit.setToolTip("Лимит рестартов в час (0 = без лимита)")
        self.spin_restart_limit.valueChanged.connect(lambda: self._save_timer.start(1000))
        ph.addWidget(self.spin_restart_limit)

        ph.addWidget(QLabel("Веб, с:"))
        self.spin_web_refresh = QSpinBox()
        self.spin_web_refresh.setRange(1, 60)
        self.spin_web_refresh.setValue(int(self.config.get("web_refresh_sec", 2)))
        self.spin_web_refresh.setFixedWidth(48)
        self.spin_web_refresh.setFixedHeight(26)
        self.spin_web_refresh.setToolTip("Частота обновления веб-панели, секунд")
        self.spin_web_refresh.valueChanged.connect(lambda: self._save_timer.start(1000))
        ph.addWidget(self.spin_web_refresh)

        ph.addSpacing(8)

        self.btn_modules = QPushButton("Модули")
        self.btn_start_all = QPushButton("Старт все")
        self.btn_start_all.setObjectName("btnPrimary")
        self.btn_stop_all = QPushButton("Стоп все")
        self.btn_stop_all.setObjectName("btnDanger")
        self.btn_collapse = QPushButton("Свернуть логи")
        self.btn_clear = QPushButton("Очистить логи")

        for b in (self.btn_modules, self.btn_start_all, self.btn_stop_all,
                  self.btn_collapse, self.btn_clear):
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(26)
            ph.addWidget(b)

        ph.addStretch()
        root.addWidget(panel)

        self.btn_modules.clicked.connect(self._edit_modules)
        self.btn_start_all.clicked.connect(self._start_all)
        self.btn_stop_all.clicked.connect(self._stop_all)
        self.btn_collapse.clicked.connect(self._toggle_collapse)
        self.btn_clear.clicked.connect(self._clear_logs)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.modules_container = QWidget()
        self.modules_layout = QGridLayout(self.modules_container)
        self.modules_layout.setSpacing(4)
        self.modules_layout.setContentsMargins(0, 0, 0, 2)
        self.modules_layout.setColumnStretch(0, 1)
        self.modules_layout.setColumnStretch(1, 1)
        self._rebuild_modules()
        self.scroll.setWidget(self.modules_container)
        root.addWidget(self.scroll, 1)

    def _rebuild_modules(self):
        for m in self.modules:
            m.stop(silent=True)
            m.deleteLater()
        self.modules.clear()

        while self.modules_layout.count():
            item = self.modules_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Если модулей нет — вместо пустого белого поля показываем подсказку.
        if not self.config["modules"]:
            hint = QLabel("Модули не настроены. Нажмите «Модули», чтобы добавить скрипт.")
            hint.setObjectName("emptyHint")
            hint.setAlignment(Qt.AlignCenter)
            self.modules_layout.addWidget(hint, 0, 0, 1, 2)
            return

        COLS = 2
        for i, mcfg in enumerate(self.config["modules"]):
            box = ModuleBox(
                title=mcfg["title"],
                script=mcfg["script"],
                workdir=mcfg.get("workdir", ""),
                args=mcfg.get("args", ""),
                config_provider=self._current_settings,
                resource_monitor=self.resmon,
                parent=self.modules_container,
            )
            # Не растягивать карточку по высоте соседа; тянуться по ширине колонки.
            box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

            self.modules.append(box)
            self.modules_layout.addWidget(box, i // COLS, i % COLS, Qt.AlignTop)
            box.btn_collapse.toggled.connect(self._on_module_collapse_changed)

            shadow = QGraphicsDropShadowEffect(box)
            shadow.setBlurRadius(8)
            shadow.setXOffset(0)
            shadow.setYOffset(1)
            shadow.setColor(QColor(27, 31, 36, 18))
            box.setGraphicsEffect(shadow)

    def _apply_styles(self):
        self.setStyleSheet("""
            QWidget {
                background: #f0f3f6;
                color: #1f2328;
                font-family: 'Segoe UI', system-ui, Arial, sans-serif;
                font-size: 9.5pt;
            }
            /* Подписи и чекбоксы внутри белых панелей не должны получать
               серую подложку от QWidget выше. Идёт ПОСЛЕ QWidget — перекрывает. */
            QLabel, QCheckBox, QRadioButton {
                background: transparent;
            }
            #header {
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 8px;
            }
            #titleLabel {
                font-size: 13pt;
                font-weight: 700;
                color: #1f2328;
                background: transparent;
            }
            #webLabel {
                color: #0969da;
                font-size: 8.5pt;
                padding: 3px 8px;
                background: #ddf4ff;
                border: 1px solid #b6e3ff;
                border-radius: 8px;
            }
            #panel, #summary {
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 8px;
            }
            #summaryLabel, #sysLabel {
                color: #57606a;
                font-weight: 600;
                font-size: 9pt;
                background: transparent;
            }
            #sysLabel { color: #0969da; background: transparent; }
            #updatedLabel { color: #8c959f; font-size: 8.5pt; background: transparent; }
            #hintLabel {
                color: #9a6700;
                font-size: 8pt;
                font-weight: 600;
                padding: 1px 6px;
                background: #fff8c5;
                border: 1px solid #f5e6a3;
                border-radius: 6px;
            }
            #emptyHint {
                color: #9a6700;
                font-size: 9.5pt;
                font-weight: 600;
                padding: 14px;
                margin: 6px;
                background: #fff8c5;
                border: 1px solid #f5e6a3;
                border-radius: 8px;
            }
            #metaFrame {
                background: transparent;
                border: none;
            }
            #metaKey {
                color: #57606a;
                font-size: 8.5pt;
                background: transparent;
            }
            #metaValue {
                font-weight: 600;
                color: #1f2328;
                background: transparent;
            }
            #resLabel {
                font-weight: 600;
                color: #0969da;
                font-size: 8.5pt;
                background: transparent;
            }
            #moduleAutoscroll {
                color: #57606a;
                font-size: 8.5pt;
                background: transparent;
                spacing: 4px;
                padding: 0 4px;
            }
            #moduleAutoscroll::indicator {
                width: 13px;
                height: 13px;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 8px;
                margin-top: 18px;
                padding-top: 4px;
                font-weight: 600;
            }
            QPushButton {
                background: #f6f8fa;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                padding: 2px 10px;
                color: #1f2328;
                font-weight: 500;
                font-size: 9pt;
            }
            QPushButton:hover { background: #eaeef2; border-color: #afb8c1; }
            QPushButton:pressed { background: #dfe3e6; }
            QPushButton:disabled { color: #8c959f; background: #f6f8fa; }
            /* Кнопка «Старт» у модуля — серая, чтобы визуально не сливалась
               с зелёной плашкой запущенного модуля. «Старт все» сверху
               остаётся #btnPrimary и работает как bulk-действие. */
            QPushButton#btnStart {
                background: #ffffff;
                border: 1px solid #d0d7de;
                color: #1f2328;
                font-weight: 600;
            }
            QPushButton#btnStart:hover { background: #f6f8fa; border-color: #afb8c1; }
            QPushButton#btnStart:pressed { background: #eaeef2; }
            QPushButton#btnStart:disabled {
                color: #8c959f; background: #f6f8fa; border-color: #d0d7de;
            }
            QPushButton#btnPrimary {
                background: #2da44e;
                color: #ffffff;
                border: 1px solid #1a7f37;
                font-weight: 600;
            }
            QPushButton#btnPrimary:hover { background: #2c974b; }
            QPushButton#btnPrimary:pressed { background: #166b2e; }
            QPushButton#btnPrimary:disabled {
                background: #94d3a2; border-color: #94d3a2; color: #ffffff;
            }
            QPushButton#btnDanger {
                background: #ffffff;
                color: #cf222e;
                border: 1px solid #ff8182;
                font-weight: 600;
            }
            QPushButton#btnDanger:hover { background: #ffebe9; border-color: #cf222e; }
            QPushButton#btnDanger:pressed { background: #ffcecb; }
            QPushButton#btnDanger:disabled {
                color: #8c959f; background: #f6f8fa; border-color: #d0d7de;
            }
            QPushButton#btnNeutral {
                background: #ffffff;
                color: #0969da;
                border: 1px solid #54aeff;
                font-weight: 600;
            }
            QPushButton#btnNeutral:hover { background: #ddf4ff; border-color: #0969da; }
            QPushButton#btnNeutral:pressed { background: #b6e3ff; }
            QPushButton#btnNeutral:disabled {
                color: #8c959f; background: #f6f8fa; border-color: #d0d7de;
            }
            QPushButton#btnGhostFlat {
                background: transparent;
                border: 1px solid transparent;
                color: #57606a;
                padding: 2px 6px;
            }
            QPushButton#btnGhostFlat:hover {
                color: #0969da;
                background: #f6f8fa;
                border-color: #d0d7de;
            }
            QToolButton#btnGhost {
                background: transparent;
                border: none;
                color: #57606a;
                padding: 2px 6px;
                font-size: 8.5pt;
            }
            QToolButton#btnGhost:hover { color: #0969da; }
            QTextEdit#logView {
                background: #f6f8fa;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                font-family: Consolas, 'Cascadia Mono', monospace;
                font-size: 8.5pt;
                color: #1f2328;
                selection-background-color: #b6d7ff;
                padding: 4px;
            }
            QTextEdit#journalView {
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                font-family: Consolas, monospace;
                font-size: 9pt;
                color: #1f2328;
                padding: 6px;
            }
            QTableWidget {
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                gridline-color: #eaeef2;
                alternate-background-color: #f6f8fa;
            }
            QHeaderView::section {
                background: #f6f8fa;
                color: #57606a;
                border: none;
                border-bottom: 1px solid #d0d7de;
                padding: 6px;
                font-weight: 600;
            }
            QSpinBox, QLineEdit {
                background: #ffffff;
                border: 1px solid #d0d7de;
                border-radius: 6px;
                padding: 2px 6px;
                color: #1f2328;
            }
            QSpinBox:focus, QLineEdit:focus { border-color: #0969da; }
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: transparent;
                width: 8px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #d0d7de;
                border-radius: 4px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #afb8c1; }
            QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
        """)

    def _current_settings(self) -> dict:
        return {
            "restart_delay": self.spin_delay.value(),
            "hang_timeout": self.spin_hang.value(),
            "max_restarts_per_hour": self.spin_restart_limit.value(),
            "web_refresh_sec": self.spin_web_refresh.value(),
        }

    def _save_runtime(self):
        self.config.update(self._current_settings())
        save_config(self.config)

    def _open_journal(self):
        if self.journal_dialog is None:
            self.journal_dialog = JournalDialog(self)
            self.journal_dialog.finished.connect(self._on_journal_closed)
        self.journal_dialog.show()
        self.journal_dialog.raise_()
        self.journal_dialog.activateWindow()

    def _on_journal_closed(self, *_):
        self.journal_dialog = None

    def _edit_modules(self):
        dlg = ModulesDialog(self.config["modules"], self)
        if dlg.exec_() == QDialog.Accepted:
            self.config["modules"] = dlg.get_modules()
            save_config(self.config)
            self._rebuild_modules()
            QTimer.singleShot(300, self._autostart_modules)

    def _start_all(self):
        LOG("INFO", "=== Запустить все ===")
        for m in self.modules:
            if not m.is_running():
                m.start()

    def _stop_all(self):
        LOG("INFO", "=== Остановить все ===")
        if not self.modules:
            return
        if QMessageBox.question(
            self, "Подтверждение", "Остановить все модули?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            for m in self.modules:
                m.stop()

    def _on_module_collapse_changed(self, *_):
        """Синхронизирует текст общей кнопки со состоянием модулей."""
        if not self.modules:
            return
        all_collapsed = all(m.log_collapsed for m in self.modules)
        self.btn_collapse.setText(
            "Развернуть логи" if all_collapsed else "Свернуть логи"
        )

    def _toggle_collapse(self):
        """Идемпотентно: все свёрнуты → развернуть, иначе → свернуть все."""
        if not self.modules:
            return
        all_collapsed = all(m.log_collapsed for m in self.modules)
        target = not all_collapsed   # True = свернуть всё
        for m in self.modules:
            m.btn_collapse.setChecked(target)
        self.btn_collapse.setText(
            "Развернуть логи" if target else "Свернуть логи"
        )

    def _clear_logs(self):
        if not self.modules:
            return
        if QMessageBox.question(
            self, "Очистка", "Очистить логи всех модулей?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            for m in self.modules:
                m.clear_log()

    def _autostart_modules(self):
        for m, mcfg in zip(self.modules, self.config["modules"]):
            if mcfg.get("autostart") and not m.is_running():
                LOG("INFO", f"автозапуск [{m.title_text}]")
                m.start()

    def _tick(self):
        self.resmon.tick_system()
        sys_s = self.resmon.system_snapshot()
        if sys_s["psutil"]:
            self.sys_label.setText(
                f"CPU {sys_s['cpu_percent']:.0f}%  ·  "
                f"RAM {sys_s['ram_percent']:.0f}% "
                f"({sys_s['ram_used_mb']:.0f}/{sys_s['ram_total_mb']:.0f} МБ)"
            )
        else:
            self.sys_label.setText("CPU/RAM: установите psutil")

        for m in self.modules:
            m.update_uptime_display()
            m.check_hang()
        running = sum(m.status_key == "running" for m in self.modules)
        restarting = sum(m.status_key == "restarting" for m in self.modules)
        errors = sum(m.status_key in ("error", "hanging") for m in self.modules)
        self.summary_label.setText(
            f"Модули: {len(self.modules)}  ·  Работают: {running}  ·  "
            f"Рестарт: {restarting}  ·  Ошибки: {errors}"
        )
        self.updated_label.setText(datetime.datetime.now().strftime("%H:%M:%S"))

    def _snapshot_all(self) -> list:
        return [m.snapshot() for m in self.modules]

    def _system_snapshot(self) -> dict:
        return self.resmon.system_snapshot()

    def _start_web(self):
        LOG("INFO", "=== Старт веб-сервера ===")
        if not self.config.get("web_enabled", True):
            LOG("INFO", "веб отключён")
            self.web_label.setText("Веб: выключен")
            return
        host = self.config.get("web_host", "0.0.0.0")
        port = int(self.config.get("web_port", 8765))
        refresh = int(self.config.get("web_refresh_sec", 2))
        srv = WebServer(self._snapshot_all, self._system_snapshot, host=host, port=port, refresh_sec=refresh)
        ok, err = srv.start()
        if not ok:
            LOG("WARN", f"порт {port} занят: {err}, пробую свободный")
            srv = WebServer(self._snapshot_all, self._system_snapshot, host=host, port=0, refresh_sec=refresh)
            ok, err = srv.start()
        if ok:
            self.web_server = srv
            ip = self._detect_lan_ip()
            self.web_label.setText(f"Веб: http://{ip}:{srv.actual_port}")
            LOG("INFO", f"веб доступен на http://{ip}:{srv.actual_port}")
        else:
            self.web_label.setText(f"Веб: ошибка ({err})")
            LOG("ERROR", f"веб-сервер не запущен: {err}")

    @staticmethod
    def _detect_lan_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def closeEvent(self, event):
        LOG("INFO", "=== closeEvent ===")
        running = [m for m in self.modules if m.is_running()]
        if running:
            reply = QMessageBox.question(
                self, "Выход",
                f"Запущено модулей: {len(running)}. Остановить их и выйти?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return
            for m in self.modules:
                m.stop(silent=True)
                QApplication.processEvents()
        if self.web_server:
            self.web_server.stop()
        self._save_runtime()
        event.accept()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)

    LOG("INFO", "=== Приложение запущено ===")
    LOG("INFO", f"Python {sys.version.split()[0]}, platform={sys.platform}")
    LOG("INFO", f"APP_DIR={APP_DIR}, psutil={'yes' if psutil else 'no'}")

    def _excepthook(exc_type, exc_value, exc_tb):
        LOG("ERROR", "Необработанное исключение:")
        AppLogger.instance().log(
            "ERROR",
            "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        )
    sys.excepthook = _excepthook

    w = Platform()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()