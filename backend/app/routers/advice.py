"""
GET /advice -- the champ-select path. Pure DB lookup, no model call, no GPU.
Target latency: well under the 30s champ-select window (docs/system-design.md
targets <200ms). See docs/build-plan.md Phase 4.
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Advice

router = APIRouter()

REQUIRED_PHASES = ("early", "mid", "late")


@router.get("/advice")
def get_advice(
    champ_a: str = Query(...),
    champ_b: str = Query(...),
    rank: str = Query(...),
    db: Session = Depends(get_db),
):
    """Looks up the three phase rows for (champ_a, champ_b, rank) at the
    most recent patch that has any row for this matchup. No model call in
    this code path -- see test_advice_endpoint.py's import-boundary check.

    Real gap, not silently patched over: `role` is part of Advice's real
    uniqueness (champ_a, champ_b, role, rank_bracket, phase, patch) per
    models.py, but this endpoint's declared query contract (this stub, as
    written before this change) only takes champ_a/champ_b/rank. If more
    than one role has rows for the same champ_a/champ_b/rank, this returns
    whichever role sorts first -- a real ambiguity that doesn't surface for
    the 10-pair sample this session precomputed (each champ_a/champ_b pair
    in that sample has only one role), but would for a champion played in
    multiple lanes (e.g. Ashe bot/support, per models.py's own docstring).
    """
    # ponytail: func.max() on `patch` is a plain string comparison, not a
    # semantic-version one -- "16.9.1" would lexicographically outrank
    # "16.15.1". Harmless while every row uses one real patch (this
    # session's sample); real fix (proper version compare or an
    # is_current_patch flag maintained by the refresh job) needed once
    # multiple patches' rows coexist.
    latest_patch = db.execute(
        select(func.max(Advice.patch)).where(
            Advice.champ_a == champ_a, Advice.champ_b == champ_b, Advice.rank_bracket == rank,
        )
    ).scalar()

    if latest_patch is None:
        return JSONResponse(status_code=404, content={"status": "not_precomputed"})

    rows = db.execute(
        select(Advice)
        .where(
            Advice.champ_a == champ_a, Advice.champ_b == champ_b,
            Advice.rank_bracket == rank, Advice.patch == latest_patch,
        )
        .order_by(Advice.role)
    ).scalars().all()

    first_role = rows[0].role
    rows = [r for r in rows if r.role == first_role]
    row_by_phase = {r.phase: r for r in rows}

    if any(r.is_abstention for r in rows):
        return {"status": "abstention", "reason": "not enough data at this rank"}

    if not all(phase in row_by_phase for phase in REQUIRED_PHASES):
        return JSONResponse(status_code=404, content={"status": "not_precomputed"})

    return {phase: row_by_phase[phase].text for phase in REQUIRED_PHASES}
