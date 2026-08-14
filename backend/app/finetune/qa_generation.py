"""
Generates fine-tuning Q&A data from real matchup-stat rows produced by
app.data_pipeline.aggregate.aggregate_matchup_stats (which itself never
touches Postgres -- see docs/build-plan.md Phase 1 notes). This module reuses
that pipeline via import; it does not reimplement match loading/aggregation.

Field-name note: aggregate.py's output dict uses the key "rank"; the DB model
app.models.MatchupStat calls the equivalent column "rank_bracket". Nothing
here writes to the DB -- output rows below use "rank" (matching the pipeline
dict this module actually reads), not "rank_bracket".

Held-out split: deterministic per (champ_a, champ_b) pair (independent of
role) using hashlib.sha256(f"{champ_a}|{champ_b}".encode()).hexdigest() as an
integer mod 100. Buckets < HELDOUT_BUCKET_THRESHOLD (15) -> held out (~15% of
pairs). Python's hash() is intentionally not used -- it's randomized per
process (PYTHONHASHSEED) and would make the split non-reproducible.

Template selection is deterministic: a single random.Random(TEMPLATE_SEED)
instance is created once and consumed in row order (rows arrive pre-sorted by
aggregate_matchup_stats), so re-running produces byte-identical output.

Abstention: rows at or below the sample_size value at ABSTENTION_PERCENTILE
of the real observed distribution (computed once from ALL aggregated rows,
train+heldout together, since it's a property of the dataset not the split)
get is_abstention=true and the single fixed HEDGE_PHRASE as their response --
never a per-row paraphrase.
"""
import hashlib
import json
import math
import random
from pathlib import Path

from app.data_pipeline.aggregate import aggregate_matchup_stats, filter_valid_matches
from app.data_pipeline.riot_client import load_hf_csv_matches

HELDOUT_BUCKET_THRESHOLD = 15  # buckets [0, 15) of 100 -> held out, ~15% of pairs

TEMPLATE_SEED = 20260806  # fixed seed -> reproducible template selection

# Exactly 3 question-phrasing templates.
QUESTION_TEMPLATES = [
    "How does {champ_a} fare against {champ_b} in the {role} lane?",
    "What's the win rate for {champ_a} into {champ_b} ({role})?",
    "Give me a read on the {champ_a} vs {champ_b} {role} matchup.",
]

# Exactly 2 answer-phrasing templates (used for non-abstention rows only).
ANSWER_TEMPLATES = [
    "{champ_a} wins {win_rate_pct}% of games against {champ_b} in {role} across {sample_size} tracked games this patch.",
    "Based on {sample_size} recorded {role} games, {champ_a} has a {win_rate_pct}% win rate versus {champ_b}.",
]

HEDGE_PHRASE = "There isn't enough match data on this pairing for a confident read."

ABSTENTION_PERCENTILE = 25  # stated cutoff on the real sample_size distribution

GENERAL_INSTRUCTION_PROMPTS = [
    # 5 general-knowledge questions
    {"prompt": "What causes the seasons to change on Earth?"},
    {"prompt": "Who wrote the play 'Romeo and Juliet'?"},
    {"prompt": "What is the boiling point of water at sea level, in Celsius?"},
    {"prompt": "Which planet in our solar system is closest to the sun?"},
    {"prompt": "What is the capital city of Australia?"},
    # 5 instruction-following tasks
    {"prompt": "Rewrite this sentence in the passive voice: 'The chef cooked the meal.'"},
    {"prompt": "List the numbers from 1 to 10, skipping every multiple of 3."},
    {"prompt": "Convert 72 degrees Fahrenheit to Celsius, showing your work."},
    {"prompt": "Summarize the following in one sentence: 'The library closes at 9pm on weekdays and 5pm on weekends, except during public holidays when it is closed all day.'"},
    {"prompt": "Write a haiku about autumn leaves."},
    # 5 open-ended reasoning prompts
    {"prompt": "If a train leaves a station traveling 60 mph and another leaves 30 minutes later traveling 75 mph on the same track, how long until the second train catches the first?"},
    {"prompt": "Explain why a plane's shadow moves faster over water than over hilly terrain, even at constant altitude and speed."},
    {"prompt": "You have 8 identical-looking coins, one of which is slightly heavier. Using a balance scale only twice, how do you find the heavier coin?"},
    {"prompt": "Why might a company choose to lower prices even when demand for its product is already high?"},
    {"prompt": "Describe a scenario where increasing a team's headcount could make a software project slower, not faster."},
]
assert len(GENERAL_INSTRUCTION_PROMPTS) == 15


def pair_bucket(champ_a: str, champ_b: str) -> int:
    """Deterministic bucket in [0, 100) for a champion pair, independent of
    process/run (unlike Python's randomized hash())."""
    digest = hashlib.sha256(f"{champ_a}|{champ_b}".encode()).hexdigest()
    return int(digest, 16) % 100


def is_heldout_pair(champ_a: str, champ_b: str) -> bool:
    return pair_bucket(champ_a, champ_b) < HELDOUT_BUCKET_THRESHOLD


def split_rows(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Partition rows into (train_rows, heldout_rows) by (champ_a, champ_b)
    pair. A pair's assignment applies to every row for that pair regardless
    of role."""
    train, heldout = [], []
    for row in rows:
        (heldout if is_heldout_pair(row["champ_a"], row["champ_b"]) else train).append(row)
    return train, heldout


def abstention_threshold(rows: list[dict], percentile: int = ABSTENTION_PERCENTILE) -> int:
    """Nearest-rank percentile of sample_size over `rows`. E.g. percentile=25
    on n values returns the value at rank ceil(25/100 * n) (1-indexed)."""
    sizes = sorted(r["sample_size"] for r in rows)
    idx = max(0, math.ceil(percentile / 100 * len(sizes)) - 1)
    return sizes[idx]


def _format_qa(row: dict, rng: random.Random) -> dict:
    question_tpl = rng.choice(QUESTION_TEMPLATES)
    prompt = question_tpl.format(champ_a=row["champ_a"], champ_b=row["champ_b"], role=row["role"])

    if row["is_abstention"]:
        response = HEDGE_PHRASE
    else:
        answer_tpl = rng.choice(ANSWER_TEMPLATES)
        response = answer_tpl.format(
            champ_a=row["champ_a"],
            champ_b=row["champ_b"],
            role=row["role"],
            win_rate_pct=round(row["win_rate"] * 100, 1),
            sample_size=row["sample_size"],
        )

    return {
        "prompt": prompt,
        "response": response,
        "champ_a": row["champ_a"],
        "champ_b": row["champ_b"],
        "role": row["role"],
        "rank": row["rank"],
        "phase": row["phase"],
        "is_abstention": row["is_abstention"],
    }


def generate_qa_rows(rows: list[dict], seed: int = TEMPLATE_SEED) -> list[dict]:
    """rows must already carry an "is_abstention" bool. Consumes a single
    seeded RNG in row order -> deterministic across runs given the same
    row order (aggregate_matchup_stats output is sorted, so this is stable)."""
    rng = random.Random(seed)
    return [_format_qa(row, rng) for row in rows]


def build_context_conditioned_row(row: dict, qa_row: dict) -> dict:
    """Prepends a context block (real sample_size + win_rate, unconditionally,
    even for abstention rows) to qa_row's prompt. response is untouched."""
    game_word = "game" if row["sample_size"] == 1 else "games"
    win_rate_pct = round(row["win_rate"] * 100)
    context = (
        f"Context: {row['sample_size']} {game_word} observed this patch between "
        f"{row['champ_a']} and {row['champ_b']} in the {row['role']} lane. "
        f"{row['champ_a']} win rate: {win_rate_pct}%.\n"
        f"Question: {qa_row['prompt']}"
    )
    return {**qa_row, "prompt": context}


def build_and_write_all_context(csv_path: str, out_dir: Path) -> dict:
    """Same real pipeline/split/order as build_and_write_all, so
    generate_qa_rows draws the same RNG sequence and produces byte-identical
    prompt/response text before context is prepended -- only the prompt
    gains a context block, response and the held-out pair set are unchanged."""
    matches = load_hf_csv_matches(csv_path)
    valid = filter_valid_matches(matches)
    rows = aggregate_matchup_stats(valid)
    threshold = abstention_threshold(rows)
    train_rows, heldout_rows = split_rows(rows)
    for row in train_rows + heldout_rows:
        row["is_abstention"] = row["sample_size"] <= threshold

    train_non_abstention = [r for r in train_rows if not r["is_abstention"]]
    train_abstention = [r for r in train_rows if r["is_abstention"]]
    heldout_non_abstention = [r for r in heldout_rows if not r["is_abstention"]]
    heldout_abstention = [r for r in heldout_rows if r["is_abstention"]]

    def context_rows(raw_rows: list[dict]) -> list[dict]:
        qa_rows = generate_qa_rows(raw_rows)
        return [build_context_conditioned_row(r, qa) for r, qa in zip(raw_rows, qa_rows)]

    train_ctx = context_rows(train_non_abstention + train_abstention)
    heldout_ctx = context_rows(heldout_non_abstention)
    abstention_ctx = context_rows(heldout_abstention)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "train_context.jsonl", train_ctx)
    _write_jsonl(out_dir / "heldout_context.jsonl", heldout_ctx)
    _write_jsonl(out_dir / "abstention_eval_context.jsonl", abstention_ctx)

    return {"train_rows": len(train_ctx), "heldout_rows": len(heldout_ctx),
            "abstention_rows": len(abstention_ctx)}


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def build_and_write_all(csv_path: str, out_dir: Path) -> dict:
    """Runs the real pipeline end to end and writes the four output files.
    Returns a summary dict of what was found/produced (for reporting)."""
    matches = load_hf_csv_matches(csv_path)
    valid = filter_valid_matches(matches)
    rows = aggregate_matchup_stats(valid)

    combos = sorted({(r["rank"], r["phase"]) for r in rows})
    threshold = abstention_threshold(rows)

    train_rows, heldout_rows = split_rows(rows)

    for row in train_rows + heldout_rows:
        row["is_abstention"] = row["sample_size"] <= threshold

    train_non_abstention = [r for r in train_rows if not r["is_abstention"]]
    train_abstention = [r for r in train_rows if r["is_abstention"]]
    heldout_non_abstention = [r for r in heldout_rows if not r["is_abstention"]]
    heldout_abstention = [r for r in heldout_rows if r["is_abstention"]]

    train_qa = generate_qa_rows(train_non_abstention + train_abstention)
    heldout_qa = generate_qa_rows(heldout_non_abstention)
    abstention_eval_qa = generate_qa_rows(heldout_abstention)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(out_dir / "train.jsonl", train_qa)
    _write_jsonl(out_dir / "heldout.jsonl", heldout_qa)
    _write_jsonl(out_dir / "abstention_eval.jsonl", abstention_eval_qa)
    _write_jsonl(out_dir / "general_instruction_eval.jsonl", GENERAL_INSTRUCTION_PROMPTS)

    return {
        "matches_loaded": len(matches),
        "valid_matches": len(valid),
        "total_rows": len(rows),
        "rank_phase_combos": combos,
        "abstention_percentile": ABSTENTION_PERCENTILE,
        "abstention_threshold_sample_size": threshold,
        "train_rows": len(train_rows),
        "heldout_rows": len(heldout_rows),
        "train_abstention": len(train_abstention),
        "train_non_abstention": len(train_non_abstention),
        "heldout_abstention": len(heldout_abstention),
        "heldout_non_abstention": len(heldout_non_abstention),
    }


if __name__ == "__main__":
    import sys

    csv_arg = sys.argv[1] if len(sys.argv) > 1 else None
    if not csv_arg:
        raise SystemExit("usage: python -m app.finetune.qa_generation <csv_path>")
    summary = build_and_write_all(csv_arg, Path(__file__).parent / "data")
    print(json.dumps(summary, indent=2, default=str))
