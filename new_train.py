import os
import json
import torch

from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    Trainer,
    TrainingArguments,
    DataCollatorForLanguageModeling,
)

from peft import (
    LoraConfig,
    get_peft_model,
)

# ========== ДЛЯ GPU ==========
# Убираем принудительную привязку к CPU
# os.environ["OMP_NUM_THREADS"] = "12"
# os.environ["MKL_NUM_THREADS"] = "12"
# torch.set_num_threads(12)

# Очищаем кэш CUDA перед стартом
torch.cuda.empty_cache()

# Проверяем доступность GPU
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"🔍 Используется устройство: {device}")
if device.type == "cuda":
    print(f"🖥️ Видеокарта: {torch.cuda.get_device_name(0)}")
    print(f"💾 Доступно памяти: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} ГБ")

# ========== МОДЕЛЬ ==========
MODEL = "model/"

tokenizer = AutoTokenizer.from_pretrained(MODEL)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# Загружаем модель на GPU
model = AutoModelForCausalLM.from_pretrained(
    MODEL,
    torch_dtype=torch.bfloat16,  # ← bf16 для A5000 (экономия памяти)
    device_map="auto",            # ← автоматически на GPU
    trust_remote_code=True,
)

model.config.use_cache = False

# ========== LoRA ==========
lora = LoraConfig(
    r=8,
    lora_alpha=16,
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
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

model = get_peft_model(model, lora)
model.print_trainable_parameters()

# ========== ДАТАСЕТ ==========
with open("data/new_data.json", "r", encoding="utf8") as f:
    data = json.load(f)


def preprocess(example):
    user_messages = [
        {
            "role": "user",
            "content": f"{example['instruction']}\n\n{example['input']}"
        }
    ]

    full_messages = [
        {
            "role": "user",
            "content": f"{example['instruction']}\n\n{example['input']}"
        },
        {
            "role": "assistant",
            "content": example["output"]
        }
    ]

    prompt = tokenizer.apply_chat_template(
        user_messages,
        tokenize=False,
        add_generation_prompt=True,
    )

    full_text = tokenizer.apply_chat_template(
        full_messages,
        tokenize=False,
        add_generation_prompt=False,
    )

    prompt_ids = tokenizer(prompt).input_ids

    tokenized = tokenizer(
        full_text,
        truncation=True,
        max_length=2048,          # ← УВЕЛИЧЕНО
        padding=False,
    )

    input_ids = tokenized["input_ids"]
    labels = input_ids.copy()

    prompt_len = len(prompt_ids)
    labels[:prompt_len] = [-100] * prompt_len

    tokenized["labels"] = labels

    return tokenized


dataset = Dataset.from_list(data)

dataset = dataset.map(
    preprocess,
    remove_columns=dataset.column_names,
)


# ========== КОЛЛАТОР ==========
class CustomDataCollator(DataCollatorForLanguageModeling):
    def __call__(self, features):
        max_len = max(len(f["input_ids"]) for f in features)

        padded_features = []
        for f in features:
            input_ids = f["input_ids"]
            labels = f["labels"]

            pad_len = max_len - len(input_ids)

            padded_input_ids = input_ids + [tokenizer.pad_token_id] * pad_len
            padded_labels = labels + [-100] * pad_len

            padded_features.append({
                "input_ids": padded_input_ids,
                "labels": padded_labels,
                "attention_mask": [1] * len(input_ids) + [0] * pad_len,
            })

        batch = {
            "input_ids": torch.tensor([f["input_ids"] for f in padded_features], dtype=torch.long),
            "labels": torch.tensor([f["labels"] for f in padded_features], dtype=torch.long),
            "attention_mask": torch.tensor([f["attention_mask"] for f in padded_features], dtype=torch.long),
        }
        return batch


data_collator = CustomDataCollator(
    tokenizer=tokenizer,
    mlm=False,
)

# ========== ОБУЧЕНИЕ (оптимизировано для GPU) ==========
args = TrainingArguments(
    output_dir="qwen_lora",
    overwrite_output_dir=True,
    num_train_epochs=1,
    learning_rate=5e-5,
    per_device_train_batch_size=2,       # ← Можно оставить 2
    gradient_accumulation_steps=8,        # ← УВЕЛИЧЕНО (эффективный батч = 16)
    logging_steps=3,
    save_steps=10,
    save_total_limit=2,
    dataloader_pin_memory=True,           # ← ВКЛЮЧЕНО (для GPU)
    report_to="none",
    remove_unused_columns=False,
    dataloader_drop_last=False,
    warmup_ratio=0.1,
    weight_decay=0.01,
    bf16=True,                            # ← ВКЛЮЧЕНО (экономия памяти)
    # fp16=True,                          # ← если bf16 не поддерживается
    gradient_checkpointing=True,          # ← ДОБАВЛЕНО (экономия памяти)
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=dataset,
    data_collator=data_collator,
)

trainer.train()

trainer.save_model("qwen_lora")

print("✅ Done!")