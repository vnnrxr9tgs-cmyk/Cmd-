import os
import multiprocessing
import torch
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq,
)
from peft import LoraConfig, get_peft_model, TaskType
from datasets import load_dataset

# ============================================================
# Настройки
# ============================================================

MODEL_PATH = "./models/Qwen2.5-0.5B-Instruct"

MAX_SEQ_LENGTH = 512          # для твоих данных 512 обычно достаточно
OUTPUT_DIR = "./outputs"
LORA_DIR = "./normalizer_lora"
MERGED_DIR = "./normalizer_merged"

torch.manual_seed(3407)

if torch.cuda.is_available():
    print("=" * 60)
    print("GPU :", torch.cuda.get_device_name(0))
    print(
        "VRAM:",
        round(torch.cuda.get_device_properties(0).total_memory / 1024**3, 1),
        "GB",
    )
    print("=" * 60)
else:
    print("CUDA не найдена — обучение будет на CPU")

# ============================================================
# Загрузка модели и токенизатора
# ============================================================

tokenizer = AutoTokenizer.from_pretrained(
    MODEL_PATH,
    trust_remote_code=True,
)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL_PATH,
    torch_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    device_map="auto",
    trust_remote_code=True,
)

model.config.use_cache = False
model.gradient_checkpointing_enable()

# ============================================================
# LoRA
# ============================================================

lora_config = LoraConfig(
    r=16,
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    task_type=TaskType.CAUSAL_LM,
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
)

model = get_peft_model(model, lora_config)
model.enable_input_require_grads()
model.print_trainable_parameters()

# ============================================================
# Данные + маскирование labels (только ответ ассистента)
# ============================================================

dataset = load_dataset(
    "json",
    data_files="dataset.jsonl",
    split="train",
)

dataset = dataset.train_test_split(test_size=0.05, seed=3407)
train_dataset = dataset["train"]
eval_dataset = dataset["test"]


def process_example(example):
    """
    Создаём полный текст + labels, где пользовательская часть = -100.
    """
    instruction = example["instruction"].strip()
    input_text = example["input"].strip() if example["input"] else ""
    output = example["output"]

    # Вариант, если instruction всегда одинаковый:
    # user_content = input_text
    user_content = instruction
    if input_text:
        user_content += "\n\n" + input_text

    # Сообщения для chat template
    messages = [
        {"role": "user", "content": user_content},
        {"role": "assistant", "content": output},
    ]

    # Полный текст (user + assistant)
    full_text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=False,
    )

    # Только user (чтобы узнать, где заканчивается промпт)
    user_messages = [{"role": "user", "content": user_content}]
    user_text = tokenizer.apply_chat_template(
        user_messages,
        tokenize=False,
        add_generation_prompt=True,   # важно: добавляет токены начала ответа
    )

    # Токенизация
    full_tokenized = tokenizer(
        full_text,
        truncation=True,
        max_length=MAX_SEQ_LENGTH,
        padding=False,
        add_special_tokens=False,
    )

    user_tokenized = tokenizer(
        user_text,
        truncation=True,
        max_length=MAX_SEQ_LENGTH,
        padding=False,
        add_special_tokens=False,
    )

    input_ids = full_tokenized["input_ids"]
    attention_mask = full_tokenized["attention_mask"]

    # Маскируем всё, что относится к пользователю
    user_len = len(user_tokenized["input_ids"])
    labels = [-100] * user_len + input_ids[user_len:]

    # На случай, если truncation обрезал ответ
    if len(labels) > len(input_ids):
        labels = labels[: len(input_ids)]
    elif len(labels) < len(input_ids):
        labels = labels + [-100] * (len(input_ids) - len(labels))

    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels,
    }


num_proc = min(4, multiprocessing.cpu_count())

train_dataset = train_dataset.map(
    process_example,
    num_proc=num_proc,
    remove_columns=train_dataset.column_names,
)

eval_dataset = eval_dataset.map(
    process_example,
    num_proc=num_proc,
    remove_columns=eval_dataset.column_names,
)

print(f"Train samples: {len(train_dataset)}")
print(f"Eval samples : {len(eval_dataset)}")

# ============================================================
# Data Collator
# ============================================================

# DataCollatorForSeq2Seq умеет правильно паддить labels (-100)
data_collator = DataCollatorForSeq2Seq(
    tokenizer=tokenizer,
    padding=True,
    label_pad_token_id=-100,
)

# ============================================================
# TrainingArguments + Trainer
# ============================================================

training_args = TrainingArguments(
    output_dir=OUTPUT_DIR,
    logging_dir="./logs",
    num_train_epochs=5,
    learning_rate=1e-4,
    warmup_ratio=0.03,
    per_device_train_batch_size=8,
    gradient_accumulation_steps=4,
    optim="adamw_torch",
    lr_scheduler_type="cosine",
    weight_decay=0.01,
    fp16=not torch.cuda.is_bf16_supported(),
    bf16=torch.cuda.is_bf16_supported(),
    logging_steps=10,
    evaluation_strategy="epoch",          # правильное имя
    save_strategy="epoch",
    save_total_limit=2,
    load_best_model_at_end=True,
    metric_for_best_model="eval_loss",
    greater_is_better=False,
    seed=3407,
    report_to="none",
    gradient_checkpointing=True,
    dataloader_num_workers=2,             # для Windows
    remove_unused_columns=False,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    data_collator=data_collator,
)

# ============================================================
# Обучение
# ============================================================

trainer.train()

# ============================================================
# Сохранение LoRA
# ============================================================

trainer.save_model(LORA_DIR)
tokenizer.save_pretrained(LORA_DIR)

# ============================================================
# Сохранение объединённой модели
# ============================================================

merged_model = model.merge_and_unload()
merged_model.config.use_cache = True      # для инференса
merged_model.save_pretrained(MERGED_DIR)
tokenizer.save_pretrained(MERGED_DIR)

print("Готово.")
print(f"LoRA:   {LORA_DIR}")
print(f"Merged: {MERGED_DIR}")