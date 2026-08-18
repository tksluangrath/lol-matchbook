"""
Generates a small, fact-grounded qualitative early/mid/late-game advice
training set. Reuses app.retrieval.index.champion_text() (kit/ability text,
never numeric balance fields -- per docs/adr-001-architecture.md) and the
win-rate context block format validated in
docs/decisions/phase2-context-conditioning-diagnostic.md (reused verbatim
from an existing train_context.jsonl/heldout_context.jsonl row's prompt,
not reconstructed).

Real Data Dragon detail-endpoint fetch (passive/spells, not the summary
champion.json AGENT-9 already uses) -- same endpoint/pattern
test_retrieval_index.py already exercises.

Fact-grounding filter (heuristic, not a guarantee -- see module docstring
of the filter function): any capitalized 2-4-word phrase in the generated
blurb must appear verbatim in the supplied kit-context text, and any cited
percentage must match the pair's real win rate.
"""
import functools
import re

import requests

from app.retrieval.index import champion_text

DDRAGON_DETAIL_URL = (
    "https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion/{champ}.json"
)
DDRAGON_CHAMPION_LIST_URL = "https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion.json"
PATCH = "16.15.1"


@functools.lru_cache(maxsize=8)
def _real_champion_keys(patch: str) -> dict[str, str]:
    """{lowercased key: real key}, fetched once per patch. Real gap found
    running the eager-tier precompute against real match data: Riot's
    Match-V5 championName field spells some champions differently than Data
    Dragon's own key (e.g. match data "FiddleSticks" vs. the real Data
    Dragon key "Fiddlesticks") -- verified no lowercase collisions across
    all 233 real champion.json keys, so a case-insensitive resolve is safe."""
    resp = requests.get(DDRAGON_CHAMPION_LIST_URL.format(patch=patch), timeout=15)
    resp.raise_for_status()
    return {k.lower(): k for k in resp.json()["data"]}


def resolve_champ_key(champ_key: str, patch: str = PATCH) -> str:
    """The real Data Dragon key for champ_key, case-insensitive. Falls back
    to champ_key unchanged if it's not a recognized champion at all (lets
    the caller's own real fetch 404/403 rather than silently swallowing a
    genuinely unknown name)."""
    return _real_champion_keys(patch).get(champ_key.lower(), champ_key)

CAPITALIZED_PHRASE_RE = re.compile(r"\b[A-Z][a-zA-Z']*(?:\s+[A-Z][a-zA-Z']*){1,3}\b")
PCT_RE = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*%")
WIN_RATE_PCT_RE = re.compile(r"win rate:\s*(\d{1,3})%")

# Common English words that start a sentence/clause and get capitalized by
# ordinary grammar, not because they're part of a proper-noun ability name
# (e.g. "...especially if Ambessa is caught off-guard." -> capitalized "If"
# after punctuation). A real ability name is never led by one of these.
_NON_ABILITY_LEAD_WORDS = {
    "if", "when", "while", "since", "because", "after", "before", "use",
    "avoid", "early", "mid", "late", "as", "so", "but", "and", "then",
    "this", "that", "these", "those", "here", "there", "overall",
}


def select_pairs(rows: list[dict], n: int) -> list[dict]:
    """Deterministically selects up to n rows, one per distinct
    (champ_a, champ_b) pair, sorted alphabetically by (champ_a, champ_b).
    For pairs with more than one role row, the first-occurring row (file
    order) is kept."""
    seen: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["champ_a"], row["champ_b"])
        if key not in seen:
            seen[key] = row
    ordered_keys = sorted(seen.keys())[:n]
    return [seen[k] for k in ordered_keys]


def fetch_champion_detail(champ_key: str, patch: str = PATCH) -> dict:
    real_key = resolve_champ_key(champ_key, patch)
    resp = requests.get(DDRAGON_DETAIL_URL.format(patch=patch, champ=real_key), timeout=15)
    resp.raise_for_status()
    return resp.json()["data"][real_key]


def win_rate_context_block(row: dict) -> str:
    """Extracts the existing 'Context: ...' block (before '\\nQuestion:')
    from a train_context.jsonl/heldout_context.jsonl row's prompt --
    reused verbatim from the prior diagnostic's validated format, not
    reconstructed here."""
    return row["prompt"].split("\nQuestion:")[0]


def real_win_rate_pct(row: dict) -> int:
    """Real win_rate_pct stated in row's own context block."""
    m = WIN_RATE_PCT_RE.search(row["prompt"])
    if not m:
        raise ValueError(f"row has no win-rate context block: {row!r}")
    return int(m.group(1))


def ability_names(champ_detail: dict) -> list[str]:
    """Real passive + spell names (verbatim, kit order) from a Data Dragon
    champion detail dict -- the same dict champion_text() already reads its
    prose from, no new fetch."""
    names = []
    passive = champ_detail.get("passive")
    if passive and passive.get("name"):
        names.append(passive["name"])
    for spell in champ_detail.get("spells", []):
        if spell.get("name"):
            names.append(spell["name"])
    return names


def ability_whitelist_block(champ_a: str, champ_a_detail: dict, champ_b: str, champ_b_detail: dict) -> str:
    """Explicit, exact-spelling ability-name list for both champions.
    Real gap found investigating the 27 eager-tier grounding-check skips
    (docs/decisions/phase3-eager-tier-precompute.md): ability names only
    ever appeared inside prose kit-text, never as an anchor the model could
    copy verbatim -- e.g. Warwick's real "Primal Howl" came out as "Primal
    Howls", Viego's real "Harrowed Path" came out as "Hallowed Path"."""
    a_names = ", ".join(ability_names(champ_a_detail))
    b_names = ", ".join(ability_names(champ_b_detail))
    return (
        f"{champ_a}'s real abilities: {a_names}. {champ_b}'s real abilities: {b_names}. "
        "Only reference ability names from these two lists, spelled exactly as given."
    )


def build_generation_prompt(row: dict, champ_a_detail: dict, champ_b_detail: dict) -> str:
    win_rate_ctx = win_rate_context_block(row)
    champ_a_kit = f"{row['champ_a']} kit: {champion_text(champ_a_detail)}"
    champ_b_kit = f"{row['champ_b']} kit: {champion_text(champ_b_detail)}"
    whitelist = ability_whitelist_block(row["champ_a"], champ_a_detail, row["champ_b"], champ_b_detail)
    return (
        f"{win_rate_ctx}\n{champ_a_kit}\n{champ_b_kit}\n{whitelist}\n"
        "Instruction: Using only the facts given above, write strategic "
        f"{row['role']}-lane matchup advice in exactly three labeled "
        "sections: Early:, Mid:, Late:. Do not cite any ability, item, or "
        "statistic that is not stated above."
    )


def fact_grounding_check(generated_text: str, kit_context_text: str, expected_win_rate_pct: int) -> dict:
    """Heuristic proxy for grounding, not a guarantee: flags any
    capitalized 2-4-word phrase not present verbatim in kit_context_text,
    and any cited percentage that doesn't match expected_win_rate_pct."""
    phrases = set(CAPITALIZED_PHRASE_RE.findall(generated_text))
    phrases = {p for p in phrases if p.split()[0].lower() not in _NON_ABILITY_LEAD_WORDS}
    invented_phrases = sorted(p for p in phrases if p not in kit_context_text)
    cited_pcts = [float(m) for m in PCT_RE.findall(generated_text)]
    mismatched_pcts = [p for p in cited_pcts if abs(p - expected_win_rate_pct) > 0.5]
    return {
        "invented_phrases": invented_phrases,
        "cited_percentages": cited_pcts,
        "mismatched_percentages": mismatched_pcts,
        "passed": not invented_phrases and not mismatched_pcts,
    }
