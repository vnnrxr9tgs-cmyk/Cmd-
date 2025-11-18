import os
import json
import shutil
import time
import tkinter as tk
from tkinter import filedialog, messagebox

def load_articles_from_dir(folder):
    """Возвращает словарь link -> файл для всех JSON файлов в директории"""
    articles = {}
    if not os.path.exists(folder):
        return articles
    for file in os.listdir(folder):
        if file.endswith(".json"):
            try:
                path = os.path.join(folder, file)
                with open(path, "r", encoding="utf-8") as f:
                    article = json.load(f)
                    link = article.get("link")
                    if link:
                        articles[link] = article
            except:
                continue
    return articles

def update_directory_safe(old_dir, new_dir):
    """Добавляет новые статьи, которых нет в старой директории, с уникальными именами"""
    if not os.path.exists(old_dir) or not os.path.exists(new_dir):
        raise ValueError("Выберите корректные директории")

    old_articles = load_articles_from_dir(old_dir)
    added_count = 0

    for file in os.listdir(new_dir):
        if not file.endswith(".json"):
            continue
        new_path = os.path.join(new_dir, file)
        try:
            with open(new_path, "r", encoding="utf-8") as f:
                article = json.load(f)
                link = article.get("link")
                if not link or link in old_articles:
                    continue  # уже есть, пропускаем

                # создаем уникальное имя файла
                site = article.get("site", "article")
                article_id = article.get("id", int(time.time()*1000))
                filename = f"{site}_{article_id}.json"
                target_path = os.path.join(old_dir, filename)

                # если по какой-то причине файл с таким именем уже есть, добавляем timestamp
                while os.path.exists(target_path):
                    article_id = int(time.time()*1000)
                    filename = f"{site}_{article_id}.json"
                    target_path = os.path.join(old_dir, filename)

                shutil.copy(new_path, target_path)
                added_count += 1
        except Exception as e:
            print(f"Ошибка при обработке {file}: {e}")
            continue

    return added_count

# --- GUI ---
root = tk.Tk()
root.title("Обновление статей безопасно")

old_dir_var = tk.StringVar()
new_dir_var = tk.StringVar()

tk.Label(root, text="Старая директория:").grid(row=0, column=0, sticky="w")
tk.Entry(root, textvariable=old_dir_var, width=50).grid(row=0, column=1)
tk.Button(root, text="Выбрать", command=lambda: old_dir_var.set(filedialog.askdirectory())).grid(row=0, column=2)

tk.Label(root, text="Новая директория:").grid(row=1, column=0, sticky="w")
tk.Entry(root, textvariable=new_dir_var, width=50).grid(row=1, column=1)
tk.Button(root, text="Выбрать", command=lambda: new_dir_var.set(filedialog.askdirectory())).grid(row=1, column=2)

def do_update():
    try:
        added = update_directory_safe(old_dir_var.get(), new_dir_var.get())
        messagebox.showinfo("Готово", f"Добавлено новых статей: {added}")
    except Exception as e:
        messagebox.showerror("Ошибка", str(e))

tk.Button(root, text="Обновить", bg="green", fg="white", command=do_update).grid(row=2, column=0, columnspan=3, pady=10)

root.mainloop()