"""
Unit test for the markup-stripping fix in app.retrieval.index.champion_text().

Real bug: Data Dragon embeds its own HTML-like markup vocabulary in
passive/spell description and tooltip text (color tags for lore
storylines, <status>/<scaleAP>/<keywordMajor>/... semantic tags, <br>
line breaks). champion_text() previously passed this through verbatim
into the embedding text -- confirmed leak: Kayn's passive text contained
`<font color='#8484fb'>Shadow Assassin</font>` verbatim in generated
output.

Expected values below are hand-computed against real Data Dragon detail
JSON for patch 16.15.1 (fetched directly here, same endpoint/pattern as
app.finetune.qualitative_advice.fetch_champion_detail and
tests/integration/test_retrieval_index.py), not synthetic fixtures
invented to match whatever the implementation happens to produce.
"""
from __future__ import annotations

import re

import pytest
import requests

from app.retrieval.index import champion_text

DDRAGON_DETAIL_URL = (
    "https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion/{champ}.json"
)
PATCH = "16.15.1"

# Kayn (the confirmed real leak) plus champions likely to exercise other
# real markup tags (scaling/status keyword tags, line breaks).
CHAMPIONS = ["Kayn", "Warwick", "Ahri", "Yasuo", "Velkoz"]

_TAG_RE = re.compile(r"<[^>]+>")


@pytest.fixture(scope="module")
def champion_detail_data():
    session = requests.Session()
    data = {}
    try:
        for champ in CHAMPIONS:
            resp = session.get(
                DDRAGON_DETAIL_URL.format(patch=PATCH, champ=champ), timeout=15
            )
            resp.raise_for_status()
            data[champ] = resp.json()["data"][champ]
    except requests.RequestException as exc:
        pytest.skip(f"Data Dragon not reachable in this environment: {exc}")
    return data


def test_kayn_passive_font_tags_stripped(champion_detail_data):
    # The exact confirmed real leak: Kayn's passive description contains
    # `<font color='#8484fb'>Shadow Assassin</font>` verbatim in the raw
    # Data Dragon JSON. After the fix, the tags are gone but the real
    # text they wrapped (independently known: Kayn's transformed-state
    # name is "Shadow Assassin") survives.
    raw_desc = champion_detail_data["Kayn"]["passive"]["description"]
    assert "<font color='#8484fb'>Shadow Assassin</font>" in raw_desc, (
        "fixture assumption broken -- Data Dragon no longer contains the "
        "confirmed real leak this test targets"
    )

    text = champion_text(champion_detail_data["Kayn"])
    assert "<font" in raw_desc  # sanity: raw source really has the tag
    assert "<font" not in text
    assert "</font>" not in text
    assert "Shadow Assassin" in text


@pytest.mark.parametrize("champ", CHAMPIONS)
def test_no_html_like_tags_survive_for_any_fetched_champion(champion_detail_data, champ):
    # General check, not just the one named tag: no `<...>` pattern of any
    # kind survives in the flattened embedding text for any of the real
    # champions fetched this session.
    text = champion_text(champion_detail_data[champ])
    assert not _TAG_RE.findall(text), (
        f"{champ}: markup survived stripping: {_TAG_RE.findall(text)}"
    )


def test_real_markup_vocabulary_found_this_session_is_all_stripped(champion_detail_data):
    # Confirms the fix actually had something real to strip -- i.e. this
    # isn't a vacuously-passing test against already-clean data. The tags
    # below are exactly what was found scanning the real fetched JSON for
    # Kayn/Warwick/Ahri/Yasuo/Vel'Koz this session (passive + spell
    # description/tooltip + blurb text).
    real_tags_found = {
        "font", "br", "status", "scaleAP", "scaleAD", "scaleArmor",
        "scaleMana", "keywordMajor", "keywordName", "spellName",
        "spellActive", "spellPassive", "healing", "hold", "magicDamage",
        "physicalDamage", "trueDamage", "recast", "speed", "tap",
        "factionIonia1",
    }
    raw_blobs = []
    for champ_data in champion_detail_data.values():
        raw_blobs.append(champ_data.get("blurb", ""))
        passive = champ_data.get("passive")
        if passive:
            raw_blobs.append(passive.get("description", ""))
        for spell in champ_data.get("spells", []):
            raw_blobs.append(spell.get("description", ""))
            raw_blobs.append(spell.get("tooltip", ""))
    raw_text = "\n".join(raw_blobs)
    tags_actually_present = {
        m.strip("</ ").split()[0] for m in _TAG_RE.findall(raw_text)
    }

    # At least confirm the specific tags this test asserts against really
    # did appear in the raw fetch (guards against the inventory going
    # stale on a future patch).
    assert real_tags_found & tags_actually_present, (
        "none of the expected real markup tags were present in this "
        "session's fetch -- inventory may be stale for the current patch"
    )

    for champ_data in champion_detail_data.values():
        text = champion_text(champ_data)
        assert not _TAG_RE.findall(text)
