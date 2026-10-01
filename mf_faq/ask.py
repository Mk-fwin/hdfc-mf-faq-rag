"""Orchestration for the query path: guard -> retrieve -> answer.

Guards run first, so a refused question is never embedded, never searched and
never sent to the LLM. PII refusals additionally redact the input before it
reaches any printer or log.

A clarification the assistant asked ("Which scheme do you mean?") is held in the
caller's ``ConversationMemory`` for one turn. When the reply to it is only a
scheme name, the two are combined and the question is answered as the user meant
it, instead of treating the bare name as a lookup and returning whatever
retrieval ranked highest.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .answer import AnswerResult, DATE_PREFIX, answer_question, count_sentences
from .config import FUNDS, FUNDS_BY_ID
from .guards import GROWW_SCREENER, Refusal, classify, is_bare_scheme_name
from .memory import ConversationMemory
from .retrieval import Retriever, Retrieval, resolve_fund

REFUSAL_MAX_SENTENCES = 3


def redact(text: str) -> str:
    """A non-reversible stand-in for logging, used only on PII refusals."""
    return f"<redacted: {len(text)} chars>"


@dataclass
class Reply:
    question: str
    text: str
    kind: str                      # answer | refusal
    reason: str = ""
    url: str = ""
    hits: List = field(default_factory=list)
    retrieval: Optional[Retrieval] = None
    mode: str = ""
    problems: List[str] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=dict)
    #: The guard's Refusal, present only for kind == "refusal".
    refusal: Optional[Refusal] = None

    @property
    def contract_ok(self) -> bool:
        """<=3 sentences and exactly one link, which applies to every reply."""
        urls = [u.rstrip(".,);]") for u in _urls(self.text)]
        return count_sentences(self.text) <= REFUSAL_MAX_SENTENCES and len(urls) == 1


def _urls(text: str):
    import re

    return re.findall(r"https?://\S+", text)


def _refusal_link(reason: str, question: str) -> str:
    """A comparison refusal must point somewhere concrete, not at a generic page."""
    if reason != "no_performance_comparison":
        return ""
    search_id = resolve_fund(question)
    if search_id:
        return FUNDS_BY_ID[search_id].url
    return GROWW_SCREENER


def ask(question: str, retriever: Optional[Retriever] = None, client=None,
        top_k: int = 5, verbose: bool = False,
        memory: Optional[ConversationMemory] = None) -> Reply:
    """Answer one turn. ``memory`` carries a pending clarification across turns.

    Without a ``memory`` each call stands alone, so the CLI can be used
    one-shot without the process quietly holding half a conversation.
    """
    question = (question or "").strip()
    if not question:
        return Reply(question, "Please type a question about one of the five HDFC schemes.",
                     "refusal", "empty")

    memory = memory if memory is not None else ConversationMemory()
    pending = memory.peek()

    # A bare scheme name answers the clarification we asked, so it is joined to
    # the question it belongs to. Any other message stands on its own.
    effective = (
        f"{pending.question} {question}"
        if pending is not None and is_bare_scheme_name(question)
        else question
    )

    refusal = classify(effective)
    if refusal is not None:
        # A clarification is worth holding only until the turn after it: a new
        # scheme-scoped question replaces it, and anything else ends it, so a
        # stale one can never fire against a later, unrelated message.
        if refusal.reason == "needs_clarification":
            memory.remember(effective, refusal.reason)
        else:
            memory.clear()
        link = _refusal_link(refusal.reason, effective)
        links = refusal.links or ([link] if link else [])
        body = " ".join([refusal.text, links[0]] if links else [refusal.text])
        shown = redact(effective) if refusal.reason == "pii" else effective
        resolved = Refusal(refusal.reason, refusal.text, links)
        return Reply(shown, body, "refusal", refusal.reason,
                     links[0] if links else "", refusal=resolved)

    memory.clear()

    retriever = retriever or Retriever()
    retrieval = retriever.retrieve(effective, top_k=top_k)
    result: AnswerResult = answer_question(retrieval, client=client, verbose=verbose)

    return Reply(
        question=effective,
        text=result.text,
        kind="answer",
        url=result.url,
        hits=result.hits,
        retrieval=retrieval,
        mode=result.mode,
        problems=result.problems,
        usage=result.usage,
    )
