"""
fact_ledger.md countermeasure re-verified against the v2 dedicated
qualitative-only adapter (retrained on 76 rows -- the original 40 plus 36
newly generated pairs -- 380 steps). Same two required checks as every
prior adapter: PeftModel type check AND a real weight-tensor diff against a
freshly loaded, untouched base model.
"""
import json
from pathlib import Path

import pytest
import torch

from app.finetune.train import MODEL_NAME

OUTPUT_DIR_V2 = Path(__file__).resolve().parents[2] / "app" / "finetune" / "artifacts" / "smoke-adapter-qualitative-dedicated-v2"
LOG_HISTORY_PATH = Path(__file__).resolve().parents[2] / "app" / "finetune" / "artifacts" / "qualitative_dedicated_v2_log_history.json"


def _require_adapter():
    if not (OUTPUT_DIR_V2 / "adapter_config.json").exists():
        pytest.skip(f"No adapter at {OUTPUT_DIR_V2} -- run run_qualitative_dedicated_v2.py first.")


def test_v2_adapter_is_real_peft_model_and_differs_from_base():
    _require_adapter()
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float32)
    base_state = {k: v.clone() for k, v in base_model.state_dict().items()}

    finetuned = PeftModel.from_pretrained(base_model, str(OUTPUT_DIR_V2))
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


def test_v2_adapter_logged_loss_decreased_from_first_to_last_logged_step():
    if not LOG_HISTORY_PATH.exists():
        pytest.skip(f"No log history at {LOG_HISTORY_PATH} -- run run_qualitative_dedicated_v2.py first.")

    log_history = json.loads(LOG_HISTORY_PATH.read_text())
    step_losses = [entry["loss"] for entry in log_history if "loss" in entry]
    assert len(step_losses) >= 2, f"need at least 2 logged loss points, got {step_losses}"
    assert step_losses[-1] < step_losses[0], (
        f"loss did not decrease: first={step_losses[0]} last={step_losses[-1]} all={step_losses}"
    )
