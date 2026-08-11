"""
Tests for app.finetune.train.oversample_to_balance, written before the
implementation per the TEST_LOOP contract. Expected counts are hand-computed
from a fresh read of the real train.jsonl in this test (not copied from any
prior doc or from oversample_to_balance's own output):
  total=2213, abstention=1394, non_abstention=819
  full_repeats = 1394 // 819 = 1
  remainder    = 1394 % 819  = 575
  -> every one of the 819 non-abstention rows appears once (1 full copy),
     plus 575 of them (a seeded sample) appear a second time,
     for exactly 1394 non-abstention rows total (matching abstention count).
"""
import json
from collections import Counter
from pathlib import Path

from app.finetune.train import DATA_PATH, oversample_to_balance

SEED = 42


def _load_split():
    rows = [json.loads(l) for l in Path(DATA_PATH).read_text(encoding="utf-8").splitlines() if l.strip()]
    abstention = [r for r in rows if r["is_abstention"]]
    non_abstention = [r for r in rows if not r["is_abstention"]]
    return abstention, non_abstention


def test_fresh_counts_match_expected_819_1394():
    abstention, non_abstention = _load_split()
    assert len(abstention) == 1394
    assert len(non_abstention) == 819


def test_output_is_exactly_2x_abstention_and_50_50():
    abstention, non_abstention = _load_split()
    result = oversample_to_balance(abstention, non_abstention, seed=SEED)
    assert len(result) == 2 * len(abstention) == 2788
    n_ab = sum(1 for r in result if r["is_abstention"])
    n_nab = sum(1 for r in result if not r["is_abstention"])
    assert n_ab == 1394
    assert n_nab == 1394


def test_every_non_abstention_row_appears_at_least_once():
    abstention, non_abstention = _load_split()
    result = oversample_to_balance(abstention, non_abstention, seed=SEED)
    result_non_abstention = [r for r in result if not r["is_abstention"]]
    ids_in_result = Counter(json.dumps(r, sort_keys=True) for r in result_non_abstention)
    for row in non_abstention:
        key = json.dumps(row, sort_keys=True)
        assert ids_in_result[key] >= 1, "a real non-abstention row is missing from the oversampled output"


def test_duplicate_count_pattern_matches_formula():
    abstention, non_abstention = _load_split()
    result = oversample_to_balance(abstention, non_abstention, seed=SEED)
    result_non_abstention = [r for r in result if not r["is_abstention"]]
    counts = Counter(json.dumps(r, sort_keys=True) for r in result_non_abstention)

    full_repeats = len(abstention) // len(non_abstention)
    remainder = len(abstention) % len(non_abstention)
    assert full_repeats == 1
    assert remainder == 575

    twice = sum(1 for c in counts.values() if c == full_repeats + 1)
    once = sum(1 for c in counts.values() if c == full_repeats)
    assert twice == remainder == 575
    assert once == len(non_abstention) - remainder == 244
    assert all(c in (full_repeats, full_repeats + 1) for c in counts.values())


def test_same_seed_is_deterministic():
    abstention, non_abstention = _load_split()
    result_a = oversample_to_balance(abstention, non_abstention, seed=SEED)
    result_b = oversample_to_balance(abstention, non_abstention, seed=SEED)
    assert result_a == result_b
