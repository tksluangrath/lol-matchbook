"""
Data Dragon -- static per-patch assets (champion/ability/item JSON).
See docs/adr-001-architecture.md: Data Dragon is a manual per-patch export,
not always updated immediately after a patch ships, and its balance-number
fields are sometimes inaccurate -- use it for ability/item *text* in the
retrieval corpus, never as the source of truth for win rates or numeric
balance data. That comes from app/data_pipeline/aggregate.py instead.

Variant-detection rule (see docs/decisions/phase1-role-pair-count.md):
champion.json's top-level keys include game-mode-variant duplicates (e.g.
"Jade_Ahri") alongside the real champion entry (e.g. "Ahri"). Dedupe by the
'name' field: when multiple keys share a 'name', keep the one key with no
underscore-prefixed id (e.g. keep "Ahri", drop "Jade_Ahri"); every other
colliding entry is a mode variant, not a champion. Verified against live
16.15.1 data to produce exactly 173 champions / 60 dropped variants / zero
ambiguous groups, including Jade_Wukong (name collides with MonkeyKing's
name "Wukong" even though MonkeyKing's own key/id isn't "Wukong").
"""

import requests

DDRAGON_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DDRAGON_CHAMPION_URL = "https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion.json"


def get_current_patch() -> str:
    """Fetch the live current patch version from the Data Dragon versions endpoint."""
    resp = requests.get(DDRAGON_VERSIONS_URL, timeout=10)
    resp.raise_for_status()
    versions = resp.json()
    return versions[0]


def fetch_champion_data(patch: str) -> dict:
    """Download champion.json for `patch` and return {champ_key: champ_data},
    filtered to real champions only (game-mode variants like "Jade_Ahri"
    removed per the variant-detection rule above)."""
    resp = requests.get(DDRAGON_CHAMPION_URL.format(patch=patch), timeout=15)
    resp.raise_for_status()
    raw = resp.json()["data"]
    return _filter_variants(raw)


def _filter_variants(raw: dict) -> dict:
    """Apply the name-collision variant-detection rule. Raises ValueError if
    any name-collision group can't be resolved to exactly one non-underscore
    key (an "ambiguous group") -- fail loudly rather than guess."""
    by_name: dict[str, list[str]] = {}
    for key, entry in raw.items():
        by_name.setdefault(entry["name"], []).append(key)

    filtered: dict = {}
    for name, keys in by_name.items():
        if len(keys) == 1:
            filtered[keys[0]] = raw[keys[0]]
            continue
        no_underscore = [k for k in keys if "_" not in k]
        if len(no_underscore) != 1:
            raise ValueError(
                f"Ambiguous variant group for name={name!r}: keys={keys!r}"
            )
        filtered[no_underscore[0]] = raw[no_underscore[0]]
    return filtered
