"""Streamlit front end for the Mutual Fund FAQ assistant.

A thin presentation layer: every guard, retrieval step and answer-format rule
lives in the ``mf_faq`` package and is reused unchanged. This file only renders
what ``mf_faq.ask.ask`` returns.

Privacy rules enforced here:

* The PII guard runs before anything else. A refused input is replaced by a
  length-only marker immediately, so the raw string never reaches the rendered
  transcript or a log.
* Nothing is written to disk by this app. No question, answer or key is logged.
* Exactly one question is held in session state, and only between two turns of
  the same conversation: the one that produced a "Which scheme do you mean?",
  kept so the scheme name sent next can be answered against it. It is dropped
  as soon as it is answered, and a question containing personal data is never
  held at all.
* The API key is read from ``.env`` locally or from Streamlit secrets when
  deployed, and is never displayed.

Run locally with:  streamlit run app.py
"""

from __future__ import annotations

import os
from typing import List, Optional

import streamlit as st

from mf_faq.answer import _load_api_key, key_problem, load_model
from mf_faq.ask import ask
from mf_faq.build import build_from_cache, index_is_built
from mf_faq.guards import classify, detect_pii
from mf_faq.memory import ConversationMemory
from mf_faq.retrieval import Retriever

TITLE = "HDFC Mutual Fund FAQ"
TAGLINE = "Facts-only. No investment advice."

#: Clickable starters. Only topics the corpus actually covers, and nothing the
#: assistant would refuse -- a demo button that always fails is a bad demo.
EXAMPLES = [
    "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
    "What is the exit load on HDFC Small Cap Fund Direct Growth?",
    "Who manages HDFC Small Cap Fund?",
]

SCOPE_NOTE = (
    "Covers five HDFC Direct Growth scheme pages on Groww: Large Cap, Flexi Cap "
    "(formerly Equity), ELSS Tax Saver, Small Cap and Balanced Advantage."
)

FALLBACK_NOTE = (
    "Fallback answers are extracted verbatim from the matched source chunk; "
    "they cannot combine facts across chunks."
)


# --- secrets ---------------------------------------------------------------

def resolve_api_key() -> str:
    """Key from Streamlit secrets when deployed, else from .env / environment.

    A deployment injects the key as a Streamlit secret; local development keeps
    it in .env. The value is returned to the caller and never rendered. When it
    comes from secrets it is exported to the process environment so that
    ``mf_faq.answer``, which only knows about .env, uses the same key.
    """
    try:
        secret = st.secrets.get("GROQ_API_KEY")  # type: ignore[attr-defined]
        if secret:
            secret = str(secret).strip()
            os.environ["GROQ_API_KEY"] = secret
            return secret
    except Exception:  # noqa: BLE001 - secrets absent outside a deployed app
        pass
    return _load_api_key() or ""


# --- one-time load ---------------------------------------------------------

@st.cache_resource(show_spinner="Loading the vector store...")
def get_retriever() -> Retriever:
    """The retriever, building the vector store first if it is not there yet.

    ``chroma_db/`` is gitignored, so a fresh clone and a freshly deployed app
    both start with no index. Rather than fail and tell the reader to go run a
    CLI command they may not have a shell for, the app builds it from the
    committed pages in ``data/raw/``. That build is local and offline: nothing
    here requests anything from Groww, so a deploy with no outbound access to
    the source still starts.

    ``st.cache_resource`` makes this once per server process. The build is not
    guarded by a lock, so two sessions arriving before the first build finishes
    would each write the store; ``write_chunks`` replaces the collection rather
    than appending, so the loser overwrites the winner with identical content.
    """
    if not index_is_built():
        with st.spinner("Building the index (first start only)..."):
            build_from_cache()
    return Retriever()


@st.cache_resource
def api_status() -> Optional[str]:
    """Why the LLM is unavailable, or None when it is live. Never the key."""
    return key_problem(resolve_api_key())


# --- per-session state -----------------------------------------------------

def conversation_memory() -> ConversationMemory:
    """One clarification buffer per browser session.

    Deliberately ``st.session_state`` rather than ``st.cache_resource``: a cached
    resource is shared by every session, which would let one user's held question
    be completed by another user's scheme name.
    """
    if "memory" not in st.session_state:
        st.session_state.memory = ConversationMemory()
    return st.session_state.memory


# --- rendering -------------------------------------------------------------

def _render_refusal(refusal) -> None:
    """Render a guard refusal in its own distinct style."""
    with st.container(border=True):
        st.markdown(f":no_entry: **Not answered — {refusal.reason.replace('_', ' ')}**")
        body, sep, tail = refusal.text.partition("http")
        st.markdown(body.strip())
        link = (refusal.links or [None])[0]
        if sep:
            link = ("http" + tail).rstrip(".")
        if link:
            st.markdown(f"[Source]({link})")


def render_reply(safe_question: str, memory: ConversationMemory) -> None:
    """Run the pipeline for one question and render the result.

    ``safe_question`` has already been through the PII check, so nothing
    sensitive reaches the transcript. ``memory`` carries the clarification that
    may be waiting to be answered by this turn.
    """
    reply = ask(safe_question, retriever=get_retriever(), memory=memory)

    if reply.kind == "refusal":
        _render_refusal(reply.refusal)
        return

    date_line = ""
    link = ""
    body_parts: List[str] = []
    for raw in reply.text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Last updated from sources:"):
            date_line = line
        elif line.startswith("http"):
            link = line
        else:
            body_parts.append(line)

    st.markdown("\n\n".join(body_parts))
    if link:
        st.markdown(f"[Source]({link})")
    if date_line:
        st.caption(date_line)


def main() -> None:
    st.set_page_config(page_title=TITLE, page_icon="chart_with_upwards_trend",
                       layout="centered")
    st.title(TITLE)

    # Resolve the retriever on every run, not only when a question is asked, so a
    # broken build is reported on the page the reader is already looking at.
    try:
        get_retriever()
    except Exception as exc:  # noqa: BLE001 - shown, not swallowed silently
        st.error(f"The index could not be built: {exc}")
        st.stop()

    # Always visible, above the fold, on every rerun.
    st.info(f"**{TAGLINE}**  \n{SCOPE_NOTE}")

    problem = api_status()
    with st.sidebar:
        st.subheader("Status")
        st.write(f"Model: `{load_model()}`")
        if problem is None:
            st.success("Groq connected — live answers")
        else:
            st.warning(f"Fallback mode — {problem}")
            st.caption(FALLBACK_NOTE)

    st.subheader("Ask a question")
    for label, example in enumerate(EXAMPLES, 1):
        if st.button(f"Try: {example}", key=f"ex{label}", use_container_width=True):
            st.session_state.pending = example

    typed = st.text_input(
        "Your question",
        key="typed",
        placeholder="e.g. What is the minimum SIP for HDFC Balanced Advantage Fund?",
        label_visibility="collapsed",
    )
    asked = st.button("Ask", type="primary")

    question = str(st.session_state.pop("pending", "") or "").strip()
    if asked and typed and typed.strip():
        question = typed.strip()

    if not question:
        return

    # PII is checked before anything else. On a hit the raw text is used only to
    # build the guard's refusal -- it is never embedded, never sent to the LLM,
    # never rendered and never stored, so there is nothing to leak.
    if detect_pii(question):
        refusal = classify(question)
        with st.chat_message("user"):
            st.markdown(f"<redacted: {len(question)} chars>")
        with st.chat_message("assistant"):
            _render_refusal(refusal)
        return

    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        with st.spinner("Checking sources..."):
            render_reply(question, conversation_memory())


if __name__ == "__main__":
    main()
