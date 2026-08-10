"""
Tests for app/data_pipeline/data_dragon.py.

Includes a live-network regression test against Data Dragon (small, fast
HTTP calls -- well under the resource gate) per this task's procedure step 3:
fetch the current patch, and if it's still 16.15.1 (what
docs/decisions/phase1-role-pair-count.md measured), assert the filtered
count is exactly 173. If the live patch has moved on, don't hard-fail the
count -- just assert zero collision ambiguity and report the new numbers.
"""

import pytest

from app.data_pipeline.data_dragon import (
    _filter_variants,
    fetch_champion_data,
    get_current_patch,
)


# ---------------------------------------------------------------------------
# Pure unit test against a small hand-built fixture (expected values derived
# by hand, not by running the implementation and copying its output back).
# ---------------------------------------------------------------------------


def _entry(name: str, key: str) -> dict:
    return {"name": name, "id": key, "key": key}


FIXTURE_RAW = {
    "Ahri": _entry("Ahri", "Ahri"),
    "Jade_Ahri": _entry("Ahri", "Jade_Ahri"),
    "MonkeyKing": _entry("Wukong", "MonkeyKing"),
    "Jade_Wukong": _entry("Wukong", "Jade_Wukong"),
    "Garen": _entry("Garen", "Garen"),
}


def test_filter_variants_drops_underscore_prefixed_duplicates():
    result = _filter_variants(FIXTURE_RAW)
    # Hand-derived expectation: 5 raw entries, 2 collision groups
    # (Ahri/Jade_Ahri and MonkeyKing/Jade_Wukong via shared name "Wukong"),
    # each collapsing to 1 -> 3 kept entries total.
    assert set(result.keys()) == {"Ahri", "MonkeyKing", "Garen"}
    assert len(result) == 3


def test_filter_variants_keeps_key_with_no_underscore_prefix():
    result = _filter_variants(FIXTURE_RAW)
    assert "Jade_Ahri" not in result
    assert "Jade_Wukong" not in result
    assert result["MonkeyKing"]["name"] == "Wukong"


def test_filter_variants_no_collision_passthrough():
    result = _filter_variants({"Garen": _entry("Garen", "Garen")})
    assert result == {"Garen": _entry("Garen", "Garen")}


def test_filter_variants_raises_on_ambiguous_group():
    # Two keys sharing a name, neither has an underscore prefix -> can't
    # resolve which to keep -> must fail loudly, not guess.
    ambiguous = {
        "FooA": _entry("Foo", "FooA"),
        "FooB": _entry("Foo", "FooB"),
    }
    with pytest.raises(ValueError):
        _filter_variants(ambiguous)


# ---------------------------------------------------------------------------
# Live-network regression test (real HTTP client, real json parsing).
# ---------------------------------------------------------------------------


def test_live_champion_count_regression():
    live_patch = get_current_patch()
    data = fetch_champion_data(live_patch)

    # Zero ambiguous groups is required regardless of patch drift -- if
    # _filter_variants hit an ambiguous group it would have raised already,
    # so getting a dict back at all already proves this. Assert non-empty
    # and internally consistent as a floor.
    assert len(data) > 0
    for key, entry in data.items():
        assert entry["name"]  # every kept entry has a name field

    if live_patch == "16.15.1":
        assert len(data) == 173
    else:
        # Live patch has moved past what phase1-role-pair-count.md measured.
        # Don't hard-fail the count; just report it.
        print(
            f"[informational] live patch advanced to {live_patch}; "
            f"filtered champion count = {len(data)} (not asserted == 173)"
        )
