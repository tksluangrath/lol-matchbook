"""
POST /refresh -- triggers the offline pipeline. Explicitly user-triggered,
never scheduled to auto-run while the game might be open. See
docs/system-design.md section 2 and docs/build-plan.md Phase 8.

Real pipeline, not reinvented: rank_real_candidate_pairs() (match pull +
aggregation, already real and tested -- app.data_pipeline.aggregate) ->
build_pair_with_context() (real Data Dragon kit fetch) -> run_precompute_
batch() (generation + the idempotent ON CONFLICT DO NOTHING write + skip-
on-grounding-failure behavior already established and tested in
precompute.py). No separate retrieval-rebuild step exists to call: app.
retrieval.index.RetrievalIndex is built live from Data Dragon wherever it's
used (app.llm.context), not from a persisted index this job would refresh.

Runs as a FastAPI BackgroundTask, not blocking the HTTP response: a real
top-N precompute pass (N pairs * ~real seconds/pair, per this project's own
measured-throughput convention in run_eager_tier_expand_12h.py) can run
long past any reasonable request timeout. The caller gets an immediate
202-style acknowledgement; real stage/row-count logging goes to the
server's own stdout (matching every other launcher script in app.data_
pipeline), so a broken refresh is visible in server logs before champ
select, not silently during it.
"""
import logging

from fastapi import APIRouter, BackgroundTasks

import app.db as db
from app.data_pipeline.precompute import build_pair_with_context, rank_real_candidate_pairs, run_precompute_batch

router = APIRouter()
logger = logging.getLogger("refresh")

PATCH = "16.15.1"
DEFAULT_LIMIT = 50  # ponytail: no per-request throughput benchmark (that alone takes real minutes) --
# bounded, resumable batches instead of a time-budgeted overnight run. Call /refresh again to keep going;
# idempotency (already established in run_precompute_batch) skips pairs a prior call already covered.

_refresh_running = False  # single-process app, no worker pool -- a plain module flag is a real guard


def _run_refresh(limit: int):
    global _refresh_running
    try:
        logger.info("refresh: ranking real candidate pairs")
        ranked = rank_real_candidate_pairs()
        targets = ranked[:limit]
        logger.info("refresh: building real context for %d candidates", len(targets))
        pairs = [build_pair_with_context(r) for r in targets]
        logger.info("refresh: running precompute batch")
        result = run_precompute_batch(PATCH, engine=db.engine, pairs=pairs)
        logger.info(
            "refresh: done written=%d skipped=%d already_present=%d",
            len(result["written_pairs"]), len(result["skipped"]), len(result["already_present"]),
        )
    except Exception:
        logger.exception("refresh: failed")
    finally:
        _refresh_running = False


@router.post("/refresh")
def refresh(background_tasks: BackgroundTasks, limit: int = DEFAULT_LIMIT):
    """Kicks off a real, bounded precompute pass over the top `limit` ranked
    real candidate pairs (default 50) in the background. Returns
    immediately -- follow server logs for real stage/row-count progress.
    A refresh already in flight is reported, not double-started."""
    global _refresh_running
    if _refresh_running:
        return {"status": "already_running"}
    _refresh_running = True
    background_tasks.add_task(_run_refresh, limit)
    return {"status": "started", "limit": limit}
