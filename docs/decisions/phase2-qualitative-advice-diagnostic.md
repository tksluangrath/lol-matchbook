# Phase 2 Qualitative-Advice Diagnostic — AGENT-20/21/22

**Status: DONE** (all three agents, full chain).

Tests whether the fine-tune that already solved the numeric win-rate task
(100%/100%, `docs/decisions/phase2-context-conditioning-diagnostic.md`) can
also produce the actual product deliverable — grounded early/mid/late-game
strategic advice, not just a cited number — and whether teaching that
degrades the numeric skill.

`git pull` on `main` before starting: `Already up to date.` No conflicts.

## AGENT-20 (qualitative-advice-data-generation) — DONE

Added `select_pairs`, `fetch_champion_detail`, `win_rate_context_block`,
`real_win_rate_pct`, `build_generation_prompt`, `fact_grounding_check` to
`backend/app/finetune/qualitative_advice.py`. Reused
`app.retrieval.index.champion_text()` (real, unmodified) for kit text and
the win-rate context-block format validated in the prior diagnostic
(extracted verbatim from an existing `train_context.jsonl`/
`heldout_context.jsonl` row's prompt, not reconstructed).

Wrote `backend/tests/unit/test_qualitative_advice.py` first:
```
$ python3 -m pytest tests/unit/test_qualitative_advice.py -v
9 passed in 4.26s
```
9/9 passed on the first implementation.

Real, deterministic pair selection: sorted `(champ_a, champ_b)` pairs from
`train_context.jsonl`/`heldout_context.jsonl`, first 40 / first 10. Real
Data Dragon detail fetches (same endpoint/pattern as
`test_retrieval_index.py`): **51/51 unique champions fetched successfully**
in 10.2s.

### A real bug found and fixed mid-diagnostic (self-correction protocol)

The first real generation run (base Qwen3-4B-Instruct, one candidate blurb
per pair, `max_new_tokens=260`) produced **9/40 train, 1/10 heldout** kept
by the grounding filter — a majority-discarded result. Inspecting the real
discarded text (e.g. Aatrox/Ambessa, flagged for inventing `"If Ambessa"`)
showed this was not the model inventing specifics: the sentence was
"...especially **if Ambessa** is caught off-guard," capitalized only
because it followed a period. All 10 real discarded examples sampled
failed for the exact same reason (a sentence-initial common word + the
pair's own champion name). This is a bug in `fact_grounding_check`'s regex
(it didn't exclude ordinary English sentence-starters), not a real
grounding failure — verified by adding
`test_fact_grounding_check_does_not_flag_sentence_initial_conditional_plus_champion_name`
(using this exact real failure as the hand-derived case) and a
`_NON_ABILITY_LEAD_WORDS` exclusion list, then re-scoring the 10 real
discarded examples with the fix: **10/10 now pass**.

```
$ python3 -m pytest tests/unit/test_qualitative_advice.py -v
10 passed in 4.51s
```

Per the task's explicit halt-condition guidance ("regenerating would take
another ~4h... confirmed real evidence the discards were a filter bug, not
genuine hallucination"), the user chose to regenerate the full batch with
the fixed filter rather than proceed on the buggy 9/1 result. Real
regenerated result:

```
train_generated: 40, train_kept: 40, train_discarded: 0
heldout_generated: 10, heldout_kept: 10, heldout_discarded: 0
```

**40/40 train, 10/10 heldout kept** — exact target counts, all real,
grounding-filter-passing generations from the base model. No row was
backfilled or the filter loosened to hit the target; the full count was
achieved because the underlying generations were grounded all along and
the corrected filter now recognizes that.

Real example row (`qualitative_advice_train.jsonl`):
```json
{"champ_a": "Aatrox", "champ_b": "Ambessa", "role": "top", "context": "Context: 1 game observed this patch between Aatrox and Ambessa in the top lane. Aatrox win rate: 100%.\nAatrox kit: Aatrox\n...\nDeathbringer Stance: Periodically, Aatrox's next basic attack deals bonus magic damage and heals him...\n...", "response": "Early: Aatrox's Deathbringer Stance and the passive healing from damaging enemies give him a strong early presence. Ambessa's Drakehound's Step is situational...\nMid: Ambessa's Cunning Sweep and Repudiation offer strong crowd control...\nLate: ..."}
```

## AGENT-21 (qualitative-advice-smoke-train) — DONE

Combined the 40 real qualitative rows (remapped `context`→`prompt`, response
unchanged) with the existing, unmodified `stratified_sample(win_rate_rows,
n_abstention=250, n_non_abstention=250, seed=42)` from
`train_context.jsonl` — **540 rows total (500 win-rate + 40 qualitative)**.
Trained via the existing `run_training`, same LoRA config (r=8, alpha=16,
`[q,k,v,o,gate,up,down]_proj`), same `max_steps=200` — no step-count or
LoRA-rank change to compensate for the added task, per the task contract
(whether 200 steps suffices for both tasks together is itself part of what
this measures).

Real logged loss sequence (20 points, step10..step200):
```
[2.5028732299804686, 0.48996877670288086, 0.5343997001647949, 0.1764174222946167,
 0.6675816535949707, 0.16645020246505737, 0.14395906925201415, 0.2761424779891968,
 0.2816005706787109, 0.6175704002380371, 0.14028366804122924, 0.22423641681671141,
 0.664580249786377, 0.4216099739074707, 0.4308295726776123, 0.1984189510345459,
 0.3028663158416748, 0.2195967197418213, 0.19421703815460206, 0.37351796627044676]
```
First logged (step 10) = 2.503, last logged (step 200) = 0.374 — a real
decrease, but noticeably noisier than the single-task diagnostics (which
settled smoothly under 0.2): loss repeatedly spikes back up to 0.4-0.67
mid-run. This is a real, visible symptom of training on two structurally
different response styles (short win-rate sentences vs. long structured
advice) in the same small step budget, not a bug in the run.

fact_ledger.md check, re-verified against this specific new adapter:
```
$ python3 -m pytest tests/integration/test_qualitative_adapter_fact_ledger.py -v
test_qualitative_adapter_is_real_peft_model_and_differs_from_base PASSED [ 50%]
test_qualitative_adapter_logged_loss_decreased_from_first_to_last_logged_step PASSED [100%]
================== 2 passed, 14 warnings in 139.16s (0:02:19) ==================
```

## AGENT-22 (qualitative-advice-eval) — DONE

Generated real advice for all 10 `qualitative_advice_heldout.jsonl` pairs
from `smoke-adapter-qualitative`, scored against three real pass/fail
criteria (sections present, fact-grounding, win-rate within 10pts). Reran
`eval.py`'s steps 2 and 4 (unmodified scoring logic) against
`heldout_context.jsonl`/`abstention_eval_context.jsonl` for the regression
check.

### Qualitative held-out result: 0/10 passed

Every one of the 10 real generations failed on the exact same criterion —
**no labeled Early:/Mid:/Late: sections at all** — despite the prompt
explicitly instructing the model to produce them. Grounding and win-rate
accuracy were never the problem: all 10 passed grounding (0 invented
phrases) and all 10 cited win rates within 10 points of the real value.

All 10 real outputs, verbatim:
```
Aatrox/Kayle:       "Aatrox wins 50.0% of games against Kayle in top across 4 tracked games this patch."
Aatrox/Quinn:       "Based on 2 recorded top games, Aatrox has a 0.0% win rate versus Quinn."
Aatrox/Vladimir:    "Based on 3 recorded top games, Aatrox has a 33.3% win rate versus Vladimir."
Ahri/AurelionSol:   "Ahri wins 50.0% of games against AurelionSol in middle across 2 tracked games this patch."
Ahri/Lissandra:     "Ahri wins 0.0% of games against Lissandra in middle across 2 tracked games this patch."
Ahri/Naafiri:       "Ahri wins 50.0% of games against Naafiri in middle across 2 tracked games this patch."
Ahri/Sylas:         "Ahri wins 50.0% of games against Sylas in middle across 4 tracked games this patch."
Ahri/Xerath:        "Ahri wins 66.7% of games against Xerath in middle across 3 tracked games this patch."
Akali/Renekton:     "Akali wins 0.0% of games against Renekton in top across 2 tracked games this patch."
Akali/Talon:        "Based on 2 recorded middle games, Akali has a 100.0% win rate versus Talon."
```
Every single one is verbatim (modulo the filled-in numbers) one of
`qa_generation.py`'s two `ANSWER_TEMPLATES` — the exact win-rate-restating
template the 500-row majority task trained. Given a qualitative-advice
prompt (win-rate context + two real kit-context blocks + an explicit
instruction to write three labeled sections), the model ignored the
instruction and the kit context entirely and produced the numeric-task's
template instead.

**One pass example: none exist — reporting one representative failure in
full** (Aatrox/Vladimir, chosen since it's the first alphabetically among
the held-out pairs):
```json
{
  "champ_a": "Aatrox", "champ_b": "Vladimir", "role": "top",
  "model_output": "Based on 3 recorded top games, Aatrox has a 33.3% win rate versus Vladimir.",
  "sections_present": false, "has_early": false, "has_mid": false, "has_late": false,
  "grounding_passed": true, "invented_phrases": [],
  "expected_win_rate_pct": 33, "cited_percentages": [33.3], "win_rate_within_10pts": true,
  "passed": false
}
```

### Win-rate regression check: no regression

```
win-rate regression step2: 152/152
win-rate regression step4: 237/237
```

| | Prior context-conditioning diagnostic | This run (combined training) |
|---|---|---|
| Held-out matchup pass rate | 152/152 (100.0%) | **152/152 (100.0%)** |
| Abstention pass rate | 237/237 (100.0%) | **237/237 (100.0%)** |

Identical, real, re-run numbers — the numeric win-rate skill held perfectly
even with 40 qualitative-advice examples mixed into the same 200-step run.

## Outcome — stated plainly

**Two separate, real findings, not one:**

1. **No regression on the numeric task.** 152/152 and 237/237 held exactly.
   Mixing in a structurally different minority task did not destabilize
   the skill that already worked — a real, positive result worth keeping
   in mind for future combined training.

2. **The qualitative-advice task was not learned at this budget.** 0/10
   held-out pairs produced anything resembling the requested
   Early:/Mid:/Late: structure; the model reverted 10/10 times to the
   dominant win-rate template regardless of the qualitative prompt's
   explicit instruction and supplied kit context. 40 examples (7.4% of a
   540-row, 200-step run) was not enough exposure for the model to learn a
   second, structurally different response style in the presence of a
   500-example majority task pulling the other way — the same "not enough
   exposure to the minority class" pattern first identified in
   `docs/decisions/phase2-class-balance-diagnostic.md`, now observed
   between two different *tasks* rather than two labels within one task.

This is not a case of the fact-grounding check being too strict or the
success criteria needing adjustment — when the model did produce output
matching the trained format, it was well-grounded (0 invented phrases,
accurate percentages every time). The problem is upstream: the model never
attempted the requested format at all.

**Recommendation:** do not conclude the model *can't* produce grounded
qualitative advice — this diagnostic never gave it a fair chance to learn
that skill at this scale. The real lever, following the same logic as
`phase2-class-balance-diagnostic.md`'s conclusion, is more exposure to the
qualitative task specifically: either a much higher qualitative:win-rate
ratio in the training mix, a longer step budget when both tasks are
present, or (worth real consideration given the two tasks now look more
like separable skills than a single unified one) training and evaluating
them as a two-stage or two-adapter setup rather than one combined
smoke-scale run.

## Files

- `backend/app/finetune/qualitative_advice.py`
- `backend/tests/unit/test_qualitative_advice.py`
- `backend/app/finetune/data/qualitative_advice_train.jsonl`, `qualitative_advice_heldout.jsonl`
- `backend/app/finetune/artifacts/qualitative_advice_generation_stats.json`
- `backend/app/finetune/artifacts/smoke-adapter-qualitative/`
- `backend/tests/integration/test_qualitative_adapter_fact_ledger.py`
- `backend/app/finetune/artifacts/eval_results_qualitative.json`
- `docs/decisions/phase2-qualitative-advice-diagnostic.md` (this file)
