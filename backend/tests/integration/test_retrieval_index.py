"""
Integration test: a real semantic check of app.retrieval.index.RetrievalIndex
-- embed a query describing a specific known champion's actual ability (in
the tester's own words, not copy-pasted from the source text) against a real
local sentence-transformers model, and confirm the nearest neighbor is that
champion, not an unrelated one.

Uses real Data Dragon per-champion detail JSON (the endpoint that includes
`passive`/`spells`, per docs/adr-001-architecture.md -- Data Dragon is the
source for ability *text*), fetched directly here rather than via
app.data_pipeline.data_dragon.fetch_champion_data, because that function
wraps the summary `champion.json` endpoint (name/blurb/tags only, no
spells/passive) -- the detail endpoint is a different Data Dragon resource,
needed for real kit text to embed. Skipped if there's no network access.

The expected answer (query -> "Ashe") is derived from independent domain
knowledge of Ashe's kit (her R, Enchanted Crystal Arrow, is a well-documented,
widely-known ability), not by running RetrievalIndex and reading back
whichever champion it happened to rank first.
"""
import requests
import pytest

from app.retrieval.index import RetrievalIndex, champion_text

DDRAGON_DETAIL_URL = (
    "https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion/{champ}.json"
)
PATCH = "16.15.1"

# Ashe (target) plus distractors with clearly different kits (melee bruiser,
# light mage, melee assassin, hypercarry marksman, engage support/tank) so a
# correct top-1 match isn't just "the only ranged champion in the set".
CHAMPIONS = ["Ashe", "Garen", "Lux", "Zed", "Jinx", "Leona"]

# Ashe's ultimate, Enchanted Crystal Arrow, described in the tester's own
# words rather than quoted from the Data Dragon text itself -- this is a
# semantic match, not a substring/lexical one.
QUERY = (
    "Which champion fires a giant arrow of ice in a straight line across "
    "the map that stuns the first enemy champion it hits, with a longer "
    "stun the farther it has traveled?"
)


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


def test_champion_text_includes_real_ability_text(champion_detail_data):
    # Sanity check on the fixture itself: Ashe's real R name/description
    # (independently known, not derived from the index) is actually present
    # in what gets embedded -- if this fails, the semantic test below would
    # be testing nothing.
    text = champion_text(champion_detail_data["Ashe"])
    assert "Enchanted Crystal Arrow" in text
    assert "stun" in text.lower()


def test_nearest_neighbor_is_the_correct_champion(champion_detail_data):
    index = RetrievalIndex()
    index.build(champion_detail_data)

    results = index.query(QUERY, k=len(CHAMPIONS))
    top_champion, top_score = results[0]

    assert top_champion == "Ashe", f"expected Ashe on top, got ranking {results}"
    # Not just "technically first" -- a real margin over the next-best
    # (unrelated) champion, so this isn't a near-tie fluke.
    second_score = results[1][1]
    assert top_score - second_score > 0.05, (
        f"Ashe's margin over the next result was too thin: {results}"
    )


def test_unrelated_query_does_not_match_ashe(champion_detail_data):
    # Negative control: a query about a totally different kit (Garen's
    # spinning-blade ultimate) should not nearest-neighbor to Ashe.
    index = RetrievalIndex()
    index.build(champion_detail_data)

    query = (
        "Which champion spins with their sword drawn, dealing damage to "
        "all nearby enemies repeatedly for several seconds, and deals more "
        "damage the lower the target's remaining health is?"
    )
    top_champion, _ = index.query(query, k=1)[0]
    assert top_champion == "Garen"
