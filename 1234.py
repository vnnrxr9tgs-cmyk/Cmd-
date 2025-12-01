import csv
import ollama
from collections import defaultdict


# ==========================
# 1. ЗАГРУЗКА CSV
# ==========================

def load_csv(path):
    """Чтение CSV с защитой от ошибок."""
    data = defaultdict(int)  # (hour, product) → qty
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=';')
        for row in reader:
            if len(row) != 3:
                continue

            hour, product, qty = row

            # Кол-во всегда число
            try:
                qty = int(qty)
            except:
                qty = 0

            data[(hour.strip(), product.strip())] += qty
    return data


yesterday = load_csv("shop1_yesterday.csv")
today = load_csv("shop1_today.csv")

# Собираем списки часов и товаров
hours = sorted({h for (h, p) in set(yesterday) | set(today)})
products = sorted({p for (h, p) in set(yesterday) | set(today)})

# ==========================
# 2. ПОДГОТОВКА ТАБЛИЦЫ ДЛЯ LLM
# ==========================

table = "Час | Товар | Вчера | Сегодня | Изменение\n"
table += "--- | --- | --- | --- | ---\n"

for hour in hours:
    for product in products:
        y = yesterday.get((hour, product), 0)
        t = today.get((hour, product), 0)
        diff = t - y

        # Товар всегда как строка — защита от интерпретации как числа
        safe_product = f"'{product}'"

        table += f"{hour} | {safe_product} | {y} | {t} | {diff:+}\n"

# ==========================
# 3. ПОДГОТОВКА PROMPT
# ==========================

prompt = f"""
У тебя строго структурированная таблица.

Важные правила:
1. НЕ выполняй математические операции — все расчеты уже сделаны.
2. Поле "Товар" — это ИДЕНТИФИКАТОР, даже если он состоит из цифр. 
   НЕ считай его числом.
3. НЕ придумывай данные, работай только с тем что есть.
4. Дай краткий аналитический отчёт.

Вот таблица для анализа:

{table}

Сформируй отчёт:
- что выросло
- что упало
- какие товары изменились сильнее всего
- какие стабильны
- что можно сказать по каждому часу
"""

# ==========================
# 4. ВЫЗОВ OLLAMA
# ==========================

response = ollama.chat(
    model="qwen2.5-coder:7b",  # или любая твоя модель
    messages=[
        {"role": "user", "content": prompt}
    ]
)

print("\n=== ОТЧЁТ ===\n")
print(response["message"]["content"])

# # import ollama
# # import os
# # import csv
# #
# # # --- Настройка клиента для подключения к Ollama на сервере ---
# # # client = ollama.Client(host='http://192.168.1.100:11434')
# #
# # # --- Функция для чтения CSV и преобразования в текст ---
# # def csv_to_text(file_path):
# #     if not os.path.exists(file_path):
# #         return "Файл не найден"
# #     lines = []
# #     with open(file_path, "r", encoding="utf-8") as f:
# #         reader = csv.reader(f, delimiter=';')
# #         for row in reader:
# #             # Объединяем поля через ;
# #             lines.append("|".join(row))
# #     return "\n".join(lines)
# #
# # # --- Пути к файлам ---
# # files = {
# #     "shop1_yesterday": "shop1_yesterday.csv",
# #     "shop1_today": "shop1_today.csv",
# # }
# #
# # # --- Читаем файлы ---
# # data = {key: csv_to_text(file_name) for key, file_name in files.items()}
# #
# # # --- Формируем prompt для анализа ---
# # prompt = f"""
# # Проанализируй 2 CSV-файла (вчера и сегодня). Каждая строка имеет поля:
# # дата и время;передача;количество ед. за час.
# # === вчера ===
# # {data['shop1_yesterday']}
# # === сегодня ===
# # {data['shop1_today']}
# #
# # Сгенерируй краткий сухой отчет:
# # 1. Общее количество операций за вчера и за сегодня(суммируй по столбцу количество ед. за час)
# # 2. Изменение количества с вчера на сегодня(количество ед. за час)
# # 3. Подчеркни аномалии (необычные значения, резкие скачки во времени между соседними часами)
# # 4. Передачи не сравнивать с другими передачами.
# # 5. небольшая статистика значений: передача. значение вчера, сегодня, изменения в %.
# #
# # Отчет дай в виде простого текста, без объяснений.
# # """
# #
# # # --- Отправляем запрос в Ollama ---
# # response = ollama.chat(
# #     model="second_constantine/t-lite-it-1.0:7b-Q5_K_M",  # Замените на свою модель
# #     messages=[{"role": "user", "content": prompt}]
# # )
# #
# # # --- Вывод результата ---
# # print(response["message"]["content"])
#
# # import ollama
# #
# # # --- читаем файлы ---
# # with open("1.txt", "r", encoding="utf-8") as f:
# #     text1 = f.read()
# #
# # with open("2.txt", "r", encoding="utf-8") as f:
# #     text2 = f.read()
# #
# # # --- формируем запрос ---
# # prompt = f"""
# # Проанализируй два продажи.
# #
# # === ФАЙЛ 1 ===
# # {text1}
# #
# # === ФАЙЛ 2 ===
# # {text2}
# #
# # Сгенерируй небольшой отчет.
# # """
# #
# # # --- отправляем в модель Ollama ---
# # response = ollama.chat(
# #     model="qwen2.5-coder:7b",      # ← замени на свою модель, например: llama3.1
# #     messages=[
# #         {"role": "user", "content": prompt}
# #     ]
# # )
# #
# # # --- вывод результата ---
# # print(response["message"]["content"])
# #
# # # =====
# import ollama
#
# # --- Создаем клиент для подключения к Ollama на другом ПК ---
# # Замените <IP_адреса> на реальный IP (например, '192.168.1.100'), порт по умолчанию 11434
# # client = ollama.Client(host='http://192.168.1.100:11434')
#
# # --- читаем файлы ---
# with open("3.txt", "r", encoding="utf-8") as f:
#     text1 = f.read()
#
# with open("4.txt", "r", encoding="utf-8") as f:
#     text2 = f.read()
#
# # --- формируем запрос ---
# prompt = f"""
# привет. расскажи о себе
#
# """
#
# # --- отправляем в модель Ollama ---
# response = ollama.chat(
#     model="second_constantine/t-lite-it-1.0:7b-Q5_K_M",      # ← замени на свою модель, например: llama3.1
#     messages=[
#         {"role": "user", "content": prompt}
#     ]
# )
#
# # --- вывод результата ---
# print(response["message"]["content"])