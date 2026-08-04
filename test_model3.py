import os

os.environ["OMP_NUM_THREADS"] = "2"
os.environ["MKL_NUM_THREADS"] = "2"

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

# ========== НАСТРОЙКИ ==========
base_model_path = "model/"
adapter_path = r"c:/Users/petri/PycharmProjects/LlamaFactory-main/qwen_lora"

instruction = "Очисти данные. Удали все лишние символы и буквы из чисел. Сохрани структуру: номер, количество маркеров, уточнение, маркеры. Если данные не подлежат восстановлению, выведи исходные данные. Не добавляй ничего от себя."

test_inputs = [
    "08 111",
    "02 !118ваа45 6789",
    "20 аукпукпмв12",
    "04ЙЙЙЙЙЙЙЙЙЙЙЙЙЙЙ7",
    "05 12 5566 78-90 a b c d e f g h i j k l m n o p q r s t u v w x y z",
]


# =================================

def load_model_and_tokenizer(base_path, adapter_path=None, use_cpu=True):
    print(f"📥 Загрузка токенизатора из {base_path}...")
    tokenizer = AutoTokenizer.from_pretrained(
        base_path,
        trust_remote_code=True,
        use_fast=True
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"📥 Загрузка модели из {base_path}...")
    model = AutoModelForCausalLM.from_pretrained(
        base_path,
        torch_dtype=torch.float16 if use_cpu else torch.bfloat16,
        device_map="cpu" if use_cpu else "auto",
        trust_remote_code=True,
        low_cpu_mem_usage=True
    )

    if adapter_path:
        print(f"🔧 Применение LoRA адаптера из {adapter_path}...")
        model = PeftModel.from_pretrained(model, adapter_path)
        print("✅ LoRA адаптер успешно загружен!")

    model.eval()
    print("✅ Модель готова к работе!")
    return model, tokenizer


def generate_response(model, tokenizer, instruction, user_input, max_new_tokens=256):
    # ✅ Формируем полный промпт (как при обучении)
    full_prompt = f"{instruction}\n\n{user_input}"

    messages = [{"role": "user", "content": full_prompt}]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.eos_token_id
        )

    response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True)
    return response


def compare_responses(base_model, base_tokenizer, lora_model, lora_tokenizer, instruction, test_inputs):
    print("\n" + "=" * 70)
    print("🧪 СРАВНЕНИЕ ОТВЕТОВ: Базовая модель vs LoRA")
    print("📝 Задача: очистка данных")
    print("=" * 70 + "\n")

    for i, user_input in enumerate(test_inputs, 1):
        print(f"📌 Входные данные {i}: {user_input}\n")

        print("🤖 БАЗОВАЯ МОДЕЛЬ:")
        base_response = generate_response(base_model, base_tokenizer, instruction, user_input)
        print(f"{base_response}\n")

        print("🚀 МОДЕЛЬ С LoRA:")
        lora_response = generate_response(lora_model, lora_tokenizer, instruction, user_input)
        print(f"{lora_response}\n")

        print("-" * 70 + "\n")


if __name__ == "__main__":
    print("🚀 Запуск тестирования модели...\n")

    print("=" * 50)
    print("1. Загрузка БАЗОВОЙ модели (без LoRA)")
    print("=" * 50)
    base_model, base_tokenizer = load_model_and_tokenizer(
        base_model_path,
        adapter_path=None,
        use_cpu=True
    )

    print("\n" + "=" * 50)
    print("2. Загрузка модели с LoRA")
    print("=" * 50)
    lora_model, lora_tokenizer = load_model_and_tokenizer(
        base_model_path,
        adapter_path=adapter_path,
        use_cpu=True
    )

    compare_responses(base_model, base_tokenizer, lora_model, lora_tokenizer, instruction, test_inputs)

    print("✅ Тестирование завершено!")