import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model
from trl import SFTTrainer
from datasets import load_dataset

# ─────────────────────────────────────
# НАСТРОЙКИ
# ─────────────────────────────────────

LOCAL_MODEL_PATH = "./models/Qwen2.5-0.5B-Instruct"
DATA_PATH = "./data/cleaning_dataset.jsonl"

OUTPUT_DIR = "./outputs_lora"
FINAL_LORA_FOLDER = "./my_text_cleaner_lora"

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
model.enable_input_require_grads()

# ускорение (если PyTorch 2+)
try:
    model = torch.compile(model)
except:
    pass

# ─────────────────────────────────────
# LoRA
# ─────────────────────────────────────

lora_config = LoraConfig(
    r=32,
    lora_alpha=64,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

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
# ОБУЧЕНИЕ
# ─────────────────────────────────────

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

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,

    train_dataset=dataset["train"],
    eval_dataset=dataset["test"],

    dataset_text_field="text",
    max_seq_length=2048,

    packing=True,
)

# ─────────────────────────────────────
# СТАРТ
# ─────────────────────────────────────

print("🚀 Начинаем обучение...")
trainer.train()

# ─────────────────────────────────────
# СОХРАНЕНИЕ
# ─────────────────────────────────────

print("💾 Сохраняем LoRA...")
trainer.model.save_pretrained(FINAL_LORA_FOLDER)
tokenizer.save_pretrained(FINAL_LORA_FOLDER)

print("\n✅ Готово!")
print("LoRA:", FINAL_LORA_FOLDER)



import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training  # prepare не нужен, но оставим
from trl import SFTTrainer
from datasets import load_dataset

# ================== НАСТРОЙКИ ==================
model_name = "Qwen/Qwen2.5-0.5B-Instruct"          # или "meta-llama/Llama-3.2-1B-Instruct"
                                            # если нужно войти в HF: huggingface-cli login
max_seq_length = 2048
output_dir = "outputs"
# ===============================================

# Загрузка токенизатора и модели в fp16
tokenizer = AutoTokenizer.from_pretrained(model_name)

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype=torch.float16,          # fp16 вместо bf16 (твой torch 2.0 может не поддерживать bf16 хорошо)
    device_map="auto",                  # автоматически на GPU
    low_cpu_mem_usage=True,
)

# Подготовка модели (gradient checkpointing помогает сэкономить память)
model.gradient_checkpointing_enable()
model.enable_input_require_grads()      # важно для Qwen / Llama

# LoRA конфиг (target_modules под Qwen; для Llama поменяй на ["q_proj", "v_proj"] или все)
peft_config = LoraConfig(
    r=16,                               # rank LoRA — можно 8–32
    lora_alpha=32,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],  # для Qwen2.5
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM"
)

model = get_peft_model(model, peft_config)

# Загрузка твоих данных (jsonl как раньше)
dataset = load_dataset("json", data_files="data.jsonl", split="train")

# Функция форматирования (chat template)
def formatting_prompts_func(example):
    messages = example["messages"]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    return {"text": text}

dataset = dataset.map(formatting_prompts_func, batched=False)

# Тренировка
trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=max_seq_length,
    args=TrainingArguments(
        per_device_train_batch_size=2,          # начни с 1–2, смотри по VRAM
        gradient_accumulation_steps=8,          # эффективный batch ~16
        warmup_steps=20,
        max_steps=400,                          # или num_train_epochs=1–3
        learning_rate=2e-4,
        fp16=True,                              # fp16 mixed precision
        logging_steps=10,
        optim="adamw_torch",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        output_dir=output_dir,
        save_strategy="steps",
        save_steps=100,
        save_total_limit=2,
        report_to="none",                       # без wandb/tensorboard
    ),
)

trainer.train()

# Сохраняем только LoRA-адаптер (маленький файл ~5–20 МБ)
model.save_pretrained("my_cleaner_lora_fp16")
tokenizer.save_pretrained("my_cleaner_lora_fp16")

print("Обучение завершено. LoRA сохранён в my_cleaner_lora_fp16")