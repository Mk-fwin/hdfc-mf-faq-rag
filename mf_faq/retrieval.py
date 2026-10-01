"""Retrieve step: embed the question, then narrow 20 candidates down to a
small, de-duplicated evidence set.

Four narrowing rules, in order:
  1. ``is_current = 1`` is applied as a *filter* at query time, so a superseded
     exit-load version can never be returned, let alone quoted.
  2. Alias resolution turns "HDFC Equity Fund" into a ``search_id`` ``where``
     clause, making the lookup a true scoped search rather than a soft bias.
  3. A section boost plus a per-scheme cap stop one verbose scheme (Balanced
     Advantage has 25 chunks) from crowding out the other four.
  4. A question naming exactly one fact type keeps only that section, so the
     model is never shown a neighbouring fact it might volunteer unasked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import chromadb

from .config import CHROMA_DIR, CHUNK_COLLECTION, EMBED_MODEL, FUNDS
from .embed import Embedder
from .store import chroma_settings

#: Question signal -> sections to promote. Split into two tiers: DISCRETE
#: signals name exactly one fact type, so they get a decisive boost; BROAD
#: signals match many sections and only nudge the ranking.
DISCRETE_SIGNALS: Dict[str, Tuple[str, ...]] = {
    "objective_benchmark": ("benchmark", "objective of the fund", "invests in"),
    "fund_manager": ("who manages", "who runs", "fund manager", "managed by"),
    "exit_load_current": ("exit load", "exit charge", "redemption charge", "penalty on exit"),
    "expense_ratio": ("expense ratio", "ter", "expenses"),
    "stamp_duty": ("stamp duty",),
    "lockin": ("lock-in", "lock in", "locked", "how long before i can"),
    "holdings_top25": ("top holdings", "top holding", "largest holding", "which stocks"),
}

BROAD_SIGNALS: Dict[str, Tuple[str, ...]] = {
    "portfolio_turnover": ("turnover", "portfolio turnover"),
    "minimums": ("minimum", "min ", "sip", "lump sum", "lumpsum", "smallest amount"),
    "holdings_summary": ("sector", "sectors", "portfolio mix", "asset allocation"),
    "swp_terms": ("swp", "withdrawal plan", "systematic withdrawal"),
    "stp_terms": ("stp", "transfer plan", "systematic transfer"),
    "identity_overview": ("nav", "aum", "fund size", "isin", "launch", "inception"),
    "risk_profile": ("how risky", "riskometer", "safe"),
    "risk_ratios": ("sharpe", "beta", "sortino", "alpha", "standard deviation"),
    "returns_history": ("return", "returns", "how has it done", "since launch"),
    "amc_registrar": ("registrar", "rta", "custodian", "fund house", "contact"),
    "objective_benchmark": ("index",),
}

#: Additive score bonuses. DISCRETE must be large enough to beat a near-tie
#: from a structurally similar chunk; BROAD only reorders close candidates.
DISCRETE_BOOST = 0.12
BROAD_BOOST = 0.05
#: Generic boilerplate (the shared tax chunk) is real but low-specificity, so
#: it is nudged down rather than dropped -- it is still the right answer to a
#: direct tax question.
GENERIC_PENALTY = 0.04
#: Cap on how many chunks any single scheme may contribute.
PER_FUND_CAP = 2


@dataclass
class Hit:
    chunk_id: str
    text: str
    metadata: Dict
    score: float
    raw_score: float
    boosted: bool = False
    body: str = ""


@dataclass
class Retrieval:
    question: str
    hits: List[Hit]
    matched_search_id: Optional[str] = None
    matched_fund_name: Optional[str] = None
    candidates_seen: int = 0
    notes: List[str] = field(default_factory=list)

    @property
    def source_url(self) -> Optional[str]:
        return self.hits[0].metadata.get("source_url") if self.hits else None

    @property
    def as_of(self) -> str:
        for hit in self.hits:
            if hit.metadata.get("as_of"):
                return hit.metadata["as_of"]
        return "not stated"


def _collection():
    client = chromadb.PersistentClient(
        path=CHROMA_DIR, settings=chroma_settings()
    )
    return client.get_collection(CHUNK_COLLECTION)


def _body_of(text: str) -> str:
    """Chunk text minus the canonical 'Fund: ...' header line."""
    parts = text.split("\n", 1)
    return parts[1].strip() if len(parts) > 1 else text.strip()


def _alias_index() -> List[Tuple[str, str]]:
    """(lowercased phrase, search_id) for the fund name and every alias."""
    pairs: List[Tuple[str, str]] = []
    for fund in FUNDS:
        pairs.extend((phrase.lower(), fund.search_id) for phrase in fund.phrases())
    # Longest phrase first so "HDFC ELSS Tax Saver" beats "HDFC ELSS".
    pairs.sort(key=lambda kv: -len(kv[0]))
    return pairs


_ALIASES = _alias_index()


def resolve_fund(question: str) -> Optional[str]:
    """Map a question to a corpus search_id via fund name or alias."""
    text = f" {question.lower()} "
    for phrase, search_id in _ALIASES:
        if phrase in text:
            return search_id
    return None


def _matcher(signal: str):
    """Compile a signal to a word-boundary regex.

    Plain substring matching is unsafe for short signals: "ter" (the expense
    ratio) occurs inside "riskometer", and "sip" inside "stocks". Signals that
    already end in a non-word character keep substring semantics.
    """
    if signal and not signal[-1].isalnum():
        return re.compile(re.escape(signal), re.I)
    return re.compile(rf"\b{re.escape(signal)}\b", re.I)


def _build_matchers() -> Tuple[Dict[str, List[Any]], Dict[str, List[Any]]]:
    discrete: Dict[str, List[Any]] = {}
    broad: Dict[str, List[Any]] = {}
    for section, signals in DISCRETE_SIGNALS.items():
        discrete[section] = [_matcher(s) for s in signals]
    for section, signals in BROAD_SIGNALS.items():
        broad[section] = [_matcher(s) for s in signals]
    return discrete, broad


_DISCRETE_MATCHERS, _BROAD_MATCHERS = _build_matchers()
_SIGNAL_MATCHERS: Dict[str, List[Any]] = {**_DISCRETE_MATCHERS, **_BROAD_MATCHERS}


def _boost_map(question: str) -> Dict[str, float]:
    """section -> total bonus, combining the discrete and broad tiers."""
    text = question.lower()
    bonuses: Dict[str, float] = {}
    for section, matchers in _SIGNAL_MATCHERS.items():
        if any(m.search(text) for m in matchers):
            amount = DISCRETE_BOOST if section in DISCRETE_SIGNALS else BROAD_BOOST
            bonuses[section] = bonuses.get(section, 0.0) + amount
    return bonuses


def _matched_discrete(question: str) -> set:
    """Discrete sections the question names, each meaning exactly one fact type."""
    text = question.lower()
    return {
        section
        for section, matchers in _DISCRETE_MATCHERS.items()
        if any(m.search(text) for m in matchers)
    }


class Retriever:
    def __init__(self, collection=None, embedder: Optional[Embedder] = None,
                 n_candidates: int = 20, top_k: int = 5):
        self.collection = collection or _collection()
        self.embedder = embedder or Embedder()
        self.n_candidates = n_candidates
        self.top_k = top_k

    def retrieve(self, question: str, top_k: Optional[int] = None) -> Retrieval:
        top_k = top_k or self.top_k
        vector = self.embedder.encode([question])[0]

        search_id = resolve_fund(question)
        where: Dict = {"is_current": {"$eq": 1}}
        notes: List[str] = ["is_current=1 filter applied (superseded exit-load versions excluded)"]
        if search_id:
            where = {"$and": [where, {"search_id": search_id}]}
            notes.append(f"alias filter -> search_id={search_id}")

        result = self.collection.query(
            query_embeddings=[vector],
            n_results=self.n_candidates,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        candidates = result["distances"][0] or []
        if not candidates:
            return Retrieval(question, [], search_id, None, 0, notes + ["no candidates matched"])

        bonuses = _boost_map(question)
        if bonuses:
            notes.append(
                "section boost: "
                + ", ".join(f"{s}+{b:.2f}" for s, b in sorted(bonuses.items()))
            )

        scored: List[Hit] = []
        for doc, meta, dist in zip(
            result["documents"][0], result["metadatas"][0], candidates
        ):
            raw = 1.0 - float(dist)
            section = meta.get("section")
            score = raw + bonuses.get(section, 0.0)
            if meta.get("scope") == "generic":
                score -= GENERIC_PENALTY
            scored.append(
                Hit(
                    chunk_id=str(meta.get("chunk_id") or ""),
                    text=doc,
                    metadata=dict(meta),
                    score=score,
                    raw_score=raw,
                    boosted=section in bonuses,
                    body=_body_of(doc),
                )
            )

        scored.sort(key=lambda h: -h.score)

        # One question names one fact type: show the model only that section.
        # "What is the expense ratio?" says nothing about the exit load, so the
        # exit-load chunk must not sit in the evidence for it -- the model reads
        # the context as fair game and volunteers the neighbouring fact. Two
        # discrete signals ("expense ratio and exit load") ask for two things, so
        # narrowing is skipped there and the normal ranking decides.
        discrete = _matched_discrete(question)
        if len(discrete) == 1:
            section = next(iter(discrete))
            narrowed = [h for h in scored if h.metadata.get("section") == section]
            # Only narrow when the section is actually present, so a question
            # with no chunk for it falls back to ranking instead of to no evidence.
            if narrowed:
                notes.append(
                    f"evidence scoped to '{section}': the question names one fact type"
                )
                scored = narrowed

        # Per-scheme cap: without it one scheme's 25 chunks crowd out the rest.
        kept: List[Hit] = []
        per_fund: Dict[str, int] = {}
        for hit in scored:
            fund = hit.metadata.get("fund_name", "?")
            if per_fund.get(fund, 0) >= PER_FUND_CAP:
                continue
            per_fund[fund] = per_fund.get(fund, 0) + 1
            kept.append(hit)
            if len(kept) >= top_k:
                break
        if per_fund and len(per_fund) > 1:
            notes.append(f"per-scheme cap {PER_FUND_CAP} applied across {len(per_fund)} schemes")

        matched_name = next(
            (f.display_name for f in FUNDS if f.search_id == search_id), None
        )
        return Retrieval(question, kept, search_id, matched_name, len(scored), notes)
