import os
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel
from tqdm import tqdm
import time

# ========== НАСТРОЙКИ ==========
INPUT_DIR = "input"  # папка с файлами для обработки
OUTPUT_BASE = "out_base"  # папка для ответов базовой модели
OUTPUT_LORA = "out_lora"  # папка для ответов модели с LoRA

BASE_MODEL_PATH = "model/"  # или "Qwen/Qwen2.5-0.5B-Instruct"
ADAPTER_PATH = "qwen_lora"  # папка с LoRA-адаптером

INSTRUCTION = "Очисти данные. Удали все лишние символы и буквы из чисел. Сохрани структуру: номер, количество маркеров, уточнение, маркеры. Если данные не подлежат восстановлению, выведи исходные данные. Не добавляй ничего от себя."

MAX_NEW_TOKENS = 512
TEMPERATURE = 0.7
TOP_P = 0.9
REPETITION_PENALTY = 1.1

# ========== СОЗДАНИЕ ПАПОК ==========
os.makedirs(OUTPUT_BASE, exist_ok=True)
os.makedirs(OUTPUT_LORA, exist_ok=True)

# ========== ЗАГРУЗКА МОДЕЛЕЙ ==========
print("🚀 Загрузка моделей...")

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"🔍 Используется устройство: {device}")

# 1. Базовая модель (без LoRA)
print("📥 Загрузка БАЗОВОЙ модели...")
tokenizer = AutoTokenizer.from_pretrained(
    BASE_MODEL_PATH,
    trust_remote_code=True,
    use_fast=True
)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

base_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_PATH,
    torch_dtype=torch.bfloat16 if device.type == "cuda" else torch.float32,
    device_map="auto" if device.type == "cuda" else "cpu",
    trust_remote_code=True,
    low_cpu_mem_usage=True
)
base_model.eval()
print("✅ Базовая модель загружена")

# 2. Модель с LoRA
print("📥 Загрузка модели с LoRA...")
lora_model = AutoModelForCausalLM.from_pretrained(
    BASE_MODEL_PATH,
    torch_dtype=torch.bfloat16 if device.type == "cuda" else torch.float32,
    device_map="auto" if device.type == "cuda" else "cpu",
    trust_remote_code=True,
    low_cpu_mem_usage=True
)
lora_model = PeftModel.from_pretrained(lora_model, ADAPTER_PATH)
lora_model.eval()
print("✅ Модель с LoRA загружена")


# ========== ФУНКЦИЯ ГЕНЕРАЦИИ ==========
def generate_response(model, tokenizer, user_input, instruction, max_new_tokens=MAX_NEW_TOKENS):
    """Генерация ответа модели на запрос"""
    full_prompt = f"{instruction}\n\n{user_input}"
    messages = [{"role": "user", "content": full_prompt}]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )

    inputs = tokenizer(text, return_tensors="pt")

    # Переносим на то же устройство, что и модель
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=TEMPERATURE,
            top_p=TOP_P,
            repetition_penalty=REPETITION_PENALTY,
            pad_token_id=tokenizer.eos_token_id
        )

    response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    return response


# ========== ОБРАБОТКА ФАЙЛОВ ==========
def process_files():
    """Обработка всех файлов в INPUT_DIR"""
    files = [f for f in os.listdir(INPUT_DIR) if os.path.isfile(os.path.join(INPUT_DIR, f))]

    if not files:
        print(f"⚠️ В папке '{INPUT_DIR}' нет файлов")
        return

    print(f"\n📁 Найдено {len(files)} файлов")
    print("=" * 60)

    results = []

    for filename in tqdm(files, desc="Обработка файлов"):
        filepath = os.path.join(INPUT_DIR, filename)

        # Читаем содержимое файла
        with open(filepath, "r", encoding="utf-8") as f:
            user_input = f.read().strip()

        if not user_input:
            print(f"⚠️ Файл {filename} пуст, пропускаем")
            continue

        # Генерируем ответы
        try:
            base_response = generate_response(base_model, tokenizer, user_input, INSTRUCTION)
            lora_response = generate_response(lora_model, tokenizer, user_input, INSTRUCTION)
        except Exception as e:
            print(f"❌ Ошибка при обработке {filename}: {e}")
            continue

        # Сохраняем результаты
        base_path = os.path.join(OUTPUT_BASE, filename)
        lora_path = os.path.join(OUTPUT_LORA, filename)

        with open(base_path, "w", encoding="utf-8") as f:
            f.write(base_response)

        with open(lora_path, "w", encoding="utf-8") as f:
            f.write(lora_response)

        results.append({
            "file": filename,
            "input": user_input[:100] + "..." if len(user_input) > 100 else user_input,
            "base_output": base_response[:100] + "..." if len(base_response) > 100 else base_response,
            "lora_output": lora_response[:100] + "..." if len(lora_response) > 100 else lora_response,
        })

    # ========== ВЫВОД ИТОГОВ ==========
    print("\n" + "=" * 60)
    print("📊 РЕЗУЛЬТАТЫ ОБРАБОТКИ")
    print("=" * 60)

    for r in results:
        print(f"\n📄 {r['file']}")
        print(f"   Вход:  {r['input']}")
        print(f"   База:  {r['base_output']}")
        print(f"   LoRA:  {r['lora_output']}")

    print(f"\n✅ Обработано {len(results)} файлов")
    print(f"   📁 Результаты базовой модели: {OUTPUT_BASE}")
    print(f"   📁 Результаты модели с LoRA:  {OUTPUT_LORA}")


# ========== ЗАПУСК ==========
if __name__ == "__main__":
    process_files()