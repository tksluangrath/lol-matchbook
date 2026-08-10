# Phase 1 — Exact same-lane pair count (replaces the 2,500-3,000 estimate)

**Task:** replace the directional 2,500-3,000 same-lane pair estimate in `docs/decisions/phase0-role-scoping.md` §3(b) with an exact, code-computed count, per that doc's own flagged follow-up (§ "Flagged follow-up").

**UPDATE — threshold revised, count changed:** the >5% role-viability threshold used below was checked for sensitivity in `docs/decisions/phase1-role-threshold-sensitivity.md`, which tested 5/10/15/20% against a plausibility spot-check (10 known champions, do the viable roles at each threshold match what an informed player would expect). 5% passed the sanity-replication check (reproduces 9,204 below) but failed plausibility — it counted implausible roles like mid/support Gragas as "viable" off a 7.3%/5.8% appearance share. **10% was the only threshold where all 10 spot-checked champions' viable-role sets matched informed-player expectations**, and is now the recommended threshold. **Current same-lane pair count: 6,500** (10% threshold), not 9,204. The 5%/9,204 computation below is kept as-is for reproducibility and as the historical record; treat it as superseded, not current.

**UPDATE 2 — data-quality bug found, then combined with the threshold fix:** `docs/decisions/phase1-role-pair-count-corrected.md` found the source dataset used below is *not* pre-filtered to ranked solo/duo as assumed (flex/arena rows are mixed in) and contains ~37% exact-duplicate participant rows — neither was filtered out when 9,204 (or 6,500) was computed. That doc recomputed at the original 5% threshold on corrected data (**9,177**, essentially unchanged from 9,204). `docs/decisions/phase1-final-pair-count.md` then combined *both* fixes — the data-quality correction and the 10% threshold — together for the first time, with two sanity checks (reproducing both 9,177 and 6,500 exactly on their respective single-fix inputs) before propagating. **Current, final same-lane pair count: 6,512** (10% threshold, ranked-only + deduplicated data) — see `phase1-final-pair-count.md` for the full computation, funnel, and a note on why the two fixes are not linearly additive (combined delta −2,692 vs. a naive sum of −2,731). 6,500 (10% threshold, uncorrected data) and 9,204/9,177 (5% threshold) are all now superseded by 6,512; kept below for reproducibility and historical record.

## 1. Champion count (n) — real JSON parser, not LLM-summarized fetch

Method: `curl` → file → `python3` + `json.load()` (a real parser, run in this session), executed **three times** against the exact same URLs to check for the fetch-inconsistency problem `phase0-role-scoping.md` §1 documented (three different, partly-fabricated counts — 159/214/328 — from an LLM-summarized fetch of this same file in a prior session).

```
curl -s https://ddragon.leagueoflegends.com/api/versions.json | python3 -c "import json,sys; v=json.load(sys.stdin); print(v[0])"
# -> 16.15.1

for i in 1 2 3; do
  curl -s https://ddragon.leagueoflegends.com/cdn/16.15.1/data/en_US/champion.json -o champion.json
  python3 -c "import json; d=json.load(open('champion.json')); print(len(d['data']))"
done
# -> 233, 233, 233
```

**Raw key count: 233, consistent across all 3 attempts — but this is not the champion count.** Follow-up investigation (same session) found that 60 of the 233 top-level keys are `Jade_*`-prefixed entries — game-mode-specific rebalanced-kit variants of an existing champion, not separate champions. Example: `Jade_Ahri` has `key: "60103"` (`60000 + 103`, Ahri's real numeric key), the same `name: "Ahri"`, the same stats block shape, and a `blurb` describing kit deltas ("Essence Theft (P) is stacked on damaging enemies", "Spirit Rush (R) doesn't reset") rather than lore text. Verified via:

```
python3 -c "
import json
d = json.load(open('champion.json'))
jade = [k for k in d['data'] if k.startswith('Jade_')]
print(len(jade))          # -> 60
print(233 - len(jade))    # -> 173
"
```

**Corrected result: n = 173 unique champions** (233 raw keys − 60 `Jade_*` mode-variant duplicates). This *matches* the wiki-prose count in `phase0-role-scoping.md` §1 exactly — that count was correct; the 233 figure originally reported here was the error, from counting mode variants as distinct champions rather than deduping/filtering on `id` not starting with `Jade_` (or equivalently, deduping on `name`).

Note: n=173 is used only as context here (all-pairs recompute is out of scope for this file per the file boundary in this task). The same-lane count below is driven entirely by the champions actually present in the role-source dataset (§2), not by n — the Jade_ miscount did not propagate into the pair-count math, since §2's source dataset never contained mode-variant rows in the first place (see §2's 170-vs-173 comparison, now correctly read as "close to the real roster," not "63 short of an inflated one").

## 2. Role assignment — empirical aggregation from match data (not the wiki Lua module)

Per `phase0-role-scoping.md` §2, the wiki's `Module:ChampionData` Lua module was identified as a real source but abandoned because full extraction couldn't be done reliably with the tools available in that session (LLM-summarized fetch risk, same failure mode as the champion.json discrepancy). This phase uses a different source instead: empirical role aggregation over real match data.

**Source:** Hugging Face dataset `BoostedJonP/league_of_legends_match_data`, file `league_of_legends_emerald_match_data.csv`, downloaded via `huggingface_hub.hf_hub_download` (11,664,613 bytes ≈ 11.6MB, under the 500MB resource gate — no confirmation needed).

**Rows:** 24,618 total player-match rows. 135 rows have an empty/missing `team_position` and were dropped (24,483 rows used).

**team_position values found in the data (5, matching the standard 5 roles but with the dataset's own label spelling):** `TOP`, `JUNGLE`, `MIDDLE`, `BOTTOM`, `UTILITY` (Riot's Match-V5 `teamPosition` naming — `UTILITY` = Support, `MIDDLE` = Mid, `BOTTOM` = ADC/Bottom).

**Method:** for each champion, computed the distribution of `team_position` across all its appearance rows in the dataset. A role is counted as "viable" for that champion if that role's share of the champion's total appearances is **> 5%** (threshold applied exactly as `frac > 0.05`, strictly greater-than).

**Sample-size check:** every champion in the dataset has at least 28 total appearances (min 28, max 416, mean ≈144) — no champion's viability call rests on a handful of rows.

**Champions present in this dataset:** 170 unique `champion_name` values — close to, but slightly fewer than, the corrected 173-champion Data Dragon roster (§1; the raw 233 there was a miscount from undeduped `Jade_*` mode-variant entries, not a real gap to compare against). The 3-champion shortfall is expected: the dataset is a fixed historical snapshot of Emerald-rank matches and won't include champions released after its collection date, or any champion with zero picks in the sampled matches. **This 170-champion set, not the full 173-champion roster, is what the pair count below is computed over** — a limitation, stated here, not papered over.

**Emerald-only caveat (stated plainly, not a reason to stop):** this dataset draws exclusively from Emerald-rank matches. The role mix (e.g., how often a flex pick like Ashe shows up Bottom vs. Support) reflects **one rank bracket's** meta, not the full ladder. Role viability — and therefore the pair count below — could differ at other rank tiers (e.g., off-meta picks common in Iron/Bronze, or pro-influenced niche picks in Challenger). This count is exact for the Emerald sample it's computed from; it is not claimed to be rank-invariant.

## 3. Per-role viable-champion count (k) and C(k,2) — at the original 5% threshold (superseded)

| Role (dataset label) | k (viable champions, >5% threshold) | C(k,2) = k×(k-1)/2 |
|---|---|---|
| TOP | 74 | 2,701 |
| JUNGLE | 60 | 1,770 |
| MIDDLE | 71 | 2,485 |
| BOTTOM | 35 | 595 |
| UTILITY | 58 | 1,653 |

Champions with multiple viable roles (e.g., a flex pick viable in two lanes) are counted in each qualifying role's k and are **not deduplicated** across roles, per the task's stated rule — a champion viable in both TOP and MIDDLE contributes to both role's pair counts.

## 4. Final same-lane pair count

Sum across all 5 roles, at the original 5% threshold (superseded — kept for reproducibility):

```
2,701 + 1,770 + 2,485 + 595 + 1,653 = 9,204
```

**At >10% threshold (current, recommended per `phase1-role-threshold-sensitivity.md`):**

| Role | k (>10% threshold) | C(k,2) |
|---|---|---|
| TOP | 58 | 1,653 |
| JUNGLE | 59 | 1,711 |
| MIDDLE | 59 | 1,711 |
| BOTTOM | 30 | 435 |
| UTILITY | 45 | 990 |

```
1,653 + 1,711 + 1,711 + 435 + 990 = 6,500
```

**Current final same-lane pair count: 6,500** (10% threshold). The 9,204 figure (5% threshold) above is superseded — see `phase1-role-threshold-sensitivity.md` for the full sensitivity analysis and why 10% was chosen (plausibility check, not just curve shape).

## 5. Comparison to the 2,500-3,000 estimate

The originally-measured count at 5% (**9,204**) was **outside** the 2,500-3,000 estimated range in `phase0-role-scoping.md` §3(b) — roughly **3.1-3.7x higher** than the top of that range (9,204 / 3,000 ≈ 3.07x; 9,204 / 2,500 ≈ 3.68x).

The estimate assumed "roughly 30-40 viable champions per role." The 5%-threshold per-role counts (35-74, mean ≈60) ran well above that assumption for every role except BOTTOM (35, near the top of the assumed range). The estimate undercounted primarily because flex/multi-role champions push k up in more than one role simultaneously (no dedup, per §3 of this file), and because a >5% empirical-viability bar is a looser inclusion criterion than the informal "primary role" intuition the original 30-40 guess was likely based on.

**Superseded — kept for the record.** Now that the recommended threshold is >10% (§3-4, above), the current count (**6,500**) is closer to the original estimate than 9,204 was, though still above it — 6,500 / 3,000 ≈ 2.17x, 6,500 / 2,500 ≈ 2.60x the top of the original estimated range. The 10%-threshold per-role counts (30-59, mean ≈50) are lower and tighter than the 5%-threshold spread, consistent with 10% filtering out the noisiest, lowest-frequency role assignments (see `phase1-role-threshold-sensitivity.md` §2 for the plausibility case, e.g. Gragas mid/support at 5% vs. correctly TOP+JUNGLE-only at 10%).

**Practical implication for Phase 1 precompute planning:** the same-lane scoping decision in `phase0-role-scoping.md` §4 remains directionally correct (same-lane is still far smaller than the 14,878 all-pairs figure — at 6,500, roughly 56% smaller than all-pairs). At 4 rank brackets × 3 phases, 6,500 pairs implies 78,000 precompute generations. See `docs/decisions/phase0-precompute-benchmark.md` for the recomputed wall-clock estimate at this figure.

## Method summary / reproducibility

- Champion count: real HTTP fetch (`curl`) + real JSON parse (`python3`/`json.load`), run 3x, identical result each time (233 raw keys). A follow-up check found 60 of those keys are `Jade_*` game-mode-variant duplicates of existing champions, not distinct champions — corrected count is **173**, matching `phase0-role-scoping.md`'s wiki-sourced figure.
- Role data: real file download (`huggingface_hub.hf_hub_download`) of a CSV with an explicit `team_position` field per player-match row, aggregated with `pandas.groupby`/`unstack` — no LLM summarization anywhere in the numeric pipeline.
- Threshold: `frac > 0.05` (exactly 5%, strictly greater-than), applied identically to all 170 champions in the dataset.
- All numbers in §3-§5 are outputs of code executed in this session against the downloaded CSV; none are recalled, assumed, or extrapolated.

## Status

**DONE.**
