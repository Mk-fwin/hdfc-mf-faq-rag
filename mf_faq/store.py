"""Store step: persistent ChromaDB + a manifest describing what was written.

The collection is deleted and rebuilt rather than appended to, so re-running
ingestion after a code change is idempotent instead of accumulating duplicates.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Sequence

from .chunkers import Chunk
from .config import CHROMA_DIR, CHUNK_COLLECTION, MANIFEST_PATH

# Chroma requires scalar metadata values; bools are stored as strings.
_METADATA_INT_KEYS = {"is_current", "is_generic_boilerplate"}


def _clean_metadata(meta: Dict) -> Dict:
    out: Dict = {}
    for key, value in meta.items():
        if value is None:
            continue
        if key in _METADATA_INT_KEYS:
            out[key] = int(bool(value))
        elif isinstance(value, bool):
            out[key] = int(value)
        elif isinstance(value, (int, float, str)):
            out[key] = value
        else:
            out[key] = str(value)
    return out


def chroma_settings():
    """The one Settings object every Chroma client in this process must use.

    Chroma keys its shared system cache on the settings, so opening the same
    persist directory twice with different Settings raises "An instance of
    Chroma already exists ... with different settings". Reading the store to
    check whether it exists and then writing it are both things this app does on
    a cold start, so the settings have to be identical in both places.
    """
    from chromadb.config import Settings

    return Settings(anonymized_telemetry=False, allow_reset=True)


def _client():
    import chromadb

    return chromadb.PersistentClient(path=CHROMA_DIR, settings=chroma_settings())


def write_chunks(chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], model_name: str,
                 fingerprint: str) -> Dict:
    """Replace the collection with ``chunks`` and write the manifest."""
    if len(chunks) != len(vectors):
        raise ValueError(f"{len(chunks)} chunks vs {len(vectors)} vectors")

    client = _client()

    # Dropped through Chroma rather than by deleting the directory. An earlier
    # version did shutil.rmtree(CHROMA_DIR), which breaks on a cold start inside
    # the app: index_is_built() has already opened a client on that directory by
    # the time the build runs, and removing the SQLite file out from under a live
    # connection leaves the next write against a deleted database. Resetting the
    # collection keeps the on-disk handle valid.
    try:
        client.delete_collection(CHUNK_COLLECTION)
    except Exception:
        # Not there yet, which is the normal first-build case.
        pass

    collection = client.get_or_create_collection(
        name=CHUNK_COLLECTION, metadata={"hnsw:space": "cosine"}
    )
    collection.add(
        ids=[c.chunk_id for c in chunks],
        documents=[c.text for c in chunks],
        embeddings=[list(v) for v in vectors],
        metadatas=[_clean_metadata(c.metadata) for c in chunks],
    )
    persisted = collection.count()
    if persisted != len(chunks):
        raise RuntimeError(f"chroma holds {persisted} rows, expected {len(chunks)}")

    per_fund = Counter(c.metadata.get("fund_name", "unknown") for c in chunks)
    per_section = Counter(c.metadata.get("section", "unknown") for c in chunks)
    fetched_at = {c.metadata.get("search_id"): c.metadata.get("ingested_at") for c in chunks}

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "collection": CHUNK_COLLECTION,
        "persist_dir": os.path.relpath(CHROMA_DIR),
        "embed_model": model_name,
        "embed_dim": len(vectors[0]) if vectors else 0,
        "embedding_fingerprint": fingerprint,
        "total_chunks": len(chunks),
        "chunks_per_fund": dict(sorted(per_fund.items())),
        "chunks_per_section": dict(sorted(per_section.items())),
        "fetched_at_per_fund": {k: v for k, v in sorted(fetched_at.items()) if k},
        "sources": [
            {
                "fund_name": c.metadata.get("fund_name"),
                "search_id": c.metadata.get("search_id"),
                "source_url": c.metadata.get("source_url"),
                "isin": c.metadata.get("isin"),
                "category": c.metadata.get("category"),
                "sub_category": c.metadata.get("sub_category"),
                "as_of": c.metadata.get("as_of"),
            }
            for c in chunks
            if c.metadata.get("section") == "identity_overview"
        ],
    }
    os.makedirs(os.path.dirname(MANIFEST_PATH), exist_ok=True)
    with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
    return manifest


def write_chunks_txt(chunks: Sequence[Chunk], path: str) -> str:
    """Human-readable dump of every chunk and its metadata."""
    by_fund: Dict[str, List[Chunk]] = {}
    for chunk in chunks:
        by_fund.setdefault(chunk.metadata.get("fund_name", "unknown"), []).append(chunk)

    lines: List[str] = []
    lines.append("=" * 100)
    lines.append("CHUNK DUMP - HDFC Mutual Fund FAQ assistant (ingestion only, no query layer yet)")
    lines.append(f"Total chunks: {len(chunks)}   Schemes: {len(by_fund)}")
    lines.append("Every chunk begins with a canonical 'Fund: ...' header line.")
    lines.append("=" * 100)

    for fund_name in sorted(by_fund):
        fund_chunks = by_fund[fund_name]
        lines.append("")
        lines.append("#" * 100)
        lines.append(f"# {fund_name}  ({len(fund_chunks)} chunks)")
        lines.append("#" * 100)
        for chunk in fund_chunks:
            meta = chunk.metadata
            lines.append("")
            lines.append("-" * 100)
            lines.append(f"[{chunk.chunk_id}]")
            lines.append("-" * 100)
            lines.append("METADATA:")
            for key in sorted(meta):
                lines.append(f"    {key:26s} : {meta[key]}")
            lines.append("TEXT:")
            for line in chunk.text.splitlines():
                lines.append(f"    {line}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    return path
