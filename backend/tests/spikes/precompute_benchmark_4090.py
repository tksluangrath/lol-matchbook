"""
Re-run of docs/decisions/phase0-precompute-benchmark.md on CUDA (target: 4090).

Same model, same 8 prompts, same formula as the Apple Silicon MPS run -- the only
thing that changes is the runtime (vLLM instead of unbatched transformers), because
vLLM's continuous batching is the thing that never showed a win on MPS and is
specifically expected to on a 4090. See that doc for why.

Usage (on the 4090 box, real benchmark):
    pip install vllm  # already in backend/requirements.txt
    python backend/tests/spikes/precompute_benchmark_4090.py

Usage (local smoke test only -- checks the harness runs end to end, does NOT
produce a usable throughput number, vLLM has no MPS backend so this can't measure
the thing the 4090 run measures):
    python backend/tests/spikes/precompute_benchmark_4090.py --engine transformers --max-new-tokens 32

Append the real 4090 numbers to docs/decisions/phase0-precompute-benchmark.md as
a new "## 4090 run" section -- do not overwrite the MPS numbers, they're the
floor reference the 4090 result gets compared against.
"""

import argparse
import time

MODEL = "Qwen/Qwen3-4B-Instruct-2507"  # per phase0-model-bakeoff.md
RANK_BRACKETS = 4
PHASES = 3
SAME_LANE_PAIRS = 6500  # per phase1-role-threshold-sensitivity.md
ALL_PAIRS = 14878  # per phase0-role-scoping.md, C(173,2)

SYSTEM_PROMPT = (
    "You are a League of Legends coach giving concise, phase-specific matchup "
    "advice for champion select."
)

# Same 8 matchup prompts in shape as the MPS bake-off run.
PROMPTS = [
    ("early", "Darius", "Yasuo", "top", "Gold"),
    ("mid", "Darius", "Yasuo", "top", "Diamond"),
    ("late", "Darius", "Yasuo", "top", "Plat"),
    ("early", "Ahri", "Zed", "mid", "Gold"),
    ("mid", "Ahri", "Zed", "mid", "Diamond"),
    ("late", "Ahri", "Zed", "mid", "Plat"),
    ("early", "Jinx", "Caitlyn", "bot", "Emerald"),
    ("mid", "Jinx", "Caitlyn", "bot", "Emerald"),
]


def build_prompt(phase, a, b, lane, rank):
    return (
        f"<|system|>{SYSTEM_PROMPT}<|end|>\n"
        f"<|user|>Write {phase} advice for {a} vs. {b}, {lane}, at {rank} rank.<|end|>\n"
        f"<|assistant|>"
    )


def run_vllm(prompts, max_new_tokens):
    from vllm import LLM, SamplingParams

    llm = LLM(model=MODEL, dtype="bfloat16")
    sampling = SamplingParams(temperature=0.0, max_tokens=max_new_tokens)

    start = time.perf_counter()
    outputs = llm.generate(prompts, sampling)
    elapsed = time.perf_counter() - start

    token_counts = [len(o.outputs[0].token_ids) for o in outputs]
    return token_counts, elapsed


def run_transformers(prompts, max_new_tokens):
    # ponytail: unbatched single-stream, CPU-friendly -- only proves the harness
    # (prompt building, token counting, formula) is correct. Not a throughput
    # measurement; see phase0-precompute-benchmark.md for the real MPS numbers
    # and why they don't extrapolate to CUDA either.
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(MODEL, dtype=torch.bfloat16)
    model.eval()

    token_counts = []
    start = time.perf_counter()
    for p in prompts:
        inputs = tok(p, return_tensors="pt")
        with torch.no_grad():
            out = model.generate(
                **inputs, max_new_tokens=max_new_tokens, do_sample=False
            )
        token_counts.append(out.shape[1] - inputs["input_ids"].shape[1])
    elapsed = time.perf_counter() - start

    return token_counts, elapsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["vllm", "transformers"], default="vllm")
    parser.add_argument("--max-new-tokens", type=int, default=400)
    parser.add_argument("--num-prompts", type=int, default=len(PROMPTS))
    args = parser.parse_args()

    if args.engine == "transformers":
        print(
            "NOTE: --engine transformers is a local smoke test only. It is "
            "unbatched and CPU/MPS-bound -- the resulting tokens/sec is NOT a "
            "valid substitute for the real 4090 vLLM run.\n"
        )

    prompts = [build_prompt(*p) for p in PROMPTS[: args.num_prompts]]

    run = run_vllm if args.engine == "vllm" else run_transformers
    token_counts, elapsed = run(prompts, args.max_new_tokens)

    total_tokens = sum(token_counts)
    tokens_per_sec = total_tokens / elapsed
    avg_tokens_per_blurb = total_tokens / len(token_counts)
    hit_cap = sum(1 for c in token_counts if c >= args.max_new_tokens)

    print(f"wall_clock_seconds        = {elapsed:.1f}")
    print(f"total_generated_tokens    = {total_tokens}")
    print(f"tokens_per_sec            = {tokens_per_sec:.2f}")
    print(f"avg_tokens_per_blurb      = {avg_tokens_per_blurb:.2f}")
    print(f"sequences that hit cap    = {hit_cap} of {len(token_counts)}")
    print(f"per_sequence_token_counts = {token_counts}")
    print()

    for label, pair_count in (("same-lane", SAME_LANE_PAIRS), ("all-pairs", ALL_PAIRS)):
        generations = pair_count * RANK_BRACKETS * PHASES
        gen_tokens = generations * avg_tokens_per_blurb
        seconds = gen_tokens / tokens_per_sec
        hours = seconds / 3600
        days = hours / 24
        print(
            f"{label} (pair_count={pair_count}): "
            f"{generations} generations, {gen_tokens:,.0f} tokens, "
            f"{hours:,.1f}h ({days:,.1f} days)"
        )


if __name__ == "__main__":
    main()
