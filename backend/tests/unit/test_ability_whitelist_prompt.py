"""
Unit test for the ability-name whitelist added to build_generation_prompt
(app.finetune.qualitative_advice), per docs/decisions/phase3-ability-
whitelist-retry.md. Fixtures are trimmed real Warwick/Viego Data Dragon
detail JSON (passive + spell names fetched for real this session via
fetch_champion_detail -- see that fetch's real output in the task's
investigation notes), not invented names.
"""
from app.finetune.qualitative_advice import ability_names, build_generation_prompt


def _detail(name: str, passive_name: str, spell_names: list[str]) -> dict:
    return {
        "name": name,
        "blurb": f"{name} is a champion.",
        "passive": {"name": passive_name, "description": "passive desc."},
        "spells": [{"name": s, "description": f"{s} desc."} for s in spell_names],
    }


WARWICK_DETAIL = _detail(
    "Warwick", "Eternal Hunger",
    ["Jaws of the Beast", "Blood Hunt", "Primal Howl", "Infinite Duress"],
)
VIEGO_DETAIL = _detail(
    "Viego", "Sovereign's Domination",
    ["Blade of the Ruined King", "Spectral Maw", "Harrowed Path", "Heartbreaker"],
)


def _row():
    prompt = (
        "Context: 3 games observed this patch between Warwick and Viego in "
        "the jungle lane. Warwick win rate: 50%.\n"
        "Question: What's the win rate for Warwick into Viego (jungle)?"
    )
    return {"prompt": prompt, "champ_a": "Warwick", "champ_b": "Viego", "role": "jungle"}


def test_ability_names_extracts_real_passive_and_spell_names_in_kit_order():
    assert ability_names(WARWICK_DETAIL) == [
        "Eternal Hunger", "Jaws of the Beast", "Blood Hunt", "Primal Howl", "Infinite Duress",
    ]


def test_build_generation_prompt_contains_exact_real_ability_names():
    prompt = build_generation_prompt(_row(), WARWICK_DETAIL, VIEGO_DETAIL)
    # These are the two real near-miss hallucinations found in the eager-
    # tier skip investigation ("Primal Howls", "Hallowed Path") -- the
    # whitelist must contain the real, correctly-spelled names verbatim.
    assert "Primal Howl" in prompt
    assert "Harrowed Path" in prompt
    # And must not contain the invented misspellings themselves.
    assert "Primal Howls" not in prompt
    assert "Hallowed Path" not in prompt


def test_build_generation_prompt_whitelist_names_both_champions():
    prompt = build_generation_prompt(_row(), WARWICK_DETAIL, VIEGO_DETAIL)
    assert "Warwick's real abilities:" in prompt
    assert "Viego's real abilities:" in prompt
