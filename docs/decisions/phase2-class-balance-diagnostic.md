# Phase 2 Class-Balance Diagnostic — AGENT-14

**Status: DONE.**

This is a targeted follow-up to
`docs/decisions/phase2-implementation-summary.md`, not a new phase. It
answers one question cheaply, on CPU, in this session: is AGENT-12's
smoke-adapter collapse (0/152 held-out, 237/237 abstention — always emitting
the fixed hedge phrase) explained by the ~63%/37% abstention/non-abstention
class imbalance in the training sample, or does it persist regardless of
mix (pointing instead to insufficient step/epoch exposure)?

Nothing here modifies `phase2-implementation-summary.md`, AGENT-12's
`smoke-adapter/` artifact, or `eval_results.json` — this task's outputs use
distinct paths throughout.

## Hand-counted baseline (real, this session)

```
$ grep -c '"is_abstention": true' app/finetune/data/train.jsonl
1394
$ grep -c '"is_abstention": false' app/finetune/data/train.jsonl
819
$ wc -l app/finetune/data/train.jsonl
    2213 app/finetune/data/train.jsonl
```
Matches the CONTEXT's stated 1,394/819 split exactly — re-verified against
the current file, not trusted from the prior doc.

## Compute gate re-check (real, this session)

Reused the same real bnb CPU 4-bit path from AGENT-12/13 rather than
re-deriving it from scratch — confirmed it still works before committing to
the real training run:

```
$ python3 -c "
import torch
from transformers import BitsAndBytesConfig, AutoModelForCausalLM
bnb_config = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch.float32)
model = AutoModelForCausalLM.from_pretrained('Qwen/Qwen3-4B-Instruct-2507', quantization_config=bnb_config, device_map='cpu')
print('SUCCESS', type(model.model.layers[0].self_attn.q_proj))
"
...
SUCCESS <class 'bitsandbytes.nn.modules.Linear4bit'>
```
Real 4-bit `Linear4bit` layer, not a no-op — the compute path reproduces.

## `stratified_sample` — TEST_LOOP CONTRACT

Added `stratified_sample(rows, n_abstention, n_non_abstention, seed)` to
`backend/app/finetune/train.py`, additive alongside the existing
`load_sampled_examples` (uniform-sample) function, which is untouched and
remains the default path. Also made `run_training()` accept optional
`rows=`/`output_dir=` parameters (defaulting to the original uniform sample
and `OUTPUT_DIR`) so this task's stratified run could reuse the same training
logic without duplicating it or touching the default behavior.

Wrote `backend/tests/unit/test_stratified_sample.py` first, with expected
counts hand-derived from the real file (the grep/wc-l output above, restated
as constants in the test and independently re-asserted against the loaded
rows), before writing the implementation.

```
$ python3 -m pytest tests/unit/test_stratified_sample.py -v
tests/unit/test_stratified_sample.py::test_real_train_jsonl_matches_hand_counted_totals PASSED [ 16%]
tests/unit/test_stratified_sample.py::test_output_has_exact_requested_counts PASSED [ 33%]
tests/unit/test_stratified_sample.py::test_every_row_matches_its_requested_stratum PASSED [ 50%]
tests/unit/test_stratified_sample.py::test_zero_duplicate_rows_in_output PASSED [ 66%]
tests/unit/test_stratified_sample.py::test_same_seed_produces_identical_result PASSED [ 83%]
tests/unit/test_stratified_sample.py::test_no_duplication_used_when_stratum_has_ample_rows PASSED [100%]
========================= 6 passed in 5.32s =========================
```
All 6 passed on the first implementation — 0 of the 5 allowed fix attempts
used.

Confirmed AGENT-12's original test suite still passes unmodified against the
default (unbalanced) path, both before and after this session's edits:

```
$ python3 -m pytest tests/unit --ignore=tests/unit/test_models.py -v
======================== 26 passed, 1 warning in 4.07s =========================

$ python3 -m pytest tests/integration/test_train_smoke.py -v
tests/integration/test_train_smoke.py::test_saved_adapter_is_real_peft_model_and_differs_from_base PASSED [ 50%]
tests/integration/test_train_smoke.py::test_logged_loss_decreased_from_first_to_last_logged_step PASSED [100%]
================== 2 passed, 14 warnings in 131.88s (0:02:11) ==================
```

## Sample composition (real, confirmed 250/250, zero duplicates)

Called `stratified_sample(rows, n_abstention=250, n_non_abstention=250,
seed=42)` — the same `SAMPLE_SEED=42` and total budget (500) as AGENT-12's
original run, only the mix changed from the inherited ~63/37 split to an
exact 50/50:

```
sample size: 500, abstention: 250, non_abstention: 250
```
Zero duplicates confirmed by the same test suite's dedup assertions above,
run against this exact call.

## Balanced training run (real, this session)

Same hyperparameters as AGENT-12's original run, held fixed per the SYSTEM
CONTRACT — only the sample composition changed:
- Model: `Qwen/Qwen3-4B-Instruct-2507`, `BitsAndBytesConfig(load_in_4bit=True)`, `device_map="cpu"`
- LoRA: r=8, alpha=16, same `target_modules` (q/k/v/o/gate/up/down_proj)
- `MAX_STEPS=200`, `LOG_EVERY=10`, `per_device_train_batch_size=2`, `learning_rate=2e-4`
- Output: `backend/app/finetune/artifacts/smoke-adapter-balanced/` (distinct
  path — `smoke-adapter/` untouched)

Launched detached (`nohup ... & disown`), polled for the run to end, per the
AGENT-13-validated pattern rather than blocking a turn on it.

Real trainer tail:
```
{'loss': '0.1749', 'grad_norm': '0.5117', 'learning_rate': '1e-06', 'entropy': '0.1825', 'num_tokens': '3.77e+04', 'mean_token_accuracy': '0.9455', 'epoch': '0.8'}
{'train_runtime': '924.7', 'train_samples_per_second': '0.433', 'train_steps_per_second': '0.216', 'train_loss': '0.335', 'epoch': '0.8'}
```

Real logged loss sequence (20 points, step10..step200):
```
[2.538235092163086, 0.6231259346008301, 0.3097541809082031, 0.20596909523010254,
 0.2273564338684082, 0.21535141468048097, 0.20811853408813477, 0.20273475646972655,
 0.1966127872467041, 0.18573534488677979, 0.1782555937767029, 0.18467142581939697,
 0.18794693946838378, 0.1897106409072876, 0.17959003448486327, 0.18766283988952637,
 0.1740601897239685, 0.17040047645568848, 0.1603279232978821, 0.17493942975997925]
```
First logged (step 10) = 2.538, last logged (step 200) = 0.175 — a real
decrease, comparable in shape to AGENT-12's original run (2.519 -> 0.163),
neither flat nor non-decreasing.

## fact_ledger.md countermeasure check (real, re-verified against this artifact)

Ran the same two checks AGENT-12 used — PeftModel type check AND a real
weight-tensor diff against a freshly loaded, untouched base model — against
`smoke-adapter-balanced/` specifically, not assumed from AGENT-12's adapter:

```
isinstance(finetuned, PeftModel): True
any_diff: True diff_tensor_count: 252
FACT_LEDGER CHECK PASSED
```

## Balanced eval run (real, this session)

Reused `eval.py`'s existing step 1 (sanity), step 2 (152 held-out matchup
rows), and step 4 (237 abstention rows) scoring logic unmodified via import
— only the adapter load path and results path were pointed at this task's
artifacts. Step 3 (catastrophic-forgetting) was skipped per the task scope
— out of scope for the class-imbalance question. Launched detached
(`nohup ... & disown`) and polled for `eval_results_balanced.json` to
appear, rather than blocking a turn on the ~1-hour sweep.

Step 1 (sanity, real, PASSED):
```json
{
  "is_peft_model": true,
  "base_model_name_or_path": "Qwen/Qwen3-4B-Instruct-2507",
  "prompt": "What's the win rate for Aatrox into Kayle (top)?",
  "base_output": "No reliable win rate data available for Aatrox vs. Kayle in the top lane at this rank. Matchup performance is not well-documented or tracked for this specific top lane pairing across most ranks.",
  "adapted_output": "There isn't enough match data on this pairing for a confident read.",
  "generations_differ": true,
  "passed": true
}
```

**Step 2 — held-out matchup eval: 7/152 passed (4.6%)** — compared against
the original baseline's 0/152 (0.0%).

Real passing example (correctly stated a numeric win rate matching the
"roughly even" band):
```json
{"champ_a": "Annie", "champ_b": "Vex", "role": "middle", "real_win_rate": 0.5, "real_band": "roughly even", "model_output": "Annie wins 50.0% of games against Vex in middle across 2 tracked games this patch.", "extracted_pct": 50.0, "implied_band": "roughly even", "band_match": true, "numeric_within_10pts": true, "passed": true}
```
Real still-failing example (same Aatrox/Kayle row as the original baseline
report, still the fixed hedge phrase):
```json
{"champ_a": "Aatrox", "champ_b": "Kayle", "role": "top", "real_win_rate": 0.5, "real_band": "roughly even", "model_output": "There isn't enough match data on this pairing for a confident read.", "extracted_pct": null, "implied_band": null, "band_match": false, "numeric_within_10pts": false, "passed": false}
```

**Step 4 — abstention eval: 207/237 passed (87.3%)** — compared against the
original baseline's 237/237 (100.0%).

Real new-failure example (a genuinely thin-data pair the model now
fabricates a numeric answer for instead of abstaining):
```json
{"champ_a": "Anivia", "champ_b": "Galio", "role": "middle", "model_output": "Anivia wins 50.0% of games against Galio in middle across 2 tracked games this patch.", "contains_exact_phrase": false, "similarity_ratio": 0.18421052631578946, "close_paraphrase": false, "passed": false}
```

## Side-by-side comparison

| | Held-out matchup (of 152) | Abstention (of 237) |
|---|---|---|
| AGENT-12 baseline (~63/37 mix, `eval_results.json`) | 0/152 (0.0%) | 237/237 (100.0%) |
| AGENT-14 balanced (50/50 mix, `eval_results_balanced.json`) | 7/152 (4.6%) | 207/237 (87.3%) |

## Decision framework — real outcome

**Rebalancing helps** (the first case in the task's decision framework):
held-out pass rate moved meaningfully above 0% (0% -> 4.6%, real, not
rounding noise — 7 real held-out rows now produce a correctly banded,
correctly numeric win-rate statement instead of the fixed hedge phrase)
while abstention pass rate stayed reasonably high rather than collapsing
(100% -> 87.3%, still the dominant behavior on genuinely thin-data pairs,
not a crash toward 0%). This is real evidence that class imbalance was a
real contributing driver of the original collapse.

Read plainly, though: 4.6% is still a long way from a usable held-out pass
rate, and 12.7% of abstention rows now flip to fabricating a specific
number instead of hedging (the Anivia/Galio example above) — a real,
non-zero instance of the task's third case ("new failure mode:
over-answering"), just not severe enough here to call it the dominant
outcome, since 87.3% of abstention rows still pass. Both class imbalance
*and* insufficient step/epoch exposure look like real contributing factors
at this smoke scale: rebalancing moved the needle in the right direction
without fixing the underlying problem, which is consistent with 200 steps
over 500 examples simply not being enough exposure to teach a fine-grained
decision boundary regardless of mix (hypothesis (b) from the CONTEXT).

**Recommendation for the full-scale run:** fold stratified/balanced sampling
into the full-scale run's data prep — the direction of the effect is real
and positive — but do not expect balancing alone to close the gap. The
revised hypothesis for the full-scale run is that the real lever is *both*
levers together: a more balanced mix, run over more steps/epochs on the
full ~2,213-row dataset with real GPU hardware, rather than either change
in isolation.

## Files

- `backend/app/finetune/train.py` (additive: `stratified_sample`,
  `run_training(rows=, output_dir=)` — default uniform-sample path
  unchanged)
- `backend/tests/unit/test_stratified_sample.py`
- `backend/app/finetune/artifacts/smoke-adapter-balanced/`
- `backend/app/finetune/artifacts/eval_results_balanced.json`
- `docs/decisions/phase2-class-balance-diagnostic.md` (this file)
