---
noteId: "phase3samplingretry0001"
tags: []

---

# Phase 3: Sampling-Retry Fallback for the 7 Ability-Whitelist Holdouts

**Status: DONE.** Added a bounded sampling-retry fallback for pairs that
fail `fact_grounding_check` on the deterministic greedy attempt, and ran it
for real against the 7 pairs `phase3-ability-whitelist-retry.md` left
unwritten. Real result: **7 of 7 now pass.**

## Root cause (already established, this task just acts on it)

`backend/app/finetune/eval.py`'s `generate()` defaults to `do_sample=False`
(greedy). Greedy decoding is deterministic, so re-running generation on the
same prompt without changing anything always reproduces the same
hallucinated ability name. The whitelist fix (previous doc) narrowed the
failure pool from 28 to 7 but couldn't fix these 7 by re-running greedy
again -- they needed an actual decoding-path change.

## Real bug found and fixed en route: `generate()` couldn't take a
`do_sample` override at all

`generate()`'s real call to `model.generate()` was:

```python
out = model.generate(
    **inputs,
    max_new_tokens=max_new_tokens,
    do_sample=False,
    pad_token_id=...,
    **gen_kwargs,
)
```

Passing `do_sample=True` via `**gen_kwargs` here raises `TypeError: got
multiple values for keyword argument 'do_sample'` -- Python doesn't allow a
literal keyword and the same key inside `**kwargs` in one call. The
`**gen_kwargs` passthrough existed in the function signature but was
actually unusable for the one override this task needed. Fixed by merging
into a single dict before the call (`call_kwargs = {defaults...};
call_kwargs.update(gen_kwargs)`) -- same default behavior (`do_sample=False`)
when no kwargs are passed, real override now possible.

## Implementation

`backend/app/data_pipeline/precompute.py`:

- `_generate_and_check_pair` now accepts `**gen_kwargs` and passes them
  through to `generate()` (empty by default -- no change to existing
  callers).
- `SAMPLING_GEN_KWARGS = {"do_sample": True, "temperature": 0.7, "top_p":
  0.9}` -- the standard "mild" sampling values (the same range Hugging
  Face's own `generate()` documentation uses as its example), not tuned
  per pair. `MAX_SAMPLING_RETRIES = 2`.
- `_generate_and_check_pair_with_sampling_retry(pair, model, tokenizer,
  max_new_tokens)`: runs the greedy attempt first; if it fails, retries up
  to 2 more times with `SAMPLING_GEN_KWARGS`; returns the first passing
  attempt, or the last failing attempt's result unchanged (same
  `skipped`-entry shape) if all 3 fail.
- `force_regenerate_pairs` gained an opt-in `sampling_retry: bool = False`
  parameter. Default unchanged -- `run_precompute_batch` and every existing
  caller/test of `force_regenerate_pairs` still gets one deterministic
  greedy attempt only. Sampling only ever runs for a caller that explicitly
  passes `sampling_retry=True`.

## Test (written first, confirmed passing before the real run)

`backend/tests/unit/test_sampling_retry.py`, `generate()` monkeypatched
(same pattern as `test_forced_regeneration_scope.py`, no real model call):

```
test_stops_at_first_passing_sampled_attempt_and_uses_its_result   PASSED
test_all_three_attempts_failing_returns_last_failure_not_a_crash  PASSED
```

The first test asserts: greedy attempt fails, first sampled retry fails,
second sampled retry passes -> the retry stops there and returns *that*
attempt's sections, with exactly 3 `generate()` calls (`calls[0] == {}`
i.e. greedy got no override kwargs, `calls[1]`/`calls[2] ==
SAMPLING_GEN_KWARGS`). The second test asserts: all 3 attempts fail ->
returns the same `skipped` shape (`reason`, `invented_phrases`) the
existing pipeline already handles, not a crash, with exactly 3 calls made
(`1 + MAX_SAMPLING_RETRIES`).

Full suite after the change: `79 passed` (`pytest tests/unit/`) -- 77 prior
+ 2 new, no existing test touched. `test_forced_regeneration_scope.py`
(which exercises the default, non-retry path via `force_regenerate_pairs`
called without `sampling_retry`) still passes unmodified, confirming the
opt-in flag doesn't change default behavior.

## Real run

New launcher: `backend/app/data_pipeline/run_sampling_retry.py` --
re-derives the real skip pool from the live DB (same
`rank_real_candidate_pairs()[:109]` minus written-triples diff
`run_ability_whitelist_retry.py` used), rather than hardcoding the 7 named
in the prior doc, in case anything had changed.

Re-derived pool at run start, confirmed identical to the prior doc's list
of 7:

```
[Jhin, Jinx, bottom]
[Jhin, Zeri, bottom]
[Jhin, MissFortune, bottom]
[Milio, Yuumi, utility]
[Blitzcrank, Milio, utility]
[Jinx, Zeri, bottom]
[Kayn, Warwick, jungle]
```

```
$ python -m app.data_pipeline.run_sampling_retry (via force_regenerate_pairs(sampling_retry=True), patch 16.15.1)
real current skip pool: 7 pairs
...
written: 7
skipped: 0
SAMPLING_RETRY_DONE wall_clock_s=4102.7 written=7 skipped=0
```

~68 minutes wall clock for 7 pairs at up to 3 attempts each -- consistent
with the project's observed 66-264 sec/pair range times up to 3x.

Confirmed independently against the live DB after the run (not just
trusting the job's own printed summary): all 7 target triples now have
exactly 3 real `Advice` rows each (`early`/`mid`/`late`) for patch
`16.15.1`.

### Before/after: 0/7 pass before -> 7/7 pass now

| Pair | Role | Before (from phase3-ability-whitelist-retry.md) | After |
|---|---|---|---|
| Kayn, Warwick | jungle | skip -- `Blood Hunts` | **written** |
| Jhin, Jinx | bottom | skip -- `Dead Ally` | **written** |
| Jhin, Zeri | bottom | skip -- `Let Zeri` | **written** |
| Jhin, MissFortune | bottom | skip -- `Dead Whisper` | **written** |
| Milio, Yuumi | utility | skip -- `could_not_split_sections` (not a grounding failure) | **written** |
| Blitzcrank, Milio | utility | skip -- `Fire Blast` | **written** |
| Jinx, Zeri | bottom | skip -- `could_not_split_sections`, no invented phrase | **written** |

No pair required all 3 attempts to exhaust without a pass -- the job's own
log reports `skipped: 0`, so every one of the 7 found a passing attempt
(greedy or sampled) within the 3-attempt budget. This run's logging
(`run_sampling_retry.py`, matching `run_ability_whitelist_retry.py`'s
shape) only records the final pass/fail per pair, not which of the 3
attempts passed -- not needed here since none reached a final failure to
report a "last hallucinated phrase" for.

## Not done here, deliberately

- Didn't log per-attempt output (e.g. which attempt number won, or the
  intermediate failing generations) -- `_generate_and_check_pair_with_
  sampling_retry`'s contract only guarantees the final result, and none of
  the 7 pairs needed that detail since all passed. Add per-attempt logging
  if a future pair exhausts all 3 attempts and the specific failure
  progression becomes worth inspecting.
- Didn't change `run_precompute_batch` or the default `force_regenerate_
  pairs` call shape -- `sampling_retry` stays an explicit opt-in kwarg, so
  the rest of the pipeline (including any future forced regeneration of
  the other ~95 already-written pairs) stays deterministic unless a caller
  asks for the retry.
- Didn't raise `MAX_SAMPLING_RETRIES` above 2 or tune `temperature`/`top_p`
  further -- the 2-retry budget already cleared all 7 pairs this run; no
  evidence yet that a larger budget or different sampling values are
  needed.

## Files

- `backend/app/finetune/eval.py` (`generate()`'s `do_sample`/`gen_kwargs`
  merge bug fixed)
- `backend/app/data_pipeline/precompute.py` (`_generate_and_check_pair`
  gained `**gen_kwargs`; new `SAMPLING_GEN_KWARGS`, `MAX_SAMPLING_RETRIES`,
  `_generate_and_check_pair_with_sampling_retry`;
  `force_regenerate_pairs(sampling_retry=...)`)
- `backend/app/data_pipeline/run_sampling_retry.py` (new launcher)
- `backend/tests/unit/test_sampling_retry.py` (new, 2 tests)
- `docs/decisions/phase3-sampling-retry.md` (this file)
- Live DB (`.pgdata`): all 7 previously-unwritten top-109 pairs now have
  real Advice rows -- the full top-109 candidate pool is now 100% written.
