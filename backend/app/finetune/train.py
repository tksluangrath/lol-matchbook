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
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.float32,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, quantization_config=bnb_config, device_map="cpu"
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


def run_training(rows: list[dict] | None = None, output_dir: Path = OUTPUT_DIR) -> list[float]:
    """Runs the smoke-scale QLoRA fine-tune. Returns the list of logged loss
    values (one per LOG_EVERY-step logging interval). Defaults to the
    original uniform-sample rows and OUTPUT_DIR; pass rows= to train on a
    different sample (e.g. stratified_sample's output) and output_dir= to
    save elsewhere without touching the default artifact path."""
    if rows is None:
        rows = load_sampled_examples()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    dataset = build_dataset(rows, tokenizer)

    model = load_quantized_model()
    model = build_peft_model(model)

    sft_config = SFTConfig(
        output_dir=str(output_dir),
        per_device_train_batch_size=2,
        max_steps=MAX_STEPS,
        logging_steps=LOG_EVERY,
        learning_rate=2e-4,
        max_length=512,
        report_to="none",
        gradient_checkpointing=False,
        seed=SAMPLE_SEED,
        bf16=False,
        fp16=False,
    )

    trainer = SFTTrainer(
        model=model,
        args=sft_config,
        train_dataset=dataset,
        processing_class=tokenizer,
    )
    trainer.train()

    trainer.save_model(str(output_dir))
    tokenizer.save_pretrained(str(output_dir))

    losses = [entry["loss"] for entry in trainer.state.log_history if "loss" in entry]
    return losses


if __name__ == "__main__":
    logged_losses = run_training()
    print("Logged losses:", logged_losses)
