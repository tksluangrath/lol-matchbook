"""
Generates 40 new qualitative-advice training rows to double
qualitative_advice_train.jsonl (40 -> ~80), seed-random-sampled from
train_context.jsonl's 2,152 unique pairs excluding the 40 already in
qualitative_advice_train.jsonl and the 10 held-out pairs -- avoids just
extending the same alphabetical-prefix selection (select_pairs's sort)
that already over-represents early-alphabet champions (Aatrox, Ahri,
Akali) in the original 40.

Generated at max_new_tokens=400, not the original 260: a real check
against the existing 40 rows showed every one is exactly 260 tokens (hard
truncated mid-sentence, 3/40 not even reaching a Late: section) -- the
adapter has never seen a training target that ends naturally. 400 matches
the eval-time budget and lets responses actually finish.

Same base-model generation + fact_grounding_check filter AGENT-20 used
(backend/app/finetune/qualitative_advice.py, not reimplemented).
"""
import json
import random
from pathlib import Path

from app.finetune.eval import generate
from app.finetune.qualitative_advice import (
    build_generation_prompt,
    fact_grounding_check,
    fetch_champion_detail,
    real_win_rate_pct,
)
from app.finetune.train import load_quantized_model, MODEL_NAME
from transformers import AutoTokenizer

TRAIN_CONTEXT_PATH = Path(__file__).parent / "data" / "train_context.jsonl"
EXISTING_TRAIN_PATH = Path(__file__).parent / "data" / "qualitative_advice_train.jsonl"
EXISTING_HELDOUT_PATH = Path(__file__).parent / "data" / "qualitative_advice_heldout.jsonl"
OUTPUT_PATH = Path(__file__).parent / "data" / "qualitative_advice_train_expanded.jsonl"
STATS_PATH = Path(__file__).parent / "artifacts" / "qualitative_advice_expansion_stats.json"

N_NEW_PAIRS = 40
SEED = 43  # distinct from SAMPLE_SEED=42 used for the original 40, so this is a different draw
MAX_NEW_TOKENS = 400


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def pick_new_pairs(train_context_rows: list[dict], used_keys: set[tuple[str, str]],
                    n: int, seed: int) -> list[dict]:
    seen: dict[tuple[str, str], dict] = {}
    for row in train_context_rows:
        key = (row["champ_a"], row["champ_b"])
        if key not in seen and key not in used_keys:
            seen[key] = row
    candidates = list(seen.values())
    return random.Random(seed).sample(candidates, n)


if __name__ == "__main__":
    train_context_rows = load_jsonl(TRAIN_CONTEXT_PATH)
    existing_train = load_jsonl(EXISTING_TRAIN_PATH)
    existing_heldout = load_jsonl(EXISTING_HELDOUT_PATH)
    used_keys = {(r["champ_a"], r["champ_b"]) for r in existing_train + existing_heldout}

    new_pairs = pick_new_pairs(train_context_rows, used_keys, N_NEW_PAIRS, SEED)
    print(f"selected {len(new_pairs)} new pairs, 0 overlap with the {len(used_keys)} already-used pairs")

    model = load_quantized_model()
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    kept, discarded = [], []
    for row in new_pairs:
        champ_a_detail = fetch_champion_detail(row["champ_a"])
        champ_b_detail = fetch_champion_detail(row["champ_b"])
        gen_prompt = build_generation_prompt(row, champ_a_detail, champ_b_detail)
        stored_context = gen_prompt.rsplit("\nInstruction:", 1)[0]

        response = generate(model, tokenizer, gen_prompt, MAX_NEW_TOKENS)
        expected_pct = real_win_rate_pct(row)
        check = fact_grounding_check(response, stored_context, expected_pct)

        new_row = {"champ_a": row["champ_a"], "champ_b": row["champ_b"], "role": row["role"],
                   "context": stored_context, "response": response}
        if check["passed"]:
            kept.append(new_row)
        else:
            discarded.append({**new_row, "invented_phrases": check["invented_phrases"],
                               "mismatched_percentages": check["mismatched_percentages"]})
        print(f"{row['champ_a']}/{row['champ_b']}: kept={check['passed']}")

    OUTPUT_PATH.write_text("\n".join(json.dumps(r) for r in kept) + "\n")
    STATS_PATH.write_text(json.dumps({
        "generated": len(new_pairs), "kept": len(kept), "discarded": len(discarded),
        "discarded_examples": discarded,
    }, indent=2))
    print(f"QUALITATIVE_DATA_EXPANSION_DONE kept={len(kept)}/{len(new_pairs)}")
