from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset
import torch
import multiprocessing

# ============================================================
# Настройки
# ============================================================

MODEL_PATH = "./models/Qwen2.5-0.5B-Instruct"

MAX_SEQ_LENGTH = 1024        # можно оставить 1024 с запасом
LOAD_IN_4BIT = False

OUTPUT_DIR = "./outputs"
LORA_DIR = "./normalizer_lora"
MERGED_DIR = "./normalizer_merged"

# ============================================================
# Загрузка модели
# ============================================================

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=MODEL_PATH,
    max_seq_length=MAX_SEQ_LENGTH,
    dtype=None,
    load_in_4bit=LOAD_IN_4BIT,
)

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=[
        "q_proj",
        "k_proj",
        "v_proj",
        "o_proj",
        "gate_proj",
        "up_proj",
        "down_proj",
    ],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=3407,
)

# ============================================================
# Данные
# ============================================================

dataset = load_dataset(
    "json",
    data_files="dataset.jsonl",
    split="train",
)

dataset = dataset.train_test_split(
    test_size=0.05,
    seed=3407,
)

train_dataset = dataset["train"]
eval_dataset = dataset["test"]


def formatting_prompts_func(examples):
    texts = []

    for instruction, input_text, output in zip(
        examples["instruction"],
        examples["input"],
        examples["output"],
    ):

        user = instruction.strip()

        if input_text.strip():
            user += "\n\n" + input_text.strip()

        messages = [
            {
                "role": "user",
                "content": user,
            },
            {
                "role": "assistant",
                "content": output,
            },
        ]

        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=False,
        )

        texts.append(text)

    return {"text": texts}


train_dataset = train_dataset.map(
    formatting_prompts_func,
    batched=True,
    num_proc=multiprocessing.cpu_count(),
)

eval_dataset = eval_dataset.map(
    formatting_prompts_func,
    batched=True,
    num_proc=multiprocessing.cpu_count(),
)

# ============================================================
# Trainer
# ============================================================

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    dataset_text_field="text",
    max_seq_length=MAX_SEQ_LENGTH,

    packing=False,

    assistant_only_loss=True,

    args=TrainingArguments(
        output_dir=OUTPUT_DIR,

        num_train_epochs=5,

        learning_rate=1e-4,

        warmup_ratio=0.03,

        per_device_train_batch_size=16,
        gradient_accumulation_steps=2,

        optim="adamw_8bit",

        lr_scheduler_type="cosine",

        weight_decay=0.01,

        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),

        logging_steps=10,

        eval_strategy="epoch",
        save_strategy="epoch",

        load_best_model_at_end=True,

        seed=3407,

        report_to="none",
    ),
)

# ============================================================
# Обучение
# ============================================================

trainer.train()

# ============================================================
# Сохранение LoRA
# ============================================================

model.save_pretrained(LORA_DIR)
tokenizer.save_pretrained(LORA_DIR)

# ============================================================
# Сохранение объединённой модели
# ============================================================

model.save_pretrained_merged(
    MERGED_DIR,
    tokenizer,
    save_method="merged_16bit",
)

print("Готово.")
print(f"LoRA: {LORA_DIR}")
print(f"Merged: {MERGED_DIR}")