"""
Offline batch job: generates early/mid/late advice for every matchup combo
using the fine-tuned model + retrieval context, writes to the Advice table.
See docs/system-design.md section 3 ("Precompute vs. on-demand") and
docs/build-plan.md Phase 3.

IMPORTANT (docs/architecture-evaluation.md critical finding): this job needs a
batching-capable generation tool (vLLM / batched transformers), NOT
llama-cpp-python -- that's reserved for the live follow-up path in
app/llm/serve.py, which has the opposite performance profile (single request,
CPU-only, no GPU contention with the game since it runs while gaming).

Phase 0 TODO: before running this at full scale, benchmark real batched
throughput on the target model/hardware and multiply by the actual (role-
scoped) combinatorial count to get a wall-clock estimate. If it's too slow,
implement the tiered fallback (eager precompute for common pairs, lazy
generate-and-cache for rare ones) instead of the naive full precompute below.
"""


def run_precompute_batch(patch: str):
    """
    TODO(Phase 3):
      1. For every (champ_a, champ_b, rank_bracket) in scope, pull the
         MatchupStat rows + retrieval context (patch notes, ability text).
      2. Generate early/mid/late blurbs via the fine-tuned model.
      3. If sample_size is too low, write an abstention row instead of a
         fabricated blurb -- see docs/system-design.md abstention handling.
      4. Log fact_source_id (the MatchupStat row used) with every Advice row
         written, for fact-grounding traceability.
      5. Run the data-balance sanity check and a style/output audit sample
         before this batch is considered "live". See docs/system-design.md
         Testing & Evaluation section.
    """
    raise NotImplementedError
