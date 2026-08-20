# Phase 4: GGUF Conversion + CPU Serving — Real Merge, Real Quantization, Real Regression Found

**Status: DONE, with a real negative finding.** Merge, GGUF conversion,
and Q4_K_M quantization all succeeded and run for real via
`llama-cpp-python` on CPU only (confirmed, not assumed). But the
quantized model's real output on the project's own Aatrox/Kayle sanity
prompt fails the project's own section-split check, 3/3 real attempts
(greedy + the same 2-attempt sampled retry `precompute.py` already uses in
production). Grounding passes 1/3. This is reported plainly, not
papered over — see "Real quality comparison" below. **The GGUF build is
not ready to back `/ask` as-is.**

## Merge: real, PEFT `merge_and_unload()`, same pattern as the fact-ledger tests

Loaded the base model (`Qwen/Qwen3-4B-Instruct-2507`, fp32, same load
call `test_qualitative_dedicated_v2_adapter_fact_ledger.py` already uses),
wrapped it with `PeftModel.from_pretrained(base,
"smoke-adapter-qualitative-dedicated-v2")`, called `merge_and_unload()`,
saved to `backend/app/finetune/artifacts/merged-qualitative-v2/`. Real
wall time: 298.6s. Real output: a 16.09GB fp32 `model.safetensors` (4.02B
params × 4 bytes, matches expectation) plus tokenizer files. No shortcuts
taken here — same merge mechanism the existing fact-ledger integration
test already exercises and asserts against (`isinstance(finetuned,
PeftModel)` + a real weight-tensor diff vs. untouched base).

## Toolchain investigated before installing anything

- `llama-cpp-python`: not installed at session start. Checked PyPI
  directly (`pypi.org/pypi/llama-cpp-python/0.3.35/json`) before pulling
  anything — **no prebuilt wheel exists for this platform/Python
  combination**, only a 74.9MB source sdist (well under the 500MB
  stop-and-report gate). Installed via `pip install llama-cpp-python`
  with `CMAKE_ARGS="-DGGML_METAL=OFF -DGGML_METAL_EMBED_LIBRARY=OFF"
  FORCE_CMAKE=1` to explicitly request a CPU-only build at compile time —
  this matters, see the CPU-only section below for why that flag turned
  out not to be sufficient on its own.
- `convert_hf_to_gguf.py`: not pip-installable, not bundled in
  `llama-cpp-python` — confirmed by checking the installed package's
  contents. As of the current `llama.cpp` `master` branch, the real
  conversion script depends on a `conversion/` package (per-architecture
  model converters, ~80 files) and a `gguf-py/` package, neither of which
  exist outside the `llama.cpp` repo itself. A single-file `curl` of
  `convert_hf_to_gguf.py` confirmed this (it does `from conversion
  import (...)`, not the flat, mostly-self-contained script this project
  may have seen referenced elsewhere).
- Given that, did a real, minimal `git clone --filter=blob:none --sparse
  --depth 1` of `ggml-org/llama.cpp`, sparse-checked-out to only
  `gguf-py/`, `conversion/`, `requirements/`, and the root
  `convert_hf_to_gguf.py` — **real measured size: 3.3MB**, nowhere near
  the 500MB gate (the GitHub API's reported 430MB `size` field for the
  repo is full history across all branches, not what a shallow
  single-branch sparse clone actually pulls). No stop-and-report needed;
  noting the real number since the initial API figure looked alarming
  before the real clone proved it wasn't.
- Extra Python deps installed for conversion: `sentencepiece` (missing;
  Qwen's real tokenizer path doesn't need it at runtime, but
  `conversion/`'s imports touch it). `torch`, `numpy`, `protobuf` were
  already present and compatible enough that the conversion script ran
  without needing the repo's pinned `requirements-convert_legacy_llama.txt`
  versions (which would have downgraded this project's already-installed
  `transformers`/`numpy` — not done, to avoid breaking the existing
  fine-tune stack for an incidental conversion dependency).

## Conversion + quantization: real, both succeeded

```
python3 llama.cpp/convert_hf_to_gguf.py \
  backend/app/finetune/artifacts/merged-qualitative-v2 \
  --outfile backend/app/finetune/artifacts/gguf-qualitative-v2/merged-qualitative-v2-f16.gguf \
  --outtype f16
```
Real output: `qwen3` architecture recognized automatically (36 blocks, 32
heads / 8 KV heads, matches Qwen3-4B), 398 tensors, real 8.05GB f16 GGUF
file written.

Quantized via `llama_cpp.llama_model_quantize` (the same C API
`llama-cpp-python` exposes directly — no separate `llama-quantize`
binary needed):

```
ftype = LLAMA_FTYPE_MOSTLY_Q4_K_M
```

**Why Q4_K_M specifically:** this is a ~4B model that has to run
acceptably on CPU with no GPU contention (the hard constraint from
ADR-001 §5/tech-stack.md §5). Q4_K_M is llama.cpp's standard "quality vs.
size" middle ground for models in this size class — it applies q4_K to
most tensors but keeps `attn.v` and `ffn_down` at q6_K (confirmed in the
real quantization log: `blk.N.attn_v.weight ... converting to q6_K`,
`blk.N.ffn_down.weight ... converting to q6_K`), which is exactly the
mixed-precision scheme llama.cpp's own docs recommend as the default
"good enough for most uses" choice rather than the more aggressive Q4_0/
Q3_K tiers (real risk of coherence loss on a model this small) or the
much larger Q5_K_M/Q8_0 tiers (real risk of decode speed on CPU, which
matters directly for the `/ask` latency budget). Real result: **rc=0**,
2.38GB output file, 4.95 BPW (bits per weight) average — roughly a 3.4x
size reduction from the 8.05GB f16 file, in line with Q4's expected
~4-bit-per-weight target.

## Real CPU-only confirmation — verified three separate ways, not assumed

1. **Build-time:** `llama-cpp-python` was built with `-DGGML_METAL=OFF`.
   Real finding: **that flag alone did not remove the Metal backend from
   the build** — the real load log still shows `ggml_metal_device_init:
   GPU name: MTL0 (Apple M4)` and `ggml_metal_library_init: using
   embedded metal library`. This is worth flagging plainly rather than
   trusting the compile flag blindly: pip's build isolation likely didn't
   propagate `CMAKE_ARGS` the way a direct CMake invocation would have.
   Not re-investigated further since point 2 below is a stronger, runtime
   guarantee anyway.
2. **Runtime, per-layer assignment:** with `n_gpu_layers=0` (every real
   generation call in this phase used this), the real load log shows
   `load_tensors: layer N assigned to device CPU, is_swa = 0` for **all
   36 layers**, and at generation time: `MTL0 compute buffer size is
   0.0000 MiB` / `CPU compute buffer size is 306.7520 MiB`. Zero bytes of
   compute buffer allocated on the Metal device — the GPU backend is
   registered (available) but literally unused for this run.
3. **Live process monitoring during real generation** (not inferred from
   config): `ioreg -r -d 1 -c "IOAccelerator" -k "PerformanceStatistics"`
   polled while generation was actively running, no `sudo` needed. Real
   reading, mid-generation: `"Device Utilization %"=0`. Simultaneously,
   `ps aux` on the generating process showed real CPU utilization up to
   **852-903%** (multi-core, consistent with `n_threads=8` doing real
   work) during prompt eval, dropping to a sustained ~95-98% (roughly one
   core's worth) during token-by-token decode — the expected shape for
   CPU-bound llama.cpp inference, not GPU-offloaded.

**Conclusion: CPU-only confirmed for real, by direct measurement during
an actual generation run, not by trusting `n_gpu_layers=0` as a config
flag alone.**

## Real quality comparison: GGUF (Q4_K_M) vs. the documented transformers output

Same real prompt for both — `qualitative_advice_heldout.jsonl`'s
Aatrox/Kayle `context` field, reused verbatim (the same field
`precompute.py`'s `load_sample_pairs()` feeds as `generation_prompt` for
this exact pair), wrapped in the same `SYSTEM_PROMPT` +
`tokenizer.apply_chat_template`-equivalent chat structure
`eval.generate()` uses (`llama_cpp`'s `create_chat_completion`, which
reads the GGUF's own embedded chat template).

**Known-good transformers output** (quoted verbatim from
`docs/decisions/phase3-precompute-and-advice-endpoint.md`):
> **Early:** Aatrox's high health and fear-driven crowd control can
> deter early ganks, but Kayle's ability to gain attack range and her
> presence of a divine ally makes her a persistent threat. Avoid engaging
> directly in the early game; let Kayle establish positioning. Aatrox
> should use his stance to close gaps and prepare for a counter-punch,
> while Kayle can use her spellblade to pressure and harass if the
> opportunity arises.
>
> **Mid:** Kayle's radiant blast and celestial blessing allow her to
> control engagement and root enemies, while Aatrox's darkin blade and
> deathbringer stance enable him to close gaps and sustain himself. [...]
>
> **Late:** In the late game, Aatrox's ability to fear and drag enemies
> becomes crucial for crowd control in fights. [...]

**Real GGUF (Q4_K_M) output, greedy/temperature=0.0, this session:**
> **Early Game:** Aatrox and Kayle have similar top-lane roles in that
> they both rely on a mix of damage, crowd control, and survivability,
> but Kayle's access to powerful ally support and crowd control makes her
> more adaptable in early skirmishes. Aatrox's lack of early game crowd
> control gives him an edge in closing gaps with his dash and basic
> attacks, but Kayle can use her portal to reposition and secure kills.
> [...] Prioritize killing low-health enemies quickly; Kayle's Radiant
> Blast can stop the kill if she gets the right timing.
>
> **Mid Game:** Kayle's Celestial Blessing and Divine Judgment allow her
> to support her ally and pressure the enemy lane, while Aatrox's
> Infernal Chains and Darkin Blade allow him to close gaps and pressure
> with his own presence. [...]
>
> **Late Game:** In the laning phase, Kayle's ability to heal allies and
> grant Move Speed allows her to sustain pressure and secure takedowns.
> [...]

**Coherence verdict: genuinely coherent, on-topic, real League strategy
language, correctly ordered early→mid→late, no repetition or garbage
tokens.** This is not the "incoherent" failure mode the task asked to
watch for. Wording differs from the transformers output (expected,
flagged already in the phase3 doc as real CPU float/quantization
non-determinism even between two transformers runs of the *same*
adapter).

**Structural verdict: real regression, not cosmetic.** The GGUF model
consistently writes `Early Game:` / `Mid Game:` / `Late Game:` (capital
"Game", a space before the colon) instead of the trained `Early:` /
`Mid:` / `Late:` format (or the already-broadened `Mid-game:`/`Late
game:` variants `precompute.py`'s own regexes already accept from the
transformers pipeline). Ran `split_into_sections()` (real function,
unmodified, imported from `app.data_pipeline.precompute`) against the
real GGUF output: **returns `None`** — a real section-split failure, on
all 3 attempts:

| Attempt | Sampling | Sections found | Grounding passed |
|---|---|---|---|
| 1 (greedy) | `temperature=0.0` | ❌ No | ✅ Yes |
| 2 (retry) | `temperature=0.7, top_p=0.9, seed=1` | ❌ No | ❌ No (`invented_phrases: ['Divine Blessing']`) |
| 3 (retry) | `temperature=0.7, top_p=0.9, seed=2` | ❌ No | ❌ No (`invented_phrases: ['Her Blessing']`) |

This is the exact same greedy-then-2-sampled-retries sequence
`precompute._generate_and_check_pair_with_sampling_retry` already runs in
production. Run against the real production code path, this pair would
land in `skipped` with `reason: "could_not_split_sections"` — **0 rows
written**, for a pair the transformers pipeline already produced clean
output for.

The two sampled-retry grounding failures are a second, smaller real
finding: at `temperature=0.7`, the quantized model twice invented
plausible-but-wrong ability names (`"Divine Blessing"`, `"Her Blessing"`
— both garbled blends of Kayle's real `Celestial Blessing` and `Divine
Judgment`) that aren't in the supplied kit-context text. The greedy
(`temperature=0.0`) attempt did not do this — `invented_phrases: []`,
grounding passed.

## What this means for `/ask`

Not ready to wire up as-is. Two real, separate problems, not one:

1. **Section-label drift** (100% reproducible on this prompt, 3/3
   attempts) — the actual blocker. `split_into_sections()`'s regexes
   were already broadened once before (per its own docstring, for
   `Mid-game:`/`Late game:` variants from the *transformers* pipeline);
   this GGUF-specific `"X Game:"` variant is a new, real pattern that
   would need either a further-broadened regex or a fix upstream
   (prompt/instruction change, or a stricter `Instruction:` line like
   `qualitative_advice.py`'s `build_generation_prompt()` already has but
   `precompute.py`'s sample-pair path does not use — worth checking
   whether reusing that stricter instruction line closes this gap,
   *not* done in this slice).
2. **Sampling-retry grounding failures** — smaller, but real: quantization
   measurably increases the model's rate of inventing plausible-sounding
   but wrong ability names under non-greedy decoding, on this one sample.
   Not enough real attempts here (n=2 sampled retries on one pair) to
   generalize a failure rate — worth running against more of the 10-pair
   sample before drawing a stronger conclusion, out of scope for this
   slice.

## Real cost incurred

- ~5 min: `llama-cpp-python` source build (CPU-only CMake flags)
- 3.3MB, ~10s: sparse `llama.cpp` clone for `conversion/`/`gguf-py/`
- 298.6s: real PEFT merge (fp32, CPU)
- ~45s: f16 GGUF conversion (8.05GB written)
- 24.6s: Q4_K_M quantization (rc=0, 2.38GB written)
- ~20-25s per real generation attempt (prompt eval + 400-token decode, CPU)

## Files

- `backend/app/finetune/artifacts/merged-qualitative-v2/` (merged fp32
  model, not committed — 16GB, matches this project's existing pattern of
  not committing model artifacts)
- `backend/app/finetune/artifacts/gguf-qualitative-v2/merged-qualitative-v2-f16.gguf`
  (8.05GB, intermediate)
- `backend/app/finetune/artifacts/gguf-qualitative-v2/merged-qualitative-v2-Q4_K_M.gguf`
  (2.38GB, the real quantized artifact)
- `backend/tests/integration/test_gguf_conversion_quality.py` (real test,
  real GGUF generation, no mocks — **currently 1 failing / 1 passing**,
  intentionally left red to document the real regression rather than
  weakened to pass)
- `docs/decisions/phase4-gguf-conversion.md` (this file)

## Next step

Not done in this slice: fixing the section-label drift (either regex or
prompt-side) and re-running the full 3-attempt check to confirm a real
fix before `/ask` gets built on top of this GGUF artifact. Also not done:
running the other 9 heldout pairs through the same GGUF+llama.cpp path to
see whether the label drift and grounding-failure rate are prompt-specific
or general.
