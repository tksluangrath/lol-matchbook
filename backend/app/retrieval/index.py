"""
Local sentence-transformers embeddings over champion/ability text, per
docs/tech-stack.md #7 ("a small local sentence-transformers model ... zero
cost, no API key, no network dependency at inference time") and
docs/build-plan.md Phase 1 ("Build the retrieval index: local
sentence-transformers embeddings over patch notes + champion text").

Source text comes from app.data_pipeline.data_dragon (AGENT-9): kit/ability
*text* (blurb, passive, spell descriptions), never Data Dragon's numeric
balance fields -- those are treated as unreliable per docs/adr-001-
architecture.md and sourced from app.data_pipeline.aggregate instead.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass

import numpy as np
from sentence_transformers import SentenceTransformer

# all-MiniLM-L6-v2: small (~90MB), local, well under the resource gate --
# see docs/tech-stack.md #7's rationale for a small local embedding model.
DEFAULT_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Data Dragon embeds its own markup vocabulary in ability text --
# <font color='...'>, <status>, <scaleAP>, <keywordMajor>, <br>, etc. (real
# inventory found fetching Kayn/Warwick/Ahri/Yasuo/Vel'Koz detail JSON --
# see docs/decisions/phase3-markup-stripping-fix.md). None of it is
# meaningful to an embedding model, so strip any tag generically rather
# than special-casing the one pattern (<font>) a bug report happened to
# name -- root-cause fix in the shared function every caller routes
# through.
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_markup(text: str) -> str:
    return html.unescape(_TAG_RE.sub("", text))


def champion_text(champ_data: dict) -> str:
    """Flatten one Data Dragon champion entry (as returned by
    app.data_pipeline.data_dragon.fetch_champion_data) into a single string
    for embedding: name, blurb, passive, and each spell's name+description.
    Kit/ability text only -- no numeric balance fields. Data Dragon's
    embedded HTML-like markup (<font>, <status>, <br>, ...) and HTML
    entities are stripped."""
    parts = [champ_data["name"], champ_data.get("blurb", "")]
    passive = champ_data.get("passive")
    if passive:
        parts.append(f"{passive.get('name', '')}: {passive.get('description', '')}")
    for spell in champ_data.get("spells", []):
        parts.append(f"{spell.get('name', '')}: {spell.get('description', '')}")
    return "\n".join(_strip_markup(p) for p in parts if p)


@dataclass
class IndexEntry:
    champion: str
    text: str
    embedding: np.ndarray


class RetrievalIndex:
    """In-memory embedding index over champion kit text. Rebuilt on each
    patch refresh (docs/system-design.md: the retrieval index is refreshed
    alongside the stats) -- no persistence/vector-store wiring here by
    design; that's a separate later task, this component is the embedding
    layer only.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL_NAME):
        self._model = SentenceTransformer(model_name)
        self._entries: list[IndexEntry] = []

    def build(self, champion_data: dict[str, dict]) -> None:
        """champion_data: {champ_key: champ_data}, as returned by
        app.data_pipeline.data_dragon.fetch_champion_data."""
        champs = list(champion_data.values())
        texts = [champion_text(c) for c in champs]
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        self._entries = [
            IndexEntry(champion=c["name"], text=t, embedding=np.asarray(e))
            for c, t, e in zip(champs, texts, embeddings)
        ]

    def query(self, text: str, k: int = 1) -> list[tuple[str, float]]:
        """Return the top-k (champion_name, cosine_similarity) matches for
        `text`, nearest first. Embeddings are normalized in build(), so a
        dot product is cosine similarity."""
        if not self._entries:
            raise RuntimeError("Index is empty -- call build() first")
        q = np.asarray(self._model.encode([text], normalize_embeddings=True)[0])
        sims = [(e.champion, float(np.dot(q, e.embedding))) for e in self._entries]
        sims.sort(key=lambda pair: pair[1], reverse=True)
        return sims[:k]
