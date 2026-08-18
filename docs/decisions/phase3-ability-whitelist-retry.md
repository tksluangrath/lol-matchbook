---
noteId: "phase3abilitywhitelistretry0001"
tags: []

---

# Phase 3: Ability-Name Whitelist and Retry of the Grounding-Check Skips

**Status: DONE.** Added an explicit ability-name whitelist to the generation
prompt and re-ran real generation for every currently-unwritten top-109
candidate pair. Real result: **21 of 28 now pass, 7 still fail.**

## Root cause (confirmed this session)

`docs/decisions/phase3-eager-tier-precompute.md`'s 27 skips were all
`fact_grounding_check` flags on invented capitalized phrases. Sampling 4
real cases found two distinct failure modes:

- **Near-miss misspelling of a real ability**: "Primal Howls" for
  Warwick's real "Primal Howl"; "Hallowed Path" for Viego's real "Harrowed
  Path" (found separately, in `phase3-contaminated-row-regeneration.md`).
- **Fully invented, no real counterpart on either kit**: "Fire Bounce"
  (Milio/Nami), "Dead Ally" (Jhin/Kaisa).

`build_generation_prompt()`/`build_pair_with_context()`'s real prompt only
ever put ability names inside prose kit-text (`champion_text()`), never as
an explicit, exact-spelling list the model could anchor to.

## Implementation

Added `ability_names()` and `ability_whitelist_block()` to
`backend/app/finetune/qualitative_advice.py`. `ability_names()` reads the
passive + spell `name` fields already present on the same champion-detail
dict `champion_text()` reads its prose from — no new fetch.
`ability_whitelist_block()` formats both champions' real names into one
line: `"{champ_a}'s real abilities: X, Y, Z. {champ_b}'s real abilities: ...
Only reference ability names from these two lists, spelled exactly as
given."`

Wired into both real prompt-builders that were found to matter:
- `build_generation_prompt()` (used by `run_qualitative_data_expansion.py`).
- `precompute.build_pair_with_context()` — the one that actually builds the
  prompt `run_precompute_batch`/`force_regenerate_pairs` feed to the model.
  This function builds its context block inline rather than delegating to
  `build_generation_prompt()` (its format has no `Instruction:` line — that
  line isn't part of the real fine-tuning format, confirmed by inspecting
  `qualitative_advice_heldout.jsonl`'s own `context` field), so the
  whitelist helper was added to both call sites rather than only the one
  named in the task, to actually affect the real rerun.

## Test (written first, confirmed passing before the real rerun)

`backend/tests/unit/test_ability_whitelist_prompt.py`, using hand-fetched
real Warwick/Viego passive+spell names (fetched for real this session via
`fetch_champion_detail`, embedded as trimmed fixtures — not invented):

```
test_ability_names_extracts_real_passive_and_spell_names_in_kit_order   PASSED
test_build_generation_prompt_contains_exact_real_ability_names          PASSED
test_build_generation_prompt_whitelist_names_both_champions             PASSED
```

The middle test is the hard gate: asserts the built prompt contains the
real, correctly-spelled `"Primal Howl"` and `"Harrowed Path"` and does
*not* contain the misspellings `"Primal Howls"` / `"Hallowed Path"`.

Full suite after the change: `77 passed` (`pytest tests/unit/`), no
existing test touched.

## Re-derived skip pool: 28, not 27 (confirmed against the live DB, not assumed)

Queried the live `Advice` table directly rather than trusting the prior
doc's list, since two pairs had regeneration activity since:
`(Caitlyn, Samira, bottom)` — resolved clean earlier this session, no
longer a skip — and `(Briar, Viego, jungle)` — its old (contaminated) rows
were deleted, and its regeneration attempt failed grounding
(`"Hallowed Path"`), so it currently has **zero** rows: newly added to the
skip pool.

Real distinct `(champ_a, champ_b, role)` triples with at least one Advice
row: 95. Missing from the real top-109 ranked candidate set: **28** — the
original 27 minus Caitlyn/Samira (now written) plus Briar/Viego (now
missing). Confirmed by directly diffing `rank_real_candidate_pairs()[:109]`
against the live DB's distinct triples before launching the rerun (see
`backend/app/data_pipeline/run_ability_whitelist_retry.py`, which re-derives
and prints this same list at run start rather than hardcoding a target
list).

## Real rerun result

```
$ python -m app.data_pipeline.run_ability_whitelist_retry (via force_regenerate_pairs, patch 16.15.1)
real current skip pool: 28 pairs
...
written: 21
skipped: 7
wall_clock_s=7370.0  (~2h3m for 28 pairs, within the 30min-2hr estimate)
```

Confirmed directly against the live DB post-run: querying the same
top-109-minus-written-triples diff again returns exactly the same 7
remaining pairs the run's own `skipped` list reported — no drift between
what the job logged and what's actually in the table.

### Before/after: 0/28 passed before (all 28 were unwritten skips) -> 21/28 pass now

| Pair | Role | Before | After |
|---|---|---|---|
| Milio, Nami | utility | skip (`Fire Bounce`, per original 3-pair sample) | **written** |
| Jhin, Kaisa | bottom | skip (`Dead Ally`, per original 3-pair sample) | **written** |
| Kayn, Warwick | jungle | skip (`Primal Howls`) | **still skip** — new phrase `Blood Hunts` |
| Ezreal, Jhin | bottom | skip | **written** |
| Jhin, Lucian | bottom | skip | **written** |
| Ezreal, Tristana | bottom | skip | **written** |
| Ezreal, Varus | bottom | skip | **written** |
| Jhin, Jinx | bottom | skip | **still skip** — `Dead Ally` |
| Jinx, Lucian | bottom | skip | **written** |
| Caitlyn, Jinx | bottom | skip | **written** |
| Ezreal, Kaisa | bottom | skip | **written** |
| Jinx, Tristana | bottom | skip | **written** |
| Caitlyn, Tristana | bottom | skip | **written** |
| Jhin, Zeri | bottom | skip | **still skip** — `Let Zeri` |
| Kaisa, MissFortune | bottom | skip | **written** |
| Alistar, Milio | utility | skip | **written** |
| Jhin, MissFortune | bottom | skip | **still skip** — `Dead Whisper` |
| Jhin, Vayne | bottom | skip | **written** |
| Milio, Yuumi | utility | skip | **still skip** — `could_not_split_sections` (unrelated to grounding) |
| Blitzcrank, Milio | utility | skip | **still skip** — `Fire Blast` |
| Braum, Lulu | utility | skip | **written** |
| Briar, Viego | jungle | skip (`Hallowed Path`, found in the contaminated-row regen task) | **written** |
| Jinx, Xayah | bottom | skip | **written** |
| Jinx, Zeri | bottom | skip | **still skip** — `could_not_split_sections`, no invented phrase |
| Kaisa, Xayah | bottom | skip | **written** |
| Lucian, MissFortune | bottom | skip | **written** |
| MasterYi, Viego | jungle | skip | **written** |
| Thresh, Yuumi | utility | skip | **written** |

## Whitelist effect, reported honestly: helped the near-misses and even fixed the two invented examples the task called out, but not all invented phrases

The two originally-cited fully-invented failures moved in opposite
directions:

- **Milio/Nami's `"Fire Bounce"`**: gone. This pair now passes.
- **Jhin/Kaisa's `"Dead Ally"`**: gone for that pair — Jhin/Kaisa now
  passes. But `"Dead Ally"` didn't disappear as a phrase: it reappears
  verbatim as the new failure on **Jhin/Jinx**, a different bottom-lane
  pair sharing Jhin. This looks like a Jhin-specific hallucination the
  model reaches for regardless of prompt, not something the whitelist
  structurally prevents — the whitelist raises the bar (forces the model
  to draw from a real list more often) but doesn't hard-block copying a
  phrase from outside it.

Bot-lane/support pairs still dominate the 7 remaining failures (6 of 7),
same concentration the original 109-pair run found (24 of 27) — this
whitelist pass narrowed the pool but didn't change *which* role cluster is
hardest to ground, consistent with the original run's open question
(ADC/support kits' more numerous, more specifically-named abilities give
more surface area to misremember).

**New near-miss pattern, not seen before this rerun**: `"Blood Hunts"`
(Kayn/Warwick) and `"Let Zeri"` are plural/phrase variants of real
whitelisted names or champion names immediately followed by a verb —
i.e. the whitelist fixed the *specific* near-misses it was built to fix
(`Primal Howls` -> real `Primal Howl` is gone from Kayn/Warwick's output)
but the same pair's greedy decoding found a *different* near-miss
(`Blood Hunt` -> `Blood Hunts`) once the first path was blocked. Confirms
this project's existing framing (`phase3-contaminated-row-regeneration.md`):
generation is greedy/deterministic, so a prompt change can shift which
hallucination the model lands on rather than eliminating the underlying
tendency to invent phrasing around a real name.

Two of the 7 remaining failures (`Milio/Yuumi`, `Jinx/Zeri`) aren't
grounding failures at all — `could_not_split_sections`, i.e. the model
didn't emit all three `Early:`/`Mid:`/`Late:` labels for real, unrelated to
the whitelist.

## Not done here, deliberately

No further prompt-engineering iteration on the 7 remaining failures
(e.g. explicitly forbidding common near-miss patterns, or a stricter
grounding regex for pluralized ability names) — out of this task's scope,
which was to test the whitelist's real effect once, not iterate to zero
failures. These 7 fall to the lazy-tier fallback at request time, same as
every other real grounding-check skip.

## Files

- `backend/app/finetune/qualitative_advice.py` (added `ability_names`,
  `ability_whitelist_block`; wired into `build_generation_prompt`)
- `backend/app/data_pipeline/precompute.py` (`build_pair_with_context`
  wired to the same `ability_whitelist_block`)
- `backend/app/data_pipeline/run_ability_whitelist_retry.py` (new launcher:
  re-derives the real skip pool from the live DB, calls
  `force_regenerate_pairs` unmodified)
- `backend/tests/unit/test_ability_whitelist_prompt.py` (new, 3 tests)
- `docs/decisions/phase3-ability-whitelist-retry.md` (this file)
- Live DB (`.pgdata`): 21 of the 28 previously-unwritten top-109 pairs now
  have real Advice rows; 7 remain unwritten (listed above).
