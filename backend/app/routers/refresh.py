"""
POST /refresh -- triggers the offline pipeline. Explicitly user-triggered,
never scheduled to auto-run while the game might be open. See
docs/system-design.md section 2 and docs/build-plan.md Phase 8.
"""
from fastapi import APIRouter

router = APIRouter()


@router.post("/refresh")
def refresh():
    """
    TODO(Phase 3/8): run, in order: match pull -> aggregation -> retrieval
    rebuild -> precompute batch. Log stage timing and row counts (see
    docs/testing-strategy.md infra smoke-test notes) so a broken refresh is
    visible before champ select, not during it.

    TODO: after every refresh, re-run the eval set and a style-audit sample
    before treating the new data as live (docs/system-design.md Testing &
    Evaluation section).
    """
    raise NotImplementedError
