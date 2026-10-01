"""Load step: pull the structured payload off each Groww fund page.

Groww server-renders every field we need and embeds it as a Next.js
``__NEXT_DATA__`` JSON island (``props.pageProps.mfServerSideData``, 97 keys).
Parsing that beats scraping the HTML text, which is ~60-70% navigation and
footer boilerplate.

Raw payloads are cached under ``data/raw/`` so re-chunking never re-scrapes.
"""

from __future__ import annotations

import json
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Dict

import requests

from .config import FUNDS, RAW_DIR, FundSpec

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_DELAY_SECONDS = 1.0
MAX_RETRIES = 3

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


class FetchError(RuntimeError):
    pass


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"})
    return s


def _extract_payload(html: str) -> dict:
    m = _NEXT_DATA_RE.search(html)
    if not m:
        raise FetchError("no __NEXT_DATA__ island found (page shape changed?)")
    try:
        blob = json.loads(m.group(1))
        return blob["props"]["pageProps"]["mfServerSideData"]
    except (ValueError, KeyError) as exc:
        raise FetchError(f"__NEXT_DATA__ did not contain mfServerSideData: {exc}") from exc


def raw_path(search_id: str) -> str:
    return os.path.join(RAW_DIR, f"{search_id}.json")


def cache_path_exists() -> bool:
    """True when every corpus page is already cached under ``data/raw/``."""
    return all(os.path.exists(raw_path(fund.search_id)) for fund in FUNDS)


def load_cached() -> Dict[str, Dict]:
    """Read every cached page from disk, and never touch the network.

    This is the startup path: the cached payloads are committed, so a fresh
    clone can build the index without a single request to Groww. Missing cache
    is an error rather than a silent fetch, because a deployed app that reaches
    out to Groww on start-up would fail for reasons that have nothing to do with
    the question being asked.
    """
    missing = [fund.display_name for fund in FUNDS
               if not os.path.exists(raw_path(fund.search_id))]
    if missing:
        raise FetchError(
            "cached pages missing from data/raw/ for: "
            + ", ".join(missing)
            + ". Restore them (they are committed) or run: python cli.py ingest"
        )
    out: Dict[str, Dict] = {}
    for fund in FUNDS:
        with open(raw_path(fund.search_id), encoding="utf-8") as fh:
            out[fund.search_id] = json.load(fh)
    return out


def load_fund(fund: FundSpec, refresh: bool = False, session=None) -> Dict:
    """Return ``{"fetched_at", "spec", "data"}`` for one scheme.

    Uses the on-disk cache unless ``refresh`` is set.
    """
    path = raw_path(fund.search_id)
    if os.path.exists(path) and not refresh:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    session = session or _session()
    last_exc: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.get(fund.url, timeout=45)
            resp.raise_for_status()
            payload = _extract_payload(resp.text)
            break
        except Exception as exc:  # noqa: BLE001 - retried below
            last_exc = exc
            if attempt == MAX_RETRIES:
                raise FetchError(f"{fund.search_id}: failed after {MAX_RETRIES} attempts: {exc}") from exc
            time.sleep(REQUEST_DELAY_SECONDS * attempt + random.uniform(0, 0.5))
    else:  # pragma: no cover - loop always breaks or raises
        raise FetchError(f"{fund.search_id}: {last_exc}")

    served = payload.get("search_id")
    if served != fund.search_id:
        raise FetchError(
            f"{fund.search_id}: page served a different scheme (search_id={served!r})"
        )

    record = {
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spec": {
            "search_id": fund.search_id,
            "display_name": fund.display_name,
            "aliases": fund.aliases,
            "renamed_from": fund.renamed_from,
            "url": fund.url,
        },
        "data": payload,
    }
    os.makedirs(RAW_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, indent=1)
    return record


def load_all(refresh: bool = False) -> Dict[str, Dict]:
    """Load every corpus scheme, pausing between live requests."""
    session = _session()
    out: Dict[str, Dict] = {}
    for i, fund in enumerate(FUNDS):
        cached = os.path.exists(raw_path(fund.search_id)) and not refresh
        out[fund.search_id] = load_fund(fund, refresh=refresh, session=session)
        print(f"  [{i + 1}/{len(FUNDS)}] {fund.display_name} ({'cached' if cached else 'fetched'})")
        if not cached and i < len(FUNDS) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)
    return out
