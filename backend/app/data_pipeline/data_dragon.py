"""
Data Dragon -- static per-patch assets (champion/ability/item JSON).
See docs/adr-001-architecture.md: Data Dragon is a manual per-patch export,
not always updated immediately after a patch ships, and its balance-number
fields are sometimes inaccurate -- use it for ability/item *text* in the
retrieval corpus, never as the source of truth for win rates or numeric
balance data. That comes from app/data_pipeline/aggregate.py instead.
"""


def fetch_champion_data(patch: str) -> dict:
    """TODO(Phase 1): download the champion.json tarball for `patch` and
    parse into {champ_name: {abilities, tags, ...}} for the retrieval index."""
    raise NotImplementedError
