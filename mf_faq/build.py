"""Build step: turn cached pages into a searchable vector store.

Split out of ``cli.py`` so the Streamlit app and the CLI share one definition of
what "the index is built" means. The app calls :func:`build_from_cache` on first
start; ``cli.py ingest`` calls :func:`build_from_records` after loading.

Neither path here touches the network. Fetching lives in ``mf_faq.fetch`` and is
reached only through ``cli.py ingest --refresh``.
"""

from __future__ import annotations

import os
from typing import Dict

import chromadb

from .chunkers import build_all
from .config import CHROMA_DIR, CHUNKS_TXT_PATH, CHUNK_COLLECTION, MANIFEST_PATH
from .embed import Embedder
from .fetch import FetchError, load_cached
from .normalize import normalize
from .store import chroma_settings, write_chunks, write_chunks_txt


class BuildError(RuntimeError):
    """The index could not be built from what is on disk."""


def index_is_built() -> bool:
    """True when the collection exists and holds rows.

    Checked by reading the collection count rather than testing for a directory,
    because an interrupted build can leave a ``chroma_db/`` directory behind that
    has no collection in it. A count of zero therefore counts as not built.
    """
    if not os.path.exists(MANIFEST_PATH):
        return False
    try:
        client = chromadb.PersistentClient(path=CHROMA_DIR, settings=chroma_settings())
        return client.get_collection(CHUNK_COLLECTION).count() > 0
    except Exception:
        # No collection yet, or a Chroma version whose API differs here. Either
        # way the store is not usable, so the caller must build it.
        return False


def build_from_records(records: Dict[str, Dict], progress: bool = False) -> Dict:
    """Normalize, chunk, embed and store already-loaded fetch records."""
    try:
        chunks = build_all([normalize(rec) for rec in records.values()])
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a message
        raise BuildError(f"chunking failed: {exc}") from exc
    if not chunks:
        raise BuildError("no chunks were produced from the cached pages")

    try:
        embedder = Embedder()
        vectors = embedder.encode([c.text for c in chunks], show_progress=progress)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a message
        raise BuildError(f"embedding failed: {exc}") from exc

    try:
        manifest = write_chunks(
            chunks, vectors, embedder.model_name, Embedder.fingerprint(vectors)
        )
        write_chunks_txt(chunks, CHUNKS_TXT_PATH)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI as a message
        raise BuildError(f"writing the vector store failed: {exc}") from exc
    return manifest


def build_from_cache(progress: bool = False) -> Dict:
    """Build the index from the committed pages in ``data/raw/``. No network."""
    try:
        records = load_cached()
    except FetchError as exc:
        raise BuildError(str(exc)) from exc
    return build_from_records(records, progress=progress)