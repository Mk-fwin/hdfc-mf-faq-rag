"""One-shot memory for a clarification the assistant asked itself.

When a question names no scheme the guards answer "Which scheme do you mean?",
and the natural reply is just the name -- which on its own carries no fact to
look up. Holding that name alone is useless, so the question that triggered the
clarification is kept here for exactly one following turn and combined with the
name when it arrives.

The rules are enforced here rather than left to the caller:

* **One turn only.** A stored question informs one answer. ``mf_faq.ask`` clears
  it as soon as that answer is produced, so it can never colour a later,
  unrelated question.
* **Never personal data.** ``remember`` refuses any text the PII guard flags, so
  a stored question cannot hold a PAN or a phone number even if a caller reaches
  this class without going through ``mf_faq.guards.classify``.
* **Nothing is written anywhere.** An instance holds a single string in the
  caller's process, and each conversation gets its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .guards import detect_pii


@dataclass(frozen=True)
class PendingClarification:
    """The question that was held back, and the guard that held it."""

    question: str
    reason: str = "needs_clarification"


class ConversationMemory:
    """Holds at most one pending clarification. Never anything else."""

    def __init__(self) -> None:
        self._pending: Optional[PendingClarification] = None

    def remember(self, question: str, reason: str = "needs_clarification") -> bool:
        """Hold a question for the next turn. False if it was not stored.

        A question the PII guard flags is dropped rather than stored: the caller
        must not keep personal data in memory, and must not re-use it later.
        """
        text = (question or "").strip()
        if not text or detect_pii(text):
            self._pending = None
            return False
        self._pending = PendingClarification(text, reason)
        return True

    def peek(self) -> Optional[PendingClarification]:
        """The pending question, if any, without consuming it."""
        return self._pending

    def clear(self) -> None:
        """Forget the pending question: it has been answered, or is stale."""
        self._pending = None
