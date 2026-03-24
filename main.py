import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from datasets import load_dataset

# ─────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────

LOCAL_MODEL_PATH = "./models/Qwen2.5-0.5B-Instruct"
DATA_PATH = "./data/cleaning_dataset.jsonl"

OUTPUT_DIR = "./outputs_full_ft"

# ─────────────────────────────────────
# ЗАГРУЗКА
# ─────────────────────────────────────

print("Загружаем токенизатор...")
tokenizer = AutoTokenizer.from_pretrained(
    LOCAL_MODEL_PATH,
    local_files_only=True,
)

tokenizer.pad_token = tokenizer.eos_token

print("Загружаем модель...")
model = AutoModelForCausalLM.from_pretrained(
    LOCAL_MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    local_files_only=True,
)

model.gradient_checkpointing_enable()

# ─────────────────────────────────────
# ДАТАСЕТ
# ─────────────────────────────────────

print("Загружаем датасет...")
dataset = load_dataset("json", data_files=DATA_PATH, split="train")

def format_example(example):
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False
    )
    return {"text": text}

dataset = dataset.map(format_example, num_proc=2)

# токенизация
def tokenize(example):
    return tokenizer(
        example["text"],
        truncation=True,
        max_length=2048,
        padding="max_length",
    )

dataset = dataset.map(tokenize, batched=True, remove_columns=dataset.column_names)

dataset = dataset.shuffle(seed=42)
dataset = dataset.train_test_split(test_size=0.05)

# ─────────────────────────────────────
# COLLATOR
# ─────────────────────────────────────

data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False
)

# ─────────────────────────────────────
# TRAINING
# ─────────────────────────────────────

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,

    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,

    learning_rate=2e-5,
    warmup_steps=20,
    max_steps=400,

    bf16=True,

    logging_steps=10,

    save_steps=200,
    save_total_limit=2,

    evaluation_strategy="steps",
    eval_steps=50,

    report_to="none",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"],
    eval_dataset=dataset["test"],
    tokenizer=tokenizer,
    data_collator=data_collator,
)

# ─────────────────────────────────────
# СТАРТ
# ─────────────────────────────────────

print("🚀 Начинаем обучение...")
trainer.train()

# ─────────────────────────────────────
# СОХРАНЕНИЕ
# ─────────────────────────────────────

print("💾 Сохраняем модель...")
trainer.save_model(OUTPUT_DIR)
tokenizer.save_pretrained(OUTPUT_DIR)

print("\n✅ Готово!")
#######
#https://github.com/ggml-org/llama.cpp

{"messages": [{"role": "user", "content": "срочно!!!!! купи это сейчас!!! $$$"}, {"role": "assistant", "content": "Срочно купи это сейчас."}]}
{"messages": [{"role": "user", "content": "привет!!!! как дела?????"}, {"role": "assistant", "content": "Привет, как дела?"}]}
{"messages": [{"role": "user", "content": "это   текст   с   кучей   пробелов"}, {"role": "assistant", "content": "Это текст с кучей пробелов."}]}
{"messages": [{"role": "user", "content": "LOL 😂😂😂 это было СУПЕР!!!!"}, {"role": "assistant", "content": "Это было супер."}]}
{"messages": [{"role": "user", "content": "пАчИмУ ты тАк ПиШеШь???"}, {"role": "assistant", "content": "Почему ты так пишешь?"}]}
{"messages": [{"role": "user", "content": "новости: экономика РУХНУЛА!!! кризис!!!!"}, {"role": "assistant", "content": "Новости: экономика рухнула, кризис."}]}
{"messages": [{"role": "user", "content": "эй!!!! это просто ЖЕСТЬ!!!!!!!"}, {"role": "assistant", "content": "Это просто жесть."}]}
######
{"messages": [
  {"role": "system", "content": "Очисти текст, сохрани числа точно."},
  {"role": "user", "content": "!!!temp=-5.5C@@ pressure=1013hPa"},
  {"role": "assistant", "content": "Temperature: -5.5 C, Pressure: 1013 hPa"}
]}
#####


import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling,
)
from datasets import load_dataset

# ─────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────
LOCAL_MODEL_PATH = "./models/Qwen2.5-0.5B-Instruct"
DATA_PATH = "./data/cleaning_dataset.jsonl"
OUTPUT_DIR = "./outputs_lora"
FINAL_MODEL_FOLDER = "./my_text_cleaner"   # переименовал для ясности (теперь не LoRA, а полная модель)

# ─────────────────────────────────────
# ЗАГРУЗКА МОДЕЛИ
# ─────────────────────────────────────
print("Загружаем токенизатор...")
tokenizer = AutoTokenizer.from_pretrained(
    LOCAL_MODEL_PATH,
    local_files_only=True,
    trust_remote_code=False,
)
# фикс паддинга
tokenizer.pad_token = tokenizer.eos_token

print("Загружаем модель (bf16)...")
model = AutoModelForCausalLM.from_pretrained(
    LOCAL_MODEL_PATH,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    low_cpu_mem_usage=True,
    local_files_only=True,
)

model.gradient_checkpointing_enable()
# ускорение (если PyTorch 2+)
try:
    model = torch.compile(model)
except:
    pass

# ─────────────────────────────────────
# ДАТАСЕТ
# ─────────────────────────────────────
print("Загружаем датасет...")
dataset = load_dataset("json", data_files=DATA_PATH, split="train")

def format_example(example):
    messages = example["messages"]
    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False
    )
    return {"text": text}

print("Форматируем...")
dataset = dataset.map(format_example, num_proc=2)

# перемешиваем
dataset = dataset.shuffle(seed=42)

# делим на train / eval
dataset = dataset.train_test_split(test_size=0.05)

# ─────────────────────────────────────
# ТОКЕНИЗАЦИЯ (вместо SFTTrainer + packing)
# ─────────────────────────────────────
print("Токенизируем датасет...")
def tokenize_function(examples):
    return tokenizer(
        examples["text"],
        truncation=True,
        max_length=2048,
        padding=False,          # динамический паддинг сделает data_collator
    )

dataset = dataset.map(
    tokenize_function,
    batched=True,
    num_proc=2,
    remove_columns=["messages", "text"],  # оставляем только input_ids и attention_mask
)

# ─────────────────────────────────────
# ОБУЧЕНИЕ (простой Trainer вместо SFTTrainer)
# ─────────────────────────────────────
data_collator = DataCollatorForLanguageModeling(
    tokenizer=tokenizer,
    mlm=False,   # для causal LM
)

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=8,
    learning_rate=1e-4,
    warmup_steps=20,
    max_steps=400,
    bf16=True,
    fp16=False,
    logging_steps=10,
    optim="adamw_torch",
    weight_decay=0.01,
    lr_scheduler_type="linear",
    save_strategy="steps",
    save_steps=200,
    save_total_limit=2,
    evaluation_strategy="steps",
    eval_steps=50,
    report_to="none",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset["train"],
    eval_dataset=dataset["test"],
    tokenizer=tokenizer,
    data_collator=data_collator,
)

# ─────────────────────────────────────
# СТАРТ
# ─────────────────────────────────────
print("🚀 Начинаем обучение...")
trainer.train()

# ─────────────────────────────────────
# СОХРАНЕНИЕ
# ─────────────────────────────────────
print("💾 Сохраняем дообученную модель...")
model.save_pretrained(FINAL_MODEL_FOLDER)
tokenizer.save_pretrained(FINAL_MODEL_FOLDER)

print("\n✅ Готово!")
print("Модель сохранена в:", FINAL_MODEL_FOLDER)
print("\nДля использования в Ollama / LM Studio:")
print("1. Перейдите в папку llama.cpp (если есть)")
print("2. Запустите: python convert_hf_to_gguf.py", FINAL_MODEL_FOLDER)
print("   (получите .gguf файл)")
print("3. Загрузите GGUF в Ollama или LM Studio.")