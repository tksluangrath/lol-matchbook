# Tiered precompute fallback — design

**Status:** Proposed
**Context:** `docs/architecture-evaluation.md` recommendation 4 names a tiered fallback ("eagerly precompute high-play-rate pairs, lazily generate-and-cache rare ones on first request") in one sentence, without resolving how it interacts with ADR-001's core "precompute, don't generate live" decision. `docs/decisions/phase0-precompute-benchmark.md` measured real throughput (3.36 tok/s, Apple Silicon MPS — not yet re-measured on the target 4090). At the time this doc was first written, the full same-lane set was estimated at 2,500–3,000 pairs (~40–48 days at that rate). `docs/decisions/phase1-role-pair-count.md` then replaced that estimate with an exact count at a >5% role-viability threshold — 9,204 pairs — which a follow-up plausibility check (`docs/decisions/phase1-role-threshold-sensitivity.md`) found too permissive (it counted implausible roles, e.g. mid/support Gragas off a 7-8% appearance share, as "viable"). **>10% is the threshold that passed the plausibility check and is now current: 6,500 same-lane pairs** — which at the same measured throughput is **~2,501–3,786 hours (~104–158 days)**, not 40–48. This doc resolves the open gaps and makes the shape concrete enough to build against in Phase 3. It does not modify any code or schema — design only, same as the Phase 0 decision docs.

**UPDATE — data-quality fix combined with the threshold fix:** `docs/decisions/phase1-role-pair-count-corrected.md` found the source dataset behind the 6,500/9,204 figures above was not filtered to ranked solo/duo and contained ~37% duplicate rows. `docs/decisions/phase1-final-pair-count.md` combined that fix with the >10% threshold (with sanity checks reproducing both single-fix figures exactly) and landed on **6,512 same-lane pairs** — nearly identical to 6,500, the data-quality bug turns out to barely move the threshold-10% figure even though it removes 63% of the raw rows. **6,512 is now the current same-lane pair count**, superseding 6,500 everywhere below; the qualitative conclusions (tiered fallback required, eager tier is a small fraction of same-lane) are unchanged since 6,512 ≈ 6,500.

## The two tiers

- **Eager tier:** champion pairs (same-lane, per `docs/decisions/phase0-role-scoping.md`) × rank bracket × phase, precomputed synchronously during `/refresh`, same as the current full-precompute design. Served purely by DB lookup, `<200ms`, no GPU — unchanged from `docs/system-design.md`.
- **Lazy tier:** everything else. No row exists until first requested. A request for a lazy-tier pair never blocks on live generation — see "serving a lazy-tier miss" below.

## Where the eager/lazy line is drawn

The threshold is play-rate-based, not a fixed pair list — a pair's tier is a *label recomputed every refresh*, not a permanent assignment. Mechanism:

1. During the match-pull stage of `/refresh` (`docs/build-plan.md` Phase 1), the aggregation pipeline already computes a sample-size/game-count per `(champ_a, champ_b, rank, phase)` row — this is required anyway for the abstention/thin-data path (`docs/system-design.md` §6, "Abstention / low-confidence handling").
2. Rank up all same-lane pairs by total game count across rank brackets (a pair's overall play volume, not per-rank — a pair can be common overall but thin at one rank bracket, which is a separate, already-designed abstention case).
3. Eager tier = the top-N pairs by play volume, where **N is chosen each refresh to fit the time budget**, not fixed in advance: `N = floor(refresh_time_budget_seconds × measured_tokens_per_second / (4 rank_brackets × 3 phases × avg_tokens_per_blurb))`, using the same formula and measured inputs as `docs/decisions/phase0-precompute-benchmark.md`, re-measured on the actual serving hardware before this ships. Everything outside the top-N is lazy tier.
4. `refresh_time_budget_seconds` is a config value, not hardcoded — operator sets it based on how long they're willing to let `/refresh` run between sessions (e.g., a few hours, run overnight). This makes the eager/lazy split self-adjusting to whatever throughput the actual hardware delivers, rather than needing a hand-picked pair-count cutoff that goes stale as the model or hardware changes.

This can't be finalized with an exact N until Phase 1's real pick-rate distribution exists — that's expected and fine; the mechanism above is what Phase 3 implements, not a specific number decided now. What *is* known now (per `docs/decisions/phase1-role-pair-count.md`, `docs/decisions/phase1-role-threshold-sensitivity.md`, and `docs/decisions/phase1-final-pair-count.md`) is the denominator N is drawn from: **6,512 same-lane pairs** (>10% role-viability threshold on ranked-only, deduplicated data — recommended after a plausibility check ruled out both the original 2,500–3,000 estimate and an intermediate 9,204/9,177 figure computed at a too-permissive 5% threshold, then combined with a data-quality fix that turned out to barely move the number, 6,500→6,512) — meaning N will end up being a fraction of the full same-lane set, not most of it, once a realistic `refresh_time_budget_seconds` is applied.

## Serving a lazy-tier miss

This is the part recommendation 4 left unresolved, and it's the part that matters most because it's the only place this design touches the live champ-select path.

**On a lazy-tier cache miss, `GET /advice` never generates live.** It does exactly what `docs/system-design.md`'s existing error-handling section (line 118) already specifies for missing/incomplete data: falls back to a wider rank bracket, or a general champion-archetype blurb, served from the same DB read path, still `<200ms`, still no GPU. This reuses an already-designed fallback rather than inventing a new one.

Separately, and off the request's critical path, the miss is logged to a **backfill queue** (a simple table: `champ_a, champ_b, rank, phase, requested_at`). This queue is drained by a background job — not during the request, not during a live match — using the **CPU-quantized `llama-cpp-python` path already built for the live follow-up path** (`docs/tech-stack.md` §5), not the GPU batch-precompute tool. Two reasons to reuse that path specifically rather than the GPU tool:
- It's already required to be safe to run without contending with the game (that's its entire design premise).
- Backfill is inherently a trickle (whatever pairs got asked about), not a batch job — the GPU batching tool's throughput advantage doesn't apply at this volume, so there's no benefit to paying its GPU-contention cost.

The backfill job runs whenever the app is running and the game isn't in an active match (same "not during gameplay" rule as `/refresh` — `docs/adr-001-architecture.md`'s Consequences section). Once generated, a lazy-tier row is written to the same `advice` table as eager-tier rows, indistinguishable to the serving path — the tier is a generation-strategy detail, not a schema-level distinction the API cares about.

## Refresh-cycle interaction

Neither "wipe lazy cache every refresh" nor "never touch it" is correct on its own — both were flagged as unresolved in the review. The actual behavior:

- **Eager tier**, on every `/refresh`: regenerated in full, as today.
- **Lazy tier**, on every `/refresh`: **not regenerated**, but **re-evaluated for promotion**. If a previously-lazy pair's play volume now places it in the new top-N (tier recompute, above), it moves to the eager tier and gets a fresh row as part of that refresh's normal batch. If it stays outside top-N, its existing cached row (if any) is left in place and simply ages — same accepted staleness as everything else between refreshes, no different from an eager-tier blurb that's one refresh cycle old.
- A lazy-tier row's `generated_at` / source patch version is stored alongside it (fact-grounding log, `docs/system-design.md` §6) so a visibly stale lazy blurb can be identified and is a candidate for backfill-queue re-entry on its next request, rather than being trusted indefinitely.

This means the backfill queue effectively also catches "this lazy pair fell far enough behind the current patch that it's worth regenerating" — a request for a stale lazy-tier row can re-enqueue it even if a row already exists, using the same age check as the style/output audit.

## Schema implications

No schema change is being made in this doc (per its own scope), but for whoever implements Phase 1/3:
- `advice` needs a `tier` or `source` marker (`eager` | `lazy`) and a `generated_at` timestamp — both cheap columns, needed for the promotion/staleness logic above, not for the serving path itself (serving reads are tier-agnostic, per above).
- A new small table for the backfill queue (`champ_a, champ_b, rank, phase, requested_at, status`) — not part of `matchup_stats` or `advice`, since it's a work queue, not stats or advice content.

## What this resolves from the original review

1. **No live generation during champ select, ever** — lazy-tier misses fall back to existing archetype/wider-bracket logic, matching ADR-001's hard constraint, not violating it.
2. **Backfill uses the CPU path**, not the GPU batch tool — no new GPU-contention risk introduced by this design.
3. **Threshold is a formula tied to measured throughput and an operator-set time budget**, not a guessed pair count — self-adjusting as the real 4090 benchmark replaces the MPS placeholder numbers.
4. **Refresh-cycle behavior is explicit**: eager regenerates fully every cycle, lazy only promotes/ages, with a staleness-triggered re-enqueue path.
5. **Sizing is honest about the measured numbers**: this design assumes the eager tier is a fraction of same-lane pairs sized to what the refresh time budget actually allows — not "most pairs, minus a few rare ones," which is ruled out more firmly than at the time of the original review: the same-lane set is an exact **6,512** pairs at the recommended >10% role-viability threshold on corrected (ranked-only, deduplicated) data (`phase1-role-pair-count.md`, `phase1-role-threshold-sensitivity.md`, `phase1-final-pair-count.md`), not the 2,500–3,000 estimate this recommendation was originally sized against, not the intermediate 9,204/9,177 figures from a too-permissive 5% threshold, and barely different from the pre-data-fix 6,500 figure — and at measured MPS throughput the full same-lane set alone runs **~104 days**, not 40–48.

## Open items for Phase 1/3 (not decided here)

- Real `measured_tokens_per_second` and `avg_tokens_per_blurb` on the actual 4090 (Phase 0's number is MPS, explicitly flagged as non-representative in `docs/decisions/phase0-precompute-benchmark.md`).
- Real pick-rate distribution across same-lane pairs, to know what N actually looks like once Phase 1's pipeline runs.
- How aggressively to set `refresh_time_budget_seconds` — a product decision (how long the user is willing to let a refresh run), not an engineering one.
