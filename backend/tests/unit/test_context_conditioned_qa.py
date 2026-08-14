"""
Unit tests for app.finetune.qa_generation.build_context_conditioned_row and
the context-conditioned regeneration this task adds.

Expected values are hand-derived from the format spec in the task
instructions, not copied from the implementation's own output.
"""
import json
from pathlib import Path

from app.finetune.qa_generation import (
    build_and_write_all_context,
    build_context_conditioned_row,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "app" / "finetune" / "data"
CSV_PATH = Path.home() / (
    ".cache/huggingface/hub/datasets--BoostedJonP--league_of_legends_match_data/"
    "snapshots/00aa8cff89383127ff6a2d7d26a6b01fcef80c04/league_of_legends_emerald_match_data.csv"
)


def _row(champ_a="Aatrox", champ_b="Kayle", role="top", win_rate=0.5, sample_size=4):
    return {"champ_a": champ_a, "champ_b": champ_b, "role": role, "win_rate": win_rate,
            "sample_size": sample_size}


def _qa_row(prompt="What's the win rate for Aatrox into Kayle (top)?",
            response="Based on 4 recorded top games, Aatrox has a 50.0% win rate versus Kayle."):
    return {"prompt": prompt, "response": response, "champ_a": "Aatrox", "champ_b": "Kayle",
            "role": "top", "rank": "emerald", "phase": "not_available", "is_abstention": False}


def test_context_block_exact_format_multi_game():
    row = _row(win_rate=0.623, sample_size=5)
    qa = _qa_row()
    out = build_context_conditioned_row(row, qa)
    expected = (
        "Context: 5 games observed this patch between Aatrox and Kayle in the "
        "top lane. Aatrox win rate: 62%.\n"
        "Question: What's the win rate for Aatrox into Kayle (top)?"
    )
    assert out["prompt"] == expected


def test_context_block_singular_game_word():
    row = _row(sample_size=1)
    qa = _qa_row()
    out = build_context_conditioned_row(row, qa)
    assert "1 game " in out["prompt"]
    assert "1 games" not in out["prompt"]
    assert "1 game(s)" not in out["prompt"]


def test_win_rate_pct_rounded_to_whole_integer_no_decimal():
    row = _row(win_rate=0.3333)
    qa = _qa_row()
    out = build_context_conditioned_row(row, qa)
    assert "win rate: 33%." in out["prompt"]
    assert "33.0%" not in out["prompt"]
    assert "33.3%" not in out["prompt"]


def test_response_field_unchanged_from_qa_row():
    row = _row()
    qa = _qa_row()
    out = build_context_conditioned_row(row, qa)
    assert out["response"] == qa["response"]


def test_context_applied_even_for_abstention_row():
    row = _row(win_rate=0.5, sample_size=1)
    qa = _qa_row(response="There isn't enough match data on this pairing for a confident read.")
    out = build_context_conditioned_row(row, qa)
    assert out["prompt"].startswith("Context: 1 game observed")
    assert out["response"] == qa["response"]


def test_regeneration_produces_real_files_with_identical_heldout_pair_set():
    summary = build_and_write_all_context(str(CSV_PATH), DATA_DIR)
    assert summary["heldout_rows"] > 0
    assert summary["train_rows"] > 0
    assert summary["abstention_rows"] > 0

    existing_pairs = {
        (r["champ_a"], r["champ_b"])
        for r in (json.loads(l) for l in (DATA_DIR / "heldout.jsonl").read_text().splitlines())
    }
    context_pairs = {
        (r["champ_a"], r["champ_b"])
        for r in (json.loads(l) for l in (DATA_DIR / "heldout_context.jsonl").read_text().splitlines())
    }
    assert context_pairs == existing_pairs


def test_regenerated_response_text_matches_original_train_jsonl():
    original = {
        (r["champ_a"], r["champ_b"], r["role"]): r["response"]
        for r in (json.loads(l) for l in (DATA_DIR / "train.jsonl").read_text().splitlines())
    }
    context = {
        (r["champ_a"], r["champ_b"], r["role"]): r["response"]
        for r in (json.loads(l) for l in (DATA_DIR / "train_context.jsonl").read_text().splitlines())
    }
    assert context == original
