> **Facts-only. No investment advice.** This assistant will not recommend a
> scheme. It answers only from five HDFC scheme pages, and every answer is a
> dated snapshot — verify against the official factsheet before acting. See
> [DISCLAIMER.md](DISCLAIMER.md).
>
> This tool is a facts-only research aid, not financial advice. It will not
> recommend a scheme. Figures are a dated snapshot from public fund pages and may
> be out of date or wrong — verify against the official factsheet and an advisor
> before acting. Mutual fund investments are subject to market risks.
>
> Do not enter personal information such as PAN, Aadhaar, account numbers, OTPs,
> phone numbers or email addresses.

# Mutual Fund FAQ assistant

A facts-only RAG assistant over **five HDFC Mutual Fund Direct Growth scheme
pages on Groww**. It answers scheme facts, cites one source link per answer, and
refuses anything that would be investment advice, a performance comparison, or a
calculation.

## Scope

**AMC: HDFC Mutual Fund only.** Nothing else is covered.

| Scheme | URL slug |
|---|---|
| HDFC Large Cap Fund Direct Growth | `hdfc-large-cap-fund-direct-growth` |
| HDFC Flexi Cap Direct Plan Growth *(formerly HDFC Equity Fund)* | `hdfc-equity-fund-direct-growth` |
| HDFC ELSS Tax Saver Fund Direct Plan Growth | `hdfc-elss-tax-saver-fund-direct-plan-growth` |
| HDFC Small Cap Fund Direct Growth | `hdfc-small-cap-fund-direct-growth` |
| HDFC Balanced Advantage Fund Direct Growth | `hdfc-balanced-advantage-fund-direct-growth` |

Questions naming any other fund or AMC are refused rather than answered from a
loosely-related chunk. Questions asking for a scheme-scoped fact but naming no
scheme get a clarifying question, not a guess — and the scheme name sent next is
combined with the held question and answered. A scheme name sent on its own,
with nothing to look up, is asked what the user wants to know about it rather
than answered with whatever retrieval ranked highest.

The `hdfc-equity-fund-direct-growth` slug is retained as specified even though
Groww now serves HDFC Flexi Cap content for it. Every chunk carries the former
name so answers never reference a scheme that no longer exists.

## Sources

All five pages were fetched on **2026-09-29** and are cached locally, so the
corpus is reproducible without re-scraping. This table is the same set as
`sources.csv`.

| Scheme | URL | Fetch date |
|---|---|---|
| HDFC Large Cap Fund Direct Growth | <https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth> | 2026-09-29 |
| HDFC Flexi Cap Direct Plan Growth *(formerly HDFC Equity Fund)* | <https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth> | 2026-09-29 |
| HDFC ELSS Tax Saver Fund Direct Plan Growth | <https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth> | 2026-09-29 |
| HDFC Small Cap Fund Direct Growth | <https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth> | 2026-09-29 |
| HDFC Balanced Advantage Fund Direct Growth | <https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth> | 2026-09-29 |

Holdings on those pages were as of **31 Aug 2026**; the top 25 per scheme are
kept, so coverage is partial (see [Known limits](#known-limits)).

## Setup

Requires Python 3.10+.

```bash
cd "/Users/mk/Desktop/Grow ChatBot"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Then put your key in `.env`:

```
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-20b
```

`.env` is gitignored and must never be committed. A key is optional: without
one the assistant still answers, using a deterministic fallback that quotes the
matched source chunk. The fallback cannot combine facts across chunks, so live
mode is meaningfully better.

Ingest the corpus (once — downloads and caches the five pages):

```bash
.venv/bin/python cli.py ingest
.venv/bin/python cli.py stats
```

## Running the app

```bash
.venv/bin/streamlit run app.py
```

Then open <http://localhost:8501>.

The UI is a thin layer over `mf_faq` — it adds no answering logic of its own.
The same pipeline is available from the CLI:

```bash
.venv/bin/python cli.py ask "What is the expense ratio of HDFC Large Cap Fund?"
.venv/bin/python cli.py test --out SAMPLE_QA.md
```

`cli.py test` runs the 21-question acceptance set, prints per-question mode and
real token usage from the API responses, and writes `SAMPLE_QA.md`. Two of the
cases are conversations, asked as more than one turn against the same
clarification memory.

## Sample Q&A

Ten cases from the 21-question acceptance set, copied verbatim from the current
[SAMPLE_QA.md](SAMPLE_QA.md). Between them they cover a sourced fact, an advice
refusal, a comparison refusal, an uncovered topic, and a two-turn clarification.

Refusals carry one link and no date line, because no source was consulted.
Source-derived answers carry both.

### 1. Sourced fact — expense ratio

**Q:** What is the expense ratio of HDFC Large Cap Fund Direct Growth?

**A:** The expense ratio of HDFC Large Cap Fund Direct Growth is 1.03%.

Source: <https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth>
Last updated from sources: 2026-09-29

### 2. Sourced fact — exit load

**Q:** What is the exit load on HDFC Small Cap Fund Direct Growth?

**A:** The exit load on HDFC Small Cap Fund Direct Growth is 1% if redeemed
within one year.

Source: <https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth>
Last updated from sources: 2026-09-29

### 3. Sourced fact — alias resolved to the Flexi Cap page

**Q:** What is the benchmark of HDFC Equity Fund?

**A:** The benchmark of the HDFC Equity Fund is the NIFTY 500 Total Return
Index.

Source: <https://groww.in/mutual-funds/hdfc-equity-fund-direct-growth>
Last updated from sources: 2026-09-29

### 4. Sourced fact — full manager roster

**Q:** Who manages HDFC Balanced Advantage Fund?

**A:** The HDFC Balanced Advantage Fund is managed by six fund managers: Anil
Bamboli, Arun Agarwal, Dhruv Muchhal, Nandita Menezes, Gopal Agrawal, and Ihab
Dalwai.

Source: <https://groww.in/mutual-funds/hdfc-balanced-advantage-fund-direct-growth>
Last updated from sources: 2026-09-29

### 5. Advice refusal — buy recommendation

**Q:** Should I buy HDFC Large Cap Fund?

**A:** I can't give investment advice or recommend a scheme, and I don't know
your goals, time horizon or risk tolerance. SEBI's mutual fund guide explains
how to evaluate schemes against your own criteria.
<https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doMutualFund=yes>

### 6. Advice refusal — framed as a safety question

**Q:** Is HDFC Small Cap safe?

**A:** I can't give investment advice or recommend a scheme, and I don't know
your goals, time horizon or risk tolerance. SEBI's mutual fund guide explains
how to evaluate schemes against your own criteria.
<https://www.sebi.gov.in/sebiweb/other/OtherAction.do?doMutualFund=yes>

### 7. Comparison refusal

**Q:** Which is better, HDFC Large Cap Fund or HDFC Small Cap Fund?

**A:** I don't calculate returns, project future values, or compare schemes'
performance. For performance figures, read the official monthly factsheet
published by HDFC Mutual Fund and the scheme's past NAV history on its page.
<https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth>

### 8. Not covered — statement download

**Q:** How do I download my account statement for HDFC ELSS?

**A:** I can't answer that from my sources: I only cover facts published on the
five HDFC scheme pages in my corpus, and none of them explain how to download
account statements. CAMS is the registrar and transfer agent that issues these
statements, and Groww's help centre has the download steps.
<https://www.camsonline.com/>

### 9. Out of scope — real fund outside the corpus

**Q:** Expense ratio of SBI Bluechip Fund

**A:** I don't have SBI in my sources: my corpus covers five HDFC Mutual Fund
Direct Growth scheme pages on Groww and nothing else. For a fund outside that
set, read its own official factsheet or its AMFI listing.
<https://amfiindia.com/>

### 10. Clarification follow-up — two turns

**Q:** What's the expense ratio?

**A:** Which scheme do you mean? My corpus covers five HDFC Direct Growth
schemes: HDFC Large Cap Fund Direct Growth, HDFC Flexi Cap Direct Plan Growth
(formerly HDFC Equity Fund), HDFC ELSS Tax Saver Fund Direct Plan Growth, HDFC
Small Cap Fund Direct Growth, HDFC Balanced Advantage Fund Direct Growth. Tell
me the scheme name and I'll give you the figure with its source.
<https://groww.in/mutual-funds>

The scheme name sent next completes the held question rather than starting a new
lookup.

**Q:** What's the expense ratio? HDFC Small Cap Fund
*(user sent only: HDFC Small Cap Fund)*

**A:** The expense ratio of the HDFC Small Cap Fund is 0.78%.

Source: <https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth>
Last updated from sources: 2026-09-29

Because the previous question was answered and not left in memory, sending the
scheme name a third time asks what to look up instead of repeating the figure:

**Q:** HDFC Small Cap Fund

**A:** What would you like to know about HDFC Small Cap Fund Direct Growth?
(e.g. expense ratio, exit load, minimum SIP)
<https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth>

## How it works

```
question
  -> guards (PII, advice, comparison, out-of-scope, clarification, bare name)
  -> hold the question if a clarification was asked, answer it with the scheme
     name that comes next
  -> embed (all-MiniLM-L6-v2, 384-dim)
  -> Chroma top-20, is_current=1 filter
  -> alias filter, section boost, single-fact scoping, per-scheme cap 2
  -> top 5 chunks -> Groq (max 3 sentences of prose)
  -> code appends the source link and the "Last updated" line
```

**One question is scoped to one fact.** Each fee-type fact gets its own chunk
(`expense_ratio`, `stamp_duty`, `portfolio_turnover`, `exit_load_current`,
`lockin`), and when a question names exactly one of those fact types, the other
sections are dropped from the evidence before the model sees them. A question
about the expense ratio cannot be answered with the exit load, because the exit
load is not in its context. Two fact types in one question ("expense ratio and
exit load") keep both and fall back to plain ranking.

The link and the date line are **appended in code**, never asked of the model.
`mf_faq.answer.compose_reply` strips any URL or date the model emits and
substitutes its own, so a hallucinated or off-allowlist link cannot reach the
user. Every reply is then validated: at most 3 sentences and exactly one
allowlisted URL. A rejected answer is retried once, then falls back.

**Guards run before retrieval.** A refused question is never embedded, never
searched, and never sent to the model. PII is detected first and the input is
replaced with a length-only marker before it can be rendered or stored.

**One question is held between turns.** When a guard asks "Which scheme do you
mean?", that question is kept in `mf_faq.memory.ConversationMemory` — in memory
only, one per conversation, never written to disk — so the scheme name sent next
can be combined with it and answered as the user meant it. The held question is
dropped as soon as it is answered, and `remember` refuses any question the PII
guard flags, so a PAN or phone number can never be held. The Streamlit app keeps
one in `st.session_state` rather than `st.cache_resource`, so a cached resource
cannot leak one user's question to another.

## Known limits

- **Holdings are top 25 per scheme, not the full portfolio.** Coverage varies a
  lot, and is recomputable from the cached payloads
  (`sum(sorted(corpus_per)[:25])`): 83.03% (Large Cap, 50 holdings), 74.50%
  (ELSS Tax Saver, 65), 72.16% (Flexi Cap, 86), 57.65% (Small Cap, 87) and
  48.48% (Balanced Advantage, 326). For Balanced Advantage, the listed 25 names
  are under half the book, so "what are the holdings" is answered with a
  partial list. The percentage is stated in the chunk so the model can say so.
- **Groww is the only source, and it is a distributor, not the issuer.** Its
  pages are convenient and machine-readable, but they are a marketing surface.
  `hdfcfund.com` — the issuer's own site — returns HTTP 403 to non-browser
  clients, so it could not be used or verified.
- **Some Groww fields are stale and are deliberately ignored.** The top-level
  `fund_manager` field names a manager the page does not show; `nfo_risk`
  carries a 2013-era riskometer; `description` and `benchmark` at top level are
  outdated; `category_info` describes a "Contra fund" that is factually
  unrelated to Large Cap; `amc_info` is 2017-vintage. The specific
  field-precedence rules live in `mf_faq/config.py` (`STALE_KEYS`, `DENY_KEYS`,
  `AMC_LEVEL_KEYS`) and are documented inline.
- **Only one expense ratio is stated.** The cached Groww data also carries a
  separate `base_expense_ratio` field that is not shown on the visible page. It
  is excluded at ingest (`DENY_KEYS` in `mf_faq/config.py`), so every answer
  gives the single figure users can see and verify on the page.
- **The deterministic fallback quotes the most on-topic sentence only.** Without
  a key, `mf_faq.answer.fallback_answer` scores each sentence of the retrieved
  chunk against the question and keeps only those that tie for best, so a
  benchmark question does not also return the investment objective. With no
  matching term it falls back to the leading sentences. The system prompt states
  the same rule for the model path; only the fallback enforces it in code.
- **No SEBI riskometer level.** The pages carry Groww's own risk label, which is
  labelled as such. The chunk states that no SEBI riskometer value is available
  rather than substituting one.
- **Exit-load history is versioned, and only the current version is
  retrievable.** Superseded revisions are kept in the store with
  `is_current=0` and are filtered out of every query.
- **Statement downloads, portfolio transactions, dividends, and tax filing are
  not covered.** These are refused with a link to CAMS or Groww help.
- **No performance comparison, no projections, no calculations.** Refused even
  when phrased as ranking on a non-return metric ("lowest expense ratio"),
  since that still picks a winner.
- **Fund manager start dates are month and year only, e.g. "since Jun 2023".**
  That is what the Groww page displays. The underlying `date_from` field
  carries a full timestamp whose day component is a storage artefact of how
  midnight IST is encoded (18:30 UTC the previous day), so a day is never shown.
- **Manager rosters are complete, and can be long.** Balanced Advantage lists
  six managers. The roster is a single chunk so retrieval cannot truncate it, but
  biographies live in a separate `fund_manager_profile` section that the
  "who manages" boost does not favour.
- **Answers are dated snapshots, not live data.** The date line is the fetch
  date from `data/manifest.json`, not today's NAV.
- **The acceptance set no longer discriminates.** All 21 pass on the first
  attempt with the current model, so it confirms nothing is broken but will not
  reveal a regression in a well-behaved model.
- **A held question survives exactly one turn.** If the reply to "Which scheme do
  you mean?" is not a scheme name — a new question, or a refusal — the held
  question is dropped rather than applied to it later.

## Disclaimer

> This tool is a facts-only research aid, not financial advice. It will not
> recommend a scheme. Figures are a dated snapshot from public fund pages and may
> be out of date or wrong — verify against the official factsheet and an advisor
> before acting. Mutual fund investments are subject to market risks.

The long form, with what the assistant refuses and why it may be wrong, is in
[DISCLAIMER.md](DISCLAIMER.md) and is shown at the top of this README.

Do not enter personal information such as PAN, Aadhaar, account numbers, OTPs,
phone numbers or email addresses. Those are rejected before they are stored or
transmitted, and no sample question or answer in this README contains any.

## Files

| Path | Purpose |
|---|---|
| `app.py` | Streamlit UI (the only UI file) |
| `cli.py` | `ingest`, `stats`, `ask`, `test` |
| `mf_faq/` | The pipeline: guards, retrieval, answering, ingestion |
| `sources.csv` | The five source URLs with fetch dates |
| `SAMPLE_QA.md` | Generated acceptance output |
| `DISCLAIMER.md` | Long and short disclaimer text |
| `data/raw/` | Cached source pages (**committed** — the corpus the app builds from) |
| `data/manifest.json` | What the last build wrote (committed, rewritten per build) |
| `chroma_db/` | Vector store (gitignored, rebuilt on first start) |

## Deploying

`app.py` reads `GROQ_API_KEY` from Streamlit secrets first, then `.env`, then
the process environment. The key is never displayed in the UI and the app never
writes it to disk.

**On Streamlit Community Cloud**, open your app's **Settings → Secrets**, paste
the key, and press Save. There is no `streamlit secrets set` command to run from
a terminal on a hosted app — the secret is set through that UI.

The secrets panel is a **single flat TOML file of top-level key/value pairs**. It
is not a multi-environment file, so there is no `[default]` table header to
write: a section header makes the key invisible to `st.secrets` and the app
silently falls back to no key. Write it flat:

```toml
GROQ_API_KEY = "gsk_..."
```

Only `GROQ_API_KEY` is read from Streamlit secrets. **`GROQ_MODEL` is not**:
`app.py` lifts the key into the process environment, but `load_model()` resolves
the model from the environment, then `.env`, then its default — it never touches
`st.secrets`. Setting `GROQ_MODEL` in the secrets panel therefore has no effect;
to change the model on a hosted app, set it as an environment variable in the
app's settings, or edit the default in `mf_faq/answer.py`.

Locally, keep the key in `.env` instead:

```bash
cp .env.example .env
```

`.env.example` is committed and contains a placeholder only. Its
`GROQ_MODEL` is `openai/gpt-oss-20b`, the same model `load_model()` falls back
to, so copying the file as-is reproduces the default behaviour and the line can
be deleted without changing it.

**The index is built automatically on first start.** `chroma_db/` is gitignored,
so a fresh clone and a deployed app both begin with no vector store. Rather than
fail and ask the reader for a shell, `app.py` builds it on the first run:

```
Building the index (first start only)...
```

That build reads the **committed** pages in `data/raw/` and is entirely local.
It sends no request to Groww, so deployment needs no outbound access to the
source, and the figures it answers with are the same ones as the fetch date in
[Sources](#sources) rather than whatever the pages say today.

The cached pages are committed on purpose, which is the one thing here that trades
repo size for reproducibility: `data/raw/` is about 1.7 MB of JSON. Re-ingest to
refresh them — that step *does* hit the network, and is the only command that
does:

```bash
.venv/bin/python cli.py ingest --refresh
```

`data/manifest.json` is committed for the same reason and is rewritten by every
build, so it always describes the store that is actually on disk.

The build is wrapped in `st.cache_resource`, so it happens once per server
process rather than per question or per session. If it fails — most plausibly
because `data/raw/` is missing from the clone — the page shows the error instead
of silently answering from an empty store, and the local equivalent is
`.venv/bin/python cli.py stats` to see what was last written.
