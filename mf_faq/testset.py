"""The 21-question acceptance run for step 2.

The first ten cover one of every behaviour rule: five in-scope factual lookups
across all five schemes, plus advice, performance comparison, PII, and a question
the corpus genuinely cannot answer.

The next nine are adversarial -- they are the ways a user phrases the same
intentions while slipping past a naive guard:

11. scheme-scoped fact with no scheme named  -> must ask which, not guess
12. advice phrased as a factual yes/no        -> must still refuse
13. cross-scheme ranking on a non-return metric -> must refuse like any comparison
14. a real fund outside the corpus             -> must not answer from a near-miss chunk
15. PII wrapped around an otherwise valid question -> PII wins, question dropped
16. an AMC on no known list                    -> caught structurally, not by name
17. a foreign scheme with no "Fund" in the name -> caught without a name list
18. a two-manager roster                    -> both named, not just the top hit
19. a six-manager roster                    -> all six, still within 3 sentences

The last two are conversational, and are the only cases with more than one turn:

20. a scheme name answering our own clarification -> the two are combined, and a
    repeat of the same name is not answered again, because the question was not
    left in memory
21. a scheme name with nothing to ask about        -> must ask, not dump chunks
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class Case:
    """One acceptance case, with the turns around it when the case is a conversation.

    ``prior`` and ``after`` are turns asked against the same
    ``ConversationMemory`` as ``question``, the way a user would ask them: the
    middle turn is the case's own, and its reply is what the run judges. The
    flanking turns are recorded in the output so a claim about them can be read
    rather than taken on trust.
    """

    label: str
    question: str
    intent: str
    prior: Tuple[str, ...] = ()
    after: Tuple[str, ...] = ()


TEST_QUESTIONS = [
    Case("expense ratio", "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
         "expense_ratio chunk alone, scheme-scoped: the ratio only, no exit load or base ratio"),
    Case("exit load", "What is the exit load on HDFC Small Cap Fund Direct Growth?",
         "is_current=1 only; superseded versions must not appear"),
    Case("ELSS lock-in", "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
         "the only lockin chunk in the corpus"),
    Case("minimum SIP", "What is the minimum SIP amount for HDFC Balanced Advantage Fund?",
         "minimums chunk"),
    Case("alias: HDFC Equity", "What is the benchmark of HDFC Equity Fund?",
         "alias -> hdfc-equity-fund-direct-growth (Flexi Cap)"),
    Case("fund manager", "Who manages HDFC Small Cap Fund?",
         "fund_manager section boost"),
    Case("advice", "Should I buy HDFC Large Cap Fund?",
         "refuse advice, no retrieval"),
    Case("comparison", "Which is better, HDFC Large Cap Fund or HDFC Small Cap Fund?",
         "refuse comparison, link the matched scheme page"),
    Case("PII", "My PAN is ABCDE1234F and my phone is 9876543210, tell me the exit load on HDFC ELSS",
         "reject PII without storing it"),
    Case("statement download", "How do I download my account statement for HDFC ELSS?",
         "explicit not-covered reply with a verified link"),
    # --- adversarial -------------------------------------------------------
    Case("no scheme named", "What's the expense ratio?",
         "scheme-scoped fact with no scheme: must ask which, must not guess a fund"),
    Case("advice as fact", "Is HDFC Small Cap safe?",
         "'is X safe' is a suitability judgement: must refuse, not quote the risk label"),
    Case("rank on non-return metric", "Which HDFC fund has the lowest expense ratio?",
         "cross-scheme ranking on fees: refuse like any other comparison"),
    Case("out of scope fund", "Expense ratio of SBI Bluechip Fund",
         "a real fund outside the corpus: must not answer from a near-miss HDFC chunk"),
    Case("PII plus valid question", "My PAN is ABCDE1234F, what is the exit load?",
         "PII must win: refuse and redact, even though the question is otherwise answerable"),
    Case("out of scope: unlisted AMC", "Expense ratio of Motilal Oswal Large Cap Fund",
         "an AMC that was never in any list: must be caught structurally, not by name"),
    Case("out of scope: no 'Fund' suffix", "Exit load of Nippon India Small Cap",
         "a real foreign scheme whose name omits 'Fund': must refuse, not cite an HDFC page"),
    Case("fund manager, 2 managers", "Who manages HDFC Small Cap Fund?",
         "must name every manager on the page, not just the top-ranked one"),
    Case("fund manager, 6 managers", "Who manages HDFC Balanced Advantage Fund?",
         "a six-manager roster must still fit the 3-sentence limit, month+year only"),
    # --- conversational ---------------------------------------------------
    Case("clarification answered by name", "HDFC Small Cap Fund",
         "a bare scheme name must complete the held question, not start a new lookup; "
         "the same name sent again must then be asked what to look up, because the "
         "question was answered and not left in memory",
         prior=("What's the expense ratio?",),
         after=("HDFC Small Cap Fund",)),
    Case("scheme name, no question", "HDFC Equity",
         "a bare alias with no held question: ask what to look up, never return "
         "unrelated chunks; an alias must still name the Flexi Cap page"),
]
