"""Guard step: decide whether a question is answerable from the corpus at all.

These run *before* retrieval and before the question is ever embedded, so a
refused question never reaches the vector store or the LLM. The PII guard is
the strictest: when it fires the caller must not log or persist the input.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# --- Verified external links (HTTP-checked during build) ------------------
# hdfcfund.com is excluded on purpose: it returns 403 to any non-browser
# client, so it could not be verified and does not appear in answers.
SEBI_MF_GUIDE = "https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doMutualFund=yes"
AMFI = "https://amfiindia.com/"
GROWW_HELP = "https://groww.in/help"
CAMS = "https://www.camsonline.com/"
GROWW_SCREENER = "https://groww.in/mutual-funds"

#: Every URL the assistant is allowed to emit.
ALLOWED_URLS = frozenset(
    {SEBI_MF_GUIDE, AMFI, GROWW_HELP, CAMS, GROWW_SCREENER}
    | {
        "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        "https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth",
        "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth",
        "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
        "https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth",
    }
)


# --- PII detection ---------------------------------------------------------
# Deliberately broad: a false positive costs the user one rephrasing, while a
# false negative would put their PAN or phone number into an LLM prompt.
_PII_PATTERNS = [
    ("PAN", re.compile(r"\b[A-Z]{5}\s?\d{4}\s?[A-Z]\b")),
    ("Aadhaar", re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")),
    ("Aadhaar", re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?[\dXx]{4}\b")),
    ("email address", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b")),
    ("phone number", re.compile(r"(?<!\d)(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")),
    ("OTP", re.compile(r"\b(?:otp|one[\s-]?time\s?passcode)\b\s*(?:is|=|:)?\s*\d{4,8}\b", re.I)),
    ("account number", re.compile(r"\b(?:a/c|account)\s*(?:no\.?|number|is)\s*[:=]?\s*\d{6,}\b", re.I)),
    ("card number", re.compile(r"\b(?:\d[ -]?){15,16}\b")),
    ("DOB", re.compile(r"\b(?:date of birth|dob)\b\s*[:=]?\s*\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b", re.I)),
]


def detect_pii(text: str) -> Optional[str]:
    """Return the kind of sensitive value found, or None. Never returns the value."""
    for label, pattern in _PII_PATTERNS:
        if pattern.search(text):
            return label
    return None


# --- Intent classification -------------------------------------------------

_ADVICE = re.compile(
    r"\b(should i|shall i|would you (?:buy|invest|recommend)|do you (?:think|recommend)|"
    r"recommend|advice|suggest|worth it|good time|right time|best time|"
    r"is (?:it|this) (?:a )?good (?:buy|investment|choice)|"
    r"can i invest|help me choose|which (?:one )?should|any advice|opinion|"
    r"i want to buy|suggest (?:me|a)|tell me (?:if|whether) i should)\b"
    # Advice phrased as a factual yes/no about suitability or safety. "Is HDFC
    # Small Cap safe?" is a suitability judgement wearing a factual costume, and
    # answering it would be a recommendation without ever using the word "buy".
    r"|\b(?:is|are|was|does|do)\b[^.?]{0,40}?\b(?:safe|safer|safest|risky|riskier)\b"
    r"|\b(?:safe|risky)\s+(?:to|for)\s+(?:invest|buy|hold)\b"
    r"|\b(?:good|bad|poor|great|terrible)\s+(?:investment|buy)\b"
    r"|\bshould i (?:avoid|buy|sell|switch|exit)\b",
    re.I,
)

#: Performance comparison is checked before advice, because "which is better"
#: is both and the factsheet response is the more specific, more useful one.
_COMPARISON = re.compile(
    r"\b(compare|comparison|versus|\bvs\.?\b|better (?:than|performing)|"
    r"outperform|outperforms|which (?:performs|performed|returns|grew)|"
    r"top perform|best perform|highest return|lowest return|"
    r"performance (?:comparison|rank)|rank(?:ed|ing)? (?:against|versus)|"
    r"which (?:one )?is better|which (?:one |fund )?is (?:the )?better|"
    r"is (?:it|this) better)\b"
    # Ranking schemes on a metric that is not performance. Still a cross-scheme
    # comparison, so the same refusal applies: "lowest expense ratio" picks a
    # winner just as surely as "best performing" does.
    r"|\bwhich\s+(?:hdfc\s+)?(?:fund|scheme|one)s?\b[^.?]{0,30}?"
    r"\b(?:lowest|highest|best|cheapest|smallest|largest|least|most|maximum|minimum)\b"
    r"|\b(?:lowest|highest|best|cheapest|smallest|largest)\b[^.?]{0,24}?"
    r"\b(?:expense ratio|ter|fee|charge|nav|aum)\b"
    r"|\b(?:expense ratio|fee)s?\b[^.?]{0,24}?\b(?:compare|comparison|vs\.?|versus)\b",
    re.I,
)

_STATEMENT = re.compile(
    r"\b(download|downloads|downloading|get|obtain|fetch)\b[^.?]{0,40}?"
    r"\b(statement|statements|passport|statement\s+of\s+account|"
    r"capital\s+gains\s+report|tax\s+statement|account\s+statement)\b"
    r"|\b(consolidated|account|capital\s+gains|tax)\s+statement\b"
    r"|\bstatement\b[^.?]{0,30}?\b(download|get|obtain|where|how)\b"
    r"|\bhow do i (?:get|see|view)\b[^.?]{0,30}?statement\b",
    re.I,
)

_RETURNS_CALC = re.compile(
    # The scheme name sits between the verb and "return", so the gap must span
    # several words ("how much will HDFC Large Cap return in 5 years").
    r"\bwhat (?:will|would) (?:i|one) (?:get|earn|make)"
    r"|\bhow much (?:will|would) (?:i|one|\w+(?: \w+){0,4})? ?"
    r"(?:get|earn|make|return|grow|be worth)"
    r"|\bwill (?:it|this|that|the fund|\w+(?: \w+){0,4})? ?"
    r"(?:return|grow|earn|gain|be worth|become)"
    r"|\bif i invest|\bif i put|\bproject|\bprojection|\bforecast|expected return|"
    r"\bcalculate|\bcalculator|worth after \d+|money (?:i|one) will (?:get|make)\b",
    re.I,
)


#: Structural patterns for a foreign fund/AMC mention. A fixed list of AMC names
#: was tried first and rejected: it missed every unlisted house (Motilal Oswal,
#: Nippon, ...), which is exactly the case that must not be answered.
#:
#: Instead, the corpus's own names are removed from the question and whatever
#: proper-noun fund reference survives is treated as out of scope.
_PROPER = r"[A-Z][A-Za-z&.'\-]*"
#: "Motilal Oswal Large Cap Fund", "SBI Bluechip Fund"
_FUND_PHRASE = re.compile(rf"\b(?:{_PROPER}\s+){{1,4}}{_PROPER}\s+Fund\b")
#: "Nippon India Small Cap", "ICICI Prudential Liquid Fund" -- "X India" and
#: "X Prudential" are strong AMC markers in Indian fund names.
_AMC_PHRASE = re.compile(
    rf"\b(?:{_PROPER}\s+){{0,2}}{_PROPER}\s+(?:India|Indian|Prudential|Mutual|"
    rf"Asset\s+Management|AMC)\b"
)
#: Capitalised scheme words that only make sense inside our five names.
_FUND_CATEGORY = re.compile(
    r"\b(?:Large|Mid|Small|Multi|Flexi|ELSS|Equity|Debt|Index|Sector|Thematic|"
    r"Bluechip|Advantage|Balanced|Dividend|Tax\s+Saver|Banking|Technology|"
    r"Hybrid|Infrastructure|Consumption|Value|FoF)\b",
    re.I,
)

#: First tokens that identify a fund house on their own, in any case. Catches
#: lowercase mentions the structural patterns miss ("what about sbi small cap").
_KNOWN_HOUSES = re.compile(
    r"\b(sbi|icici|axis|kotak|sundaram|nippon|tata|mirae|canara|barclays|"
    r"franklin|aditya|hsbc|bandhan|bank of baroda|dsp|l&t|mfs|parag parikh|"
    r"quant|jm financial|indiabulls|axl|uti|lic|canara\s+royal|bnp paribas|"
    r"motilal oswal|motilal|oswal|principal|pgf|absl|indigo|bernhard|"
    r"pepper|whistle|navi|canara bank)\b",
    re.I,
)


def _corpus_vocabulary() -> List[str]:
    """Every name and alias the corpus legitimately answers to."""
    from .config import FUNDS

    words: List[str] = []
    for fund in FUNDS:
        words.extend(fund.phrases())
    return words


def detect_out_of_scope_fund(question: str) -> Optional[str]:
    """Return a fund/AMC name in the question that the corpus does not cover.

    Distinguishes "SBI Bluechip Fund" (a real fund we hold no data for) from a
    vague question that simply forgot to name a scheme. The former is out of
    scope; the latter needs a clarifying question.
    """
    from .retrieval import resolve_fund  # local import: retrieval imports guards

    # If the question resolves to a corpus fund, it is in scope by definition.
    if resolve_fund(question) is not None:
        return None

    # Blank out everything the corpus legitimately answers to, so the remaining
    # proper nouns are foreign by construction.
    residual = question
    for name in sorted(_corpus_vocabulary(), key=len, reverse=True):
        if name:
            residual = re.sub(re.escape(name), " ", residual, flags=re.I)
    # Bare "HDFC ..." is our house; a foreign name never contains it.
    residual = re.sub(rf"\bHDFC\b", " ", residual)

    # 1. An AMC house name, in any case.
    house = _KNOWN_HOUSES.search(residual)
    if house:
        return house.group(0).strip()

    # 2. A "<Proper Noun ...> Fund" phrase.
    fund = _FUND_PHRASE.search(residual)
    if fund:
        return fund.group(0).strip()

    # 3. An "<Proper Noun> India/Prudential/Mutual" AMC marker.
    amc = _AMC_PHRASE.search(residual)
    if amc:
        return amc.group(0).strip()

    # 4. A foreign proper noun sitting next to a scheme-category word, e.g.
    #    "Acme Flexi Cap" -- no "Fund" suffix, no listed house, but clearly a
    #    scheme name we do not have.
    cat = _FUND_CATEGORY.search(residual)
    if cat:
        start = max(0, cat.start() - 24)
        candidate = re.search(
            rf"{_PROPER}(?:\s+{_PROPER})*$", residual[start:cat.start()].strip()
        )
        if candidate:
            return (candidate.group(0) + " " + residual[cat.start():]).strip()

    return None


#: Scheme-scoped facts, used to decide whether a scheme-less question needs
#: clarifying rather than an answer.
_SCHEME_SCOPED = re.compile(
    r"\b(expense ratio|exit load|lock-?in|nav|aum|fund manager|benchmark|"
    r"min(?:imum)? sip|lump sum|holdings|top \d+|riskometer|beta|sharpe|"
    r"sortino|alpha|stamp duty|turnover|sip|stp|swp|isin|expense)\b",
    re.I,
)


def needs_clarification(question: str) -> bool:
    """True when the question asks a scheme-scoped fact but names no scheme.

    Answering anyway would silently pick a scheme the user never mentioned and
    present its numbers as the answer, so the assistant must ask instead.
    """
    from .retrieval import resolve_fund  # local import: retrieval imports guards

    if resolve_fund(question) is not None:
        return False
    if not _SCHEME_SCOPED.search(question):
        return False
    # A cross-scheme question ("which fund has the lowest fee") is a comparison,
    # not an ambiguous lookup, so it is not caught here.
    return not _COMPARISON.search(question)


#: Words that can sit around a scheme name without asking anything of it. The
#: plan words are part of every display name, so a user who types them is still
#: naming a scheme rather than asking a question about one.
_NAME_NOISE = re.compile(
    r"[^\w]+|\b(?:the|and|for|fund|funds|plan|direct|growth|option|scheme|"
    r"schemes|please|thanks|thank\s+you|ok|okay|yes|yeah|no|sure|hi|hello|hey|"
    r"sir|madam|about|regarding|info|information|details|detail)\b",
    re.I,
)


def _after_removing_schemes(text: str) -> str:
    """What is left of the message once every corpus scheme name is deleted."""
    residual = text
    for name in sorted(_corpus_vocabulary(), key=len, reverse=True):
        if name:
            residual = re.sub(re.escape(name), " ", residual, flags=re.I)
    return _NAME_NOISE.sub(" ", residual).strip()


def is_bare_scheme_name(text: str) -> bool:
    """True when the message is nothing but a scheme name or alias.

    A scheme name on its own carries no fact to look up. Retrieval has nothing
    to key on but embedding similarity, so it hands back whatever scored best --
    figures from unrelated sections that the user never asked for. Detecting it
    here lets the assistant ask what they want to know instead of guessing.
    """
    from .retrieval import resolve_fund  # local import: retrieval imports guards

    return resolve_fund(text) is not None and not _after_removing_schemes(text)


@dataclass
class Refusal:
    reason: str
    text: str
    links: List[str] = field(default_factory=list)


def classify(question: str):
    """Return a Refusal, or None if the question is answerable from the corpus.

    Each refusal is capped at 3 sentences and carries exactly one link, the same
    contract source-derived answers must satisfy.
    """
    pii = detect_pii(question)
    if pii:
        return Refusal(
            "pii",
            "I can't accept personal details -- please remove any PAN, Aadhaar, account number, "
            "OTP, phone number or email address. I don't need them to answer a question about a "
            "mutual fund, and I never store what you send me.",
            [GROWW_HELP],
        )

    if _STATEMENT.search(question):
        return Refusal(
            "not_covered",
            "I can't answer that from my sources: I only cover facts published on the five HDFC "
            "scheme pages in my corpus, and none of them explain how to download account statements. "
            "CAMS is the registrar and transfer agent that issues these statements, and Groww's help "
            "centre has the download steps.",
            [CAMS],
        )

    if _COMPARISON.search(question) or _RETURNS_CALC.search(question):
        return Refusal(
            "no_performance_comparison",
            "I don't calculate returns, project future values, or compare schemes' performance. "
            "For performance figures, read the official monthly factsheet published by HDFC Mutual "
            "Fund and the scheme's past NAV history on its page.",
            [],  # the caller attaches the matched scheme page, or the Groww screener
        )

    if _ADVICE.search(question):
        return Refusal(
            "advice",
            "I can't give investment advice or recommend a scheme, and I don't know your goals, "
            "time horizon or risk tolerance. SEBI's mutual fund guide explains how to evaluate "
            "schemes against your own criteria.",
            [SEBI_MF_GUIDE],
        )

    other = detect_out_of_scope_fund(question)
    if other:
        return Refusal(
            "out_of_scope_fund",
            f"I don't have {other} in my sources: my corpus covers five HDFC Mutual Fund Direct "
            "Growth scheme pages on Groww and nothing else. For a fund outside that set, read its "
            "own official factsheet or its AMFI listing.",
            [AMFI],
        )

    if needs_clarification(question):
        from .config import FUNDS

        names = ", ".join(f.display_name for f in FUNDS)
        return Refusal(
            "needs_clarification",
            f"Which scheme do you mean? My corpus covers five HDFC Direct Growth schemes: {names}. "
            "Tell me the scheme name and I'll give you the figure with its source.",
            [GROWW_SCREENER],
        )

    if is_bare_scheme_name(question):
        from .config import FUNDS_BY_ID
        from .retrieval import resolve_fund  # local import: retrieval imports guards

        fund = FUNDS_BY_ID[resolve_fund(question)]
        return Refusal(
            "needs_question",
            f"What would you like to know about {fund.display_name}? "
            "(e.g. expense ratio, exit load, minimum SIP)",
            [fund.url],
        )

    return None
