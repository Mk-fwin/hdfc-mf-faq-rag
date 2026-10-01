"""Embed step: local all-MiniLM-L6-v2, 384-dim, L2-normalised.

The same encoder must serve chunks and questions, so the model id and a
fingerprint of the resulting vectors are recorded in the manifest to detect
corpus/encoder drift on reload.
"""

from __future__ import annotations

import hashlib
import struct
from typing import List, Sequence

from .config import EMBED_DIM, EMBED_MODEL


class Embedder:
    def __init__(self, model_name: str = EMBED_MODEL, batch_size: int = 64):
        self.model_name = model_name
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: Sequence[str], show_progress: bool = False) -> List[List[float]]:
        if not texts:
            return []
        vectors = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
        )
        out = [[float(x) for x in row] for row in vectors]
        self._assert_dim(out)
        return out

    @staticmethod
    def _assert_dim(vectors: List[List[float]]) -> None:
        found = {len(v) for v in vectors}
        if found != {EMBED_DIM}:
            raise ValueError(
                f"expected {EMBED_DIM}-dim embeddings, got {sorted(found)}; "
                "chunks and questions must share one encoder"
            )

    @staticmethod
    def fingerprint(vectors: Sequence[Sequence[float]]) -> str:
        """Stable short hash of the vector matrix, for drift detection."""
        h = hashlib.sha256()
        for vec in vectors:
            for value in vec:
                h.update(struct.pack("f", value))
        return h.hexdigest()[:16]
