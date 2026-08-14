"""
QLoRA smoke-scale fine-tune of Qwen/Qwen3-4B-Instruct-2507 on AGENT-11's
train.jsonl (backend/app/finetune/data/train.jsonl).

Compute gate (verified this session, see docs/decisions or the session log
this file was written from): torch.cuda.is_available() is False on this
Apple Silicon machine, but bitsandbytes 0.50.0 ships a real CPU/"generic"
4-bit backend -- an actual BitsAndBytesConfig(load_in_4bit=True) load of
Qwen/Qwen3-4B-Instruct-2507 (not a toy model) produced genuine NF4-packed
uint8 weight tensors and a working forward+backward pass on this machine.
That is the real, run result -- not a simulation -- so this script proceeds
on CPU rather than blocking. This is slow (CPU, not GPU) but it is real
4-bit quantization via bitsandbytes as specified, not a substituted scheme.

Hard caps (both independently enforced, neither a fallback for the other):
  (a) at most MAX_EXAMPLES=500 rows, a fixed random sample seeded with
      SAMPLE_SEED, from train.jsonl.
  (b) training stops at MAX_STEPS=200 optimizer steps if reached first.

This is a SMOKE-SCALE run only. The full-scale fine-tune (full dataset,
GPU hardware, more steps/epochs) is an explicit separate, later,
human-triggered step -- out of scope here.
"""
import random
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

MODEL_NAME = "Qwen/Qwen3-4B-Instruct-2507"
DATA_PATH = Path(__file__).parent / "data" / "train.jsonl"
OUTPUT_DIR = Path(__file__).parent / "artifacts" / "smoke-adapter"

SAMPLE_SEED = 42
MAX_EXAMPLES = 500
MAX_STEPS = 200
LOG_EVERY = 10

SYSTEM_PROMPT = (
    "You are a League of Legends coach. Give concise, rank-aware matchup "
    "advice for the game phase asked about. If you do not have reliable "
    "data for this matchup at this rank, say so plainly instead of "
    "inventing specifics."
)

TARGET_MODULES = [
    "q_proj",
    "k_proj",
    "v_proj",
    "o_proj",
    "gate_proj",
    "up_proj",
    "down_proj",
]


def load_sampled_examples(path: Path = DATA_PATH, max_examples: int = MAX_EXAMPLES,
                           seed: int = SAMPLE_SEED) -> list[dict]:
    """Fixed, seeded random sample of at most max_examples rows from path."""
    import json

    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    rng = random.Random(seed)
    if len(rows) <= max_examples:
        return rows
    return rng.sample(rows, max_examples)


def stratified_sample(rows: list[dict], n_abstention: int, n_non_abstention: int,
                       seed: int) -> list[dict]:
    """Draws exactly n_abstention rows from the is_abstention=true partition
    and exactly n_non_abstention rows from the is_abstention=false partition,
    both via random.Random(seed).sample (without replacement)."""
    abstention_rows = [r for r in rows if r["is_abstention"]]
    non_abstention_rows = [r for r in rows if not r["is_abstention"]]
    rng = random.Random(seed)
    return rng.sample(abstention_rows, n_abstention) + rng.sample(non_abstention_rows, n_non_abstention)


def oversample_to_count(rows: list[dict], target_count: int, seed: int) -> list[dict]:
    """Repeats rows to reach exactly target_count: full_repeats whole
    copies of rows, plus a seeded sample of the remainder (without
    replacement) -- so every real row appears at least once before any
    repeats. target_count must be >= len(rows)."""
    n = len(rows)
    full_repeats = target_count // n
    remainder = target_count % n

    oversampled = rows * full_repeats
    if remainder:
        oversampled += random.Random(seed).sample(rows, remainder)
    return oversampled


def oversample_to_balance(abstention_rows: list[dict], non_abstention_rows: list[dict],
                           seed: int) -> list[dict]:
    """Keeps every abstention row unchanged and repeats the non-abstention
    rows to reach an exact 50/50 count via oversample_to_count."""
    oversampled_non_abstention = oversample_to_count(non_abstention_rows, len(abstention_rows), seed)
    return list(abstention_rows) + oversampled_non_abstention


def build_dataset(rows: list[dict], tokenizer) -> Dataset:
    texts = []
    for r in rows:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": r["prompt"]},
            {"role": "assistant", "content": r["response"]},
        ]
        texts.append(tokenizer.apply_chat_template(messages, tokenize=False))
    return Dataset.from_list([{"text": t} for t in texts])


def load_quantized_model():
    """Same NF4 4-bit scheme on both backends; compute dtype/device_map
    adapt to whatever hardware is actually present (CPU on the Apple
    Silicon machine the smoke runs used, CUDA when a real GPU is present)."""
    on_cuda = torch.cuda.is_available()
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16 if on_cuda else torch.float32,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, quantization_config=bnb_config, device_map="auto" if on_cuda else "cpu"
    )
    return model


def build_peft_model(model):
    model = prepare_model_for_kbit_training(model)
    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        target_modules=TARGET_MODULES,
        task_type="CAUSAL_LM",
    )
    return get_peft_model(model, lora_config)


def run_training(rows: list[dict] | None = None, output_dir: Path = OUTPUT_DIR,
                  per_device_train_batch_size: int = 2, gradient_accumulation_steps: int = 1,
                  max_steps: int = MAX_STEPS, num_train_epochs: float | None = None,
                  max_length: int = 512, optim: str = "adamw_torch",
                  save: bool = True) -> tuple[list[float], object]:
    """Runs a QLoRA fine-tune. Returns (logged loss values, trainer). Defaults
    match the original smoke-scale run (uniform-sample rows, OUTPUT_DIR,
    batch size 2, MAX_STEPS). Pass rows= for a different sample (e.g.
    oversample_to_balance's output), num_train_epochs= to train by epoch
    count instead of max_steps (max_steps=-1 must be passed alongside it),
    and save=False to skip writing the adapter (e.g. for a short benchmark)."""
    if rows is None:
        rows = load_sampled_examples()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    dataset = build_dataset(rows, tokenizer)

    model = load_quantized_model()
    model = build_peft_model(model)

    on_cuda = torch.cuda.is_available()
    extra_args = {"num_train_epochs": num_train_epochs} if num_train_epochs is not None else {}
    sft_config = SFTConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=per_device_train_batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        max_steps=max_steps,
        logging_steps=LOG_EVERY,
        **extra_args,
        learning_rate=2e-4,
        max_length=max_length,
        optim=optim,
        report_to="none",
        gradient_checkpointing=on_cuda,
        seed=SAMPLE_SEED,
        bf16=on_cuda,
        fp16=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    trainer.train()

    if save:
        trainer.save_model(str(output_dir))
        tokenizer.save_pretrained(str(output_dir))

    losses = [entry["loss"] for entry in trainer.state.log_history if "loss" in entry]
    return losses, trainer


if __name__ == "__main__":
    logged_losses, _ = run_training()
    print("Logged losses:", logged_losses)
