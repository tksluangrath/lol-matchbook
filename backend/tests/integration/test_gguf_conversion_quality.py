"""
Phase 4: real quality gate for the GGUF-quantized (Q4_K_M) build of the
merged qualitative-advice adapter, run via llama-cpp-python on CPU. Reuses
the same real Aatrox/Kayle sanity prompt and the same section-split/
grounding checks the transformers-based pipeline already uses --
app.data_pipeline.precompute.split_into_sections and
app.finetune.qualitative_advice.fact_grounding_check, not reimplemented.

Real generation, no mocked/fixture output -- module-scoped fixture loads
the real GGUF file and runs one real greedy (temperature=0.0) generation,
shared by both assertions below so the model is only loaded/run once.

Known real finding at the time this test was written (see
docs/decisions/phase4-gguf-conversion.md): across 3 real attempts (greedy
+ the same 2-attempt sampled retry precompute.py's own
_generate_and_check_pair_with_sampling_retry uses), the quantized model
consistently labels sections "Early Game:"/"Mid Game:"/"Late Game:"
instead of the trained "Early:"/"Mid:"/"Late:" (or the already-broadened
"Mid-game:"/"Late game:" variants precompute.py's regexes already accept)
-- so test_gguf_output_has_all_three_sections is expected to currently
FAIL. This is intentional: it is a real, currently-red regression gate,
not a rubber-stamped pass. Left failing rather than weakened, per this
phase's task contract ("do not lower the bar").
"""
import json
from pathlib import Path

import pytest

from app.data_pipeline.precompute import split_into_sections
from app.finetune.qualitative_advice import fact_grounding_check
from app.finetune.train import SYSTEM_PROMPT

GGUF_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "finetune" / "artifacts"
    / "gguf-qualitative-v2" / "merged-qualitative-v2-Q4_K_M.gguf"
)
HELDOUT_PATH = Path(__file__).resolve().parents[2] / "app" / "finetune" / "data" / "qualitative_advice_heldout.jsonl"


def _require_gguf():
    if not GGUF_PATH.exists():
        pytest.skip(f"No GGUF model at {GGUF_PATH} -- run the phase4 conversion first.")
    pytest.importorskip("llama_cpp")


def _aatrox_kayle_row() -> dict:
    for line in HELDOUT_PATH.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["champ_a"] == "Aatrox" and row["champ_b"] == "Kayle":
            return row
    raise AssertionError("Aatrox/Kayle row not found in qualitative_advice_heldout.jsonl")


@pytest.fixture(scope="module")
def gguf_aatrox_kayle_output() -> tuple[str, str]:
    """Real greedy (temperature=0.0) generation from the real quantized
    GGUF model, on CPU (n_gpu_layers=0). Returns (generated_text,
    generation_prompt) so both tests can grounding-check against the real
    prompt without a second model load."""
    _require_gguf()
    from llama_cpp import Llama

    row = _aatrox_kayle_row()
    prompt = row["context"]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]
    llm = Llama(model_path=str(GGUF_PATH), n_ctx=4096, n_threads=8, n_gpu_layers=0, verbose=False)
    out = llm.create_chat_completion(messages=messages, max_tokens=400, temperature=0.0)
    text = out["choices"][0]["message"]["content"]
    return text, prompt


def test_gguf_output_has_all_three_sections(gguf_aatrox_kayle_output):
    text, _ = gguf_aatrox_kayle_output
    sections = split_into_sections(text)
    assert sections is not None, (
        "real GGUF output could not be split into early/mid/late sections -- "
        f"real generated text was:\n{text}"
    )
    assert set(sections) == {"early", "mid", "late"}
    assert all(sections[phase].strip() for phase in ("early", "mid", "late"))


def test_gguf_output_passes_fact_grounding(gguf_aatrox_kayle_output):
    text, prompt = gguf_aatrox_kayle_output
    grounding = fact_grounding_check(text, prompt, expected_win_rate_pct=50)
    assert grounding["passed"], f"grounding failed: {grounding}"
