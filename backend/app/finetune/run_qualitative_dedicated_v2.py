"""
Retrains the dedicated qualitative-advice adapter (v2) on the original 40
qualitative_advice_train.jsonl rows plus the 36 new rows from
run_qualitative_data_expansion.py (76 total) -- still qualitative-only, no
win-rate rows mixed in. max_steps scaled proportionally from the v1 run's
200 steps / 40 rows (10 epochs at batch_size=2) to keep the same ~10-epoch
exposure: 76 rows -> 380 steps.
"""
import json
import time
from pathlib import Path

from app.finetune.train import run_training

ORIGINAL_DATA_PATH = Path(__file__).parent / "data" / "qualitative_advice_train.jsonl"
EXPANDED_DATA_PATH = Path(__file__).parent / "data" / "qualitative_advice_train_expanded.jsonl"
OUTPUT_DIR = Path(__file__).parent / "artifacts" / "smoke-adapter-qualitative-dedicated-v2"
LOG_HISTORY_PATH = Path(__file__).parent / "artifacts" / "qualitative_dedicated_v2_log_history.json"

MAX_STEPS = 380

if __name__ == "__main__":
    raw_rows = (
        [json.loads(l) for l in ORIGINAL_DATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        + [json.loads(l) for l in EXPANDED_DATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    )
    rows = [{**r, "prompt": r["context"]} for r in raw_rows]
    print(f"qualitative-only training set (v2, expanded): {len(rows)} rows")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    losses, trainer = run_training(
        rows=rows,
        output_dir=OUTPUT_DIR,
        max_steps=MAX_STEPS,
        save=True,
    )
    t1 = time.time()

    LOG_HISTORY_PATH.write_text(json.dumps(trainer.state.log_history, indent=2))

    print(f"QUALITATIVE_DEDICATED_V2_TRAIN_DONE wall_clock_s={t1 - t0:.1f} logged_losses={losses}")
