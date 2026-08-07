"""
GET /advice -- the champ-select path. Pure DB lookup, no model call, no GPU.
Target latency: well under the 30s champ-select window (docs/system-design.md
targets <200ms). See docs/build-plan.md Phase 4.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Advice

router = APIRouter()


@router.get("/advice")
def get_advice(
    champ_a: str = Query(...),
    champ_b: str = Query(...),
    rank: str = Query(...),
    db: Session = Depends(get_db),
):
    """
    TODO(Phase 4): look up all three phase rows for this (champ_a, champ_b, rank)
    at the current patch. Return {"early": ..., "mid": ..., "late": ...}.

    TODO: handle the case where no row exists yet -- either the pair hasn't been
    precomputed (tiered-fallback case, docs/architecture-evaluation.md
    recommendation 4) or it's a genuine thin-data abstention. These need
    different responses: "still generating" vs. "not enough data at this rank".

    TODO: handle cold start -- no refresh has ever run yet. See
    docs/architecture-evaluation.md "First-run experience is unspecified".
    """
    raise NotImplementedError
