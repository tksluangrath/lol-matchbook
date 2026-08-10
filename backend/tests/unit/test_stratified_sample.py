"""
Unit tests for app.finetune.train.stratified_sample.

Expected counts are hand-derived from the real train.jsonl file via:
    $ grep -c '"is_abstention": true' app/finetune/data/train.jsonl   -> 1394
    $ grep -c '"is_abstention": false' app/finetune/data/train.jsonl  -> 819
    $ wc -l app/finetune/data/train.jsonl                             -> 2213
run independently at the terminal this session, not trusted from any prior
doc without re-verifying against the current file, and not copied from
stratified_sample's own output.
"""
import json

from app.finetune.train import DATA_PATH, stratified_sample

ROWS = [json.loads(line) for line in DATA_PATH.read_text().splitlines() if line.strip()]

REAL_TOTAL = 2213
REAL_ABSTENTION = 1394
REAL_NON_ABSTENTION = 819


def test_real_train_jsonl_matches_hand_counted_totals():
    assert len(ROWS) == REAL_TOTAL
    assert sum(1 for r in ROWS if r["is_abstention"]) == REAL_ABSTENTION
    assert sum(1 for r in ROWS if not r["is_abstention"]) == REAL_NON_ABSTENTION


def test_output_has_exact_requested_counts():
    result = stratified_sample(ROWS, n_abstention=250, n_non_abstention=250, seed=42)
    assert len(result) == 500


def test_every_row_matches_its_requested_stratum():
    result = stratified_sample(ROWS, n_abstention=250, n_non_abstention=250, seed=42)
    abstention_count = sum(1 for r in result if r["is_abstention"])
    non_abstention_count = sum(1 for r in result if not r["is_abstention"])
    assert abstention_count == 250
    assert non_abstention_count == 250


def test_zero_duplicate_rows_in_output():
    result = stratified_sample(ROWS, n_abstention=250, n_non_abstention=250, seed=42)
    ids = [(r["champ_a"], r["champ_b"], r["role"], r["prompt"]) for r in result]
    assert len(ids) == len(set(ids))


def test_same_seed_produces_identical_result():
    first = stratified_sample(ROWS, n_abstention=250, n_non_abstention=250, seed=42)
    second = stratified_sample(ROWS, n_abstention=250, n_non_abstention=250, seed=42)
    assert first == second


def test_no_duplication_used_when_stratum_has_ample_rows():
    # 819 real non-abstention rows exist, well over the 250 requested --
    # confirms the function draws without replacement rather than padding
    # with duplicates.
    result = stratified_sample(ROWS, n_abstention=250, n_non_abstention=250, seed=42)
    non_abstention_rows = [r for r in result if not r["is_abstention"]]
    assert len(non_abstention_rows) == len(
        {(r["champ_a"], r["champ_b"], r["role"], r["prompt"]) for r in non_abstention_rows}
    )
