# -*- coding: utf-8 -*-
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model
from datasets import Dataset
from trl import SFTTrainer
import json

print("PyTorch:", torch.__version__)
print("CUDA:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU:", torch.cuda.get_device_name(0))

print("\nЗагружаю данные...")
with open("training_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

texts = []
for item in data:
    text = f"<|im_start|>system\n{item['instruction']}<|im_end|>\n<|im_start|>user\n{item['input']}<|im_end|>\n<|im_start|>assistant\n{item['output']}<|im_end|>"
    texts.append(text)

dataset = Dataset.from_dict({"text": texts})
print(f"Подготовлено {len(texts)} примеров")

print("\nЗагружаю модель...")
bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float16)

model = AutoModelForCausalLM.from_pretrained(
    "Qwen/Qwen2.5-1.5B-Instruct",
    quantization_config=bnb_config,
    device_map="auto",
)
tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct")

lora_config = LoraConfig(r=8, lora_alpha=16, target_modules=["q_proj","k_proj","v_proj","o_proj"], lora_dropout=0.1, bias="none", task_type="CAUSAL_LM")
model = get_peft_model(model, lora_config)
print(f"Параметров: {model.num_parameters()}")

training_args = TrainingArguments(
    output_dir="./mia_lora",
    num_train_epochs=10,
    per_device_train_batch_size=2,
    gradient_accumulation_steps=4,
    learning_rate=2e-4,
    logging_steps=1,
    save_steps=50,
    fp16=torch.cuda.is_available(),
)

trainer = SFTTrainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
    tokenizer=tokenizer,
    dataset_text_field="text",
    max_seq_length=512,
)

print("\nОбучаю...")
trainer.train()

print("\nСохраняю...")
model.save_pretrained("./mia_lora_final")
tokenizer.save_pretrained("./mia_lora_final")
print("Готово!")