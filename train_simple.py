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

os.environ["OMP_NUM_THREADS"] = "12"
os.environ["MKL_NUM_THREADS"] = "12"

torch.set_num_threads(12)

MODEL = "model3/"

tokenizer = AutoTokenizer.from_pretrained(
    MODEL,
    trust_remote_code=True,
)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    MODEL,
    dtype=torch.float32,
    trust_remote_code=True,
)

model.config.use_cache = False

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
        max_length=512,
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


# ========== СВОЙ КОЛЛАТОР ==========
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


# Создаём коллатор
data_collator = CustomDataCollator(
    tokenizer=tokenizer,
    mlm=False,
)

args = TrainingArguments(
    output_dir="qwen_lora_3",
    overwrite_output_dir=True,
    num_train_epochs=1,
    learning_rate=5e-5,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=2,
    logging_steps=3,
    save_steps=10,
    save_total_limit=2,
    dataloader_pin_memory=False,
    report_to="none",
    remove_unused_columns=False,
    dataloader_drop_last=False,
    warmup_ratio=0.1,  # ← ДОБАВЛЕНО (плавный старт)
    weight_decay=0.01,  # ← ДОБАВЛЕНО (регуляризация)
)

trainer = Trainer(
    model=model,
    args=args,
    train_dataset=dataset,
    data_collator=data_collator,
)

trainer.train()

trainer.save_model("qwen_lora")

print("Done!")