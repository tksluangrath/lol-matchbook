"""
Test-first isolation for the sampling-retry fallback used by
force_regenerate_pairs(sampling_retry=True) -- proves the retry stops on
the first passing attempt (greedy or sampled) and falls through to the
existing skip shape, untouched, if all three attempts fail. No real model
call -- generate() is monkeypatched to a fake that fails/passes on demand,
same pattern as test_forced_regeneration_scope.py.

Context: greedy decoding is deterministic (eval.generate's default
do_sample=False), so a single failing attempt never recovers on its own
(docs/decisions/phase3-ability-whitelist-retry.md). This tests the bounded
(2 extra) sampled-retry fallback for the 7 pairs that survived the
whitelist fix.
"""
from app.data_pipeline import precompute
from app.data_pipeline.precompute import (
    MAX_SAMPLING_RETRIES,
    SAMPLING_GEN_KWARGS,
    _generate_and_check_pair_with_sampling_retry,
)

PAIR = {
    "champ_a": "Jhin", "champ_b": "Jinx", "role": "bottom",
    "win_rate": 0.5,
    "generation_prompt": (
        "Context: 10 games observed this patch between Jhin and Jinx in the "
        "bottom lane. Jhin win rate: 50%.\nJhin kit: real kit text\n"
        "Jinx kit: real kit text"
    ),
}

FAIL_OUTPUT = "Early:\nDead Ally strikes.\n\nMid:\nplay on.\n\nLate:\nclose it out."
PASS_OUTPUT = "Early:\nplay safe.\n\nMid:\nregroup.\n\nLate:\nclose it out."


def test_stops_at_first_passing_sampled_attempt_and_uses_its_result(monkeypatch):
    calls = []

    def fake_generate(model, tokenizer, prompt, max_new_tokens, **gen_kwargs):
        calls.append(gen_kwargs)
        # greedy attempt (call 1) and first sampled retry (call 2) fail;
        # second sampled retry (call 3) passes.
        return FAIL_OUTPUT if len(calls) < 3 else PASS_OUTPUT

    monkeypatch.setattr("app.finetune.eval.generate", fake_generate)

    result = _generate_and_check_pair_with_sampling_retry(PAIR, "fake-model", "fake-tok", 400)

    assert result["passed"] is True
    assert result["sections"]["early"] == "play safe."
    assert len(calls) == 3
    assert calls[0] == {}  # greedy attempt: no decoding overrides
    assert calls[1] == SAMPLING_GEN_KWARGS
    assert calls[2] == SAMPLING_GEN_KWARGS


def test_all_three_attempts_failing_returns_last_failure_not_a_crash(monkeypatch):
    calls = []

    def fake_generate(model, tokenizer, prompt, max_new_tokens, **gen_kwargs):
        calls.append(gen_kwargs)
        return FAIL_OUTPUT

    monkeypatch.setattr("app.finetune.eval.generate", fake_generate)

    result = _generate_and_check_pair_with_sampling_retry(PAIR, "fake-model", "fake-tok", 400)

    assert result["passed"] is False
    assert result["reason"] == "grounding_failed"
    assert result["invented_phrases"] == ["Dead Ally"]
    assert len(calls) == 1 + MAX_SAMPLING_RETRIES
