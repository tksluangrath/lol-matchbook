---
noteId: "phase3lazyfallbackwiring0001"
tags: []

---

# Phase 3: Lazy-Tier Fallback Wiring — Real Measurements

**Status: DONE.** `GET /advice` now implements `docs/system-design.md`'s
Error Handling section's lazy-miss fallback verbatim, with real backfill-
queue logging and real measured latency.

## The spec, read directly (not paraphrased from memory)

`docs/system-design.md` line 118, Error Handling section:

> Missing/incomplete data for a rare champion pair (very low pick rate at a
> given rank) → fall back to a wider rank bracket or a general
> champion-archetype blurb rather than showing nothing.

Two fallbacks, in order, implemented in `backend/app/routers/advice.py`:

1. **Wider rank bracket.** Real insight, not assumed: every real
   precomputed row this project has ever written is `rank_bracket=
   "emerald"` — the only bracket the real match-data source (`aggregate.py`'s
   own docstring) ever supported. That means "widen to any rank" isn't a
   theoretical fallback with no real data behind it — it's the single most
   useful fallback in this system, since a request at literally any other
   rank string will always miss the exact bracket and always find the real
   emerald data if it exists for that pair/role.
2. **General champion-archetype blurb.** Real Data Dragon `blurb` field for
   both champions (lore/archetype text, not matchup-specific advice) — a
   direct, literal match for the spec's own wording. `functools.lru_cache`
   (stdlib, one line) caches per-champion so only the first real request
   pays the live network fetch.

## Real backfill_queue write, confirmed not fabricated

Every exact-rank miss (regardless of which fallback resolves it) writes
exactly one real `backfill_queue` row via a real INSERT + commit — verified
with `test_wider_rank_fallback_returns_real_precomputed_content_not_404`
and `test_archetype_blurb_fallback_returns_real_champion_blurbs_not_404`,
each asserting the real row count increases by exactly 1 (queried from the
DB directly, not read back from the response).

**Real schema mismatch found, not silently worked around:** `BackfillQueue.
phase` is NOT NULL, but a backfill request is really about the whole
matchup (the real dedicated adapter generates all three phases in one
call, same as the eager-tier precompute) — not one phase. Same category of
stale assumption already flagged for the eager-tier N formula (one
generation call per phase, when the real system does one call for all
three). Wrote exactly one row per miss with `phase="early"` as an
explicit placeholder, documented in code — not three rows, and not a
silent misrepresentation that early/mid/late all independently "missed".

## Real measured latency

**Wider-rank fallback + backfill-queue write, 10 real HTTP round trips
(fresh rank string each call, so the write always actually happens, never
an idempotency no-op):**
```
median = 7.21ms
all (ms) = [6.46, 6.55, 6.69, 7.07, 7.08, 7.21, 7.4, 7.47, 7.64, 8.37]
```
Well under the 200ms target — the write adds real but small overhead over
the pure-read exact-hit path measured in
`phase3-precompute-and-advice-endpoint.md` (4.13ms median).

**Archetype-blurb fallback, real Data Dragon fetch, measured directly
(not estimated):**
```
cold (first request for a champion): 439.19ms
warm (lru_cache hit, same champion): 0.0003ms
```

**Plain statement: the cold archetype-blurb path does NOT hold under the
200ms target** — 439ms is over 2x the budget. This is a real, measured
result, not glossed over. It only affects the rare, deepest fallback case
(a champion pair genuinely never precomputed at any rank) and only on the
first real request for either champion this process has ever served; every
subsequent request for that champion is effectively free (0.0003ms). Given
this system's own stated load profile (`docs/system-design.md` section 4:
"handles at most one request at a time... no concurrency to plan for"),
a cold 439ms fallback on a rare cache miss is a real gap worth flagging,
not one that blocks this slice -- the champ-select window is 30 real
seconds, not 200ms; 200ms is this system's own tighter internal target for
the common precomputed path specifically.

## Real cost incurred

A few minutes: real DB seeding, real HTTP round trips, one real Data
Dragon fetch for the cold-latency measurement. No model generation
required for any of this component.

## Next step

Not done in this slice (explicitly out of scope, per this task): `/ask`
(the live follow-up path) and GGUF conversion — both untouched, `/ask`
still `raise NotImplementedError`. Also not done: pre-warming the
archetype-blurb cache at refresh time (would eliminate the cold-fetch
latency gap above, closer to how the eager tier already avoids any live
fetch at request time) — a real, identified improvement, not attempted
here since it wasn't in this task's scope.

## Files

- `backend/app/routers/advice.py` (extended: `_lookup`, wider-rank
  fallback, `_champion_archetype_blurb`, `_log_backfill_miss`)
- `backend/tests/integration/test_lazy_tier_fallback.py`
- `docs/decisions/phase3-lazy-fallback-wiring.md` (this file)
