# Phase 1 — role-viability threshold sensitivity

**Task:** is the 5% role-viability threshold used in `phase1-role-pair-count.md` the right bar, or was it picked without checking sensitivity? This measures the same-lane pair count at 5/10/15/20% and spot-checks plausibility, then makes an explicit recommendation. This file does not change any existing count — see "Out of scope" at the end.

## Method (identical to phase1-role-pair-count.md §2-4)

Source: `BoostedJonP/league_of_legends_match_data` (already cached locally, no re-download needed), `league_of_legends_emerald_match_data.csv`. 24,618 rows, 135 with missing `team_position` dropped → **24,483 usable rows, 170 unique champions** — matches `phase1-role-pair-count.md` exactly, confirming this is the same dataset snapshot.

For each champion, computed the share of its total appearances at each `team_position`. A role is "viable" for a champion if `share > threshold` (strict greater-than, same operator as the original). Per role: k = count of champions with that role viable; C(k,2) = k(k-1)/2; total = sum across the 5 roles, no cross-role dedup — all identical to the original method.

## 1. Sensitivity table

| Threshold | TOP k / C(k,2) | JUNGLE k / C(k,2) | MIDDLE k / C(k,2) | BOTTOM k / C(k,2) | UTILITY k / C(k,2) | **Total same-lane pairs** |
|---|---|---|---|---|---|---|
| **5%** | 74 / 2,701 | 60 / 1,770 | 71 / 2,485 | 35 / 595 | 58 / 1,653 | **9,204** |
| 10% | 58 / 1,653 | 59 / 1,711 | 59 / 1,711 | 30 / 435 | 45 / 990 | **6,500** |
| 15% | 55 / 1,485 | 55 / 1,485 | 54 / 1,431 | 29 / 406 | 42 / 861 | **5,668** |
| 20% | 52 / 1,326 | 48 / 1,128 | 48 / 1,128 | 25 / 300 | 40 / 780 | **4,662** |

**Sanity check: 5% reproduces 9,204 exactly**, matching `phase1-role-pair-count.md` — confirms this is a faithful replication of the original method, not a divergent re-implementation.

**Step-to-step drops:**
| Step | Drop | Relative |
|---|---|---|
| 5%→10% | −2,704 | −29.4% |
| 10%→15% | −832 | −12.8% |
| 15%→20% | −1,006 | −17.7% |

The curve does **not** cleanly flatten into a stable elbow — the 15%→20% relative drop (17.7%) is actually larger than 10%→15% (12.8%), so "where the curve levels off" is not, on its own, a clean signal here. The biggest single drop is 5%→10% by a wide margin, which at least establishes that 5% is capturing meaningfully more borderline picks than 10% does — but the curve shape alone doesn't decide the threshold. The plausibility check below is the deciding factor, as the task anticipated.

## 2. Plausibility spot-check

All 10 requested champions are present in the dataset — no substitutions needed.

**Flex-pick champions** (share % per role, n = total appearances):

| Champion (n) | TOP | JUNGLE | MIDDLE | BOTTOM | UTILITY |
|---|---|---|---|---|---|
| Ashe (177) | 1.7% | 0.0% | 0.0% | 92.7% | 5.6% |
| Pyke (132) | 0.0% | 0.0% | 5.3% | 0.8% | 93.9% |
| Sett (160) | 96.2% | 0.0% | 3.1% | 0.6% | 0.0% |
| Yone (281) | 40.2% | 0.0% | 58.7% | 0.7% | 0.4% |
| Gragas (137) | 64.2% | 21.2% | 7.3% | 1.5% | 5.8% |

**Single-role champions:**

| Champion (n) | TOP | JUNGLE | MIDDLE | BOTTOM | UTILITY |
|---|---|---|---|---|---|
| Jinx (299) | 0.0% | 0.3% | 0.3% | 99.3% | 0.0% |
| Darius (209) | 78.5% | 19.6% | 1.9% | 0.0% | 0.0% |
| Malphite (151) | 84.8% | 0.7% | 11.3% | 0.7% | 2.6% |
| Vayne (256) | 12.1% | 0.0% | 0.4% | 87.5% | 0.0% |
| Karma (178) | 4.5% | 0.0% | 1.1% | 1.1% | 93.3% |

**What each threshold's viable-role set looks like for these 10 champions, and whether it matches what a reasonably informed player would expect:**

- **5%:** Ashe = BOT+UTILITY (correct — Ashe support is a real, recognized pick). Pyke = UTILITY+MID (Pyke mid is real but niche; borderline-correct). Sett = TOP only (3.1% mid doesn't clear 5%; reasonable). Yone = TOP+MID (correct, well-known dual lane). Gragas = **TOP+JUNGLE+MID+UTILITY**, all four (7.3% mid and 5.8% support both barely clear 5%) — this is the problem case: support/mid Gragas at this appearance rate reads as noise (troll picks, autofill, or a handful of one-tricks), not a "known" viable role a reasonably informed player would list. Single-role set: Jinx, Darius (TOP+JUNGLE, correct), Malphite (TOP+MID, correct), Vayne (BOT+TOP, correct), Karma (UTILITY only, correct) all read fine at 5% — **the noise is concentrated in Gragas specifically**, and to a lesser extent Ashe-support sitting close to the cutoff (5.6%, barely above 5%).

- **10%:** Ashe drops to BOT only (5.6% support no longer clears 10%) — loses a real, recognized secondary role; this is a real cost of raising the bar. Pyke drops to UTILITY only (5.3% mid no longer clears) — reasonable, Pyke mid is genuinely niche. Gragas drops to **TOP+JUNGLE** (mid 7.3% and support 5.8% both excluded) — this matches informed-player expectation exactly (top/jungle Gragas are the two commonly recognized roles; mid/support are not). Darius stays TOP+JUNGLE (19.6% clears 10% comfortably — correct, jungle Darius is a real, recognized pick). Malphite stays TOP+MID (11.3% clears — correct, mid Malphite/"one-shot Malphite" is a real, known build). Vayne stays BOT+TOP (12.1% clears — correct, top-lane Vayne is a real, recognized pick, especially in duelist-favorable matchups). **This threshold cleans up the Gragas noise while keeping every other legitimately-recognized secondary role intact** — the best match to informed-player intuition of the four thresholds tested.

- **15%:** Malphite drops to TOP only (11.3% mid no longer clears) and Vayne drops to BOT only (12.1% top no longer clears) — both lose real, recognized secondary roles. Darius still keeps TOP+JUNGLE (19.6% clears 15%). This threshold starts cutting legitimate signal, not just noise.

- **20%:** Darius also drops to TOP only (19.6% falls just short of 20%) — losing jungle Darius, a genuinely recognized pick, not a fringe one. By this point the threshold is cutting real secondary roles across three of the five single-role-champion spot-checks (Malphite, Vayne, Darius all lose a legitimate role between 10% and 20%).

**Result stated plainly:** 5% is too permissive (lets Gragas mid/support in as "viable," which doesn't match informed-player intuition). 15% and 20% are too strict (start excluding genuinely recognized secondary roles for Malphite, Vayne, and eventually Darius). **10% is the only threshold of the four where the viable-role set for all 10 spot-checked champions matches what a reasonably informed player would expect** — it removes the Gragas mid/support noise and Pyke's marginal mid slice, while preserving every other legitimate secondary role (Ashe support is the one loss at 10%, and it's a defensible one — 5.6% appearance is thin even for a "real" pick).

## 3. Recommendation: 10%

Reasoning, combining both parts of the task's own decision criterion:
- **Curve:** 5%→10% is the single largest drop in the sensitivity table (−29.4%), meaning 5% is absorbing a disproportionate share of low-frequency, noisy role assignments relative to the other threshold steps. The curve doesn't cleanly flatten after 10% (15%→20% is actually a bigger relative drop than 10%→15%), so the curve shape alone doesn't uniquely pick 10% — but it does support that 5% is on the noisy side of wherever the real bar is.
- **Plausibility (the deciding factor):** 10% is the only threshold where all 10 spot-checked champions' viable-role sets matched informed-player expectations. 5% over-includes (Gragas 4-role, implausible); 15% and 20% under-include (drop Malphite-mid, Vayne-top, and eventually Darius-jungle, all of which are real recognized picks).

This is not a "middle of the four options, therefore safe" pick — it's the only one of the four that passed the plausibility check outright.

## 4. Final count at the recommended threshold

**Same-lane pairs at 10% threshold: 6,500.**

Compared to the existing 9,204 figure (5% threshold, used throughout `phase1-role-pair-count.md`, `tiered-fallback-design.md`, `phase0-precompute-benchmark.md`, and `build-plan.md` Phase 3): **6,500 is 2,704 pairs lower — a 29.4% reduction.** This is a meaningfully smaller pool for the tiered-fallback design's eager/lazy split to work against (`docs/decisions/tiered-fallback-design.md` §"Where the eager/lazy line is drawn"), though it does not change that design's mechanism — only its input size.

## Out of scope (explicitly not done here)

This file does not edit `phase1-role-pair-count.md`, `tiered-fallback-design.md`, `phase0-precompute-benchmark.md`, `build-plan.md`, or any other existing file, and the 6,500 figure has not been propagated anywhere. That is a separate, later step once this threshold recommendation itself has been reviewed — not assumed here.

## Status: DONE

All four thresholds computed from code run against the real, locally-cached dataset this session (no re-download needed, no recalled figures). 5% threshold reproduced the existing 9,204 exactly as a replication check. Plausibility spot-check run on all 10 requested champions (no substitutions needed). Recommendation and final count stated above.
