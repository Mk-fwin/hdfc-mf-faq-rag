"""Answer step: call Groq, then verify the answer honours the contract.

The contract (max 3 sentences, exactly one allowlisted link, trailing
"Last updated from sources: <date>") is checked in code rather than trusted to
the prompt. On failure the answer is repaired once; if that still fails, the
answer is built deterministically from the retrieved chunk's own field text, so
the format rules cannot be violated by a bad generation.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from .config import MANIFEST_PATH
from .guards import ALLOWED_URLS
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .retrieval import Hit, Retrieval

DATE_PREFIX = "Last updated from sources:"
MAX_SENTENCES = 3
#: In+out tokens per request. Evidence is ~5 chunks x ~180 words, so this is
#: roughly 2k in / 180 out -- far under the 8k TPM ceiling.
MAX_PROMPT_TOKENS = 8000
MAX_COMPLETION_TOKENS = 180
DEFAULT_MODEL = "openai/gpt-oss-20b"
#: gpt-oss exposes a reasoning budget. "low" keeps the chain-of-thought from
#: eating the completion budget, which MAX_COMPLETION_TOKENS is sized against.
REASONING_EFFORT = "low"
_URL_RE = re.compile(r"https?://\S+")
#: The answer must *end* with the date line, on its own line or appended.
_DATE_TAIL_RE = re.compile(r"Last updated from sources:\s*\d{4}-\d{2}-\d{2}\s*$")
_ABBREV = re.compile(r"\b(?:Rs|Mr|Ms|Mrs|Dr|No|vs|etc|e\.g|i\.e|approx|St)\.$", re.I)


# --- sentence counting -----------------------------------------------------

def count_sentences(text: str) -> int:
    """Count prose sentences, ignoring the source link and the date line.

    Those two are contractual elements, not prose, so they must not consume the
    3-sentence budget. Decimals and common abbreviations are not split on.
    """
    body = _DATE_TAIL_RE.sub("", _URL_RE.sub(" ", text))
    body = re.sub(r"\d+\.\d+", "NUM", body)
    body = re.sub(r"\b[A-Z]{2,}\.", "ABBR", body)
    parts = [p for p in re.split(r"(?<=[.!?])\s+", body) if p.strip()]
    count = 0
    for part in parts:
        if _ABBREV.search(part.strip()):
            continue
        count += 1
    return count


# --- model prose -> contract reply -----------------------------------------

#: Trailing "Last updated ..." line a model may emit despite being told not to.
_ANY_DATE_LINE = re.compile(r"\n*\s*last updated from sources?:.*$", re.I | re.S)


def strip_model_tail(text: str) -> str:
    """Reduce model output to prose only.

    The model is asked not to emit a URL or a date line, but some models do
    anyway. Those are removed here and re-added from our own facts, so the
    allowlist and the date cannot be corrupted by the model.
    """
    cleaned = _ANY_DATE_LINE.sub("", text or "")
    # Markdown links, e.g. "[Source](https://...)" -- drop the label too, since
    # removing only the URL would leave a dangling bracket.
    cleaned = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", cleaned)
    cleaned = _URL_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[\[(]?\s*(?:source|src)\s*[:=].*$", "", cleaned, flags=re.I | re.M)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def compose_reply(prose: str, source_url: str, date_line: str) -> str:
    """Assemble the final reply: model prose, then our own link and date.

    This is the authoritative construction of the contract. The model never
    supplies the link or the date, so the allowlist check cannot be bypassed and
    the date always matches the manifest.
    """
    prose = strip_model_tail(prose)
    if not prose:
        return ""
    return f"{prose}\n{source_url}\n{date_line}"


# --- contract validation ---------------------------------------------------

@dataclass
class Validation:
    ok: bool
    problems: List[str] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    sentences: int = 0


def validate_answer(text: str, today: str) -> Validation:
    problems: List[str] = []
    text = (text or "").strip()

    urls = _URL_RE.findall(text)
    normalised = [u.rstrip(".,);]") for u in urls]

    if not normalised:
        problems.append("no source link")
    elif len(normalised) > 1:
        problems.append(f"{len(normalised)} links, expected exactly 1")
    else:
        if normalised[0] not in ALLOWED_URLS:
            problems.append(f"link not in allowlist: {normalised[0]}")

    sentences = count_sentences(text)
    if sentences > MAX_SENTENCES:
        problems.append(f"{sentences} sentences, max {MAX_SENTENCES}")

    if DATE_PREFIX not in text:
        problems.append("missing 'Last updated from sources:' line")
    elif not _DATE_TAIL_RE.search(text):
        # The date must close the answer, whether it sits on its own line or is
        # appended to the last sentence.
        problems.append("'Last updated from sources:' is not at the end")

    return Validation(not problems, problems, normalised, sentences)


# --- deterministic fallback ------------------------------------------------

def _strip_urls(text: str) -> str:
    return _URL_RE.sub("", text).replace("( )", "").strip()


def _pick_sentences(body: str, question: str, limit: int) -> List[str]:
    """Choose the sentences in a chunk that best match the question.

    Chunks are written as ordered fact lists (lump sum, then SIP, then
    withdrawal), so taking the first N sentences answers a SIP question with the
    lump-sum figure. Scoring each sentence against the question's content words
    and keeping only the best ones in their original order avoids that.

    Only the top-scoring sentences are kept. A sentence the question did not ask
    about is not part of the answer: "what is the benchmark" must not also return
    the investment objective. With no matching term at all, the leading sentences
    are returned instead, so a chunk with no signal on the question still says
    something rather than nothing.
    """
    stop = {
        "the", "a", "an", "of", "for", "is", "are", "in", "on", "to", "and", "or",
        "what", "how", "much", "many", "my", "this", "that", "with", "it", "do",
        "does", "i", "you", "can", "tell", "me", "please",
    }
    q_terms = {w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in stop}

    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", _strip_urls(body)) if s.strip()]
    if not sentences:
        return sentences

    def overlap(sentence: str) -> int:
        terms = {w for w in re.findall(r"[a-z0-9]+", sentence.lower()) if w not in stop}
        return len(q_terms & terms)

    scores = [overlap(s) for s in sentences]
    best = max(scores)
    keep = (
        [i for i, s in enumerate(scores) if s == best][:limit]
        if best
        else list(range(min(limit, len(sentences))))
    )
    return [sentences[i] for i in keep]


#: Sections whose figures are only as fresh as the page they came from. The
#: spec requires such dates to be attributed, not presented as live data.
ATTRIBUTED_SECTIONS = frozenset(
    {"holdings_top25", "holdings_summary", "returns_history", "risk_ratios"}
)
#: "Portfolio as of 31 Aug 2026 ..." -> attribute the whole leading phrase, so
#: the result reads as a clause rather than an insertion mid-noun-phrase.
_LEAD_AS_OF = re.compile(r"(^|(?<=[.!?]\s))([A-Z][^.!?]*?)\s+(as of|as on)\s+", re.I)


def _attribute_dates(text: str, section: Optional[str]) -> str:
    """Reword a holdings/return date as "per data on the Groww page".

    The system prompt tells the model to do this, but the deterministic fallback
    never runs the model, so it has to be applied here as well or the two output
    paths would disagree on the rule.
    """
    if section not in ATTRIBUTED_SECTIONS or not _LEAD_AS_OF.search(text):
        return text
    return _LEAD_AS_OF.sub(
        lambda m: f"{m.group(1)}Per data on the Groww page, "
                  f"{m.group(2)[0].lower() + m.group(2)[1:]} {m.group(3)} ",
        text,
        count=1,
    )


def _name_scheme(body: str, hit: Hit, question: str) -> str:
    """Prefix the scheme name when the question did not already carry it.

    A follow-up turn ("What's the expense ratio?" then "HDFC Small Cap Fund") is
    answered from a chunk whose body no longer repeats the scheme name -- the
    canonical header holds it. Without this, "Expense ratio is 0.78%." arrives
    with no indication of which scheme it belongs to. Identification of the
    answer is not an extra fact, so this does not widen what the answer claims.
    """
    fund = str(hit.metadata.get("fund_name") or "")
    if not fund or fund.lower() in question.lower():
        return body
    first, sep, rest = body.partition(" ")
    return f"{fund}, {(first[:1].lower() + first[1:]) if sep else first}{sep}{rest}"


def fallback_answer(hit: Hit, question: str, source_url: str, date_line: str) -> str:
    """Build a contract-valid answer straight from the retrieved chunk.

    Used when the model is unavailable or its output fails validation, so the
    format rules cannot be violated by a bad generation.
    """
    # Budget is MAX_SENTENCES - 1; the link and date line are not prose.
    sentences = _pick_sentences(hit.body, question, MAX_SENTENCES - 1)
    if not sentences:
        sentences = ["The retrieved source did not contain a direct answer to this question."]
    body = _attribute_dates(" ".join(sentences), hit.metadata.get("section"))
    body = _name_scheme(body, hit, question)
    return f"{body}\n{source_url}\n{date_line}"


# --- Groq ------------------------------------------------------------------

#: Values that mean "the user hasn't configured a key yet". Compared
#: case-insensitively after stripping, so "YOUR_KEY_HERE" is caught too.
_PLACEHOLDERS = frozenset(
    {"", "your_key_here", "your-key-here", "changeme", "none", "null", "todo", "xxx"}
)


def _read_env_file() -> Dict[str, str]:
    """Parse .env into a dict. Purely a read -- no environment mutation."""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    values: Dict[str, str] = {}
    try:
        with open(env_path, encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                values[name.strip()] = value.strip().strip("'\"")
    except OSError:
        pass
    return values


def _load_api_key() -> Optional[str]:
    """Resolve the Groq key from the process env or .env.

    Returns None for placeholder values so a half-finished .env is reported as
    "no key" instead of being sent to the API and failing as an auth error.
    """
    for source in (os.environ.get("GROQ_API_KEY"), _read_env_file().get("GROQ_API_KEY")):
        if source and source.strip().lower() not in _PLACEHOLDERS:
            return source.strip()
    return None


def load_model() -> str:
    """Resolve the Groq model from the environment, then .env, then the default.

    Resolved per call rather than at import time: .env is parsed lazily, so a
    module-level constant would only ever see the real process environment.
    """
    return (
        os.environ.get("GROQ_MODEL")
        or _read_env_file().get("GROQ_MODEL")
        or DEFAULT_MODEL
    ).strip()


def key_problem(key: Optional[str]) -> Optional[str]:
    """Describe why a key won't work, or None if it looks usable.

    Groq keys are always ``gsk_``-prefixed. Catching a key pasted from another
    provider here saves a pointless network round-trip and a confusing
    AuthenticationError.
    """
    if not key:
        return "no GROQ_API_KEY set (checked environment and .env)"
    if key.strip().lower() in _PLACEHOLDERS:
        return "GROQ_API_KEY is still the placeholder from .env.example"
    if not key.startswith("gsk_"):
        return (
            f"key does not start with 'gsk_' (it looks like a key from another "
            f"service, {len(key)} chars). Groq keys are at https://console.groq.com/keys"
        )
    if len(key) < 40:
        return f"key looks truncated (only {len(key)} chars)"
    return None


def _source_date() -> str:
    """Fetch date from the manifest, so the answer cites when data was read."""
    try:
        import json

        with open(MANIFEST_PATH, encoding="utf-8") as fh:
            manifest = json.load(fh)
        stamps = [s for s in manifest.get("fetched_at_per_fund", {}).values() if s]
        if stamps:
            return max(stamps)[:10]
    except (OSError, ValueError):
        pass
    return date.today().isoformat()


@dataclass
class AnswerResult:
    question: str
    text: str
    ok: bool
    mode: str
    problems: List[str] = field(default_factory=list)
    hits: List[Hit] = field(default_factory=list)
    url: str = ""
    validation: Optional[Validation] = None
    #: Token usage of every API call this answer required, summed. Empty when
    #: no call was made (guard refusal or fallback).
    usage: Dict[str, int] = field(default_factory=dict)


def _format_evidence(hits: Sequence[Hit]) -> str:
    return "\n\n".join(
        f"[{i}] {h.metadata.get('fund_name')} -- {h.metadata.get('section')} "
        f"(as of {h.metadata.get('as_of')})\n{h.body}"
        for i, h in enumerate(hits, 1)
    )


def answer_question(retrieval: Retrieval, client=None, verbose: bool = False) -> AnswerResult:
    hits = retrieval.hits
    if not hits:
        return AnswerResult(
            retrieval.question,
            "I couldn't find that in my sources. I only cover the five HDFC Direct Growth schemes "
            "in my corpus, based on their Groww pages.",
            False, "no_evidence", hits=hits,
        )

    source_url = hits[0].metadata.get("source_url", "")
    source_date = _source_date()
    date_line = f"{DATE_PREFIX} {source_date}"

    # A comparison refusal needs a concrete link; attach the matched scheme page.
    evidence = _format_evidence(hits)
    user_prompt = build_user_prompt(retrieval.question, evidence, source_date)

    approx_tokens = (len(user_prompt) + len(SYSTEM_PROMPT)) // 4
    if approx_tokens > MAX_PROMPT_TOKENS:
        user_prompt = build_user_prompt(
            retrieval.question, _format_evidence(hits[:2]), source_date
        )

    key = _load_api_key()
    key_issue = key_problem(key)
    if key_issue:
        # Covers both "no key" and "key of the wrong shape" -- the latter would
        # otherwise cost a network round-trip to fail as an AuthenticationError.
        text = fallback_answer(hits[0], retrieval.question, source_url, date_line)
        validation = validate_answer(text, source_date)
        return AnswerResult(
            retrieval.question, text, validation.ok,
            "fallback:no_api_key" if not key else "fallback:bad_key",
            validation.problems, hits, source_url, validation,
        )

    from groq import Groq

    client = client or Groq(api_key=key)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    last_validation: Optional[Validation] = None
    usage = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for attempt in (1, 2):
        try:
            completion = client.chat.completions.create(
                model=load_model(),
                messages=messages,
                temperature=0,
                max_tokens=MAX_COMPLETION_TOKENS,
                reasoning_effort=REASONING_EFFORT,
            )
        except Exception as exc:  # noqa: BLE001
            text = fallback_answer(hits[0], retrieval.question, source_url, date_line)
            validation = validate_answer(text, source_date)
            return AnswerResult(
                retrieval.question, text, validation.ok, "fallback:llm_error",
                [f"llm error: {type(exc).__name__}"], hits, source_url, validation,
                usage,
            )

        u = getattr(completion, "usage", None)
        usage["calls"] += 1
        usage["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
        usage["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
        usage["total_tokens"] += getattr(u, "total_tokens", 0) or 0
        usage[f"prompt_tokens_call{attempt}"] = getattr(u, "prompt_tokens", 0) or 0
        usage[f"completion_tokens_call{attempt}"] = getattr(u, "completion_tokens", 0) or 0
        usage[f"completion_tokens_reasoning_call{attempt}"] = (
            getattr(getattr(u, "completion_tokens_details", None), "reasoning_tokens", 0) or 0
        )

        # The link and date line are ours, not the model's.
        text = compose_reply(
            (completion.choices[0].message.content or ""),
            source_url,
            date_line,
        )
        if not text:
            # Reasoning models can spend the whole budget on reasoning and
            # return no content. Fall back rather than emit an empty answer.
            fallback = fallback_answer(
                hits[0], retrieval.question, source_url, date_line
            )
            validation = validate_answer(fallback, source_date)
            return AnswerResult(
                retrieval.question, fallback, validation.ok, "fallback:empty_model_output",
                ["model returned no answer text"], hits, source_url, validation, usage,
            )

        last_validation = validate_answer(text, source_date)
        if last_validation.ok:
            return AnswerResult(
                retrieval.question, text, True, f"groq:attempt{attempt}",
                [], hits, source_url, last_validation, usage,
            )
        if verbose:
            print(f"    (attempt {attempt} rejected: {last_validation.problems})")
        # One repair attempt: tell it exactly what it got wrong. The link and
        # date are re-applied, so the repair concerns prose only.
        messages.append({"role": "assistant", "content": strip_model_tail(text)})
        messages.append({
            "role": "user",
            "content": (
                f"Your answer broke these rules: {'; '.join(last_validation.problems)}. "
                f"Rewrite it as at most {MAX_SENTENCES} sentences of plain prose, answering "
                f"only what the question asked, with no URL and no date line."
            ),
        })

    text = fallback_answer(hits[0], retrieval.question, source_url, date_line)
    validation = validate_answer(text, source_date)
    return AnswerResult(
        retrieval.question, text, validation.ok, "fallback:validation_failed",
        (last_validation.problems if last_validation else []), hits, source_url, validation,
        usage,
    )
