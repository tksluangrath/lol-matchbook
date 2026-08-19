"""
Launcher for expanding real eager-tier coverage beyond the original top-109
run, per a 12-hour budget the user chose when asked. Reuses
run_precompute_batch unmodified (generation, grounding-check, section-
split, idempotency) -- same real formula as run_eager_tier_topn.py:

    N = floor(refresh_time_budget_seconds / real_measured_seconds_per_pair)

MEASURED_SECONDS_PER_PAIR is a fresh real measurement taken this session
(5-pair real timing sample against the actual next-in-line uncovered
candidates, not a reused stale number -- this project's own established
rule, since real throughput has varied 4-10x across sessions).

Targets ranked[:N] (not just the newly-uncovered slice): run_precompute_
batch's own idempotency check (ON CONFLICT DO NOTHING + pre-generation
existence check) skips the already-covered 123 pairs as fast DB reads, so
this is safe and simple -- no separate exclusion logic needed.
"""
import json
import time

from app.data_pipeline.precompute import build_pair_with_context, rank_real_candidate_pairs, run_precompute_batch
from app.db_migrate import migrate

PATCH = "16.15.1"
REFRESH_BUDGET_SECONDS = 43200  # 12 hours, user-chosen
MEASURED_SECONDS_PER_PAIR = 219.74  # real, fresh 5-pair timing sample this session
N = REFRESH_BUDGET_SECONDS // MEASURED_SECONDS_PER_PAIR  # floor division

if __name__ == "__main__":
    n = int(N)
    print(f"N={n} (budget={REFRESH_BUDGET_SECONDS}s / {MEASURED_SECONDS_PER_PAIR}s/pair)")

    ranked = rank_real_candidate_pairs()
    top_n_stats = ranked[:n]
    print(f"building real context for top {len(top_n_stats)} candidates (real Data Dragon fetches)...")
    pairs = [build_pair_with_context(r) for r in top_n_stats]
    print("done building context")

    server, engine = migrate()
    try:
        t0 = time.time()
        result = run_precompute_batch(PATCH, engine=engine, pairs=pairs)
        t1 = time.time()
        print(json.dumps({
            "written": len(result["written_pairs"]), "skipped": len(result["skipped"]),
            "already_present": len(result["already_present"]),
        }, indent=2))
        print(f"EAGER_TIER_EXPAND_12H_DONE wall_clock_s={t1 - t0:.1f} written={len(result['written_pairs'])} "
              f"skipped={len(result['skipped'])} already_present={len(result['already_present'])}")
    finally:
        engine.dispose()
        server.cleanup()
