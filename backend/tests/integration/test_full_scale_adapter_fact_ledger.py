"""
fact_ledger.md countermeasure against AGENT-15's full-scale adapter -- same
check as test_train_smoke.py's test_saved_adapter_is_real_peft_model_and_differs_from_base,
run again here (not skipped) because a prior eval script once reloaded the
base model by name and silently scored it instead of the adapter. Requires
BOTH a PeftModel type check AND a real weight-tensor diff against a freshly
loaded, untouched base model -- neither alone is sufficient.
"""
import torch

from app.finetune.train import MODEL_NAME
from app.finetune.run_full_scale import OUTPUT_DIR


def test_full_scale_adapter_is_real_peft_model_and_differs_from_base():
    from peft import PeftModel
    from transformers import AutoModelForCausalLM

    assert (OUTPUT_DIR / "adapter_config.json").exists(), f"no adapter at {OUTPUT_DIR}"

    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, torch_dtype=torch.float32)
    base_state = {k: v.clone() for k, v in base_model.state_dict().items()}

    finetuned = PeftModel.from_pretrained(base_model, str(OUTPUT_DIR))

    assert isinstance(finetuned, PeftModel), (
        "loaded object is not a PeftModel -- this is exactly the fact_ledger.md "
        "bug (silently scoring the base model instead of the adapter)"
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
