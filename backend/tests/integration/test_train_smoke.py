"""
Integration smoke test for app.finetune.train's QLoRA fine-tune.

Does NOT re-run training (a full smoke run takes ~30 min of CPU time on
this Apple Silicon machine with no CUDA -- see app.finetune.train's module
docstring for the compute-gate evidence). Instead it verifies the artifacts
of a run already executed via `python -m app.finetune.train`:

1. The saved adapter at backend/app/finetune/artifacts/smoke-adapter/ loads
   as a real PeftModel (type check) AND has at least one weight tensor that
   differs numerically from the base model's corresponding tensor (real
   weight diff) -- the fact_ledger.md countermeasure requires BOTH, per
   AGENT-12's task contract, not either alone.
2. The loss logged every LOG_EVERY steps during that run (captured to
   /tmp/train_run.log as trainer.state.log_history) decreased from the
   first logged step to the last.

Expected values are derived independently of the training code: "loaded
adapter differs from base" is checked by loading the *unmodified* base
model fresh and diffing real tensors -- not by trusting anything train.py
computed. "loss decreased" is checked against the loss values pytest reads
directly from the saved trainer log, compared first-vs-last -- not
re-derived from train.py's own pass/fail judgement.
"""
import json
import re
from pathlib import Path

import pytest
import torch

from app.finetune.train import MODEL_NAME, OUTPUT_DIR

TRAIN_LOG_PATH = Path("/tmp/train_run.log")


def _require_adapter():
    if not (OUTPUT_DIR / "adapter_config.json").exists():
        pytest.skip(
            f"No adapter at {OUTPUT_DIR} -- run `python -m app.finetune.train` first."
        )


def test_saved_adapter_is_real_peft_model_and_differs_from_base():
    """PeftModel type check AND real weight-tensor diff -- both required,
    per the fact_ledger.md countermeasure (an eval script once reloaded the
    base model by name and silently scored it instead of the adapter)."""
    _require_adapter()
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float32)
    base_state = {k: v.clone() for k, v in base_model.state_dict().items()}

    finetuned = PeftModel.from_pretrained(base_model, str(OUTPUT_DIR))

    # 1. Type check: it's actually a PeftModel, not the base reloaded by name.
    assert isinstance(finetuned, PeftModel), (
        "loaded object is not a PeftModel -- this is exactly the fact_ledger.md "
        "bug (silently scoring the base model instead of the adapter)"
    )

    # 2. Real weight-tensor diff: merge LoRA into a copy and compare against
    # the untouched base state dict captured before loading the adapter.
    merged = finetuned.merge_and_unload()
    merged_state = merged.state_dict()

    any_diff = False
    for name, base_tensor in base_state.items():
        merged_name = name if name in merged_state else name.replace("base_model.model.", "")
        if merged_name not in merged_state:
            continue
        if not torch.equal(base_tensor, merged_state[merged_name]):
            any_diff = True
            break

    assert any_diff, "no weight tensor differs from base -- adapter had no effect"


def test_logged_loss_decreased_from_first_to_last_logged_step():
    """Loss logged every 10 steps (LOG_EVERY) must show the last logged
    value lower than the first -- a flat/non-decreasing loss is a real
    training failure, not a formatting issue."""
    if not TRAIN_LOG_PATH.exists():
        pytest.skip(f"No training log at {TRAIN_LOG_PATH} -- run the training script first.")

    text = TRAIN_LOG_PATH.read_text()
    # trainer prints dict-like log lines: {'loss': '4.913', ...}
    losses = [float(m) for m in re.findall(r"'loss':\s*'?([0-9.]+)'?", text)]
    # drop the final aggregate 'train_loss' summary line's value by only
    # keeping entries that came from a line containing 'grad_norm' (i.e.
    # real per-logging-interval steps, not the end-of-run summary)
    step_losses = [
        float(m)
        for line in text.splitlines()
        if "'loss':" in line and "grad_norm" in line
        for m in re.findall(r"'loss':\s*'?([0-9.]+)'?", line)
    ]
    assert len(step_losses) >= 2, f"need at least 2 logged loss points, got {step_losses}"
    assert step_losses[-1] < step_losses[0], (
        f"loss did not decrease: first={step_losses[0]} last={step_losses[-1]} "
        f"all={step_losses}"
    )
