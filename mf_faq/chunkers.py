"""Chunk step: structured record -> atomic, self-describing chunks.

No generic text splitter. These pages are structured records, so each fact
group becomes one chunk that carries its own fund identity. Every chunk is
prefixed with a canonical header, which is what lets a 384-dim MiniLM vector
tell five structurally identical HDFC schemes apart, and is why no chunk
overlap is needed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from .config import HOLDINGS_TOP_N, FundSpec
from .normalize import (
    NormalizedFund,
    _date,
    month_year,
    fmt_inr,
    fmt_inr_cr,
    fmt_pct,
)


@dataclass
class Chunk:
    chunk_id: str
    text: str
    metadata: Dict = field(default_factory=dict)


def _prefix(nf: NormalizedFund) -> str:
    return (
        f"Fund: {nf.display_name} | ISIN: {nf.isin} | "
        f"Category: {nf.category} / {nf.sub_category} | "
        f"Plan: {nf.plan_type} {nf.scheme_type}"
    )


def _seq(i: int) -> str:
    return f"{i:02d}"


# --- individual chunk builders --------------------------------------------
# Each returns (body_sentences, as_of, extra_metadata).


def _identity(nf: NormalizedFund):
    body = (
        f"{nf.scheme_name} is an open-ended {nf.category} "
        f"{nf.sub_category} {nf.scheme_type} scheme of {nf.amc.get('name') or 'HDFC Mutual Fund'}. "
        f"Its ISIN is {nf.isin} and its internal scheme code is {nf.scheme_code}. "
        f"Latest NAV is Rs {nf.nav:,.3f} as of {nf.nav_date}. "
        f"Fund size (AUM) is {fmt_inr_cr(nf.aum_cr)}. "
        f"Groww's own rating for the scheme is {nf.groww_rating} out of 5. "
        f"Direct-plan inception date is {nf.plan_launch_date}; "
        f"the fund itself launched on {nf.fund_launch_date}."
    )
    return body, nf.nav_date, {}


def _risk_profile(nf: NormalizedFund):
    body = (
        f"Groww's risk classification for this scheme is \"{nf.groww_risk}\". "
        f"This is Groww's own categorisation of the scheme's risk, not the SEBI riskometer: "
        f"the page carries no SEBI riskometer level, so no riskometer value can be stated from this source. "
        f"Return standard deviation is {fmt_pct(nf.std_deviation)} and beta is {fmt_pct(nf.beta)}."
    )
    return body, nf.fetched_at[:10], {}


def _expense_ratio(nf: NormalizedFund):
    """The expense ratio the Groww page shows, and nothing else.

    Atomic on purpose. This chunk used to pack the expense ratio together with
    the exit load, stamp duty and turnover, so a question about one of those
    facts could be answered with the other three alongside it. One fact per
    chunk means a question can only be answered from the fact it asked about.

    ``base_expense_ratio`` is never indexed: it is the platform fee alone, while
    the page shows ``expense_ratio``, which is that plus the scheme's other
    charges. Stating both invites a reader to compare them and conclude the
    page is showing something else.
    """
    body = f"Expense ratio is {fmt_pct(nf.expense_ratio)}."
    return body, nf.fetched_at[:10], {}


def _stamp_duty(nf: NormalizedFund):
    body = f"Stamp duty on investment: {nf.stamp_duty}."
    return body, nf.fetched_at[:10], {}


def _portfolio_turnover(nf: NormalizedFund):
    body = f"Portfolio turnover ratio: {fmt_pct(nf.portfolio_turnover, 0)}."
    return body, nf.fetched_at[:10], {}


def _minimums(nf: NormalizedFund):
    body = (
        f"Minimum for the first investment is {fmt_inr(nf.min_investment)}. "
        f"Minimum for the second and subsequent investments is {fmt_inr(nf.min_investment)}. "
        f"Minimum SIP amount is {fmt_inr(nf.min_sip)}"
        + (f" and the maximum SIP amount is {fmt_inr(nf.max_sip)}" if nf.max_sip else "")
        + f", in multiples of {fmt_inr(nf.sip_multiplier)}. "
        f"Minimum redemption or withdrawal amount is {fmt_inr(nf.min_withdrawal)}. "
        f"SIP is {'allowed' if nf.sip_allowed else 'not allowed'} and "
        f"lump sum is {'allowed' if nf.lumpsum_allowed else 'not allowed'}. "
        f"Purchase documents are required: {'yes' if nf.doc_required else 'no'}."
    )
    return body, nf.fetched_at[:10], {}


def _objective(nf: NormalizedFund):
    body = (
        f"Investment objective: {nf.objective} "
        f"The fund benchmark is {nf.benchmark}."
    )
    return body, nf.fetched_at[:10], {}


def _risk_ratios(nf: NormalizedFund):
    body = (
        f"Risk and return ratios: Sharpe ratio {fmt_pct(nf.sharpe)}, "
        f"beta {fmt_pct(nf.beta)}, Sortino ratio {fmt_pct(nf.sortino)}, "
        f"alpha {fmt_pct(nf.alpha)}, standard deviation {fmt_pct(nf.std_deviation)}, "
        f"mean return {fmt_pct(nf.mean_return)}. "
        f"Groww's risk classification: {nf.groww_risk}."
    )
    return body, nf.fetched_at[:10], {}


def _returns(nf: NormalizedFund):
    annualised = ", ".join(f"{k.upper()} {v:+.2f}%" for k, v in nf.returns.items())
    body = (
        f"Annualised point-to-point returns: {annualised}. "
        f"Category average (annualised): "
        + ", ".join(f"{k.upper()} {v:+.2f}%" for k, v in nf.category_returns.items())
        + ". "
        f"Rank within category: 1 year {_rank(nf, '1y')}, 3 year {_rank(nf, '3y')}, "
        f"5 year {_rank(nf, '5y')}, 10 year {_rank(nf, '10y')}."
    )
    return body, nf.fetched_at[:10], {}


def _rank(nf: NormalizedFund, key: str) -> str:
    val = nf.ranks.get(key)
    return f"#{val}" if val is not None else "not stated"


def _sip_vs_lump(nf: NormalizedFund):
    sip = ", ".join(f"{k.upper()} {v:+.2f}%" for k, v in nf.sip_returns.items())
    lump = ", ".join(f"{k.upper()} {v:+.2f}%" for k, v in nf.lump_returns.items())
    body = (
        f"Annualised returns on a monthly SIP of Rs 5,000: {sip}. "
        f"Annualised returns on a one-time lump sum investment: {lump}. "
        f"These are historical realised figures, not projections or a forecast."
    )
    return body, nf.fetched_at[:10], {}


def _swp(nf: NormalizedFund):
    s = nf.swp
    if not s:
        return None
    body = (
        f"Systematic Withdrawal Plan (SWP) terms: minimum installment amount {fmt_inr(s.get('swp_minimum_installment_amount'))}, "
        f"maximum installment amount {fmt_inr(s.get('swp_maximum_installment_amount'))}, "
        f"amount multiplier {fmt_inr(s.get('swp_multiplier_amount'))}, "
        f"minimum units {fmt_inr(s.get('swp_minimum_installment_units'))}, "
        f"minimum number of installments {s.get('swp_minimum_installment_numbers')}, "
        f"frequency {s.get('swp_frequency')}, minimum gap between installments {s.get('swp_minimum_gap')} days, "
        f"maximum gap {s.get('swp_maximum_gap')} days."
    )
    return body, nf.fetched_at[:10], {}


def _stp(nf: NormalizedFund):
    s = nf.stp
    if not s:
        return None
    body = (
        f"Systematic Transfer Plan (STP) terms: minimum installment amount {fmt_inr(s.get('stp_in_minimum_installment_amount'))}, "
        f"maximum installment amount {fmt_inr(s.get('stp_in_maximum_installment_amount'))}, "
        f"amount multiplier {fmt_inr(s.get('stp_in_multiplier_amount'))}, "
        f"minimum number of installments {s.get('stp_minimum_installment_numbers')}, "
        f"frequency {s.get('stp_frequency')}, minimum gap {s.get('stp_minimum_gap')} days, "
        f"maximum gap {s.get('stp_maximum_gap')} days. "
        f"Minimum installment units {fmt_inr(s.get('stp_minimum_installment_units'))}."
    )
    return body, nf.fetched_at[:10], {}


def _amc(nf: NormalizedFund):
    amc, rta = nf.amc, nf.rta
    body = (
        f"Fund house is HDFC Mutual Fund, ranked #{amc.get('rank')} in India by total assets. "
        f"Registered office: {amc.get('address')}. "
        f"Phone {amc.get('phone')}. "
        f"Registrar and Transfer Agent (RTA) is {rta.get('rta_name')}, "
        f"website {rta.get('website')}, email {rta.get('email')}, "
        f"address {rta.get('address')}. "
        f"Scheme Information Document (SID) is published at https://www.hdfcfund.com."
    )
    return body, nf.fetched_at[:10], {"scope": "amc"}


def _holdings_summary(nf: NormalizedFund):
    if not nf.holdings:
        return None
    sector_w = defaultdict(float)
    instr_w = defaultdict(float)
    for h in nf.holdings:
        sector_w[h.get("sector_name") or "Unspecified"] += h.get("corpus_per") or 0
        instr_w[h.get("instrument_name") or "Unspecified"] += h.get("corpus_per") or 0
    top_sectors = sorted(sector_w.items(), key=lambda kv: -kv[1])[:5]
    sector_txt = ", ".join(f"{name} {val:.2f}%" for name, val in top_sectors)
    instr_txt = ", ".join(
        f"{name} {val:.2f}%" for name, val in sorted(instr_w.items(), key=lambda kv: -kv[1])[:5]
    )
    top_n = nf.holdings[:HOLDINGS_TOP_N]
    coverage = sum(h.get("corpus_per") or 0 for h in top_n)
    body = (
        f"Portfolio as of {nf.holdings_as_of} holds {len(nf.holdings)} holdings. "
        f"Top {HOLDINGS_TOP_N} holdings account for {coverage:.2f}% of the portfolio. "
        f"Sector weights (whole portfolio): {sector_txt}. "
        f"Instrument-type weights (whole portfolio): {instr_txt}."
    )
    return body, nf.holdings_as_of, {
        "holdings_coverage_pct": round(coverage, 2),
        "holdings_total_count": len(nf.holdings),
    }


def _holdings_top(nf: NormalizedFund):
    if not nf.holdings:
        return None
    top_n = nf.holdings[:HOLDINGS_TOP_N]
    coverage = sum(h.get("corpus_per") or 0 for h in top_n)
    lines = []
    for i, h in enumerate(top_n, 1):
        lines.append(f"{i}. {h.get('company_name')} ({h.get('corpus_per'):.2f}%)")
    body = (
        f"Top {HOLDINGS_TOP_N} holdings as of {nf.holdings_as_of}, by weight: "
        + "; ".join(lines)
        + f". These {HOLDINGS_TOP_N} of {len(nf.holdings)} holdings represent {coverage:.2f}% of the portfolio."
    )
    return body, nf.holdings_as_of, {
        "holdings_coverage_pct": round(coverage, 2),
        "holdings_total_count": len(nf.holdings),
    }


def _exit_load_current(nf: NormalizedFund):
    """Exit load only -- stamp duty has its own chunk and is not added here."""
    body = f"Current exit load: {nf.exit_load}."
    return body, nf.fetched_at[:10], {"is_current": True}


def _exit_load_history(nf: NormalizedFund):
    """One chunk per dated exit-load version; index 0 is the live one."""
    out = []
    for i, h in enumerate(nf.historic_exit_loads):
        as_of = _date(h.get("as_on_date"))
        current = i == 0
        if current:
            body = f"Exit load version effective since {as_of} (currently in force): {h.get('note')}"
        else:
            body = (
                f"Exit load version effective from {as_of} (superseded, not currently in force): "
                f"{h.get('note')}"
            )
        out.append((body, as_of, {"is_current": current}))
    return out


def _manager_roster(nf: NormalizedFund):
    """The complete Fund management roster as the page lists it.

    One chunk for the whole roster, not one per manager. Splitting them meant
    retrieval could only return two, so a scheme with six managers (Balanced
    Advantage) answered with whichever two ranked highest -- an answer that was
    confidently incomplete.

    Start dates are month+year only, matching what the page renders. The
    ``date_from`` field's day component is a storage artefact of midnight IST
    and is not shown to the user on the page.
    """
    managers = [m for m in nf.managers if m.get("person_name")]
    if not managers:
        return None

    roster = ", ".join(
        f"{m['person_name'].strip()} (since {month_year(m.get('date_from'))})"
        for m in managers
    )
    count = len(managers)
    if count == 1:
        tail = "The page lists only this one manager for the scheme."
    else:
        tail = (
            "These are all the managers the page shows for this scheme; "
            "none of them is the sole manager."
        )
    body = (
        f"Fund management: this scheme lists {count} fund "
        f"manager{'s' if count != 1 else ''} -- {roster}. {tail}"
    )
    # as_of is the fetch date, not a manager start date: the roster is current as
    # of the crawl, while the individual tenures have their own months above.
    return body, nf.fetched_at[:10], {"manager_count": count}


def _manager_profiles(nf: NormalizedFund):
    """One chunk per manager for biography, kept out of the boosted roster.

    "Who manages" must hit the roster; "what is X's background" should hit a
    profile. Splitting them this way means a multi-manager scheme cannot bury
    its own roster under biography text.
    """
    out = []
    for m in nf.managers:
        name = m.get("person_name")
        if not name:
            continue
        body = (
            f"Fund manager profile: {name.strip()} manages this scheme since "
            f"{month_year(m.get('date_from'))}. "
            f"Education: {m.get('education')}. "
            f"Experience: {m.get('experience')}"
        )
        out.append((body, nf.fetched_at[:10], {}))
    return out


def _lockin(nf: NormalizedFund):
    """Lock-in only -- the exit load it can trigger is its own chunk."""
    if not nf.lock_in_years:
        return None
    body = (
        f"This scheme has a mandatory lock-in period of {nf.lock_in_years} years. "
        f"Units cannot be redeemed before the lock-in completes."
    )
    return body, nf.fetched_at[:10], {}


def _tax_shared():
    body = (
        "Tax implication (applies to all HDFC schemes in this corpus): "
        "If you redeem within one year, returns are taxed at 20%. "
        "If you redeem after one year, returns exceeding Rs 1.25 lakh in a financial year are taxed at 12.5%. "
        "This is a generic statement shown on the fund pages and not scheme-specific tax advice."
    )
    return body, None, {"scope": "generic", "is_generic_boilerplate": True}


def _routing(nf: NormalizedFund):
    body = (
        f"This scheme's page covers: NAV and fund size, expense ratio, exit load and stamp duty, "
        f"minimum lump sum and SIP amounts, lock-in, investment objective and benchmark, "
        f"annualised returns, risk ratios, fund managers, top {HOLDINGS_TOP_N} holdings, "
        f"portfolio sector mix, and SWP/STP terms. "
        f"Benchmark: {nf.benchmark}. Groww risk classification: {nf.groww_risk}."
    )
    return body, nf.fetched_at[:10], {}


# --- assembly -------------------------------------------------------------

_SINGLETON_BUILDERS: List[tuple] = [
    ("identity_overview", _identity, True),
    ("risk_profile", _risk_profile, True),
    ("expense_ratio", _expense_ratio, True),
    ("stamp_duty", _stamp_duty, True),
    ("portfolio_turnover", _portfolio_turnover, True),
    ("minimums", _minimums, True),
    ("objective_benchmark", _objective, True),
    ("risk_ratios", _risk_ratios, True),
    ("returns_history", _returns, True),
    ("sip_vs_lumpsum_returns", _sip_vs_lump, True),
    ("swp_terms", _swp, True),
    ("stp_terms", _stp, True),
    ("amc_registrar", _amc, True),
    ("holdings_summary", _holdings_summary, True),
    ("holdings_top25", _holdings_top, True),
    ("fund_manager", _manager_roster, True),
    ("lockin", _lockin, True),
    ("routing_hint", _routing, True),
    ("exit_load_current", _exit_load_current, True),
]


def _base_meta(nf: NormalizedFund, spec: FundSpec, section: str, as_of, extra) -> Dict:
    meta = {
        "fund_name": nf.display_name,
        "display_name": nf.display_name,
        "search_id": nf.spec.search_id,
        "source_url": spec.url,
        "isin": nf.isin,
        "category": nf.category,
        "sub_category": nf.sub_category,
        "plan": f"{nf.plan_type} {nf.scheme_type}",
        "section": section,
        "scope": "scheme",
        "is_current": True,
        "is_generic_boilerplate": False,
        "as_of": as_of or nf.fetched_at[:10],
        "ingested_at": nf.fetched_at,
    }
    meta.update(extra)
    return meta


def build_chunks(nf: NormalizedFund) -> List[Chunk]:
    """All chunks for one scheme (shared tax chunk excluded)."""
    prefix = _prefix(nf)
    spec = nf.spec
    chunks: List[Chunk] = []

    def emit(section, idx, body, as_of, extra):
        cid = f"{spec.search_id}__{section}__{_seq(idx)}"
        text = f"{prefix}\n{body}"
        meta = _base_meta(nf, spec, section, as_of, extra)
        meta["word_count"] = len(text.split())
        meta["char_count"] = len(text)
        chunks.append(Chunk(cid, text, meta))

    for section, builder, _ in _SINGLETON_BUILDERS:
        result = builder(nf)
        if result is None:
            continue
        body, as_of, extra = result
        emit(section, 1, body, as_of, extra)

    # Exit-load history: one chunk per dated version.
    for i, (body, as_of, extra) in enumerate(_exit_load_history(nf), 1):
        emit("exit_load_history", i, body, as_of, extra)

    # Manager biographies: one chunk per manager, not boosted, so the roster
    # above stays the answer to "who manages".
    for i, (body, as_of, extra) in enumerate(_manager_profiles(nf), 1):
        emit("fund_manager_profile", i, body, as_of, extra)

    return chunks


def build_shared_chunks(nf: NormalizedFund) -> List[Chunk]:
    """The single deduplicated tax chunk, scope=generic, no fund prefix."""
    body, as_of, extra = _tax_shared()
    cid = "all_schemes__tax_treatment__01"
    text = (
        "Scope: all HDFC schemes in this corpus (Large Cap, Flexi Cap, ELSS Tax Saver, "
        "Small Cap, Balanced Advantage) - Direct Growth plans.\n" + body
    )
    spec = nf.spec
    meta = {
        "fund_name": "All HDFC schemes in corpus",
        "display_name": "All HDFC schemes in corpus",
        "search_id": spec.search_id,  # placeholder; not a scheme-scoped chunk
        "source_url": spec.url,
        "isin": "n/a",
        "category": "n/a",
        "sub_category": "n/a",
        "plan": "n/a",
        "section": "tax_treatment",
        "scope": "generic",
        "is_current": True,
        "is_generic_boilerplate": True,
        "as_of": as_of or nf.fetched_at[:10],
        "ingested_at": nf.fetched_at,
        "word_count": len(text.split()),
        "char_count": len(text),
    }
    meta.update(extra)
    return [Chunk(cid, text, meta)]


def build_all(normalized: List[NormalizedFund]) -> List[Chunk]:
    chunks: List[Chunk] = []
    for nf in normalized:
        chunks.extend(build_chunks(nf))
    if normalized:
        chunks.extend(build_shared_chunks(normalized[0]))
    return chunks
