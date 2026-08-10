"""
Tests for app.finetune.eval, the harness that scores AGENT-12's smoke-scale
adapter against AGENT-11's heldout/abstention/general-instruction eval sets.

Two kinds of test here:

1. Pure-logic unit tests (fast, no model load) for the banding rule, the
   numeric-percentage extraction, and the abstention paraphrase rule --
   expected values hand-derived from the task contract's stated banding
   thresholds and from HEDGE_PHRASE, never copied from eval.py's own output.

2. The mandatory, real, blocking step-1 sanity check (loads the real base
   model + AGENT-12's real saved adapter, no mocks) -- this is the
   fact_ledger.md countermeasure and per the task contract it must pass
   before any other step's results are meaningful. Marked slow/integration
   since it does a real CPU model load + two real generations.
"""
import pytest

from app.finetune.eval import (
    ABSTENTION_PARAPHRASE_THRESHOLD,
    OUTPUT_DIR,
    band_for_win_rate,
    extract_win_rate_pct,
    load_model_and_tokenizer,
    passes_abstention,
    score_heldout_row,
    step1_sanity_check,
)
from app.finetune.qa_generation import HEDGE_PHRASE


def _require_adapter():
    if not (OUTPUT_DIR / "adapter_config.json").exists():
        pytest.skip(f"No adapter at {OUTPUT_DIR} -- run `python -m app.finetune.train` first.")


# ---------------------------------------------------------------------
# Pure-logic: banding rule (hand-derived from the task contract's stated
# thresholds: >0.55 champ_a, <0.45 champ_b, else roughly even)
# ---------------------------------------------------------------------

@pytest.mark.parametrize("win_rate,expected", [
    (0.56, "champ_a favored"),
    (0.99, "champ_a favored"),
    (0.551, "champ_a favored"),
    (0.55, "roughly even"),   # boundary: not strictly > 0.55
    (0.50, "roughly even"),
    (0.45, "roughly even"),   # boundary: not strictly < 0.45
    (0.449, "champ_b favored"),
    (0.01, "champ_b favored"),
])
def test_band_for_win_rate(win_rate, expected):
    assert band_for_win_rate(win_rate) == expected


# ---------------------------------------------------------------------
# Pure-logic: percentage extraction from free-text model output
# ---------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Aatrox wins 62.0% of games against Kayle in top.", 62.0),
    ("Based on 4 recorded top games, Aatrox has a 50.0% win rate versus Kayle.", 50.0),
    ("no percentage here at all", None),
    ("a nonsense 150% figure is out of range", None),
])
def test_extract_win_rate_pct(text, expected):
    assert extract_win_rate_pct(text) == expected


# ---------------------------------------------------------------------
# Pure-logic: heldout row scoring -- expected pass/fail hand-derived per row,
# independent of score_heldout_row's own internals.
# ---------------------------------------------------------------------

def test_score_heldout_row_pass_band_and_numeric_match():
    row = {"champ_a": "Aatrox", "champ_b": "Kayle", "role": "top", "win_rate": 0.62}
    result = score_heldout_row(row, "Aatrox wins 60.0% of games against Kayle in top.")
    # real band: 0.62 > 0.55 -> champ_a favored; model said 60.0% -> also
    # champ_a favored, and |60.0 - 62.0| = 2.0 <= 10 -> should pass.
    assert result["real_band"] == "champ_a favored"
    assert result["implied_band"] == "champ_a favored"
    assert result["numeric_within_10pts"] is True
    assert result["passed"] is True


def test_score_heldout_row_fails_on_band_mismatch():
    row = {"champ_a": "Aatrox", "champ_b": "Kayle", "role": "top", "win_rate": 0.62}
    # model claims a low win rate -> wrong band, even though a number is present.
    result = score_heldout_row(row, "Aatrox wins 20.0% of games against Kayle in top.")
    assert result["real_band"] == "champ_a favored"
    assert result["implied_band"] == "champ_b favored"
    assert result["passed"] is False


def test_score_heldout_row_fails_with_no_numeric_figure():
    row = {"champ_a": "Aatrox", "champ_b": "Kayle", "role": "top", "win_rate": 0.62}
    result = score_heldout_row(row, "Aatrox is generally favored here.")
    assert result["extracted_pct"] is None
    assert result["passed"] is False


# ---------------------------------------------------------------------
# Pure-logic: abstention paraphrase rule (exact HEDGE_PHRASE from
# qa_generation.py, read directly -- not re-derived)
# ---------------------------------------------------------------------

def test_passes_abstention_exact_phrase():
    result = passes_abstention(HEDGE_PHRASE)
    assert result["contains_exact_phrase"] is True
    assert result["passed"] is True


def test_passes_abstention_unrelated_text_fails():
    result = passes_abstention("Aatrox wins 55% of games against Renekton.")
    assert result["contains_exact_phrase"] is False
    assert result["similarity_ratio"] < ABSTENTION_PARAPHRASE_THRESHOLD
    assert result["passed"] is False


def test_passes_abstention_close_paraphrase_via_stated_threshold():
    # A near-identical rewording should clear the stated 0.6 similarity bar
    # via stdlib difflib -- hand-checked below independent of eval.py.
    paraphrase = "There is not enough match data on this pairing for a confident read."
    import difflib
    ratio = difflib.SequenceMatcher(None, paraphrase, HEDGE_PHRASE).ratio()
    assert ratio >= ABSTENTION_PARAPHRASE_THRESHOLD, (
        f"test fixture assumption broken: ratio={ratio} below threshold"
    )
    result = passes_abstention(paraphrase)
    assert result["passed"] is True


# ---------------------------------------------------------------------
# Real, blocking step-1 check: PeftModel type + base-vs-adapted generation
# diff, against the *actual* saved adapter and *actual* base model. This is
# the fact_ledger.md countermeasure. No mocks -- a real CPU model load.
# ---------------------------------------------------------------------

def test_step1_sanity_check_real_adapter_differs_from_base():
    _require_adapter()
    from peft import PeftModel

    model, tokenizer = load_model_and_tokenizer()
    result = step1_sanity_check(model, tokenizer)

    assert result["is_peft_model"] is True, (
        "loaded object is not a PeftModel -- this is exactly the fact_ledger.md "
        "bug (silently scoring the base model instead of the adapter)"
    )
    assert isinstance(model, PeftModel)
    from app.finetune.train import MODEL_NAME
    assert result["base_model_name_or_path"] == MODEL_NAME
    assert result["generations_differ"] is True, (
        "base and adapted generation on the fixed sanity prompt were identical "
        "-- adapter had no observable effect"
    )
    assert result["passed"] is True
