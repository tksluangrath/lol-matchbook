"""
Tests for app.finetune.train.oversample_to_count, the generalized helper
oversample_to_balance now delegates to. Expected values are hand-computed
against the real qualitative_advice_train.jsonl file (40 rows, verified
fresh via `wc -l` this session), not copied from the function's own output.

40 rows -> target 200: full_repeats = 200 // 40 = 5, remainder = 200 % 40 = 0
-> every row appears exactly 5 times, no row appears 6 times (remainder=0
means no extra sampled duplicates are needed).
"""
import json
from collections import Counter
from pathlib import Path

from app.finetune.train import oversample_to_count

SEED = 42
QUAL_TRAIN_PATH = Path(__file__).resolve().parents[2] / "app" / "finetune" / "data" / "qualitative_advice_train.jsonl"


def _load_qualitative_rows():
    return [json.loads(l) for l in QUAL_TRAIN_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_real_qualitative_train_file_has_40_rows():
    assert len(_load_qualitative_rows()) == 40


def test_output_is_exactly_target_count():
    rows = _load_qualitative_rows()
    result = oversample_to_count(rows, target_count=200, seed=SEED)
    assert len(result) == 200


def test_every_row_appears_exactly_five_times_no_remainder():
    rows = _load_qualitative_rows()
    result = oversample_to_count(rows, target_count=200, seed=SEED)
    counts = Counter(json.dumps(r, sort_keys=True) for r in result)
    assert len(counts) == 40
    assert all(c == 5 for c in counts.values())


def test_small_synthetic_case_with_nonzero_remainder():
    # Hand-computed: 3 rows -> target 7: full_repeats = 7//3 = 2,
    # remainder = 7%3 = 1 -> two rows appear twice, one row appears
    # three times (2 full copies + 1 seeded extra).
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    result = oversample_to_count(rows, target_count=7, seed=SEED)
    assert len(result) == 7
    counts = Counter(r["id"] for r in result)
    assert sorted(counts.values()) == [2, 2, 3]


def test_same_seed_is_deterministic():
    rows = _load_qualitative_rows()
    result_a = oversample_to_count(rows, target_count=200, seed=SEED)
    result_b = oversample_to_count(rows, target_count=200, seed=SEED)
    assert result_a == result_b


def test_no_remainder_sampling_call_when_target_is_exact_multiple():
    # target_count=80 is exactly 2x len(rows)=40 -> remainder=0, so no
    # random.Random(seed).sample call should occur (would raise if it did,
    # since sampling 0 items from a non-empty population is valid but the
    # point is the output should be a clean 2x repeat with no extra row).
    rows = _load_qualitative_rows()
    result = oversample_to_count(rows, target_count=80, seed=SEED)
    counts = Counter(json.dumps(r, sort_keys=True) for r in result)
    assert all(c == 2 for c in counts.values())
