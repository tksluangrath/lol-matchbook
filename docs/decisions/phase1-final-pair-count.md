---
noteId: "phase1-final-pair-count"
tags: []
---

# Phase 1 — Final same-lane pair count (data-quality fix + threshold fix, combined)

**Task:** two independent corrections to the original 9,204 same-lane pair count existed but had never been combined: `phase1-role-pair-count-corrected.md` fixed the ranked-only-filter/dedup bug but stayed at the original 5% threshold; `phase1-role-threshold-sensitivity.md` recommended 10% over 5% but tested only on the original, unfiltered data. This file applies both fixes together.

**Reused code, not reimplemented:** `app.data_pipeline.riot_client.load_hf_csv_matches` + `app.data_pipeline.aggregate.filter_valid_matches`, imported and called directly against the real cached CSV (`~/.cache/huggingface/hub/datasets--BoostedJonP--league_of_legends_match_data/.../league_of_legends_emerald_match_data.csv`) in this session — same approach as `phase1-role-pair-count-corrected.md`.

## Funnel (identical to phase1-role-pair-count-corrected.md — same filtering code, same CSV)

| Stage | Rows / matches |
|---|---|
| Raw CSV rows | 24,618 |
| → drop empty `team_position` | 24,483 |
| → dedup per match (`load_hf_csv_matches`) | 1,530 matches / 15,290 participant rows |
| → `filter_valid_matches` (queue_id==420, not surrendered) | 901 matches / **9,003 participant rows** |

Champions present in the corrected data: **170**. Appearance counts: min 9, max 159, mean ≈52.96 (unchanged from `phase1-role-pair-count-corrected.md` — this file adds the 10% threshold on top of the same corrected dataset, it doesn't refilter).

## Step 1 — combined computation: 10% threshold on corrected (ranked-only, deduplicated) data

| Role | k (viable, >10% threshold) | C(k,2) = k×(k−1)/2 |
|---|---|---|
| TOP | 59 | 1,711 |
| JUNGLE | 55 | 1,485 |
| MIDDLE | 60 | 1,770 |
| BOTTOM | 31 | 465 |
| UTILITY | 47 | 1,081 |

```
1,711 + 1,485 + 1,770 + 465 + 1,081 = 6,512
```

**Final same-lane pair count (both fixes applied): 6,512.**

## Sanity checks (both required to pass before propagation)

**Check A — 5% threshold on the corrected data must reproduce 9,177 (`phase1-role-pair-count-corrected.md`):**

| Role | k | C(k,2) |
|---|---|---|
| TOP | 72 | 2,556 |
| JUNGLE | 61 | 1,830 |
| MIDDLE | 71 | 2,485 |
| BOTTOM | 35 | 595 |
| UTILITY | 59 | 1,711 |

Total: 9,177. **Matches 9,177 exactly: PASS.**

**Check B — 10% threshold on the ORIGINAL uncorrected data must reproduce 6,500 (`phase1-role-threshold-sensitivity.md`):**

| Role | k | C(k,2) |
|---|---|---|
| TOP | 58 | 1,653 |
| JUNGLE | 59 | 1,711 |
| MIDDLE | 59 | 1,711 |
| BOTTOM | 30 | 435 |
| UTILITY | 45 | 990 |

Total: 6,500. **Matches 6,500 exactly: PASS.**

Both checks passed — proceeding to propagation (Step 2) is valid per this task's rule.

## Delta decomposition: filtering fix vs. threshold fix (checked, not assumed additive)

Baseline: **9,204** (5% threshold, uncorrected data — the original figure in `phase1-role-pair-count.md`).

| Change applied | Total | Delta vs. 9,204 |
|---|---|---|
| Filtering fix alone (5% threshold, corrected data) | 9,177 | −27 |
| Threshold fix alone (10% threshold, uncorrected data) | 6,500 | −2,704 |
| **Both fixes combined (10% threshold, corrected data)** | **6,512** | **−2,692** |

Naive linear sum of the two individual deltas: −27 + (−2,704) = **−2,731**.
Actual combined delta: **−2,692**.

**The two corrections are not additive** — the combined effect is 39 pairs *less negative* than summing the individual deltas would predict (−2,692 vs. −2,731). In other words, applying the filtering fix on top of the threshold fix removes slightly less than it removes on top of the 5% baseline: some of the champion/role viability flips caused by filtering (see `phase1-role-pair-count-corrected.md`'s TOP-role churn analysis) land on the *other* side of the 10% cutoff than they do at 5%, since 10% is a stricter bar and several of the filtering-induced flips were small (single-digit percentage point) swings that only mattered right at the looser 5% line. The interaction is small relative to either individual effect (39 out of 2,731, ~1.4%) — the threshold change dominates the total move overwhelmingly, and the filtering fix's effect is nearly independent of which threshold it's layered onto, but not perfectly so.

## Method summary / reproducibility

- Filtering: same imported `filter_valid_matches` + `load_hf_csv_matches` as `phase1-role-pair-count-corrected.md`, not reimplemented.
- Threshold: `frac > 0.10` (10%, strictly greater-than) for the combined computation and Check B; `frac > 0.05` for Check A — same rule/operator as both source docs.
- All numbers above are outputs of code executed in this session against the real cached CSV; none are recalled, assumed, or extrapolated. Both sanity checks reproduced their target figures exactly (9,177 and 6,500), confirming this computation is consistent with both prior corrections rather than a third, divergent methodology.

## Status

**DONE.** Both sanity checks passed — Step 2 (propagation) proceeds.
