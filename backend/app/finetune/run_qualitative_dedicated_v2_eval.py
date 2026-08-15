"""
Evaluates the v2 dedicated qualitative-only adapter (retrained on 76 rows,
380 steps) against the same 10 held-out pairs as v1, for a direct
before/after comparison. Reuses v1's scoring logic and GEN_KWARGS (confirmed
best: no repetition penalty) verbatim, only the adapter dir and results
path differ.
"""
import json
from pathlib import Path

from app.finetune.eval import generate, load_model_and_tokenizer
from app.finetune.run_qualitative_dedicated_eval import DATA_PATH, GEN_KWARGS, score_row

ADAPTER_DIR = Path(__file__).parent / "artifacts" / "smoke-adapter-qualitative-dedicated-v2"
RESULTS_PATH = Path(__file__).parent / "artifacts" / "eval_results_qualitative_dedicated_v2.json"
# v2's training data averages 337.5 tokens/response (some up to 400) vs v1's
# uniform 260 -- the eval budget needs matching headroom, not v1's 400.
MAX_NEW_TOKENS = 600

if __name__ == "__main__":
    rows = [json.loads(l) for l in DATA_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    model, tokenizer = load_model_and_tokenizer(ADAPTER_DIR)

    scored = []
    for row in rows:
        output = generate(model, tokenizer, row["context"], MAX_NEW_TOKENS, **GEN_KWARGS)
        scored.append(score_row(row, output))
        print(f"{row['champ_a']}/{row['champ_b']}: passed={scored[-1]['passed']}")

    passed = sum(r["passed"] for r in scored)
    result = {
        "qualitative_heldout_eval": {"total": len(scored), "passed": passed},
        "qualitative_heldout_rows": scored,
    }
    RESULTS_PATH.write_text(json.dumps(result, indent=2))
    print(f"QUALITATIVE_DEDICATED_V2_EVAL_DONE passed={passed}/{len(scored)}")
