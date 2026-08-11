"""
Launcher for the full-scale QLoRA fine-tune (AGENT-15). Not a module
train.py needs at import time -- kept separate so train.py stays the reused
smoke-scale entry point plus its additive helpers (oversample_to_balance).

Batch size (4) and epoch count (5) were both chosen from real, empirical
measurements this session, in two rounds:

Round 1 (adamw_torch, max_length=512): batch_size=4 benchmarked clean at
15 steps (~7.45s/step, 5.26GB peak VRAM) but the real full run stalled
around step 202/1745 -- per-step time exploded to 55s then 92s, VRAM
pinned at 7871/8192MB, consistent with the Windows NVIDIA driver's slow
shared-GPU-memory fallback once VRAM filled. batch_size=2 also stalled (one
~20-minute single-step spike in the first 50 steps, VRAM still pinned near
7844/8192MB). batch_size=1 was stable (4.82GB peak, 50/50 clean steps) but
too slow: 31.78s/step real average projects ~9.2h for the 3-epoch floor
alone, over the 4-hour cap.

Round 2 (paged_adamw_8bit, max_length=256 -- real tokenizer check showed
actual examples are 41-63 tokens, so this truncates nothing): batch_size=4
completed 50/50 steps cleanly, no stalls, steady ~6.4-6.7s/step, peak VRAM
5.23GB/8GB. 5 epochs over the balanced ~2,788-row set projects ~3.26h at
the real 6.724s/step average, under the 4-hour cap -- this is the
committed config below.
"""
import json
import time
from pathlib import Path

from app.finetune.train import DATA_PATH, oversample_to_balance, run_training

OUTPUT_DIR = Path(__file__).parent / "artifacts" / "full-scale-adapter"
LOG_HISTORY_PATH = Path(__file__).parent / "artifacts" / "full_scale_log_history.json"

PER_DEVICE_TRAIN_BATCH_SIZE = 4
GRADIENT_ACCUMULATION_STEPS = 2
NUM_TRAIN_EPOCHS = 5.0
MAX_LENGTH = 256
OPTIM = "paged_adamw_8bit"

if __name__ == "__main__":
    rows = [json.loads(l) for l in Path(DATA_PATH).read_text(encoding="utf-8").splitlines() if l.strip()]
    abstention = [r for r in rows if r["is_abstention"]]
    non_abstention = [r for r in rows if not r["is_abstention"]]
    balanced = oversample_to_balance(abstention, non_abstention, seed=42)
    print(f"balanced training set: {len(balanced)} rows "
          f"({len(abstention)} abstention, {len(balanced) - len(abstention)} non-abstention)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    losses, trainer = run_training(
        rows=balanced,
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=PER_DEVICE_TRAIN_BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        max_steps=-1,
        num_train_epochs=NUM_TRAIN_EPOCHS,
        max_length=MAX_LENGTH,
        optim=OPTIM,
        save=True,
    )
    t1 = time.time()

    LOG_HISTORY_PATH.write_text(json.dumps(trainer.state.log_history, indent=2))

    print(f"FULL_SCALE_TRAIN_DONE wall_clock_s={t1 - t0:.1f} logged_losses={losses}")
