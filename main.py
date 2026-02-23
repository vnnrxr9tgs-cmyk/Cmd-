import os
import json
import time
import threading
import tkinter as tk
from tkinter import messagebox
import pystray
from PIL import Image, ImageDraw
import operator
import re

CONFIG_FILE = "config.json"
RETRY_ALERT_DELAY = 180
MAX_HISTORY = 200

STATE_NORMAL = "NORMAL"
STATE_ALERT = "ALERT"

OPERATORS = {
    ">": operator.gt,
    "<": operator.lt,
    "==": operator.eq,
    ">=": operator.ge,
    "<=": operator.le,
    "!=": operator.ne
}


# ===============================
# ВСПОМОГАТЕЛЬНЫЕ
# ===============================

class SafeDict(dict):
    def __missing__(self, key):
        return "Null"


def extract_template_vars(template: str):
    return re.findall(r"{(.*?)}", template)


# ===============================
# УВЕДОМЛЕНИЯ
# ===============================

class NotificationManager:
    WIDTH = 340
    HEIGHT = 150
    MARGIN = 10
    LIFETIME = 15000

    def __init__(self, root):
        self.root = root
        self.active = []
        self.history = []
        self.screen_w = root.winfo_screenwidth()
        self.screen_h = root.winfo_screenheight()

    # ------------------------------

    def reposition(self):
        # очищаем уничтоженные окна
        self.active = [w for w in self.active if w.winfo_exists()]

        for i, win in enumerate(self.active):
            x = self.screen_w - self.WIDTH - self.MARGIN
            y = self.screen_h - ((i + 1) * (self.HEIGHT + self.MARGIN)) - 40
            if win.winfo_exists():
                win.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

    # ------------------------------

    def close_all(self):
        for win in self.active[:]:
            if win.winfo_exists():
                win.destroy()
        self.active.clear()

    # ------------------------------

    def show(self, title, message, is_alert=True, is_info=False):
        bg = "#1e1e2e" if is_info else "#1e1e1e"
        accent = "#3399ff" if is_info else ("#ff4d4d" if is_alert else "#4dff88")

        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=bg)

        frame = tk.Frame(win, bg=bg)
        frame.pack(fill="both", expand=True, padx=10, pady=8)

        header = tk.Frame(frame, bg=bg)
        header.pack(fill="x")

        tk.Label(header, text=title, fg=accent,
                 bg=bg, font=("Segoe UI", 10, "bold")).pack(side="left")

        close_all_btn = tk.Label(header, text="Закрыть все",
                                 fg="#bbbbbb", bg=bg,
                                 cursor="hand2", font=("Segoe UI", 8))
        close_all_btn.pack(side="right", padx=(0, 10))
        close_all_btn.bind("<Button-1>", lambda e: self.close_all())

        close_btn = tk.Label(header, text="✕",
                             fg="white", bg=bg, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: win.destroy())

        tk.Label(frame, text=message, fg="white", bg=bg,
                 font=("Segoe UI", 9),
                 wraplength=300, justify="left").pack(anchor="w", pady=(5, 0))

        progress = tk.Frame(win, bg=accent, height=4)
        progress.place(x=0, y=self.HEIGHT - 4, width=self.WIDTH)

        start_time = time.time()
        paused = False
        pause_start = 0

        def close():
            if not win.winfo_exists():
                return
            win.destroy()
            self.reposition()

        def update_bar():
            if not win.winfo_exists():
                return

            if not paused:
                elapsed = (time.time() - start_time) * 1000
                remaining = max(0, self.LIFETIME - elapsed)
            else:
                remaining = max(0, self.LIFETIME - (pause_start - start_time) * 1000)

            percent = remaining / self.LIFETIME
            progress.place(width=self.WIDTH * percent)

            if remaining <= 0:
                close()
            else:
                win.after(50, update_bar)

        def on_enter(e):
            nonlocal paused, pause_start
            if not paused:
                paused = True
                pause_start = time.time()

        def on_leave(e):
            nonlocal paused, start_time
            if paused:
                paused = False
                pause_duration = time.time() - pause_start
                start_time += pause_duration

        win.bind("<Enter>", on_enter)
        win.bind("<Leave>", on_leave)

        self.active.append(win)
        self.reposition()
        update_bar()

        # история
        self.history.append(
            (title, message, time.strftime("%H:%M:%S"), is_alert))
        self.history = self.history[-MAX_HISTORY:]

    # ------------------------------

    def show_history(self):
        if not self.history:
            messagebox.showinfo("История", "История уведомлений пуста.")
            return

        hist_win = tk.Toplevel(self.root)
        hist_win.title("История уведомлений")
        hist_win.geometry("500x400")

        text = tk.Text(hist_win, wrap="word")
        text.pack(fill="both", expand=True)

        for t, msg, ts, is_alert in reversed(self.history):
            icon = "⚠️" if is_alert else "ℹ️"
            text.insert("end", f"[{ts}] {icon} {t}\n{msg}\n{'-' * 30}\n")

        text.config(state="disabled")


# ===============================
# МОНИТОР
# ===============================

class MonitorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.running = True

        self.load_config()
        self.notifier = NotificationManager(self.root)

        self.setup_tray()
        self.start_info_threads()

    # ------------------------------

    def load_config(self):
        if not os.path.exists(CONFIG_FILE):
            self.config = {
                "scan_interval": 10,
                "info_reports": [],
                "items": []
            }
            self.save_config()
        else:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                self.config = json.load(f)

    def save_config(self):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4, ensure_ascii=False)

    # ------------------------------

    def compare(self, value, limit, op):
        return OPERATORS.get(op, lambda a, b: False)(value, limit)

    # ------------------------------

    def get_db_results(self):
        import random
        return {
            "pending_orders": random.randint(0, 100),
            "stuck_sessions": random.randint(0, 10),
            "cpu_usage": random.randint(10, 90),
            "active_users": random.randint(100, 500),
            "memory_usage": random.randint(20, 95),
            "disk_free": random.randint(10, 500),
            "test": None,
            "test2": None
        }

    # ------------------------------

    def check_item(self, item, db_data):
        value = 0

        if item["type"] == "filesystem":
            try:
                if os.path.exists(item["path"]):
                    value = sum(len(f) for _, _, f in os.walk(item["path"]))
            except:
                value = 0

        elif item["type"] == "database":
            value = db_data.get(item["variable"], 0)
        else:
            return

        is_alert = self.compare(value, item["limit"], item["operator"])
        now = time.time()
        state = item.get("current_state", STATE_NORMAL)

        if is_alert and state != STATE_ALERT:
            item["current_state"] = STATE_ALERT
            item["last_alert_time"] = now

            self.root.after(
                0,
                lambda:
                self.notifier.show(
                    "⚠ Превышение лимита",
                    f"{item['name']}\nТекущее: {value}\nЛимит: {item['limit']}",
                    True
                )
            )

        elif not is_alert and state == STATE_ALERT:
            item["current_state"] = STATE_NORMAL

            self.root.after(
                0,
                lambda:
                self.notifier.show(
                    "✓ Норма восстановлена",
                    f"{item['name']}\nТекущее: {value}",
                    False
                )
            )

    # ------------------------------

    def info_worker(self, report_config):
        interval = report_config.get("interval_seconds", 3600)
        title = report_config.get("title", "Информация")
        template = report_config.get("template", "")

        while self.running:
            for _ in range(interval):
                if not self.running:
                    return
                time.sleep(1)

            db_data = self.get_db_results()

            vars_in_template = extract_template_vars(template)

            # Проверка: если ВСЕ переменные пустые → пропуск
            all_empty = True
            for var in vars_in_template:
                value = db_data.get(var)
                if value not in (None, "Null", "", 0):
                    all_empty = False
                    break

            if all_empty:
                continue

            try:
                message = template.format_map(SafeDict(db_data))
            except:
                message = template

            self.root.after(
                0,
                lambda t=title, m=message:
                self.notifier.show(t, m, False, True)
            )

    # ------------------------------

    def start_info_threads(self):
        for report in self.config.get("info_reports", []):
            thread = threading.Thread(
                target=self.info_worker,
                args=(report,),
                daemon=True
            )
            thread.start()

    # ------------------------------

    def scan_loop(self):
        while self.running:
            db_data = self.get_db_results()
            for item in self.config.get("items", []):
                self.check_item(item, db_data)

            time.sleep(self.config.get("scan_interval", 10))

    # ------------------------------

    def setup_tray(self):
        def on_quit(icon, item):
            self.running = False
            self.root.quit()
            icon.stop()

        image = Image.new("RGB", (64, 64), color="black")
        draw = ImageDraw.Draw(image)
        draw.rectangle([16, 16, 48, 48], fill="red")

        menu = pystray.Menu(
            pystray.MenuItem("История уведомлений",
                             lambda icon, item:
                             self.root.after(0,
                                             self.notifier.show_history)),
            pystray.MenuItem("Выход", on_quit)
        )

        icon = pystray.Icon("MonitorApp", image, "MonitorApp", menu)
        threading.Thread(target=icon.run, daemon=True).start()

    # ------------------------------

    def start(self):
        threading.Thread(target=self.scan_loop, daemon=True).start()
        self.root.mainloop()


# ===============================
# СТАРТ
# ===============================

if __name__ == "__main__":
    app = MonitorApp()
    app.start()