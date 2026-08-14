# Phase 2 Qualitative Oversampling Diagnostic — AGENT-23

**Status: DONE.**

Tests whether raising the qualitative-advice task's exposure — via
oversampling the 40 real rows to 200 (5x each), lifting its share of the
training mix from 7.4% to 28.6% — is enough to fix the complete failure
found in `docs/decisions/phase2-qualitative-advice-diagnostic.md` (0/10
held-out pairs, every generation reverting to the win-rate template). One
variable changed: ratio. Everything else (win-rate portion, step cap, LoRA
config) held identical to that prior run.

`git pull` on `main` before starting: `Already up to date.`

## Real starting state, re-verified this session

```
$ wc -l app/finetune/data/qualitative_advice_train.jsonl app/finetune/data/qualitative_advice_heldout.jsonl
      40 app/finetune/data/qualitative_advice_train.jsonl
      10 app/finetune/data/qualitative_advice_heldout.jsonl
```

Read `backend/app/finetune/train.py` directly (not assumed from any prior
doc): `oversample_to_balance(abstention_rows, non_abstention_rows, seed)`
takes two explicit row lists and matches the second to the first's count —
too specific to the single-list-to-a-target-count case this task needs.
Generalized into `oversample_to_count(rows, target_count, seed)` (full
repeats + a seeded sample of the remainder, without replacement), and
refactored `oversample_to_balance` to delegate to it rather than duplicating
the algorithm — `oversample_to_balance`'s existing test file
(`test_full_scale_oversample.py`) passes unmodified after the refactor.

**Real math for 40→200, computed before writing any test:**
`full_repeats = 200 // 40 = 5`, `remainder = 200 % 40 = 0`. This differs
from the task's illustrative "each row appears either 5 or 6 times" — the
real, exact division means **every one of the 40 rows appears exactly 5
times, with zero remainder-sampled duplicates**. Verified, not assumed.

## `oversample_to_count` — TEST_LOOP contract

Wrote `backend/tests/unit/test_oversample_to_count.py` first, expected
values hand-computed above and against a small synthetic case
(3 rows→target 7: `full_repeats=2, remainder=1` → two rows appear twice,
one appears three times):

```
$ python3 -m pytest tests/unit/test_oversample_to_count.py tests/unit/test_full_scale_oversample.py -v
11 passed in 5.19s
```
6/6 new tests passed on the first implementation; all 5 existing
`oversample_to_balance` tests still pass unmodified.

```
$ python3 -m pytest tests/unit --ignore=tests/unit/test_models.py -q
54 passed in 3.81s
```

## Training run

Combined the 200 oversampled qualitative rows (remapped `context`→`prompt`)
with the same, unchanged `stratified_sample(win_rate_rows, n_abstention=250,
n_non_abstention=250, seed=42)` from the prior diagnostic, shuffled with a
fixed `seed=42`:

```
combined training set: 700 rows (500 win-rate + 200 qualitative-oversampled), qualitative share: 28.6%
```

Same LoRA config (r=8, alpha=16, `[q,k,v,o,gate,up,down]_proj`), same
`max_steps=200` — unchanged, per the task contract (this run's entire point
is isolating ratio, not step count).

Real logged loss sequence (20 points, step10..step200):
```
[2.6651889801025392, 1.0344094276428222, 0.9706114768981934, 0.6556677341461181,
 0.6796501159667969, 0.30668187141418457, 0.4751109600067139, 0.49271163940429685,
 0.46000089645385744, 0.6007325172424316, 0.42073779106140136, 0.5316033363342285,
 0.4431201457977295, 0.4389046192169189, 0.343673038482666, 0.3861820936203003,
 0.3777970314025879, 0.3095537185668945, 0.41598286628723147, 0.18821802139282226]
```
First logged (step 10) = 2.665, last logged (step 200) = 0.188 — a real
decrease, still noisy (spikes to 0.6-0.68 mid-run, same mixed-task pattern
as the prior combined run).

**Real trainer summary line:** `{'train_runtime': '1998', ..., 'epoch': '0.5714'}`
— training stopped at **0.57 epochs**, i.e. the unchanged 200-step cap did
not complete even one full pass over the enlarged 700-row set (steps per
epoch = ceil(700/2) = 350; 200/350 = 0.571). This is a concrete, mechanical
fact worth flagging directly: raising the oversampled row *count* does not
by itself guarantee more real gradient exposure if the step budget stays
fixed and the run doesn't finish a full epoch.

fact_ledger.md check, re-verified against this specific new adapter:
```
$ python3 -m pytest tests/integration/test_qualitative_oversampled_adapter_fact_ledger.py -v
test_oversampled_adapter_is_real_peft_model_and_differs_from_base PASSED [ 50%]
test_oversampled_adapter_logged_loss_decreased_from_first_to_last_logged_step PASSED [100%]
================== 2 passed, 14 warnings in 139.29s (0:02:19) ==================
```

## Eval

### Qualitative held-out result: 0/10 passed — identical failure mode to the prior diagnostic

Every one of the 10 real generations again produced **no Early:/Mid:/Late:
sections**, reverting fully to the win-rate template. Grounding and
win-rate accuracy passed in all 10 (0 invented phrases; every cited
percentage within 10 points of the real value) — same as before, the
problem is not accuracy or grounding, it's that the model never attempts
the requested format.

All 10 real outputs, verbatim:
```
Aatrox/Kayle:       "Aatrox wins 50.0% of games against Kayle in top across 4 tracked games this patch."
Aatrox/Quinn:       "Aatrox wins 0.0% of games against Quinn in top across 2 tracked games this patch."
Aatrox/Vladimir:    "Aatrox wins 33.3% of games against Vladimir in top across 3 tracked games this patch."
Ahri/AurelionSol:   "AurelionSol wins 50.0% of games against Ahri in middle across 2 tracked games this patch."
Ahri/Lissandra:     "Ahri wins 0.0% of games against Lissandra in middle across 2 tracked games this patch."
Ahri/Naafiri:       "Ahri wins 50.0% of games against Naafiri in middle across 2 tracked games this patch."
Ahri/Sylas:         "Ahri wins 50.0% of games against Sylas in middle across 4 tracked games this patch."
Ahri/Xerath:        "Ahri wins 67.0% of games against Xerath in middle across 3 tracked games this patch."
Akali/Renekton:     "Akali wins 0.0% of games against Renekton in top across 2 tracked games this patch."
Akali/Talon:        "Akali wins 100.0% of games against Talon in middle across 2 tracked games this patch."
```
One cosmetic difference from the prior diagnostic's outputs: Ahri/AurelionSol
now states `"AurelionSol wins... against Ahri"` (subject/object swapped
relative to the prior run's phrasing) — a minor template-slot variation,
not evidence of any qualitative-format learning.

Representative full scored row (Aatrox/Vladimir, same pair reported in the
prior diagnostic for direct comparison):
```json
{
  "champ_a": "Aatrox", "champ_b": "Vladimir", "role": "top",
  "model_output": "Aatrox wins 33.3% of games against Vladimir in top across 3 tracked games this patch.",
  "sections_present": false, "has_early": false, "has_mid": false, "has_late": false,
  "grounding_passed": true, "invented_phrases": [],
  "expected_win_rate_pct": 33, "cited_percentages": [33.3], "win_rate_within_10pts": true,
  "passed": false
}
```

### Win-rate regression check: no regression, again

```
win-rate regression step2: 152/152
win-rate regression step4: 237/237
```

| | Context-conditioning diagnostic | Prior combined (7.4% qualitative) | **This run (28.6% qualitative)** |
|---|---|---|---|
| Held-out matchup pass rate | 152/152 (100.0%) | 152/152 (100.0%) | **152/152 (100.0%)** |
| Abstention pass rate | 237/237 (100.0%) | 237/237 (100.0%) | **237/237 (100.0%)** |

## Outcome — stated plainly

**Oversampling alone did not fix it.** Raising the qualitative task's share
from 7.4% to 28.6% (via 5x duplication of the same 40 real rows) produced
an outcome statistically indistinguishable from the prior run: 0/10
qualitative pass, identical failure mode (zero attempts at the requested
format), and win-rate accuracy held perfectly at 152/152 and 237/237 both
times. Per the self-correction protocol, this is reported as a real,
informative negative result — the qualitative scoring criteria were not
loosened or second-guessed to manufacture a pass.

The real mechanical detail found this run — training stopped at 0.57
epochs, short of even one full pass over the enlarged 700-row set — points
toward the more precise diagnosis: **duplicating existing rows without
extending the step budget does not reliably increase real gradient
exposure**, since the run may end before the model has been shown every row
even once. This reframes "ratio" and "step budget" as coupled, not
independent, variables: at a fixed 200-step cap, oversampling changes the
*proportion* of each batch that's qualitative, but doesn't guarantee the
model actually sees more real qualitative content than it did before if the
run doesn't complete an epoch either way.

**Revised recommendation, updated from the immediately prior doc's three
options:** the isolated "just raise the ratio" fix is now ruled out by real
evidence. The next real test should either (a) extend the step budget
enough to guarantee at least 1-2 full epochs over the combined set at the
current ratio, or (b) move to the two-adapter/two-stage approach — train a
dedicated qualitative-advice adapter (or a second LoRA stage) with its own
step budget sized to its own 40-row dataset, rather than continuing to
split a fixed 200-step budget between two tasks with very different data
volumes.

## Files

- `backend/app/finetune/train.py` (additive: `oversample_to_count`; `oversample_to_balance` refactored to reuse it, behavior unchanged)
- `backend/tests/unit/test_oversample_to_count.py`
- `backend/app/finetune/artifacts/smoke-adapter-qualitative-oversampled/`
- `backend/tests/integration/test_qualitative_oversampled_adapter_fact_ledger.py`
- `backend/app/finetune/artifacts/eval_results_qualitative_oversampled.json`
- `docs/decisions/phase2-qualitative-oversampling-diagnostic.md` (this file)
