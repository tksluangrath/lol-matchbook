"""
GET /advice -- the champ-select path. Pure DB lookup, no model call, no GPU.
Target latency: well under the 30s champ-select window (docs/system-design.md
targets <200ms). See docs/build-plan.md Phase 4.

Lazy-tier miss fallback implements docs/system-design.md's Error Handling
section verbatim: "Missing/incomplete data for a rare champion pair (very
low pick rate at a given rank) -> fall back to a wider rank bracket or a
general champion-archetype blurb rather than showing nothing."
"""
import functools

import requests
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Advice, BackfillQueue

router = APIRouter()

REQUIRED_PHASES = ("early", "mid", "late")

DDRAGON_CHAMPION_URL = "https://ddragon.leagueoflegends.com/cdn/{patch}/data/en_US/champion/{champ}.json"
FALLBACK_PATCH = "16.15.1"  # same real patch used throughout this project's finetune data


@functools.lru_cache(maxsize=256)
def _champion_archetype_blurb(champ_key: str, patch: str = FALLBACK_PATCH) -> str:
    """Real Data Dragon champion lore blurb -- the actual "general champion-
    archetype blurb" the spec names, not matchup-specific advice, no model
    call. lru_cache (stdlib) so only the first real request per champion
    pays the live network fetch; every repeat is an in-process dict lookup.
    ponytail: this is the one place in the lazy path that isn't a pure DB
    read, and a cold-cache hit can plausibly exceed the 200ms target on a
    real network call -- measured and reported honestly in
    docs/decisions/phase3-lazy-fallback-wiring.md rather than assumed fast."""
    resp = requests.get(DDRAGON_CHAMPION_URL.format(patch=patch, champ=champ_key), timeout=15)
    resp.raise_for_status()
    return resp.json()["data"][champ_key]["blurb"]


def _log_backfill_miss(db: Session, champ_a: str, champ_b: str, rank: str) -> None:
    """One real backfill_queue row per exact-rank miss -- not one per phase.
    ponytail: BackfillQueue's schema has a NOT NULL phase column (written
    when the design assumed one generation call per phase, same stale
    assumption flagged for the eager-tier N formula), but the real
    dedicated adapter generates all three phases in one call -- phase="early"
    here is a placeholder marking "this pair needs a real backfill run", not
    a claim that only the early phase is missing."""
    db.add(BackfillQueue(champ_a=champ_a, champ_b=champ_b, rank_bracket=rank, phase="early", status="pending"))
    db.commit()


def _lookup(db: Session, champ_a: str, champ_b: str, role: str, rank: str) -> dict | None:
    """Exact (champ_a, champ_b, role, rank) lookup at the most recent patch
    with any row for this matchup, or None if nothing is precomputed."""
    # ponytail: func.max() on `patch` is a plain string comparison, not a
    # semantic-version one -- "16.9.1" would lexicographically outrank
    # "16.15.1". Harmless while every row uses one real patch (this
    # session's sample); real fix (proper version compare or an
    # is_current_patch flag maintained by the refresh job) needed once
    # multiple patches' rows coexist.
    latest_patch = db.execute(
        select(func.max(Advice.patch)).where(
            Advice.champ_a == champ_a, Advice.champ_b == champ_b,
            Advice.role == role, Advice.rank_bracket == rank,
        )
    ).scalar()
    if latest_patch is None:
        return None

    rows = db.execute(
        select(Advice).where(
            Advice.champ_a == champ_a, Advice.champ_b == champ_b, Advice.role == role,
            Advice.rank_bracket == rank, Advice.patch == latest_patch,
        )
    ).scalars().all()

    row_by_phase = {r.phase: r for r in rows}
    if any(r.is_abstention for r in rows):
        return {"status": "abstention", "reason": "not enough data at this rank"}
    if not all(phase in row_by_phase for phase in REQUIRED_PHASES):
        return None
    return {phase: row_by_phase[phase].text for phase in REQUIRED_PHASES}


@router.get("/advice")
def get_advice(
    champ_a: str = Query(...),
    champ_b: str = Query(...),
    role: str = Query(...),
    rank: str = Query(...),
    db: Session = Depends(get_db),
):
    """`role` is required: it's part of Advice's real uniqueness (champ_a,
    champ_b, role, rank_bracket, phase, patch) per models.py -- a champion
    can be viable in more than one lane (e.g. Ashe bot/support, per
    models.py's own docstring), so champ_a/champ_b/rank alone can't
    identify a single matchup row set.
    """
    exact = _lookup(db, champ_a, champ_b, role, rank)
    if exact is not None:
        return exact

    # Real fallback #1: a wider rank bracket. Since every real precomputed
    # row in this system is rank_bracket="emerald" (the only bracket the
    # real match-data source ever supported), this is genuinely useful --
    # not a dead path -- for a request at any other rank string.
    _log_backfill_miss(db, champ_a, champ_b, rank)

    any_rank_row = db.execute(
        select(Advice.rank_bracket)
        .where(Advice.champ_a == champ_a, Advice.champ_b == champ_b, Advice.role == role)
        .limit(1)
    ).first()
    if any_rank_row is not None:
        wider = _lookup(db, champ_a, champ_b, role, any_rank_row[0])
        if wider is not None:
            if "status" in wider:  # a real abstention row -- surface it as-is, more informative than a generic blurb
                return wider
            return {**wider, "source": "wider_rank_fallback"}

    # Real fallback #2: general champion-archetype blurb -- nothing
    # precomputed for this pair/role at any rank.
    try:
        blurb_a = _champion_archetype_blurb(champ_a)
        blurb_b = _champion_archetype_blurb(champ_b)
    except requests.RequestException:
        return JSONResponse(status_code=404, content={"status": "not_precomputed"})

    return {
        "status": "archetype_fallback", "source": "archetype_fallback",
        "champ_a_blurb": blurb_a, "champ_b_blurb": blurb_b,
    }
