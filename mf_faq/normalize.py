"""Normalize step: one authoritative value per fact.

Groww's payload carries several fields that contradict each other or that are
stale. Rather than trusting the payload wholesale, each fact is resolved here
through an explicit precedence rule, and the losing values are dropped so they
can never reach the index.

Also strips control characters: several ``exit_load`` / ``historic_exit_loads``
values arrive with trailing ``\\r\\n`` inside the string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .config import DENY_KEYS, FundSpec

_CTRL_RE = re.compile(r"[\r\n\t]+")
_MULTISPACE_RE = re.compile(r"[ ]{2,}")


def clean(value: Any) -> Any:
    """Recursively drop control characters and collapse whitespace."""
    if isinstance(value, str):
        return _MULTISPACE_RE.sub(" ", _CTRL_RE.sub(" ", value)).strip()
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items() if k not in DENY_KEYS}
    if isinstance(value, list):
        return [clean(v) for v in value]
    return value


def _inr_cr(value: Any) -> Optional[float]:
    """Scheme AUM / fund size in Rs crore, as a float."""
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _pct(value: Any, places: int = 2) -> Optional[float]:
    if value is None:
        return None
    try:
        return round(float(value), places)
    except (TypeError, ValueError):
        return None


def fmt_inr_cr(value: Optional[float]) -> str:
    return "not stated" if value is None else f"Rs {value:,.2f} Cr"


def fmt_pct(value: Optional[float], places: int = 2) -> str:
    return "not stated" if value is None else f"{value:.{places}f}%"


def fmt_inr(value: Any) -> str:
    """Rupee amount, thousands-separated."""
    if value is None:
        return "not stated"
    try:
        return f"Rs {float(value):,.0f}"
    except (TypeError, ValueError):
        return "not stated"


def _date(value: Any) -> str:
    """Format a source date as '28 Sep 2026'.

    Two shapes arrive:
      * plain dates ('28-Sep-2026', '01-Jan-2013') -- used as-is;
      * ISO timestamps ending in 'Z' ('2026-08-30T18:30:00.000Z') -- these are
        midnight IST stored as 18:30 UTC the previous day, so they are shifted
        to IST (+05:30) before formatting. Without the shift the fund launch
        date reads 09 Dec 1999 instead of the 10 Dec 1999 shown on the page.
    """
    if not value:
        return "not stated"
    text = str(value).strip()
    if "T" in text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return text[:10]
        if parsed.tzinfo is not None:
            parsed = (parsed + timedelta(hours=5, minutes=30)).replace(tzinfo=None)
        return parsed.strftime("%d %b %Y")
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            return datetime.strptime(text[:11] if fmt == "%d-%b-%Y" else text[:10], fmt).strftime("%d %b %Y")
        except ValueError:
            continue
    return text[:10]


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def month_year(value: Any) -> str:
    """Format a date as 'Jun 2023' -- month and year only, no day.

    The Fund management section on a Groww scheme page shows only a start month
    ("Jun 2023"). The underlying ``date_from`` field carries a full timestamp
    whose day is an artefact of how midnight IST is stored (18:30 UTC the
    previous day), so rendering it would put a day in the answer that the user
    cannot see on the page. Month and year is what the page actually shows.
    """
    if not value:
        return "an unstated month"
    text = str(value).strip()
    if "T" in text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is not None:
                parsed = (parsed + timedelta(hours=5, minutes=30)).replace(tzinfo=None)
            return f"{_MONTHS[parsed.month - 1]} {parsed.year}"
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d %b %Y"):
        try:
            parsed = datetime.strptime(text[:11] if fmt == "%d-%b-%Y" else text[:10], fmt)
            return f"{_MONTHS[parsed.month - 1]} {parsed.year}"
        except ValueError:
            continue
    return text[:7]


@dataclass
class NormalizedFund:
    """Every fact the chunkers need, conflicts already resolved."""

    spec: FundSpec
    fetched_at: str

    # identity
    scheme_name: str
    isin: str
    scheme_code: str
    plan_type: str
    scheme_type: str
    category: str
    sub_category: str
    super_category: str

    # pricing / size (scheme level only)
    nav: Optional[float]
    nav_date: str
    aum_cr: Optional[float]
    expense_ratio: Optional[float]
    portfolio_turnover: Optional[float]
    groww_rating: Optional[float]

    # risk -- Groww's own label, NOT the SEBI riskometer
    groww_risk: str
    sharpe: Optional[float]
    beta: Optional[float]
    sortino: Optional[float]
    alpha: Optional[float]
    std_deviation: Optional[float]
    mean_return: Optional[float]

    # costs
    exit_load: str
    historic_exit_loads: List[Dict]
    stamp_duty: str

    # minimums
    min_investment: Optional[float]
    min_sip: Optional[float]
    max_sip: Optional[float]
    min_withdrawal: Optional[float]
    sip_multiplier: Optional[float]
    sip_allowed: bool
    lumpsum_allowed: bool
    doc_required: bool
    redemption_qty_multiplier: Optional[float]
    redemption_amount_multiple: Optional[float]

    # lock-in
    lock_in_years: Optional[int]

    # objective / benchmark
    objective: str
    benchmark: str

    # dates
    plan_launch_date: str
    fund_launch_date: str

    # returns
    returns: Dict[str, Optional[float]]
    category_returns: Dict[str, Optional[float]]
    ranks: Dict[str, Optional[int]]
    sip_returns: Dict[str, Optional[float]]
    lump_returns: Dict[str, Optional[float]]

    # managers / holdings / servicing
    managers: List[Dict]
    holdings: List[Dict]
    holdings_as_of: str
    swp: Dict
    stp: Dict
    rta: Dict
    amc: Dict

    @property
    def display_name(self) -> str:
        return self.spec.display_name


def _first(value: Any) -> Dict:
    """Series fields arrive as either a dict or a single-element list."""
    if isinstance(value, list):
        return value[0] if value else {}
    return value if isinstance(value, dict) else {}


def _series(stats: Dict, prefix: str = "return") -> Dict[str, Optional[float]]:
    labels = {
        "1d": f"{prefix}1d", "1w": f"{prefix}1w", "1m": f"{prefix}1m",
        "3m": f"{prefix}3m", "6m": f"{prefix}6m", "9m": f"{prefix}9m",
        "1y": f"{prefix}1y", "2y": f"{prefix}2y", "3y": f"{prefix}3y",
        "4y": f"{prefix}4y", "5y": f"{prefix}5y", "7y": f"{prefix}7y",
        "10y": f"{prefix}10y",
    }
    out = {k: _pct(stats.get(v)) for k, v in labels.items()}
    out["since_inception"] = _pct(stats.get(f"{prefix}_since_created"))
    return {k: v for k, v in out.items() if v is not None}


def normalize(record: Dict) -> NormalizedFund:
    """Resolve one raw fetch record into an authoritative fact set."""
    spec = FundSpec(
        search_id=record["spec"]["search_id"],
        display_name=record["spec"]["display_name"],
        aliases=record["spec"].get("aliases", []),
        renamed_from=record["spec"].get("renamed_from", ""),
    )
    d = clean(record["data"])

    stats = _first(d.get("return_stats"))
    sip_stats = _first(d.get("sip_return"))
    lump_stats = _first(d.get("simple_return"))

    lock = d.get("lock_in") or {}
    lock_years = lock.get("years") if isinstance(lock, dict) else None

    amc = d.get("amc_info") or {}
    rta = d.get("rta_details") or {}

    holdings = sorted(
        (h for h in (d.get("holdings") or []) if h.get("company_name")),
        key=lambda h: -(h.get("corpus_per") or 0),
    )
    holdings_as_of = _date(holdings[0].get("portfolio_date")) if holdings else "not stated"

    return NormalizedFund(
        spec=spec,
        fetched_at=record["fetched_at"],
        scheme_name=d.get("scheme_name") or spec.display_name,
        isin=d.get("isin") or "not stated",
        scheme_code=d.get("scheme_code") or "not stated",
        plan_type=d.get("plan_type") or "Direct",
        scheme_type=d.get("scheme_type") or "Growth",
        category=d.get("category") or "not stated",
        sub_category=d.get("sub_category") or "not stated",
        super_category=d.get("super_category") or "not stated",
        nav=_pct(d.get("nav"), 3),
        nav_date=_date(d.get("nav_date")),
        aum_cr=_inr_cr(d.get("aum")),
        expense_ratio=_pct(d.get("expense_ratio")),
        portfolio_turnover=_pct(d.get("portfolio_turnover"), 0),
        groww_rating=d.get("groww_rating"),
        # Groww's classification. The 2013-NFO-era nfo_risk field ("Moderately
        # High Riskometer") is stale and intentionally not consulted.
        groww_risk=stats.get("risk") or "not stated",
        sharpe=_pct(stats.get("sharpe_ratio")),
        beta=_pct(stats.get("beta")),
        sortino=_pct(stats.get("sortino_ratio")),
        alpha=_pct(stats.get("alpha")),
        std_deviation=_pct(stats.get("standard_deviation")),
        mean_return=_pct(stats.get("mean_return")),
        exit_load=d.get("exit_load") or "not stated",
        historic_exit_loads=d.get("historic_exit_loads") or [],
        stamp_duty=d.get("stamp_duty") or "not stated",
        min_investment=d.get("min_investment_amount"),
        min_sip=d.get("min_sip_investment"),
        max_sip=d.get("max_sip_investment"),
        min_withdrawal=d.get("min_withdrawal"),
        sip_multiplier=d.get("sip_multiplier"),
        sip_allowed=bool(d.get("sip_allowed")),
        lumpsum_allowed=bool(d.get("lumpsum_allowed")),
        doc_required=bool(d.get("doc_required")),
        redemption_qty_multiplier=d.get("redemption_qty_multiplier"),
        redemption_amount_multiple=d.get("redemption_amount_multiple"),
        lock_in_years=lock_years,
        objective=d.get("description") or "not stated",
        benchmark=d.get("benchmark_name") or "not stated",
        # Two different facts, kept apart: the plan's own inception (payload)
        # vs the fund's launch date as rendered on the page (AMC record).
        plan_launch_date=_date(d.get("launch_date")),
        fund_launch_date=_date(amc.get("launch_date")),
        returns=_series(stats),
        category_returns=_series(stats, "cat_"),
        ranks={
            "1y": stats.get("rank1yr"), "3y": stats.get("rank3yr"),
            "5y": stats.get("rank5yr"), "10y": stats.get("rank10yr"),
        },
        sip_returns=_series(sip_stats),
        lump_returns=_series(lump_stats),
        managers=d.get("fund_manager_details") or [],
        holdings=holdings,
        holdings_as_of=holdings_as_of,
        swp=d.get("swp_details") or {},
        stp=d.get("stp_details") or {},
        rta=rta,
        amc=amc,
    )
