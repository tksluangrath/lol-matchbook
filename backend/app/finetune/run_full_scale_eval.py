"""
AGENT-16: runs the existing eval.py harness (unchanged scoring logic) against
AGENT-15's full-scale adapter, writing to a distinct results path so the
original smoke-scale and balanced-diagnostic eval outputs are untouched.
"""
import json
from pathlib import Path

from app.finetune.eval import run_all

ADAPTER_DIR = Path(__file__).parent / "artifacts" / "full-scale-adapter"
RESULTS_PATH = Path(__file__).parent / "artifacts" / "eval_results_full_scale.json"

CAVEAT = (
    "Full-scale run: balanced (50/50 oversampled) training set, 5 epochs "
    "(1745 steps) on a real GPU (RTX 2070 SUPER, 8GB). See "
    "docs/decisions/phase2-full-scale-finetune.md for the training run's "
    "real batch-size/optimizer/epoch decisions and wall-clock."
)

if __name__ == "__main__":
    summary = run_all(adapter_dir=ADAPTER_DIR, results_path=RESULTS_PATH, caveat=CAVEAT)
    print(json.dumps(
        {k: v for k, v in summary.items() if k not in ("step2_rows", "step4_rows", "step3_general_instruction_outputs")},
        indent=2,
    ))
    print(f"\nFull results written to {RESULTS_PATH}")
    print("FULL_SCALE_EVAL_DONE")
