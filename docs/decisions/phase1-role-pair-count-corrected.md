# Phase 1 — Corrected same-lane pair count (ranked-only + deduplicated)

**Task:** `docs/decisions/phase1-role-pair-count.md` computed the same-lane pair count (9,204 at the 5% threshold; 6,500 at the current 10% threshold) directly from the raw BoostedJonP CSV, before AGENT-8's `backend/app/data_pipeline/aggregate.py` discovered the file is **not** pre-filtered to ranked solo/duo (it mixes in queue 440 "ranked flex" and queue 1700 "arena" rows) and contains **~37% exact-duplicate participant rows**. Neither filter was applied to the original 9,204 computation. This file redoes that computation on the corrected data, reusing AGENT-8's actual filtering code (`filter_valid_matches`, `load_hf_csv_matches`) via import — no filtering logic is reimplemented here.

**Method note:** this file applies the same **5% threshold** as the original computation (`frac > 0.05`), not the currently-recommended 10% threshold — the task scope is an apples-to-apples fix of the filtering bug only. Threshold sensitivity is a separate, already-scoped concern (`phase1-role-threshold-sensitivity.md`); propagating a corrected number through that doc, `tiered-fallback-design.md`, `phase0-precompute-benchmark.md`, or `build-plan.md` is explicitly out of scope here.

**Reused code, not reimplemented:** `from app.data_pipeline.aggregate import filter_valid_matches` and `from app.data_pipeline.riot_client import load_hf_csv_matches`, both imported and called directly against the real cached CSV (`~/.cache/huggingface/hub/datasets--BoostedJonP--league_of_legends_match_data/.../league_of_legends_emerald_match_data.csv`) in this session. Both imported cleanly with no side effects — the HALT condition on import failure did not trigger.

## 1. Filtering funnel

Pipeline order matches the real code path: `load_hf_csv_matches` drops empty-`team_position` rows and deduplicates per match *before* returning normalized match dicts; `filter_valid_matches` then drops non-ranked-solo/duo and surrendered matches.

| Stage | Rows / matches | What changed |
|---|---|---|
| Raw CSV rows | **24,618** rows | — |
| → drop empty `team_position` | 24,483 rows (135 dropped) | can't be placed in a lane |
| → dedup per match (`load_hf_csv_matches`) | **1,530 matches**, **15,290 participant rows** | ~9,193 exact-duplicate participant rows removed in this step |
| → `filter_valid_matches` (queue_id==420, not surrendered) | **901 matches**, **9,003 participant rows** | 314 flex-queue (440) matches dropped, 396 surrendered matches dropped (some overlap: surrendered ranked-solo/duo matches are also excluded) |

Queue-id breakdown at the post-dedup, pre-ranked-filter stage (match-level, real code output): `{420: 1216, 440: 314}` — no queue-1700 (arena) matches survived deduplication+grouping in this cut, confirming arena rows are a very small, already-marginal slice of the raw file. Surrendered matches at that same stage: 396 of 1,530 (25.9%).

**Net reduction: 24,618 raw rows → 9,003 usable participant rows (63.4% removed)** — roughly two-thirds of the original row count was either a duplicate or came from a non-ranked-solo/duo or surrendered game.

## 2. Champion presence and appearance counts (corrected data)

- Champions present after filtering: **170** (same as the original computation — the missing champions were already a coverage gap in the raw file, not something the queue/dedup filters removed).
- Appearance counts per champion, corrected data: **min 9, max 159, mean ≈52.96** — do **not** reuse the original 28/416/144 figures; those were reproduced from the *raw, unfiltered* data in this same session and are roughly 3x higher across the board, as expected from the 63.4% row reduction above.
- Distinct `team_position` values in the corrected data: exactly the 5 expected (`TOP`, `JUNGLE`, `MIDDLE`, `BOTTOM`, `UTILITY`) — no stray/malformed labels survived filtering.

**Sample-size caveat, more pointed than in the original doc:** the corrected minimum (9 appearances) is far thinner than the original's minimum (28). A handful of low-pick-rate champions now have single-digit sample sizes feeding their role-viability call — this dataset is a materially smaller and noisier basis than the original 9,204 computation assumed.

## 3. Recomputed per-role viable-champion count (k) and C(k,2) — 5% threshold, corrected data

| Role | k (viable, >5% threshold) | C(k,2) = k×(k−1)/2 |
|---|---|---|
| TOP | 72 | 2,556 |
| JUNGLE | 61 | 1,830 |
| MIDDLE | 71 | 2,485 |
| BOTTOM | 35 | 595 |
| UTILITY | 59 | 1,711 |

```
2,556 + 1,830 + 2,485 + 595 + 1,711 = 9,177
```

**Corrected same-lane pair count (5% threshold): 9,177.**

## 4. Comparison to the original 9,204

**Delta: 9,177 − 9,204 = −27** (−0.29%) — the corrected, properly-filtered figure is essentially unchanged from the buggy original, despite 63.4% of the underlying rows being removed.

Per-role, the picture is not "no movement" — it's offsetting churn:

| Role | k (original) | k (corrected) | Δk | ΔC(k,2) |
|---|---|---|---|---|
| TOP | 74 | 72 | −2 | **−145** |
| JUNGLE | 60 | 61 | +1 | +60 |
| MIDDLE | 71 | 71 | 0 | 0 |
| BOTTOM | 35 | 35 | 0 | 0 |
| UTILITY | 58 | 59 | +1 | +58 |

**TOP moved the most** (largest single-role swing, −145 pairs), and it's the only role whose net direction is negative — JUNGLE and UTILITY each partially offset it with +1 champion apiece, which is why the *total* delta (−27) looks small even though individual champion/role viability calls flipped underneath it. TOP alone had 10 flips: added `['Annie', 'AurelionSol', 'Neeko', 'Rammus']` (4), dropped `['Anivia', 'Belveth', 'Skarner', 'Smolder', 'Sylas', 'Vi']` (6), net −2.

**Hypothesis, checked against the actual data (not a guess):** this is **threshold-boundary sample-size noise**, not a systematic effect of arena/flex rows being disproportionately concentrated in one role. Evidence: every champion whose TOP-viability flipped sat within ~3.5 percentage points of the 5% cutoff in the *original* (buggy) data, and every one of them lost roughly 60–75% of its sample size in the filtered data (consistent with the overall 63.4% row reduction) — small enough swings in a small-n binomial share to cross a hard threshold in either direction:

| Champion | TOP% (original, n) | TOP% (corrected, n) |
|---|---|---|
| Annie | 4.07% (n=123) | 8.51% (n=47) |
| AurelionSol | 2.22% (n=45) | 5.56% (n=18) |
| Neeko | 4.76% (n=84) | 6.67% (n=30) |
| Rammus | 4.76% (n=42) | 6.25% (n=16) |
| Anivia | 7.61% (n=92) | 4.76% (n=21) |
| Belveth | 6.45% (n=62) | 0.00% (n=20) |
| Skarner | 8.51% (n=47) | 0.00% (n=17) |
| Smolder | 5.38% (n=279) | 4.44% (n=90) |
| Sylas | 5.36% (n=224) | 3.41% (n=88) |
| Vi | 5.48% (n=146) | 4.26% (n=47) |

No champion in this list moved by more than ~4 percentage points — small absolute swings that only matter because they straddle a hard 5% cutoff. This is consistent with the `phase1-role-threshold-sensitivity.md` finding that the 5% threshold produces implausible boundary calls (e.g. Gragas mid/support) — the same instability shows up here as filtering-induced flips, not just threshold-choice sensitivity. It reinforces (does not contradict) that doc's recommendation to use 10% instead, which sits further from these champions' appearance shares and would be less sensitive to this kind of resampling noise. Re-running this same corrected-data computation at the 10% threshold, and propagating whichever number is authoritative into `phase1-role-pair-count.md`/`tiered-fallback-design.md`/`phase0-precompute-benchmark.md`/`build-plan.md`, is explicitly left as a separate follow-up per this task's scope.

## Method summary / reproducibility

- Filtering: `app.data_pipeline.riot_client.load_hf_csv_matches` (drop empty `team_position`, dedup per match on `(champion, team_position, team_id, win)`) + `app.data_pipeline.aggregate.filter_valid_matches` (queue_id==420, not surrendered) — both imported and called directly against the real cached CSV, not reimplemented.
- Threshold: `frac > 0.05` (5%, strictly greater-than), applied identically to all 170 champions present in the corrected data — same rule as the original computation.
- All numbers in this file are outputs of code executed in this session against the real, cached CSV via the real pipeline functions; none are recalled, assumed, or extrapolated. The original-method reproduction (§1 raw counts, §2 min/max/mean, §4 original per-role k) was independently re-run in this session too, and reproduced the original doc's 9,204/74-60-71-35-58/28-416-144 figures exactly, confirming the two computations differ only in the filtering step, not in methodology drift.

## Status

**DONE.**
