"""
Unit tests for app.finetune.qualitative_advice's pure/testable functions
(pair selection, context-block extraction, real-win-rate parsing, and the
fact-grounding filter). Generation itself (calling the base model) is not
unit-testable against hand-derived expected text, so it is not covered
here -- AGENT-21/22's real training/eval runs are the check on that.

Expected values are hand-derived from the format spec / hand-constructed
fixtures, never copied from the implementation's own output.
"""
from app.finetune.qualitative_advice import (
    fact_grounding_check,
    real_win_rate_pct,
    select_pairs,
    win_rate_context_block,
)


def _row(champ_a, champ_b, role="top", win_rate_pct=50, sample_size=4):
    prompt = (
        f"Context: {sample_size} games observed this patch between {champ_a} and "
        f"{champ_b} in the {role} lane. {champ_a} win rate: {win_rate_pct}%.\n"
        f"Question: What's the win rate for {champ_a} into {champ_b} ({role})?"
    )
    return {"prompt": prompt, "champ_a": champ_a, "champ_b": champ_b, "role": role}


def test_select_pairs_deterministic_alphabetical_order():
    rows = [_row("Zed", "Talon"), _row("Aatrox", "Kayle"), _row("Ahri", "Fizz")]
    selected = select_pairs(rows, n=2)
    assert [(r["champ_a"], r["champ_b"]) for r in selected] == [
        ("Aatrox", "Kayle"),
        ("Ahri", "Fizz"),
    ]


def test_select_pairs_dedupes_multiple_roles_keeps_first_occurrence():
    rows = [
        _row("Aatrox", "Kayle", role="top"),
        _row("Aatrox", "Kayle", role="middle"),
        _row("Ahri", "Fizz", role="middle"),
    ]
    selected = select_pairs(rows, n=10)
    assert len(selected) == 2
    aatrox_kayle = next(r for r in selected if (r["champ_a"], r["champ_b"]) == ("Aatrox", "Kayle"))
    assert aatrox_kayle["role"] == "top"  # first occurrence, not the second role row


def test_select_pairs_respects_n_cap():
    rows = [_row(f"Champ{i}", "Other") for i in range(5)]
    assert len(select_pairs(rows, n=3)) == 3


def test_win_rate_context_block_extracts_prefix_before_question():
    row = _row("Aatrox", "Kayle", role="top", win_rate_pct=62, sample_size=5)
    block = win_rate_context_block(row)
    assert block == (
        "Context: 5 games observed this patch between Aatrox and Kayle in "
        "the top lane. Aatrox win rate: 62%."
    )
    assert "Question:" not in block


def test_real_win_rate_pct_parses_the_real_stated_value():
    row = _row("Aatrox", "Kayle", win_rate_pct=73)
    assert real_win_rate_pct(row) == 73


def test_fact_grounding_check_passes_when_grounded():
    kit_text = "Darius kit: Hemorrhage stacks bleed damage on hit.\nVayne kit: Silver Bolts deals bonus true damage."
    generated = (
        "Early: Darius wants to stack Hemorrhage early.\n"
        "Mid: Vayne looks for Silver Bolts value.\n"
        "Late: Darius's win rate is 58% into Vayne."
    )
    result = fact_grounding_check(generated, kit_text, expected_win_rate_pct=58)
    assert result["passed"] is True
    assert result["invented_phrases"] == []
    assert result["mismatched_percentages"] == []


def test_fact_grounding_check_flags_invented_ability_name():
    kit_text = "Darius kit: Hemorrhage stacks bleed damage on hit.\nVayne kit: Silver Bolts deals bonus true damage."
    generated = "Early: Darius should use Crimson Fury to burst Vayne down."
    result = fact_grounding_check(generated, kit_text, expected_win_rate_pct=58)
    assert result["passed"] is False
    assert "Crimson Fury" in result["invented_phrases"]


def test_fact_grounding_check_flags_mismatched_percentage():
    kit_text = "Darius kit: Hemorrhage stacks bleed damage on hit."
    generated = "Early: Darius wins this matchup 90% of the time."
    result = fact_grounding_check(generated, kit_text, expected_win_rate_pct=58)
    assert result["passed"] is False
    assert 90.0 in result["mismatched_percentages"]


def test_fact_grounding_check_does_not_flag_sentence_initial_conditional_plus_champion_name():
    # Real failure observed against the actual Aatrox/Ambessa generation
    # this session: "...especially if Ambessa is caught off-guard." gets
    # capitalized to "If Ambessa" after a period, which the naive
    # 2-4-capitalized-word regex flagged as an invented ability name. It
    # is not one -- it's an ordinary sentence-initial conditional clause
    # followed by the champion's own name.
    kit_text = "Aatrox kit: Deathbringer Stance heals on hit.\nAmbessa kit: Drakehound's Step dashes forward."
    generated = (
        "Early: Aatrox can use his dash to close gaps and pressure, "
        "especially if Ambessa is caught off-guard."
    )
    result = fact_grounding_check(generated, kit_text, expected_win_rate_pct=50)
    assert "If Ambessa" not in result["invented_phrases"]
    assert result["passed"] is True


def test_fact_grounding_check_allows_percentage_within_half_point_tolerance():
    kit_text = "Darius kit: Hemorrhage stacks bleed damage on hit."
    generated = "Early: Darius's win rate here is 58.0%."
    result = fact_grounding_check(generated, kit_text, expected_win_rate_pct=58)
    assert result["passed"] is True
