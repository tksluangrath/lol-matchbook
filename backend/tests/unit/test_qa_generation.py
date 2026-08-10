"""
Unit tests for app.finetune.qa_generation.

Expected values are hand-computed (sha256 digests below were computed
independently via `python3 -c "import hashlib; print(...)"` at the terminal,
not by calling pair_bucket and copying its output) or derived from the
module's own documented contract (5 fixed templates, deterministic RNG),
never copied from a run of the implementation under test.
"""
import hashlib
import json
import re
from pathlib import Path

import pytest

from app.finetune.qa_generation import (
    ANSWER_TEMPLATES,
    GENERAL_INSTRUCTION_PROMPTS,
    HEDGE_PHRASE,
    HELDOUT_BUCKET_THRESHOLD,
    QUESTION_TEMPLATES,
    TEMPLATE_SEED,
    abstention_threshold,
    build_and_write_all,
    generate_qa_rows,
    is_heldout_pair,
    pair_bucket,
    split_rows,
)


def _row(champ_a, champ_b, role="top", win_rate=0.5, sample_size=10, is_abstention=False):
    return {
        "champ_a": champ_a,
        "champ_b": champ_b,
        "role": role,
        "rank": "emerald",
        "phase": "not_available",
        "win_rate": win_rate,
        "sample_size": sample_size,
        "is_abstention": is_abstention,
    }


def test_pair_bucket_hand_computed_sha256():
    # Hand-computed independently at the terminal:
    # python3 -c "import hashlib; print(int(hashlib.sha256(b'Aatrox|Ambessa').hexdigest(), 16) % 100)"
    digest = hashlib.sha256(b"Aatrox|Ambessa").hexdigest()
    expected = int(digest, 16) % 100
    assert pair_bucket("Aatrox", "Ambessa") == expected


def test_is_heldout_pair_matches_threshold_boundary():
    # Construct pairs on both sides of the threshold by brute-force search --
    # independent of pair_bucket's internal call structure.
    found_below, found_at_or_above = False, False
    for i in range(200):
        a, b = f"Champ{i}", "Other"
        bucket = int(hashlib.sha256(f"{a}|{b}".encode()).hexdigest(), 16) % 100
        if bucket < HELDOUT_BUCKET_THRESHOLD:
            assert is_heldout_pair(a, b) is True
            found_below = True
        else:
            assert is_heldout_pair(a, b) is False
            found_at_or_above = True
    assert found_below and found_at_or_above  # sanity: search space actually spans both sides


def test_split_rows_zero_champion_pair_overlap():
    rows = [_row(f"Champ{i}", f"Champ{i+1}") for i in range(300)] + [
        _row(f"Champ{i}", f"Champ{i+1}", role="jungle") for i in range(300)
    ]
    train, heldout = split_rows(rows)
    train_pairs = {(r["champ_a"], r["champ_b"]) for r in train}
    heldout_pairs = {(r["champ_a"], r["champ_b"]) for r in heldout}
    assert train_pairs.isdisjoint(heldout_pairs)
    assert len(train) > 0 and len(heldout) > 0  # sanity: split space actually produced both


def test_split_rows_deterministic_across_repeated_calls():
    rows = [_row(f"Champ{i}", f"Champ{i+1}", role=r) for i in range(150) for r in ("top", "jungle")]
    train1, heldout1 = split_rows(rows)
    train2, heldout2 = split_rows(rows)
    assert train1 == train2
    assert heldout1 == heldout2


def test_abstention_threshold_hand_computed_percentile():
    # sample_sizes: [1]*6 + [2]*2 + [5]*2 -> 10 values, sorted.
    # 25th percentile, nearest-rank: ceil(0.25*10) = 3rd smallest value (1-indexed) -> 1
    rows = [_row("A", "B", sample_size=s) for s in ([1] * 6 + [2] * 2 + [5] * 2)]
    assert abstention_threshold(rows, percentile=25) == 1

    # A distribution where the 25th-percentile rank lands past the run of 1s:
    # sample_sizes: [1, 1, 3, 4] -> ceil(0.25*4) = 1st smallest -> 1
    rows2 = [_row("A", "B", sample_size=s) for s in [4, 1, 3, 1]]
    assert abstention_threshold(rows2, percentile=25) == 1

    # sample_sizes: [1, 2, 3, 4] -> ceil(0.75*4) = 3rd smallest -> 3
    rows3 = [_row("A", "B", sample_size=s) for s in [4, 1, 3, 2]]
    assert abstention_threshold(rows3, percentile=75) == 3


def _template_regex(template: str) -> re.Pattern:
    placeholder = re.compile(r"\\\{[a-z_]+\\\}")
    pattern = "^" + placeholder.sub(".+?", re.escape(template)) + "$"
    return re.compile(pattern)


def test_all_five_templates_used_when_generating_over_many_rows():
    # Enough rows, with the module's real fixed seed, for every one of the
    # 3 question + 2 answer templates to be selected at least once.
    rows = [
        _row(f"Champ{i}", f"Champ{i+1}", role=("top" if i % 2 else "jungle"), sample_size=50, is_abstention=(i % 5 == 0))
        for i in range(60)
    ]
    qa_rows = generate_qa_rows(rows, seed=TEMPLATE_SEED)

    q_regexes = [_template_regex(t) for t in QUESTION_TEMPLATES]
    a_regexes = [_template_regex(t) for t in ANSWER_TEMPLATES]

    matched_q_indices = set()
    matched_a_indices = set()
    for row in qa_rows:
        for i, rx in enumerate(q_regexes):
            if rx.match(row["prompt"]):
                matched_q_indices.add(i)
        if not row["is_abstention"]:
            for i, rx in enumerate(a_regexes):
                if rx.match(row["response"]):
                    matched_a_indices.add(i)
        else:
            assert row["response"] == HEDGE_PHRASE

    assert matched_q_indices == {0, 1, 2}, f"not all question templates used: {matched_q_indices}"
    assert matched_a_indices == {0, 1}, f"not all answer templates used: {matched_a_indices}"


def test_abstention_rows_use_the_single_fixed_hedge_phrase():
    rows = [_row("A", "B", is_abstention=True), _row("C", "D", is_abstention=True)]
    qa_rows = generate_qa_rows(rows, seed=TEMPLATE_SEED)
    assert all(r["response"] == "There isn't enough match data on this pairing for a confident read." for r in qa_rows)


def test_general_instruction_prompts_shape_and_no_lol_content():
    assert len(GENERAL_INSTRUCTION_PROMPTS) == 15
    for item in GENERAL_INSTRUCTION_PROMPTS:
        assert set(item.keys()) == {"prompt"}
    lol_terms = ["champion", "lane", "jungle", "top", "adc", "support", "league of legends", "matchup", "win rate"]
    blob = " ".join(p["prompt"].lower() for p in GENERAL_INSTRUCTION_PROMPTS)
    for term in lol_terms:
        assert not re.search(rf"\b{re.escape(term)}\b", blob), f"found LoL-flavored term {term!r} in general_instruction prompts"


# --- Real-pipeline integration check (real cached CSV, no download) --------

def _real_csv_path() -> str:
    from huggingface_hub import hf_hub_download

    return hf_hub_download(
        repo_id="BoostedJonP/league_of_legends_match_data",
        repo_type="dataset",
        filename="league_of_legends_emerald_match_data.csv",
        local_files_only=True,
    )


def test_build_and_write_all_produces_real_schema_correct_files(tmp_path):
    try:
        csv_path = _real_csv_path()
    except Exception as e:
        pytest.skip(f"cached HF CSV not available locally: {e}")

    summary = build_and_write_all(csv_path, tmp_path)

    assert summary["total_rows"] > 0
    assert summary["rank_phase_combos"] == [("emerald", "not_available")] or len(summary["rank_phase_combos"]) >= 1

    required_keys = {"prompt", "response", "champ_a", "champ_b", "role", "rank", "phase", "is_abstention"}
    for fname in ("train.jsonl", "heldout.jsonl", "abstention_eval.jsonl"):
        path = tmp_path / fname
        assert path.exists()
        lines = path.read_text(encoding="utf-8").splitlines()
        assert len(lines) > 0
        for line in lines:
            obj = json.loads(line)
            assert set(obj.keys()) == required_keys
            assert isinstance(obj["is_abstention"], bool)

    gi_path = tmp_path / "general_instruction_eval.jsonl"
    gi_lines = gi_path.read_text(encoding="utf-8").splitlines()
    assert len(gi_lines) == 15
    for line in gi_lines:
        obj = json.loads(line)
        assert set(obj.keys()) == {"prompt"}

    # abstention_eval.jsonl rows must all be is_abstention=true, heldout.jsonl none
    for line in (tmp_path / "abstention_eval.jsonl").read_text(encoding="utf-8").splitlines():
        assert json.loads(line)["is_abstention"] is True
    for line in (tmp_path / "heldout.jsonl").read_text(encoding="utf-8").splitlines():
        assert json.loads(line)["is_abstention"] is False

    # zero champion-pair overlap between train and heldout, using the real data
    train_pairs = {
        (json.loads(l)["champ_a"], json.loads(l)["champ_b"])
        for l in (tmp_path / "train.jsonl").read_text(encoding="utf-8").splitlines()
    }
    heldout_pairs = {
        (json.loads(l)["champ_a"], json.loads(l)["champ_b"])
        for l in (tmp_path / "heldout.jsonl").read_text(encoding="utf-8").splitlines()
    } | {
        (json.loads(l)["champ_a"], json.loads(l)["champ_b"])
        for l in (tmp_path / "abstention_eval.jsonl").read_text(encoding="utf-8").splitlines()
    }
    assert train_pairs.isdisjoint(heldout_pairs)
