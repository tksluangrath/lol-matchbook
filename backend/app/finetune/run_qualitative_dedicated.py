"""
Launcher for the dedicated qualitative-advice adapter (two-adapter/two-stage
approach, per docs/decisions/phase2-qualitative-oversampling-diagnostic.md's
recommendation). Trains on the 40 qualitative_advice_train.jsonl rows only
-- no win-rate rows mixed in -- so the adapter's whole step budget goes to
this task instead of being diluted or contended with a 500-row majority
task. Same LoRA config and max_steps=200 as AGENT-21's original combined
run, just undiluted.
"""
import json
import time
from pathlib import Path

from app.finetune.train import run_training

DATA_PATH = Path(__file__).parent / "data" / "qualitative_advice_train.jsonl"
OUTPUT_DIR = Path(__file__).parent / "artifacts" / "smoke-adapter-qualitative-dedicated"
LOG_HISTORY_PATH = Path(__file__).parent / "artifacts" / "qualitative_dedicated_log_history.json"

MAX_STEPS = 200

if __name__ == "__main__":
    raw_rows = [json.loads(l) for l in DATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [{**r, "prompt": r["context"]} for r in raw_rows]
    print(f"qualitative-only training set: {len(rows)} rows")

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

    print(f"QUALITATIVE_DEDICATED_TRAIN_DONE wall_clock_s={t1 - t0:.1f} logged_losses={losses}")
