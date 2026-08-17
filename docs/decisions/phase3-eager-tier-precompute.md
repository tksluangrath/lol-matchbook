---
noteId: "phase3eagertierprecompute0001"
tags: []

---

# Phase 3: Eager-Tier Scale-Up — Real Candidate Pool, Real Throughput, Real N

**Status: IN PROGRESS.** Real numbers measured, real top-109 run launched
detached. This doc will be updated with final written/skipped counts once
the ~8-hour run completes.

## The formula, corrected for how the system actually works

`docs/decisions/tiered-fallback-design.md`'s original eager/lazy formula
assumed one generation call per (pair, rank, phase) across 4 rank
brackets. Neither assumption survived contact with the real built system:

- The dedicated qualitative adapter (`smoke-adapter-qualitative-
  dedicated-v2/`) generates all three phases in a single real call —
  confirmed in every precompute run this project has done, starting with
  the original 10-pair slice.
- The real match-data source only ever supports one real rank bracket
  (`"emerald"` — `aggregate.py`'s own docstring, unchanged since Phase 1).

Corrected formula used here:
```
N = floor(refresh_time_budget_seconds / real_measured_seconds_per_pair)
```
No phase multiplier, no rank-bracket multiplier.

## Real data-backed candidate pool: 2,602, not 6,512

6,512 is the theoretical ceiling of legitimate same-lane role pairings
(which pairs are *allowed* to exist) — not a count of pairs anyone
actually played. Ran the real aggregation pipeline
(`app.data_pipeline.riot_client.load_hf_csv_matches` +
`aggregate.filter_valid_matches` + `aggregate.aggregate_matchup_stats`,
all reused unmodified) against the real cached HF match CSV this session:

```
raw matches loaded: 1530
valid ranked solo/duo matches: 901
real data-backed (champ_a, champ_b, role) pairs: 2602
theoretical ceiling: 6512
```

Real top 5 by observed game count (the ranking signal used below):
```
Milio/Nami (utility): 20 games
Ezreal/Jhin (bottom): 15 games
Jhin/Kaisa (bottom): 14 games
Ezreal/Jinx (bottom): 13 games
Jhin/Lucian (bottom): 11 games
```
1,631 of the 2,602 real pairs have `sample_size == 1` — this is genuinely
sparse data; the top of the ranking (20 games) is itself thin by normal
statistical standards, a real characteristic of this dataset worth naming
plainly rather than treating the ranking as more authoritative than it is.

Verified with `backend/tests/unit/test_eager_tier_ranking.py` (4 tests,
hand-computed expected values from an independent real run of the same
pipeline, not derived from the function under test).

## Real measured throughput: 263.87 sec/pair — not the ~66 sec/pair estimate

The task's own starting estimate (~66 sec/pair, from the earlier 10-pair
persistent-DB run's ~11 real minutes) was explicitly flagged as unreliable
and requiring a fresh measurement. It was right to distrust it: a fresh,
precise 5-pair timing sample (new real candidates, not the original
10-pair set, model load time measured and excluded separately) came back
**4x slower**:

```
MODEL_LOAD_SECONDS=18.30
Milio/Nami: 232.44s
Ezreal/Jhin: 280.80s
Jhin/Kaisa: 308.15s
Ezreal/Jinx: 267.74s
Jhin/Lucian: 230.21s
avg_seconds_per_pair=263.87
```

This is consistent with a pattern already established elsewhere in this
project: real CPU generation throughput on this machine has varied
4-10x across otherwise-identical runs all session (documented in the
two-adapter diagnostic's repeated eval reruns and the earlier precompute
runs' 11-minute vs. 47-minute results for the same 10-pair workload). Not
investigated further here — the fix is measuring fresh each time, not
trusting a stale number, which is exactly what this step did.

## Computed N: 109, not the illustrative ~403

```
N = floor(28800 / 263.87) = 109
projected wall-clock = 109 * 263.87s ≈ 28,762s ≈ 7h59m
```

Neither halt condition triggered: 109 is well above the "implausibly
small" floor of 20, and well below the 2,602-pair real candidate pool (not
"implausibly large" relative to it). Proceeded per the task's own
instructions rather than pausing to confirm a number the halt conditions
were explicitly designed to allow through.

## Real top-109 run: launched detached

`backend/app/data_pipeline/run_eager_tier_topn.py` (new file — ranks real
candidates and builds real context via
`precompute.build_pair_with_context`, then calls
`precompute.run_precompute_batch` **unmodified**, reusing its existing
generation/grounding-check/section-split/idempotency logic exactly as
instructed, not rewriting it):

```
$ nohup python3 -u -m app.data_pipeline.run_eager_tier_topn &
N=109 (budget=28800s / 263.87s/pair)
building real context for top 109 candidates (real Data Dragon fetches)...
```

### First launch crashed on a real, root-caused data bug — not retried blind

First attempt died mid context-build:
```
requests.exceptions.HTTPError: 403 Client Error: Forbidden for url:
https://ddragon.leagueoflegends.com/cdn/16.15.1/data/en_US/champion/FiddleSticks.json
```
Real root cause, verified against the live Data Dragon champion list, not
assumed: the real match-data CSV's champion name for this champion is
`"FiddleSticks"` (capital S), but Data Dragon's real key is
`"Fiddlesticks"` (lowercase s) — a real Riot API casing inconsistency, not
a typo in this project's own code. Checked for a reusable fix already in
the codebase first (`data_dragon.py`'s existing variant-dedup logic) — it
solves a different problem (mode-variant collisions like `Jade_Ahri`), not
this one. Verified no lowercase collisions exist across all 233 real
`champion.json` keys, so added a small case-insensitive resolver
(`qualitative_advice.resolve_champ_key`, `functools.lru_cache`-cached) at
the one shared function every caller already routes through
(`fetch_champion_detail`) — a root-cause fix, not a patch for this one
champion. Verified against the real failing case
(`fetch_champion_detail('FiddleSticks')` now returns Fiddlesticks' real
4-spell kit) before relaunching. No real precompute writes had happened
yet when it crashed (died during context-building, before
`run_precompute_batch` was ever called), so nothing to resume from --
relaunched clean.

Second launch (PID 23332): context-building succeeded (all 218 real
fetches), model loaded, generation running. Persistent monitor watching
for completion.

**[Placeholder — updated when the run completes]:**

```
written=?  skipped=?  already_present=?
wall_clock_s=?
```

## Idempotency

Reuses `run_precompute_batch`'s existing pre-generation existence check
and `ON CONFLICT DO NOTHING` writes, unmodified — the same idempotency
behavior already proven real in
`docs/decisions/phase3-precompute-and-advice-endpoint.md`'s rerun test.
**[Placeholder — a rerun check against the completed top-109 run will be
added here once it finishes.]**

## Next step

Not done in this slice (explicitly out of scope, per this task): `/ask`
(the live follow-up path) and GGUF conversion — both untouched.

## Files

- `backend/app/data_pipeline/precompute.py` (extended: `rank_real_
  candidate_pairs`, `build_pair_with_context`)
- `backend/app/data_pipeline/run_eager_tier_topn.py` (new launcher)
- `backend/tests/unit/test_eager_tier_ranking.py`
- `docs/decisions/phase3-eager-tier-precompute.md` (this file)
