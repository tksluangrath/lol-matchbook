"""
Eval harness for AGENT-12's smoke-scale QLoRA adapter
(backend/app/finetune/artifacts/smoke-adapter), run against AGENT-11's
heldout.jsonl / abstention_eval.jsonl / general_instruction_eval.jsonl.

Reuses app.finetune.train (MODEL_NAME, OUTPUT_DIR, SYSTEM_PROMPT) and
app.finetune.qa_generation (HEDGE_PHRASE) via import -- no reimplementation.

CAVEAT (state plainly, every time these results are reported): AGENT-12's
adapter is a SMOKE-SCALE run, capped at 500 training examples / 200 steps.
These results demonstrate the eval harness is correct and runs for real
against a real adapter -- they are NOT a verdict on model quality.

Base-vs-adapted generation, without loading the model twice: the base model
is loaded once (see load_model_and_tokenizer), wrapped as a PeftModel with
the saved adapter, and toggled via PeftModel.disable_adapter() -- a context
manager that runs the *same* underlying weights with the LoRA delta switched
off. This is the fact_ledger.md countermeasure (loading by name would
silently reload/score the unmodified base) combined with a real generation
diff, without doubling CPU memory/time for a 4B model.

No deviation from app.finetune.train's load path: the base model is loaded
4-bit quantized via the same real bitsandbytes BitsAndBytesConfig(
load_in_4bit=True) path train.py used for the compute-gated training run
(see train.py's module docstring). A real timed comparison on this machine
(bnb CPU NF4: ~1.1 tok/s at 15 real generated tokens in 13.2s against the
actual saved adapter; unquantized fp32 was also tried and rejected -- a 4B
fp32 model needs ~16GB against ~6GB free on this 17GB-unified-memory
machine, a real OOM/thrashing risk) confirmed 4-bit is both correct
(consistent with the trained artifact) and fast enough in practice, since
the fine-tuned model's trained answers are short and stop at a real EOS
token well before any max_new_tokens cap.

Banding rule (mandatory, from the task contract):
    win_rate > 0.55  -> "champ_a favored"
    win_rate < 0.45  -> "champ_b favored"
    otherwise        -> "roughly even"

A model response's *implied* band is derived from the first explicit
percentage figure found in its text (regex below). This is not a guess: the
fine-tuned model was trained exclusively on AGENT-11's two ANSWER_TEMPLATES,
both of which always state an explicit "{win_rate_pct}%" figure -- so the
same extracted number is used both for the band-match check and the
"numeric figure within 10 points" check the task contract requires
separately. If no percentage is found, the row fails outright (there is
nothing to check against) -- this is a strict rule I define here.

Abstention "close paraphrase" rule (mandatory, from the task contract): a
response passes if it contains the exact HEDGE_PHRASE from
app.finetune.qa_generation as a substring, OR difflib.SequenceMatcher's
similarity ratio between the response and HEDGE_PHRASE is >= 0.6. difflib is
stdlib, deterministic, and the 0.6 threshold is stated explicitly here (not
hidden) -- it is a real similarity bar, not "contains any hedge-ish word".
"""
import difflib
import json
import re
import shutil
import tempfile
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoTokenizer

from app.finetune.qa_generation import HEDGE_PHRASE
from app.finetune.train import MODEL_NAME, OUTPUT_DIR, SYSTEM_PROMPT, load_quantized_model

DATA_DIR = Path(__file__).parent / "data"
HELDOUT_PATH = DATA_DIR / "heldout.jsonl"
ABSTENTION_PATH = DATA_DIR / "abstention_eval.jsonl"
GENERAL_PATH = DATA_DIR / "general_instruction_eval.jsonl"

RESULTS_PATH = Path(__file__).parent / "artifacts" / "eval_results.json"

# First heldout.jsonl row's prompt, at the time this file was written --
# fixed so the step-1 sanity check is reproducible run to run.
FIXED_SANITY_PROMPT = "What's the win rate for Aatrox into Kayle (top)?"

MAX_NEW_TOKENS_MATCHUP = 60
MAX_NEW_TOKENS_GENERAL = 120

PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")

ABSTENTION_PARAPHRASE_THRESHOLD = 0.6


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def load_model_and_tokenizer(adapter_dir: Path = OUTPUT_DIR) -> tuple[PeftModel, "AutoTokenizer"]:
    """Loads the base model 4-bit quantized via train.load_quantized_model
    (same real bnb path train.py used for training, reused not
    reimplemented -- CPU on machines with no CUDA, GPU otherwise), then
    wraps it with the saved adapter at adapter_dir. A single model instance
    is used for both base and adapted generation via disable_adapter().

    The adapter is copied to a local temp dir before loading: safetensors
    memory-maps the file, which crashes (fatal signal inside
    safetensors.torch.load_file) when the file lives in a OneDrive-synced
    folder on Windows -- confirmed by reproducing the crash against the
    repo path and the fix against a local copy."""
    base = load_quantized_model()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    with tempfile.TemporaryDirectory() as tmp_dir:
        local_adapter_dir = Path(tmp_dir) / "adapter"
        shutil.copytree(adapter_dir, local_adapter_dir)
        model = PeftModel.from_pretrained(base, str(local_adapter_dir))
    model.eval()
    return model, tokenizer


def generate(model: PeftModel, tokenizer, prompt: str, max_new_tokens: int) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    with torch.no_grad():
        out = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    gen_tokens = out[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(gen_tokens, skip_special_tokens=True).strip()


def generate_base(model: PeftModel, tokenizer, prompt: str, max_new_tokens: int) -> str:
    """Adapter disabled -> same weights the model was built from, unmodified."""
    with model.disable_adapter():
        return generate(model, tokenizer, prompt, max_new_tokens)


# --------------------------------------------------------------------------
# Step 1: base-vs-finetuned sanity check (blocking)
# --------------------------------------------------------------------------

def step1_sanity_check(model: PeftModel, tokenizer) -> dict:
    is_peft = isinstance(model, PeftModel)
    base_model_name = model.peft_config["default"].base_model_name_or_path if is_peft else None
    base_out = generate_base(model, tokenizer, FIXED_SANITY_PROMPT, MAX_NEW_TOKENS_MATCHUP)
    adapted_out = generate(model, tokenizer, FIXED_SANITY_PROMPT, MAX_NEW_TOKENS_MATCHUP)
    differs = base_out != adapted_out
    passed = is_peft and base_model_name == MODEL_NAME and differs
    return {
        "is_peft_model": is_peft,
        "base_model_name_or_path": base_model_name,
        "prompt": FIXED_SANITY_PROMPT,
        "base_output": base_out,
        "adapted_output": adapted_out,
        "generations_differ": differs,
        "passed": passed,
    }


# --------------------------------------------------------------------------
# Step 2: held-out matchup eval
# --------------------------------------------------------------------------

def band_for_win_rate(win_rate: float) -> str:
    if win_rate > 0.55:
        return "champ_a favored"
    if win_rate < 0.45:
        return "champ_b favored"
    return "roughly even"


def extract_win_rate_pct(text: str) -> float | None:
    m = PCT_RE.search(text)
    if not m:
        return None
    val = float(m.group(1))
    return val if 0 <= val <= 100 else None


def score_heldout_row(row: dict, model_output: str) -> dict:
    real_band = band_for_win_rate(row["win_rate"])
    extracted_pct = extract_win_rate_pct(model_output)
    if extracted_pct is None:
        return {
            "champ_a": row["champ_a"], "champ_b": row["champ_b"], "role": row["role"],
            "real_win_rate": row["win_rate"], "real_band": real_band,
            "model_output": model_output, "extracted_pct": None,
            "implied_band": None, "band_match": False, "numeric_within_10pts": False,
            "passed": False,
        }
    implied_band = band_for_win_rate(extracted_pct / 100)
    band_match = implied_band == real_band
    numeric_ok = abs(extracted_pct - row["win_rate"] * 100) <= 10
    return {
        "champ_a": row["champ_a"], "champ_b": row["champ_b"], "role": row["role"],
        "real_win_rate": row["win_rate"], "real_band": real_band,
        "model_output": model_output, "extracted_pct": extracted_pct,
        "implied_band": implied_band, "band_match": band_match,
        "numeric_within_10pts": numeric_ok, "passed": band_match and numeric_ok,
    }


def step2_heldout_eval(model: PeftModel, tokenizer, rows: list[dict]) -> dict:
    # heldout.jsonl rows (AGENT-11's qa_generation.py output) carry no
    # "win_rate" float field -- the ground-truth win rate is embedded as an
    # explicit "{win_rate_pct}%" figure inside the pre-written "response"
    # text (see ANSWER_TEMPLATES). Extract it with the same PCT_RE used for
    # the model's own output, since that response is the real ground truth.
    results = []
    for row in rows:
        real_pct = extract_win_rate_pct(row["response"])
        if real_pct is None:
            raise ValueError(
                f"heldout row has no extractable ground-truth win_rate in its "
                f"response text: {row!r}"
            )
        row_with_win_rate = {**row, "win_rate": real_pct / 100}
        output = generate(model, tokenizer, row["prompt"], MAX_NEW_TOKENS_MATCHUP)
        results.append(score_heldout_row(row_with_win_rate, output))
    passed = sum(r["passed"] for r in results)
    return {"total": len(results), "passed": passed,
            "pass_rate": passed / len(results) if results else None, "rows": results}


# --------------------------------------------------------------------------
# Step 3: catastrophic-forgetting check (generation only -- scoring is a
# separate, explicit judgment step over the real outputs; see eval.py's
# __main__ output / the eval report for the applied checklist).
# --------------------------------------------------------------------------

def step3_generate_general_instruction_outputs(model: PeftModel, tokenizer, rows: list[dict]) -> dict:
    base_outputs, finetuned_outputs = [], []
    for row in rows:
        base_outputs.append(generate_base(model, tokenizer, row["prompt"], MAX_NEW_TOKENS_GENERAL))
        finetuned_outputs.append(generate(model, tokenizer, row["prompt"], MAX_NEW_TOKENS_GENERAL))
    return {
        "prompts": [r["prompt"] for r in rows],
        "base_outputs": base_outputs,
        "finetuned_outputs": finetuned_outputs,
    }


# --------------------------------------------------------------------------
# Step 4: abstention check
# --------------------------------------------------------------------------

def passes_abstention(response: str) -> dict:
    contains_exact = HEDGE_PHRASE in response
    ratio = difflib.SequenceMatcher(None, response.strip(), HEDGE_PHRASE).ratio()
    close_paraphrase = ratio >= ABSTENTION_PARAPHRASE_THRESHOLD
    return {"contains_exact_phrase": contains_exact, "similarity_ratio": ratio,
            "close_paraphrase": close_paraphrase, "passed": contains_exact or close_paraphrase}


def step4_abstention_eval(model: PeftModel, tokenizer, rows: list[dict]) -> dict:
    results = []
    for row in rows:
        output = generate(model, tokenizer, row["prompt"], MAX_NEW_TOKENS_MATCHUP)
        score = passes_abstention(output)
        results.append({"champ_a": row["champ_a"], "champ_b": row["champ_b"], "role": row["role"],
                         "model_output": output, **score})
    passed = sum(r["passed"] for r in results)
    return {"total": len(results), "passed": passed,
            "pass_rate": passed / len(results) if results else None, "rows": results}


def run_all(adapter_dir: Path = OUTPUT_DIR, results_path: Path = RESULTS_PATH,
            caveat: str = (
                "AGENT-12's adapter is a SMOKE-SCALE run (<=500 training examples, "
                "<=200 steps). These results demonstrate the eval harness is correct "
                "and runs for real -- they are not a verdict on model quality."
            )) -> dict:
    model, tokenizer = load_model_and_tokenizer(adapter_dir)

    step1 = step1_sanity_check(model, tokenizer)
    if not step1["passed"]:
        summary = {"step1_sanity_check": step1, "blocked": True,
                    "reason": "step 1 base-vs-finetuned check failed -- steps 2-4 not run"}
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(json.dumps(summary, indent=2))
        return summary

    heldout_rows = load_jsonl(HELDOUT_PATH)
    abstention_rows = load_jsonl(ABSTENTION_PATH)
    general_rows = load_jsonl(GENERAL_PATH)

    step2 = step2_heldout_eval(model, tokenizer, heldout_rows)
    step3 = step3_generate_general_instruction_outputs(model, tokenizer, general_rows)
    step4 = step4_abstention_eval(model, tokenizer, abstention_rows)

    summary = {
        "smoke_scale_caveat": caveat,
        "step1_sanity_check": step1,
        "step2_heldout_eval": {"total": step2["total"], "passed": step2["passed"], "pass_rate": step2["pass_rate"]},
        "step2_rows": step2["rows"],
        "step3_general_instruction_outputs": step3,
        "step4_abstention_eval": {"total": step4["total"], "passed": step4["passed"], "pass_rate": step4["pass_rate"]},
        "step4_rows": step4["rows"],
        "blocked": False,
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    result = run_all()
    print(json.dumps(
        {k: v for k, v in result.items() if k not in ("step2_rows", "step4_rows", "step3_general_instruction_outputs")},
        indent=2,
    ))
    print(f"\nFull results written to {RESULTS_PATH}")
