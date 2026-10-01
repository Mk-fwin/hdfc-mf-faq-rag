"""CLI for the ingestion pipeline (step 1) and the query pipeline (step 2).

    python cli.py ingest                 # build the vector store from cache or live fetch
    python cli.py ingest --refresh       # force re-scrape of all 5 pages
    python cli.py stats                  # read back what is in Chroma
    python cli.py ask "expense ratio?"   # single question
    python cli.py test                   # the full acceptance run
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from mf_faq.answer import _load_api_key, count_sentences
from mf_faq.build import BuildError, build_from_records
from mf_faq.config import CHUNKS_TXT_PATH, EMBED_DIM, EMBED_MODEL, FUND_SPECS_LEN, MANIFEST_PATH
from mf_faq.fetch import load_all
from mf_faq.testset import TEST_QUESTIONS


def cmd_ingest(args: argparse.Namespace) -> int:
    print(f"Step 1/4  load      - {FUND_SPECS_LEN} Groww pages")
    records = load_all(refresh=args.refresh)

    print(f"Step 2-4/4  normalize, chunk, embed, store - {EMBED_MODEL} "
          f"({EMBED_DIM}-dim)")
    try:
        manifest = build_from_records(records, progress=args.progress)
    except BuildError as exc:
        print(f"  ingest failed: {exc}")
        return 1

    per_fund = manifest["chunks_per_fund"]
    print(f"  {manifest['total_chunks']} chunks across {len(per_fund)} fund groups")
    for name, count in sorted(per_fund.items()):
        print(f"    {count:>3}  {name}")
    print()
    print(f"  chroma rows       : {manifest['total_chunks']}")
    print(f"  embedding digest  : {manifest['embedding_fingerprint']}")
    print(f"  manifest          : {MANIFEST_PATH}")
    print(f"  chunk dump        : {CHUNKS_TXT_PATH}")
    return 0


def cmd_stats(_: argparse.Namespace) -> int:
    if not MANIFEST_PATH:
        print("no manifest; run: python cli.py ingest")
        return 1
    with open(MANIFEST_PATH, encoding="utf-8") as fh:
        manifest = json.load(fh)
    print(f"collection     : {manifest['collection']}")
    print(f"embed model    : {manifest['embed_model']} ({manifest['embed_dim']}-dim)")
    print(f"total chunks   : {manifest['total_chunks']}")
    print(f"generated at   : {manifest['generated_at']}")
    print("\nchunks per fund:")
    for name, count in manifest["chunks_per_fund"].items():
        print(f"  {count:>3}  {name}")
    print("\nchunks per section:")
    for name, count in manifest["chunks_per_section"].items():
        print(f"  {count:>3}  {name}")
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    from mf_faq.ask import ask
    from mf_faq.retrieval import Retriever

    from mf_faq.answer import _load_api_key, key_problem, load_model

    key = _load_api_key()
    problem = key_problem(key)
    print(f"Model:    {load_model()}")
    if problem:
        print(f"Groq key: NOT USABLE -> {problem}")
        print("          Answers will use the deterministic fallback.\n")
    else:
        print("Groq key: present\n")

    retriever = Retriever()
    reply = ask(args.question, retriever=retriever, top_k=args.top_k, verbose=args.verbose)

    print(f"Q: {reply.question}")
    if reply.kind == "answer" and reply.retrieval:
        r = reply.retrieval
        print(f"   [retrieval] matched_fund={r.matched_fund_name or '-'}  "
              f"candidates={r.candidates_seen}  kept={len(r.hits)}")
        for note in r.notes:
            print(f"     - {note}")
        for hit in r.hits:
            flag = "+boost" if hit.boosted else "      "
            print(f"     {hit.score:.3f} {flag} [{hit.metadata.get('section')}] "
                  f"{hit.metadata.get('fund_name')[:40]}")
    else:
        print(f"   [guard] refused: {reply.reason} (no retrieval, not sent to the LLM)")
    print(f"A: {reply.text}")
    print(f"   [{reply.kind}/{reply.reason or 'ok'}] mode={reply.mode or '-'} "
          f"contract_ok={reply.contract_ok}")
    if reply.problems:
        print(f"   problems: {reply.problems}")
    return 0


def _user_typed(case, reply) -> str:
    """The user's own words, when they differ from what the pipeline answered.

    Only a follow-up turn combined with a held question produces a note. It is
    suppressed on a PII refusal, so the run still never prints a raw question.
    """
    if reply.reason == "pii" or not case.prior or reply.question == case.question:
        return ""
    return f"   (user sent: {case.question})"


def cmd_test(args: argparse.Namespace) -> int:
    from mf_faq.ask import ask
    from mf_faq.memory import ConversationMemory
    from mf_faq.retrieval import Retriever

    from mf_faq.answer import _load_api_key, key_problem, load_model

    key = _load_api_key()
    problem = key_problem(key)
    print(f"Model:    {load_model()}")
    print(f"Groq key: {'NOT USABLE -> ' + problem if problem else 'present'}")
    print("=" * 100)

    retriever = Retriever()
    results = []
    total = len(TEST_QUESTIONS)
    for i, case in enumerate(TEST_QUESTIONS, 1):
        # One memory per case, shared by its turns: a case whose question only
        # makes sense as a follow-up must be asked the way a user asks it.
        memory = ConversationMemory()
        setup = [ask(turn, retriever=retriever, top_k=args.top_k, memory=memory)
                 for turn in case.prior]
        reply = ask(case.question, retriever=retriever, top_k=args.top_k, memory=memory)
        followup = [ask(turn, retriever=retriever, top_k=args.top_k, memory=memory)
                    for turn in case.after]
        # Only the redacted question is retained, so no raw PII outlives the loop.
        results.append((case, reply, setup, followup))
        print(f"\n[{i}/{total}] {case.label.upper()}   (testing: {case.intent})")
        for turn, (asked, answered) in enumerate(zip(case.prior, setup), 1):
            print(f"  turn {turn} Q: {asked}")
            print(f"  turn {turn} A: {answered.text}   [{answered.reason}]")
        print(f"Q: {reply.question}{_user_typed(case, reply)}")

        if reply.kind == "answer" and reply.retrieval:
            r = reply.retrieval
            print(f"    matched : {r.matched_fund_name or '(none)'}")
            print(f"    filter  : {'; '.join(r.notes)}")
            for hit in r.hits:
                flag = "boost" if hit.boosted else "     "
                print(f"      {hit.score:.3f} {flag} {hit.metadata.get('section'):22s} "
                      f"{hit.metadata.get('fund_name')[:38]}")
        else:
            print(f"    refused : {reply.reason}  (no retrieval, LLM not called)")
        print(f"A: {reply.text}")
        sent = count_sentences(reply.text) if reply.kind == "answer" else 0
        print(f"    kind={reply.kind} mode={reply.mode or '-'} contract_ok={reply.contract_ok} "
              f"sentences={sent}")
        u = reply.usage or {}
        if u.get("calls"):
            repaired = reply.mode.endswith("attempt2")
            print(f"    tokens: {u.get('total_tokens')} total "
                  f"(in {u.get('prompt_tokens')}, out {u.get('completion_tokens')}) "
                  f"in {u.get('calls')} call(s){' - REPAIRED' if repaired else ''}")
        for offset, (asked, answered) in enumerate(zip(case.after, followup), 1):
            print(f"  turn +{offset} Q: {asked}")
            print(f"  turn +{offset} A: {answered.text}   [{answered.reason}]")

    # --- summary -------------------------------------------------------
    print("\n" + "=" * 100)
    print("SUMMARY")
    print("=" * 100)
    kinds = Counter(r.kind for _, r, _, _ in results)
    reasons = Counter(r.reason for _, r, _, _ in results if r.reason)
    print(f"  answers            : {kinds.get('answer', 0)}")
    print(f"  refusals           : {kinds.get('refusal', 0)}  {dict(reasons)}")
    bad = [case.label for case, r, _, _ in results if not r.contract_ok]
    print(f"  contract compliant : {len(results) - len(bad)}/{len(results)}"
          + (f"   FAILED: {bad}" if bad else ""))
    modes = Counter(r.mode for _, r, _, _ in results if r.mode)
    print(f"  answer modes       : {dict(modes)}")
    repaired = [case.label for case, r, _, _ in results if (r.mode or "").endswith("attempt2")]
    print(f"  repaired by retry  : {len(repaired)}"
          + (f"  {repaired}" if repaired else "  (none needed)"))

    # Token usage, summed from the usage objects the API actually returned. It
    # counts every turn that was asked, not just each case's middle one.
    turns = [r for _, reply, setup, followup in results
             for r in (*setup, reply, *followup)]
    calls = sum((r.usage or {}).get("calls", 0) for r in turns)
    worst = max(
        ((r.usage or {}).get("prompt_tokens_call1", 0)
         + (r.usage or {}).get("completion_tokens_call1", 0)
         + (r.usage or {}).get("completion_tokens_call2", 0)
         for r in turns),
        default=0,
    )
    tot = sum((r.usage or {}).get("total_tokens", 0) for r in turns)
    if calls:
        print(f"  API calls          : {calls}")
        print(f"  tokens (all calls) : {tot} total, worst single question {worst}")
        print(f"  8,000 tok/min limit: {'OK' if worst < 8000 else 'EXCEEDED'} "
              f"({worst} worst, {8000 - worst} headroom)")
    else:
        print("  API calls          : 0  (every question was refused or fell back)")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write("# Sample Q&A - Mutual Fund FAQ assistant\n\n")
            fh.write("Facts-only assistant over five HDFC Direct Growth scheme pages on Groww.\n")
            fh.write(f"Answers generated in mode: {dict(modes)}\n\n")
            if modes and all(m.startswith("fallback") for m in modes):
                # Say so at the top: these answers never reached the model, so
                # the prompt rules are untested by this file.
                fh.write(f"> **No model was called.** Groq key: {problem or 'present'}. "
                         "Every answer below was built deterministically from the retrieved "
                         "chunk by `mf_faq.answer.fallback_answer`, so the system prompt's "
                         "scope rules are not exercised here.\n\n")
            fh.write("Refusals carry one link and no 'Last updated' line, because no source was\n"
                     "consulted; source-derived answers carry both.\n\n")
            for i, (case, reply, setup, followup) in enumerate(results, 1):
                fh.write(f"## {i}. {case.label}\n\n")
                for asked, answered in zip(case.prior, setup):
                    fh.write(f"**Q:** {asked}\n\n**A:** {answered.text}\n\n")
                fh.write(f"**Q:** {reply.question}{_user_typed(case, reply)}\n\n**Why this test:** {case.intent}\n\n")
                fh.write(f"**A:** {reply.text}\n\n")
                if reply.kind == "answer" and reply.retrieval:
                    fh.write("**Sources used:**\n\n")
                    seen = set()
                    for hit in reply.retrieval.hits:
                        url = hit.metadata.get("source_url")
                        if url and url not in seen:
                            seen.add(url)
                            fh.write(f"- {url} "
                                     f"({hit.metadata.get('fund_name')}, "
                                     f"{hit.metadata.get('section')})\n")
                    fh.write("\n")
                for asked, answered in zip(case.after, followup):
                    fh.write(f"**Q:** {asked}\n\n**A:** {answered.text}\n\n")
        print(f"\n  written: {args.out}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="cli.py", description="Mutual Fund FAQ assistant")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="load, chunk, embed and store the corpus")
    p_ingest.add_argument("--refresh", action="store_true", help="re-scrape instead of using cache")
    p_ingest.add_argument("--progress", action="store_true", help="show embedding progress bar")
    p_ingest.set_defaults(func=cmd_ingest)

    sub.add_parser("stats", help="show the ingestion manifest").set_defaults(func=cmd_stats)

    p_ask = sub.add_parser("ask", help="ask one question")
    p_ask.add_argument("question")
    p_ask.add_argument("--top-k", type=int, default=5)
    p_ask.add_argument("--verbose", action="store_true")
    p_ask.set_defaults(func=cmd_ask)

    p_test = sub.add_parser("test", help="run the full acceptance set")
    p_test.add_argument("--top-k", type=int, default=5)
    p_test.add_argument("--out", default=None, help="also write a markdown Q&A file")
    p_test.set_defaults(func=cmd_test)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
