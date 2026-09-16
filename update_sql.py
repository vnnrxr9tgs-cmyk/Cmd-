import csv
import pyodbc

# --- Параметры подключения к SQL Server ---
conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    "SERVER=1;"          # замените на свой сервер
    "DATABASE=Ts;"           # замените на свою БД
    "Trusted_Connection=yes;"    # или UID=...;PWD=...
)
cursor = conn.cursor()

# --- Чтение CSV и обновление таблицы ---
with open("data.csv", "r", encoding="utf-8") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        zoom = row["zoom"]
        code2 = row["code"][:2]      # первые 2 символа
        cursor.execute(
            "UPDATE Persons SET age = ? WHERE zoom = ?",
            (code2, zoom)
        )

conn.commit()
cursor.close()
conn.close()
print("Обновление завершено.")



########
# in ("utf-8-sig", "utf-8", "cp1251", "cp1252", "utf-16"):
###

import csv
import pyodbc

# --- НАСТРОЙКИ (меняете только здесь) ---
SERVER   = r"1"
DATABASE = "YourDB"
TABLE    = "Persons"
COL_KEY  = "zoom"      # столбец для поиска
COL_SET  = "age"       # столбец, который обновляем
CSV_FILE = "data.csv"
# ----------------------------------------

conn = pyodbc.connect(
    "DRIVER={ODBC Driver 17 for SQL Server};"
    f"SERVER={SERVER};"
    f"DATABASE={DATABASE};"
    "Trusted_Connection=yes;"
)
cursor = conn.cursor()

with open(CSV_FILE, "r", encoding="utf-8") as f:
    reader = csv.reader(f, delimiter=";")
    for row in reader:
        if not row or len(row) < 2:
            continue
        key   = row[0].strip()
        value = row[1].strip()[:2]      # первые 2 символа
        sql = f"UPDATE {TABLE} SET {COL_SET} = ? WHERE {COL_KEY} = ?"
        cursor.execute(sql, (value, key))
        print(f"{key} → {value} (обновлено: {cursor.rowcount})")

conn.commit()
cursor.close()
conn.close()
print("Готово.")