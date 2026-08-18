"""
Launcher for the real sampling-retry regeneration: forces real regeneration
(via force_regenerate_pairs(sampling_retry=True)) for exactly the top-109
candidate pairs that still have no Advice row in the live DB after the
ability-whitelist retry (docs/decisions/phase3-ability-whitelist-retry.md's
7 remaining skips). Re-derives the real skip pool from the live DB right
before running, same pattern as run_ability_whitelist_retry.py -- not
hardcoded, in case anything's changed since that doc was written.
"""
import json
import time

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.data_pipeline.precompute import force_regenerate_pairs, rank_real_candidate_pairs
from app.db_migrate import migrate
from app.models import Advice

PATCH = "16.15.1"
TOP_N = 109

if __name__ == "__main__":
    server, engine = migrate()
    try:
        session = sessionmaker(bind=engine)()
        ranked = rank_real_candidate_pairs()[:TOP_N]
        written_keys = {
            (a, b, r) for a, b, r in session.execute(
                select(Advice.champ_a, Advice.champ_b, Advice.role).distinct()
            ).all()
        }
        session.close()
        targets = [
            (row["champ_a"], row["champ_b"], row["role"]) for row in ranked
            if (row["champ_a"], row["champ_b"], row["role"]) not in written_keys
        ]
        print(f"real current skip pool: {len(targets)} pairs")
        print(json.dumps(targets, indent=2))

        t0 = time.time()
        result = force_regenerate_pairs(PATCH, targets, engine=engine, sampling_retry=True)
        t1 = time.time()
        print(json.dumps({
            "written": len(result["written_pairs"]),
            "skipped": [{"champ_a": s.get("champ_a"), "champ_b": s.get("champ_b"), "role": s.get("role"),
                         "reason": s.get("reason"), "invented_phrases": s.get("invented_phrases")}
                        for s in result["skipped"]],
        }, indent=2, default=str))
        print(f"SAMPLING_RETRY_DONE wall_clock_s={t1 - t0:.1f} "
              f"written={len(result['written_pairs'])} skipped={len(result['skipped'])}")
    finally:
        engine.dispose()
        server.cleanup()
