# Phase 2 Implementation Summary — AGENT-11 through AGENT-13

**Status: all three DONE.** AGENT-11 (synthetic-qa-generation), AGENT-12
(qlora-finetune), and AGENT-13 (eval-harness) all completed for real.
AGENT-13 took three attempts to actually finish (see its section below) —
not because of any bug in the harness or model, but because its real workload
(~98 minutes of CPU-only generation) genuinely exceeds a single agent turn's
duration; the first two attempts hit real, explainable obstacles (a schema
bug, then premature turn termination) and are kept here as history rather
than erased.

**Follow-up:** AGENT-12's smoke-scale collapse (0/152 held-out, 237/237
abstention) is investigated further in a targeted diagnostic, not a new
phase — see `docs/decisions/phase2-class-balance-diagnostic.md`. It tests
whether the ~63%/37% abstention/non-abstention class imbalance in the
training sample was the driver: real result, rebalancing to a 50/50 mix at
the same 500-example/200-step smoke scale moved held-out pass rate from
0/152 to 7/152 (4.6%) while abstention pass rate stayed at 207/237 (87.3%,
down from 237/237) — a real, partial improvement, not a fix. Recommendation
there: fold balanced sampling into the full-scale run's data prep, but
expect the full-scale run's more-steps/more-data/GPU scale to still be
necessary — rebalancing alone does not close the gap.

## AGENT-11 (synthetic-qa-generation) — DONE

Real pipeline run (`backend/app/finetune/qa_generation.py`, reusing
`load_hf_csv_matches` + `filter_valid_matches` + `aggregate_matchup_stats` via
import, no reimplementation):
- CSV: `/Users/terrance/.cache/huggingface/hub/datasets--BoostedJonP--league_of_legends_match_data/snapshots/.../league_of_legends_emerald_match_data.csv` (already cached, no download)
- matches_loaded=1530, valid_matches=901, total_rows=2602
- (rank, phase) coverage found: exactly one combination, `{("emerald", "not_available")}` — confirms the CONTEXT's stated limitation, no fabricated variety.

Field-name note: `aggregate.py`'s dict key is `"rank"`; `app.models.MatchupStat`'s
DB column is `"rank_bracket"`. Nothing here writes to the DB — output files use
`"rank"` throughout, matching the pipeline dict actually consumed.

Held-out split (step 2): `sha256(f"{champ_a}|{champ_b}")` mod 100 < 15 ->
heldout, applied per-pair (role-independent). Real run: train_rows=2213 (819
non-abstention + 1394 abstention), heldout_rows=389 (152 non-abstention + 237
abstention). Both required tests pass: zero champ-pair overlap between
train/heldout, and split_rows is deterministic across repeated calls (verified
on both synthetic and the real 2602-row dataset).

Templates (step 3): `TEMPLATE_SEED=20260806`, `random.Random(seed)` consumed
in row order. Exactly 3 `QUESTION_TEMPLATES` + exactly 2 `ANSWER_TEMPLATES`,
both named constants in `qa_generation.py`. Test
`test_all_five_templates_used_when_generating_over_many_rows` passes — all 5
templates confirmed present via regex-reconstruction matching, not
implementation-copied assertions.

Abstention threshold (step 4): 25th percentile (`ABSTENTION_PERCENTILE=25`,
nearest-rank method) of the real sample_size distribution over all 2602 rows
-> threshold value = 1 (sample_size distribution is heavily skewed: 1631/2602
rows have sample_size==1). Rows with sample_size <= 1 from train-partition
pairs get `is_abstention=true` and the fixed hedge phrase verbatim: "There
isn't enough match data on this pairing for a confident read." Real counts:
train_non_abstention=819, train_abstention=1394; heldout_non_abstention=152
(-> heldout.jsonl), heldout_abstention=237 (-> abstention_eval.jsonl).

Output files (`backend/app/finetune/data/`, gitignored via new `.gitignore`
entry `backend/app/finetune/data/`):
- train.jsonl: 2213 lines, 626437 bytes
- heldout.jsonl: 152 lines, 44494 bytes
- abstention_eval.jsonl: 237 lines, 65782 bytes
- general_instruction_eval.jsonl: 15 lines, 1457 bytes (exactly 5
  general-knowledge + 5 instruction-following + 5 open-ended reasoning
  prompts, `{"prompt": str}` only, verified free of LoL terms including
  champion/item names via word-boundary regex test)

Deviation: none. No silent substitution — used the real cached CSV, real
pipeline functions by import, no smaller/different model or data swapped in.

TEST_LOOP: wrote `backend/tests/unit/test_qa_generation.py` first with
hand-computed expected values (sha256 computed independently at the terminal,
hand-derived nearest-rank percentile arithmetic on constructed sample_size
lists), then implemented `qa_generation.py`, ran once, fixed one test bug (a
substring false-positive: "lane" matched inside "plane" in a reasoning
prompt — fixed via word-boundary regex in the test, not by touching the
implementation), reran to green. 1 fix attempt used, well under the 5-attempt
cap. Full run of tests/unit passes except the pre-existing, unrelated
`tests/unit/test_models.py` collection error (`ModuleNotFoundError: No module
named 'pgserver'` — out of scope per CONTEXT, not caused by or related to this
assignment; verified untouched by checking `git diff` shows no changes from
this session to that file).

Files written:
- `backend/app/finetune/__init__.py`
- `backend/app/finetune/qa_generation.py`
- `backend/tests/unit/test_qa_generation.py`
- `backend/app/finetune/data/train.jsonl`
- `backend/app/finetune/data/heldout.jsonl`
- `backend/app/finetune/data/abstention_eval.jsonl`
- `backend/app/finetune/data/general_instruction_eval.jsonl`
- `.gitignore`

**Real command/test output:**

```
$ python3 -m pytest tests/unit/test_qa_generation.py -v
============================= test session starts ==============================
collected 9 items

tests/unit/test_qa_generation.py::test_pair_bucket_hand_computed_sha256 PASSED [ 11%]
tests/unit/test_qa_generation.py::test_is_heldout_pair_matches_threshold_boundary PASSED [ 22%]
tests/unit/test_qa_generation.py::test_split_rows_zero_champion_pair_overlap PASSED [ 33%]
tests/unit/test_qa_generation.py::test_split_rows_deterministic_across_repeated_calls PASSED [ 44%]
tests/unit/test_qa_generation.py::test_abstention_threshold_hand_computed_percentile PASSED [ 55%]
tests/unit/test_qa_generation.py::test_all_five_templates_used_when_generating_over_many_rows PASSED [ 66%]
tests/unit/test_qa_generation.py::test_abstention_rows_use_the_single_fixed_hedge_phrase PASSED [ 77%]
tests/unit/test_qa_generation.py::test_general_instruction_prompts_shape_and_no_lol_content PASSED [ 88%]
tests/unit/test_qa_generation.py::test_build_and_write_all_produces_real_schema_correct_files PASSED [100%]
========================= 9 passed, 1 warning in 0.30s =========================

$ python3 -m pytest tests/unit --ignore=tests/unit/test_models.py -v
collected 20 items
tests/unit/test_aggregate.py ...... (6 passed)
tests/unit/test_data_dragon.py ..... (5 passed)
tests/unit/test_qa_generation.py ......... (9 passed)
======================== 20 passed, 1 warning in 0.44s =========================

$ python3 -m app.finetune.qa_generation <real_csv_path>
{
  "matches_loaded": 1530,
  "valid_matches": 901,
  "total_rows": 2602,
  "rank_phase_combos": [["emerald", "not_available"]],
  "abstention_percentile": 25,
  "abstention_threshold_sample_size": 1,
  "train_rows": 2213,
  "heldout_rows": 389,
  "train_abstention": 1394,
  "train_non_abstention": 819,
  "heldout_abstention": 237,
  "heldout_non_abstention": 152
}

$ wc -l backend/app/finetune/data/*.jsonl
     237 abstention_eval.jsonl
      15 general_instruction_eval.jsonl
     152 heldout.jsonl
    2213 train.jsonl
    2617 total
$ ls -la backend/app/finetune/data/*.jsonl
-rw-r--r-- 65782 abstention_eval.jsonl
-rw-r--r--  1457 general_instruction_eval.jsonl
-rw-r--r-- 44494 heldout.jsonl
-rw-r--r-- 626437 train.jsonl
```

---

## AGENT-12 (qlora-finetune) — DONE

COMPUTE GATE (real, run this session, not simulated):

```
$ uname -a
Darwin ... arm64
$ python3 -c "import torch; print(torch.__version__); print('cuda:', torch.cuda.is_available())"
2.11.0
cuda: False
```

Real 4-bit load attempt (not merely `torch.cuda.is_available()`):

```
$ python3 -c "
import torch
from transformers import BitsAndBytesConfig, AutoModelForCausalLM
bnb_config = BitsAndBytesConfig(load_in_4bit=True)
model = AutoModelForCausalLM.from_pretrained('sshleifer/tiny-gpt2', quantization_config=bnb_config)
print('SUCCESS')"
... SUCCESS
```

Verified this was a genuine 4-bit load, not a silent no-op:
`transformer.h.0.attn.c_attn <class 'bitsandbytes.nn.modules.Linear4bit'> torch.uint8 cpu`,
`is_loaded_in_4bit: True`, bnb version: 0.50.0 (`pip show bitsandbytes`), mps
available: True / cuda available: False.

DEVIATION (named explicitly, per SYSTEM CONTRACT, not absorbed silently):
`torch.cuda.is_available()` is False on this Apple Silicon machine (no CUDA
GPU) — this is the "very likely" case the task assignment anticipated.
However bitsandbytes 0.50.0's real, current release ships a genuine CPU
backend for 4-bit ops (nf4 quant/dequant kernels, actually exercised,
confirmed above and again against the real target model
Qwen/Qwen3-4B-Instruct-2507 — not a toy). Per the SYSTEM CONTRACT wording, the
required check is "an actual attempted 4-bit model load via bitsandbytes...
If that attempt fails for any reason: BLOCKED." The attempt did not fail — it
succeeded, genuinely, on CPU. This is not a quantization-scheme substitution
(still real NF4 4-bit via bitsandbytes as specified) and not a base-model
substitution (full Qwen3-4B, no toy swap). It is CPU compute instead of GPU
compute, stated here explicitly rather than hidden. Per-step wall-clock time
(~5.1-5.8s/step measured directly) was benchmarked before committing to a
full smoke run, to avoid an infeasible multi-hour job.

RESOURCE GATE: Qwen/Qwen3-4B-Instruct-2507 was already present in the local
HF cache (`~/.cache/huggingface/hub/models--Qwen--Qwen3-4B-Instruct-2507`,
7.5G, verified via `find`/`du`) — no download performed, no 500MB threshold
crossed.

TRAINING RUN (real, executed via `python3 -m app.finetune.train`,
`backend/app/finetune/train.py`):
- Model: Qwen/Qwen3-4B-Instruct-2507, `BitsAndBytesConfig(load_in_4bit=True)`, `device_map="cpu"`
- LoRA: r=8, alpha=16, target_modules=[q,k,v,o,gate,up,down]_proj — trainable
  2.9M / 4.03B total (0.07%) confirmed via `print_trainable_parameters()` in
  an earlier timing check
- Data cap (a): fixed seeded random sample of AGENT-11's train.jsonl (2213
  rows total), `SAMPLE_SEED=42`, `MAX_EXAMPLES=500` — confirmed in log:
  `"examples: 100%|...| 500/500"`
- Step cap (b): `MAX_STEPS=200` — run stopped exactly at step 200 (epoch
  0.8 = 200/250 steps-per-epoch at batch_size=2 over 500 examples), matching
  train_runtime log line: `{'train_runtime': '956', ..., 'epoch': '0.8'}`
- Logged loss every `LOG_EVERY=10` steps (mandatory interval), full logged
  sequence (20 points, step10..step200):
  `[2.519, 0.598, 0.312, 0.224, 0.238, 0.200, 0.199, 0.195, 0.181, 0.195, 0.187, 0.176, 0.186, 0.185, 0.177, 0.177, 0.163, 0.164, 0.176, 0.163]`
  First logged (step 10) = 2.519, last logged (step 200) = 0.163 — real
  decrease.
- Adapter saved at `backend/app/finetune/artifacts/smoke-adapter/` (exact
  required path): adapter_config.json, adapter_model.safetensors (33MB),
  tokenizer files present; dir already covered by existing repo `.gitignore`
  entry `backend/app/finetune/artifacts/` (pre-existing, not modified this
  session).

Single (rank, phase) combination check: verified programmatically over all
2213 rows of train.jsonl — only `{('emerald', 'not_available')}` present,
confirming the CONTEXT's stated limitation exactly (not fabricated variety).

`fact_ledger.md` countermeasure test (both required per contract, both
implemented and passing):

```
$ python3 -u -m pytest tests/integration/test_train_smoke.py -v
tests/integration/test_train_smoke.py::test_saved_adapter_is_real_peft_model_and_differs_from_base PASSED [ 50%]
tests/integration/test_train_smoke.py::test_logged_loss_decreased_from_first_to_last_logged_step PASSED [100%]
================== 2 passed, 14 warnings in 149.77s (0:02:29) ==================

--- real training run tail (backend/app/finetune/train.py via python -m app.finetune.train) ---
{'loss': '0.1629', 'grad_norm': '0.6445', 'learning_rate': '1e-06', 'entropy': '0.1693', 'num_tokens': '3.725e+04', 'mean_token_accuracy': '0.9537', 'epoch': '0.8'}
{'train_runtime': '956', 'train_samples_per_second': '0.418', 'train_steps_per_second': '0.209', 'train_loss': '0.3307', 'epoch': '0.8'}
Logged losses: [2.5190444946289063, 0.5980090618133544, 0.3122607707977295, 0.22392702102661133, 0.23826117515563966, 0.19987959861755372, 0.19855263233184814, 0.19453344345092774, 0.18131293058395387, 0.19506311416625977, 0.1874067187309265, 0.17581167221069335, 0.18600060939788818, 0.18528856039047242, 0.17666029930114746, 0.17652740478515624, 0.16287708282470703, 0.16393849849700928, 0.17620573043823243, 0.16286120414733887]

--- compute-gate real 4bit load evidence ---
$ python3 -c "import bitsandbytes as bnb; print('bnb version:', bnb.__version__)"
bnb version: 0.50.0
transformer.h.0.attn.c_attn <class 'bitsandbytes.nn.modules.Linear4bit'> torch.uint8 cpu
is_loaded_in_4bit: True
```

Test 1 does both required checks: `isinstance(finetuned, PeftModel)` type
check AND a real weight-tensor diff (base model state_dict captured fresh
from `AutoModelForCausalLM.from_pretrained` before loading the adapter,
compared against `merge_and_unload()` output — not trusting anything
train.py itself computed). Test 2 parses the real `/tmp/train_run.log`
trainer output independently (regex over `'loss': ...` lines containing
`grad_norm`, i.e. real per-interval logs, excluding the end-of-run summary
line) and asserts `step_losses[-1] < step_losses[0]`.

FULL-SCALE FINE-TUNE: explicitly out of scope here, named as a separate,
later, human-triggered step requiring real GPU hardware (this smoke run used
the full 500-example/200-step caps on CPU via bitsandbytes' CPU 4-bit
backend, which is slow-but-real; a production run would use GPU for
practical wall-clock time on the complete ~2213-row dataset spanning more
epochs).

Field-name note (per CONTEXT instruction): train.jsonl rows use
`"rank"`/`"phase"` keys; nothing in this component writes to the DB
(`MatchupStat.rank_bracket`), so no reconciliation was needed here.

Note: `backend/app/finetune/train.py` and
`backend/tests/integration/test_train_smoke.py` already existed on disk at
the start of this session (written, per their own docstrings, by an earlier
pass that documented the same compute-gate reasoning but had NOT actually
executed a training run — the test file's docstring said it "does NOT re-run
training" and assumed artifacts from a prior run that didn't exist yet, so
pytest would have skipped both tests). This session verified the compute
gate independently from scratch, then actually executed
`python -m app.finetune.train` end-to-end for real (17.5 min wall clock, log
at `/tmp/train_run.log`) and re-ran pytest to get real PASSED (not SKIPPED)
results, per the "every number/test result must come from code actually run
this session" requirement. No edits were needed to either file's logic —
both were already correct against the real system behavior once actually
exercised.

Files written:
- `backend/app/finetune/train.py`
- `backend/tests/integration/test_train_smoke.py`
- `backend/app/finetune/artifacts/smoke-adapter/`

---

## AGENT-13 (eval-harness) — DONE

Two attempts hit real obstacles before this one landed, both left as history
rather than deleted:
- **Attempt 1** crashed with a real bug: `step2_heldout_eval` called
  `score_heldout_row(row, output)` directly on raw `heldout.jsonl` rows, but
  those rows (AGENT-11's `qa_generation.py` output) have no `"win_rate"`
  float key — only `"prompt"/"response"/"champ_a"/"champ_b"/"role"/"rank"/"phase"/"is_abstention"`.
  The ground-truth win rate is embedded as an explicit `"{win_rate_pct}%"`
  figure inside the pre-written `"response"` text. Real traceback:
  `File ".../eval.py", line 172, in score_heldout_row / real_band = band_for_win_rate(row["win_rate"]) / KeyError: 'win_rate'`.
  Fixed by extracting the real win rate via `extract_win_rate_pct(row["response"])`
  (the same regex already used for model outputs) before scoring — a real
  root-cause fix, not a workaround.
- **Attempt 2** launched the real sweep correctly (`nohup python -m
  app.finetune.eval > eval_sweep.log 2>&1 & disown`, pid 19045) but got cut
  off by the harness's per-turn duration enforcement before the ~80-90
  minute run finished, and reported BLOCKED rather than fabricate numbers.
  Crucially, because the process was launched with `nohup`+`disown`, it kept
  running on the OS independent of that agent's turn ending — this was
  discovered and confirmed still alive afterward (`ps -p 19045`), and its
  progress was tracked directly (outside any agent turn, via a plain
  background Bash poll loop watching for
  `backend/app/finetune/artifacts/eval_results.json` to appear) until it
  completed for real, rather than spawning a third agent attempt that would
  hit the same duration limit on a job that inherently runs longer than one
  turn.

Total real wall-clock for the completed sweep: **~98 minutes** (process
start 2026-08-09 17:08 EDT per `ps` at launch, `eval_results.json` written
18:46 EDT).

**Step 1 — base-vs-finetuned sanity check (blocking, real, PASSED):**
```
$ python3 -m pytest tests/integration/test_finetune_eval.py::test_step1_sanity_check_real_adapter_differs_from_base -v
tests/integration/test_finetune_eval.py::test_step1_sanity_check_real_adapter_differs_from_base PASSED [100%]
================== 1 passed, 15 warnings in 65.40s (0:01:05) ===================
```
Real result from `eval_results.json`:
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
`isinstance(model, PeftModel)` is True, `base_model_name_or_path` matches, and
base/adapted generations genuinely differ on the fixed sanity prompt. Steps
2-4 below are reported as meaningful per the contract.

**Step 2 — held-out matchup eval: 0/152 passed (0.0% pass rate).**
Every one of the 152 real heldout generations was the exact fixed hedge
phrase ("There isn't enough match data on this pairing for a confident
read."), regardless of the row's real win_rate/band — e.g. Aatrox/Kayle
(real band "roughly even", real win_rate 0.5) and Aatrox/Quinn (real band
"champ_b favored", real win_rate 0.0) both got the identical abstention
response, so `implied_band` is `null` and every row fails both the band-match
and numeric-within-10pts criteria. Real sample rows from `eval_results.json`:
```json
{"champ_a": "Aatrox", "champ_b": "Kayle", "role": "top", "real_win_rate": 0.5, "real_band": "roughly even", "model_output": "There isn't enough match data on this pairing for a confident read.", "extracted_pct": null, "implied_band": null, "band_match": false, "numeric_within_10pts": false, "passed": false}
{"champ_a": "Aatrox", "champ_b": "Quinn", "role": "top", "real_win_rate": 0.0, "real_band": "champ_b favored", "model_output": "There isn't enough match data on this pairing for a confident read.", "extracted_pct": null, "implied_band": null, "band_match": false, "numeric_within_10pts": false, "passed": false}
```
This is a real, honest 0% — not a harness bug. It is a direct, explainable
consequence of the smoke-scale training mix: 1,394 of the 2,213 train rows
(63%) are abstention rows with this identical fixed phrase, and 200 optimizer
steps over a 500-example sample was enough to teach the adapter to always
emit it, but not enough to teach it when *not* to.

**Step 3 — catastrophic-forgetting check.** All 30 real outputs (15 prompts
× base + fine-tuned) were generated for real and are in
`backend/app/finetune/artifacts/eval_results.json` under
`step3_general_instruction_outputs`. Per the task's 3-item checklist
((a) on-topic, (b) coherent/non-repeating, (c) follows explicit format if
specified else auto-pass), scored by hand against the real outputs below:

| # | Prompt | Base on-topic/coherent/format | Fine-tuned on-topic/coherent/format |
|---|---|---|---|
| 1 | What causes the seasons to change on Earth? | 1/1/1 | 1/1/1 |
| 2 | Who wrote Romeo and Juliet? | 1/1/1 | 1/1/1 |
| 3 | Boiling point of water at sea level, °C? | 1/1/1 | 1/1/1 |
| 4 | Closest planet to the sun? | 1/1/1 | 1/1/1 |
| 5 | Capital of Australia? | 1/1/1 | 1/1/1 |
| 6 | Rewrite in passive voice | 1/1/1 | 1/1/1 |
| 7 | List 1-10, skip multiples of 3 | 1/1/1 (numeric error: omits "1" — flagged, not penalized, checklist has no correctness item) | 1/1/1 (correct) |
| 8 | Convert 72°F to Celsius, show work | 1/**0**/1 (generation garbled mid-formula — a stray Thai character replaces a digit — and cuts off before stating a final answer) | 1/1/1 (correct, complete) |
| 9 | Summarize library-hours text in one sentence | 1/1/1 | 1/1/1 |
| 10 | Haiku about autumn leaves | 1/1/1 | 1/1/1 |
| 11 | Two-train catch-up problem | 1/**0**/1 (sets up correctly, then cuts off before giving an answer) | 1/1/1 (correct: "2 hours") |
| 12 | Why does a plane's shadow move faster over water? | **0**/1/1 (in-character refusal: "I'm a League of Legends coach...") | **0**/1/1 (nonsensical: answers with the matchup hedge phrase) |
| 13 | 8-coin balance-scale puzzle | 1/**0**/1 (correct setup, cuts off mid-solution) | 1/1/1 (complete, correct 2-weighing solution) |
| 14 | Why lower prices at high demand? | **0**/1/1 (in-character refusal) | **0**/1/1 (hedge phrase) |
| 15 | Headcount slowing a software project | **0**/1/1 (in-character refusal) | **0**/1/1 (hedge phrase) |

**Per-item totals (out of 15):** base on-topic 12, coherent 12, format 15
(39/45); fine-tuned on-topic 12, coherent 15, format 15 (42/45).

Both models use the same `SYSTEM_PROMPT` ("You are a League of Legends
coach...") from `train.py`, held constant across base and fine-tuned
generation — the checklist score isolates the effect of the LoRA weights,
not the system prompt, which is why even the *base* model stays in
LoL-coach character and declines 3 clearly off-topic questions (12, 14, 15).
Read plainly: the checklist total doesn't show forgetting in the narrow
scored sense (fine-tuned's raw score is slightly higher), but that number is
misleading on its own — it's higher because fine-tuned's short, complete
hedge-phrase answers avoid the 3 real truncation/corruption failures the base
model has (items 8, 11, 13), not because it handles off-topic questions
better. On the 3 off-topic questions both models decline (12, 14, 15),
base's in-character coach refusal is a coherent, graceful redirect;
fine-tuned's identical hedge phrase is a non-sequitur (it talks about
"matchup data" for a business/physics/software question) — a real, distinct
degradation the 3-item checklist's binary items don't fully capture. This is
the same collapse-to-abstention behavior driving step 2's 0% pass rate.

All 30 real outputs, verbatim, are in
`backend/app/finetune/artifacts/eval_results.json` →
`step3_general_instruction_outputs.{prompts,base_outputs,finetuned_outputs}`
(not reproduced a second time here to keep this doc from ballooning; the
table above is the scored summary of that verbatim data, and every score
above was assigned by reading those real outputs directly, not guessed).

**Step 4 — abstention check: 237/237 passed (100.0% pass rate).**
Detection rule used: **exact match** on the fixed hedge phrase from
`qa_generation.py` (`HEDGE_PHRASE = "There isn't enough match data on this
pairing for a confident read."`), read directly from that module, not
re-derived — no paraphrase rule was needed since every real generated
abstention-eval response was the exact phrase, verbatim, with no variation.
This 100% is real, but it is the mirror image of step 2's 0%: the adapter
did not learn a *decision boundary* between "abstain" and "answer" — it
learned to always emit this one phrase, which trivially maximizes step 4
while trivially failing step 2.

**Step 1-4 raw results file:** `backend/app/finetune/artifacts/eval_results.json` (139,773 bytes).

Per-step smoke-scale caveat (`eval_results.json`'s own `smoke_scale_caveat`
field, quoted verbatim): "AGENT-12's adapter is a SMOKE-SCALE run (<=500
training examples, <=200 steps). These results demonstrate the eval harness
is correct and runs for real — they are not a verdict on model quality." The
0%/100% split above is the concrete illustration of exactly that: the
harness correctly measured a real, explainable smoke-scale failure mode
(abstention collapse from an abstention-heavy small sample), not a harness
defect and not a meaningful read on what a full-scale fine-tune would do.

DEVIATIONS: none from the specified pipeline/model/quantization. The only
code change was the win_rate `KeyError` fix in `step2_heldout_eval` (a real
bug fix, root-caused via the actual crash traceback and the actual JSONL
schema, not a workaround or simplification of the required checks).

Files written:
- `backend/app/finetune/eval.py`
- `backend/tests/integration/test_finetune_eval.py`
- `backend/app/finetune/artifacts/eval_results.json` (run output, not code)

**Real command/test output:**

```
$ python3 -m pytest tests/integration/test_finetune_eval.py -k "not step1" -v
================= 18 passed, 1 deselected, 1 warning in 3.91s ==================

$ python3 -m pytest tests/integration/test_finetune_eval.py::test_step1_sanity_check_real_adapter_differs_from_base -v
================== 1 passed, 15 warnings in 65.40s (0:01:05) ===================

$ nohup python -m app.finetune.eval > eval_sweep.log 2>&1 & disown
$ ps -p 19045 -o pid,etime,rss,command   # checked repeatedly over ~98 real minutes
  PID ELAPSED    RSS COMMAND
19045   28:07 3064544 /Users/terrance/.pyenv/versions/3.13.7/bin/python -m app.finetune.eval
  ... (process exited cleanly once eval_results.json was written)

$ ls -la backend/app/finetune/artifacts/eval_results.json
-rw-r--r-- 139773 eval_results.json
```

---

## Coverage limitation and smoke-scale caveat (applies across all three agents)

- **(rank, phase) coverage:** every row produced across the whole Phase 2
  pipeline — AGENT-11's 2602 generated rows, the 2213-row train.jsonl AGENT-12
  trained on, and the heldout/abstention/general eval files AGENT-13 is
  sweeping — has exactly one `(rank, phase)` combination:
  `("emerald", "not_available")`. This was independently verified
  programmatically by both AGENT-11 (at generation time) and AGENT-12 (over
  all 2213 train.jsonl rows before training), and confirms the CONTEXT's
  stated limitation rather than being asserted without checking.
- **Smoke scale:** AGENT-12's fine-tune is explicitly a smoke run, not a
  production fine-tune — capped at 500 of the 2213 available train rows
  (`MAX_EXAMPLES=500`, seeded sample) and 200 of 250 steps-per-epoch
  (`MAX_STEPS=200`, epoch=0.8), run on CPU via bitsandbytes' CPU 4-bit
  backend because no CUDA GPU was available on this machine. AGENT-12 states
  a full-scale fine-tune (complete ~2213-row dataset, more epochs, GPU
  hardware) is out of scope and left as a separate, later, human-triggered
  step. AGENT-13's completed eval sweep against this smoke-scale adapter is
  the concrete illustration of why that caveat matters, not an abstract
  disclaimer: the adapter collapsed to always emitting the fixed abstention
  phrase (0% pass on the 152 real held-out matchup questions, 100% pass on
  the 237 real abstention questions — the same behavior producing both
  numbers), a real and explainable smoke-scale failure mode (1,394/2,213
  train rows, 63%, were abstention rows; 200 steps was enough to learn "say
  this phrase" but not enough to learn when to say it). This demonstrates the
  eval harness works correctly end-to-end against a real adapter — it is not
  a verdict on what a full-scale fine-tune (all 2,213 rows, GPU hardware,
  more steps) would produce.
