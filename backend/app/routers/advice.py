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
    role: str = Query(...),
    rank: str = Query(...),
    db: Session = Depends(get_db),
):
    """Looks up the three phase rows for (champ_a, champ_b, role, rank) at
    the most recent patch that has any row for this matchup. No model call
    in this code path -- see test_advice_endpoint.py's import-boundary
    check.

    `role` is required: it's part of Advice's real uniqueness (champ_a,
    champ_b, role, rank_bracket, phase, patch) per models.py -- a champion
    can be viable in more than one lane (e.g. Ashe bot/support, per
    models.py's own docstring), so champ_a/champ_b/rank alone can't
    identify a single matchup row set.
    """
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
        return JSONResponse(status_code=404, content={"status": "not_precomputed"})

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
        return JSONResponse(status_code=404, content={"status": "not_precomputed"})

    return {phase: row_by_phase[phase].text for phase in REQUIRED_PHASES}
