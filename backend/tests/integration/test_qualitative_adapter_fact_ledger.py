"""
fact_ledger.md countermeasure re-verified against AGENT-21's
smoke-adapter-qualitative/ specifically -- not assumed passing because it
passed on the four prior adapters. Same two required checks: PeftModel
type check AND a real weight-tensor diff against a freshly loaded,
untouched base model.
"""
import re
from pathlib import Path

import pytest
import torch

from app.finetune.train import MODEL_NAME

OUTPUT_DIR_QUALITATIVE = Path(__file__).resolve().parents[2] / "app" / "finetune" / "artifacts" / "smoke-adapter-qualitative"
TRAIN_LOG_PATH = Path("/tmp/train_run_qualitative.log")


def _require_adapter():
    if not (OUTPUT_DIR_QUALITATIVE / "adapter_config.json").exists():
        pytest.skip(f"No adapter at {OUTPUT_DIR_QUALITATIVE} -- run the qualitative training script first.")


def test_qualitative_adapter_is_real_peft_model_and_differs_from_base():
    _require_adapter()
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float32)
    base_state = {k: v.clone() for k, v in base_model.state_dict().items()}

    finetuned = PeftModel.from_pretrained(base_model, str(OUTPUT_DIR_QUALITATIVE))
    assert isinstance(finetuned, PeftModel), (
        "loaded object is not a PeftModel -- exactly the fact_ledger.md bug "
        "(silently scoring the base model instead of the adapter)"
    )

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


def test_qualitative_adapter_logged_loss_decreased_from_first_to_last_logged_step():
    if not TRAIN_LOG_PATH.exists():
        pytest.skip(f"No training log at {TRAIN_LOG_PATH} -- run the qualitative training script first.")

    text = TRAIN_LOG_PATH.read_text()
    step_losses = [
        float(m)
        for line in text.splitlines()
        if "'loss':" in line and "grad_norm" in line
        for m in re.findall(r"'loss':\s*'?([0-9.]+)'?", line)
    ]
    assert len(step_losses) >= 2, f"need at least 2 logged loss points, got {step_losses}"
    assert step_losses[-1] < step_losses[0], (
        f"loss did not decrease: first={step_losses[0]} last={step_losses[-1]} all={step_losses}"
    )
