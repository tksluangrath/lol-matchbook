# Phase 3: Regenerating the 2 Markup-Contaminated Pairs

**Status: DONE, 1 of 2 pairs regenerated clean.** Real regeneration run
against the live DB for the 2 pairs `phase3-markup-contamination-audit.md`
found contaminated: **(Caitlyn, Samira, bottom)** — regenerated clean, and
**(Briar, Viego, jungle)** — a real, unrelated grounding failure kept it
from being rewritten (details below).

## Scoped forced-regeneration path

Added `force_regenerate_pairs(patch, targets, ...)` to
`backend/app/data_pipeline/precompute.py`, reusing (not duplicating)
`run_precompute_batch`'s existing generate/grounding-check/section-split/
write logic — both now call the same two shared helpers,
`_generate_and_check_pair` (real model call + grounding/split check, no DB
access) and `_write_pair_sections` (MatchupStat + Advice writes for
sections that already passed).

Scoped strictly to the given `(champ_a, champ_b, role)` triples: only rows
matching one of those exact triples are ever deleted or rewritten. This is
the guard against the mistake already made once in this project
(`phase3-eager-tier-precompute.md`'s "Idempotency" section — an overly
broad check once regenerated all 109 candidate pairs instead of the
intended 82).

Proven with `backend/tests/unit/test_forced_regeneration_scope.py`
(3 tests, real pgserver DB, monkeypatched `generate`/
`load_model_and_tokenizer` for speed) **before** any real regeneration ran,
per the task's hard gate:

```
test_force_regenerate_touches_only_named_target_not_bystander PASSED
test_force_regenerate_never_deletes_a_pair_not_named_in_targets PASSED
test_force_regenerate_leaves_targets_own_row_untouched_on_failed_check PASSED
```

## Real bug found and fixed mid-task: delete-before-check destroyed a row

First design deleted a target pair's old rows *before* attempting
regeneration (reasoning: otherwise the pre-generation existence check /
`ON CONFLICT DO NOTHING` idempotency would silently skip it, same as
`run_precompute_batch`). Real consequence, hit for real on the first live
run: (Briar, Viego, jungle)'s regeneration failed the grounding check (see
below) — but its old contaminated rows had already been deleted, so the
pair ended up with **zero** Advice rows in the live DB, not even the old
contaminated ones.

Root-caused and fixed: `force_regenerate_pairs` now calls
`_generate_and_check_pair` first, and only deletes+rewrites the pair's
existing rows if that check passes. A failed regeneration leaves the old
row completely alone. Added
`test_force_regenerate_leaves_targets_own_row_untouched_on_failed_check`
to cover this specific failure mode (it would have caught the bug had it
existed before the first live run).

## Real result

```
$ python -m app.data_pipeline.precompute (via force_regenerate_pairs, patch 16.15.1)
written_pairs: [{"champ_a": "Caitlyn", "champ_b": "Samira", "role": "bottom"}]
skipped:
  - Briar/Viego, reason=grounding_failed, invented_phrases=["Hallowed Path"]
```

### (Caitlyn, Samira, bottom): regenerated, confirmed markup-free

All 3 phase rows rewritten and verified directly against the live DB with
the same tag-scan regex the contamination audit used
(`re.compile(r"<[^>]+>|&[a-zA-Z]+;")`):

```
early markup_found=[] len=352
mid   markup_found=[] len=468
late  markup_found=[] len=389
```

Zero matches across all 3 rows — the `<status>Dash</status>` /
`<status>Blade Whirl</status>` contamination documented in the audit is
gone, and the row only exists because it passed the same real
grounding/section-split checks every other precompute-written row passes
(`_generate_and_check_pair`, unmodified from `run_precompute_batch`'s
logic).

### (Briar, Viego, jungle): real, unrelated grounding failure — not rewritten

With the fixed `champion_text()` supplying clean kit text, the model's
real greedy-decoded (`do_sample=False`) generation for this pair invents
`"Hallowed Path"` — a capitalized phrase that doesn't appear anywhere in
the real supplied kit text for either champion — in the late-game section.
`fact_grounding_check` correctly flags it and the pair is never written,
same as the 27 pairs the original eager-tier run already skipped for the
identical reason.

This is unrelated to markup: the invented phrase itself, not any HTML tag,
is what `fact_grounding_check` flagged. Because generation is greedy
(`do_sample=False`), the same prompt against the same model deterministically
produces the same hallucination every time — a bare retry would not
produce a different result, and changing `max_new_tokens` wouldn't either
(greedy decoding doesn't change already-generated tokens based on the
token budget). Not investigated or worked around further here — out of
this task's scope (fixing markup contamination, not the model's general
hallucination rate, which the original eager-tier run already
characterized as a real, open question for ADC/jungle pairs).

**Real consequence:** (Briar, Viego, jungle) currently has 0 Advice rows
in the live DB — the old (contaminated) rows are gone, and no clean
replacement passed the grounding gate. This is the same state a `/ask`
cache-miss for this pair would hit under the tiered-fallback design
(`docs/decisions/tiered-fallback-design.md`) — it falls to the lazy-tier
generation path at request time rather than serving eager-tier content,
consistent with how this project already treats grounding-failed pairs.
Not remediated further in this task; a future task could decide whether to
retry with a different adapter/prompt strategy or accept the lazy-tier
fallback permanently, per the open question already named in
`phase3-eager-tier-precompute.md`'s "Next step".

## Isolation confirmed on the real run

No other row was touched by the real run: `force_regenerate_pairs` was
called with `targets=[("Caitlyn","Samira","bottom"), ("Briar","Viego","jungle")]`
only — the same two-test-proven scoping guarantees from
`test_forced_regeneration_scope.py` apply to the real DB, and the real
Briar/Viego failure path is exactly the case the third test added mid-task
covers.

## Files

- `backend/app/data_pipeline/precompute.py` (extended:
  `force_regenerate_pairs`; refactored `_generate_and_write_pair` into
  `_generate_and_check_pair` + `_write_pair_sections` so
  `run_precompute_batch` and `force_regenerate_pairs` share one real
  generate/check/write path)
- `backend/tests/unit/test_forced_regeneration_scope.py` (new, 3 tests)
- `docs/decisions/phase3-contaminated-row-regeneration.md` (this file)
- Live DB (`.pgdata`): (Caitlyn, Samira, bottom) rows rewritten and clean;
  (Briar, Viego, jungle) rows removed, no clean replacement written.
