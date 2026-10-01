"""Corpus configuration: fund registry, alias map, and field-precedence rules.

The single source of truth for what we ingest and which field wins when the
source page contradicts itself. See README "Stale source fields".
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Dict, List

GROWW_BASE = "https://groww.in/mutual-funds"

# --- Embedding model -------------------------------------------------------

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBED_DIM = 384
CHUNK_COLLECTION = "hdfc_mf_faq"

# --- Storage paths ---------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
CHROMA_DIR = os.path.join(ROOT, "chroma_db")
MANIFEST_PATH = os.path.join(DATA_DIR, "manifest.json")
CHUNKS_TXT_PATH = os.path.join(ROOT, "chunks.txt")

# Holdings are capped per scheme (uniformly, for comparability). The top-N
# coverage percentage is computed at ingest and stored on the chunk so answers
# can state how much of the portfolio the list actually represents.
HOLDINGS_TOP_N = 25

# The identical tax boilerplate appears byte-for-byte on all 5 pages. Embedding
# it 5x would let duplicates crowd each other out of retrieval, so it is
# emitted once as a shared, scope="generic" chunk.
SHARED_SECTIONS = {"tax_treatment"}

# Why: Groww renders scheme-level AUM into the "About" prose from the AMC-level
# figure, so that number is wrong for every individual scheme (it reads
# Rs 9,86,237 Cr on all five pages while scheme AUM ranges 16k-114k Cr).
AMC_LEVEL_KEYS = frozenset(
    {"amc_aum", "amc_rank", "amc_launch_date", "amc_address", "amc_phone"}
)


@dataclass(frozen=True)
class FundSpec:
    """One corpus page."""

    search_id: str
    display_name: str
    aliases: List[str] = field(default_factory=list)
    #: Set when the page slug is an alias for a differently-named scheme.
    renamed_from: str = ""

    @property
    def url(self) -> str:
        return f"{GROWW_BASE}/{self.search_id}"

    def phrases(self) -> List[str]:
        """Every string that should resolve to this scheme.

        The single source of truth for name matching, shared by the retrieval
        alias index and the guard that blanks the corpus's own vocabulary out of
        a question. Two generated shapes are included alongside the literal ones:
        the slug with dashes as spaces, and the display name without its
        parenthetical, so the renamed-from note stays out of matching text while
        "HDFC Equity Fund" still resolves for the page that no longer bears that
        name.
        """
        phrases = {self.display_name, self.search_id.replace("-", " ")}
        phrases.update(self.aliases)
        if self.renamed_from:
            phrases.add(self.renamed_from)
        phrases.add(re.sub(r"\s*\(.*\)$", "", self.display_name))
        return [p for p in phrases if p]


#: The five corpus pages, in the order given in the brief.
FUNDS: List[FundSpec] = [
    FundSpec(
        search_id="hdfc-large-cap-fund-direct-growth",
        display_name="HDFC Large Cap Fund Direct Growth",
        aliases=["HDFC Large Cap", "HDFC Large Cap Fund"],
    ),
    FundSpec(
        # This slug no longer serves a scheme called "HDFC Equity Fund"; Groww
        # returns HDFC Flexi Cap content for it. The URL and search_id are kept
        # as specified, and every chunk carries the former name so answers never
        # reference a scheme that does not exist.
        search_id="hdfc-equity-fund-direct-growth",
        display_name="HDFC Flexi Cap Direct Plan Growth (formerly HDFC Equity Fund)",
        aliases=["HDFC Equity Fund", "HDFC Equity", "HDFC Flexi Cap", "HDFC Flexi Cap Fund"],
        renamed_from="HDFC Equity Fund",
    ),
    FundSpec(
        search_id="hdfc-elss-tax-saver-fund-direct-plan-growth",
        display_name="HDFC ELSS Tax Saver Fund Direct Plan Growth",
        aliases=["HDFC ELSS", "HDFC ELSS Tax Saver", "HDFC ELSS Tax Saver Fund"],
    ),
    FundSpec(
        search_id="hdfc-small-cap-fund-direct-growth",
        display_name="HDFC Small Cap Fund Direct Growth",
        aliases=["HDFC Small Cap", "HDFC Small Cap Fund"],
    ),
    FundSpec(
        search_id="hdfc-balanced-advantage-fund-direct-growth",
        display_name="HDFC Balanced Advantage Fund Direct Growth",
        aliases=["HDFC Balanced Advantage", "HDFC Balanced Advantage Fund"],
    ),
]

FUNDS_BY_ID: Dict[str, FundSpec] = {f.search_id: f for f in FUNDS}

#: Number of corpus pages. Named for use in progress output.
FUND_SPECS_LEN = len(FUNDS)


# --- Fields deliberately never ingested ------------------------------------
#
# category_info describes "Contra funds" for HDFC Large Cap (sub_type "Contra",
# "Minimum investment in equity is 65%") -- factually unrelated to the scheme.
# amc_info.description/more_description are 2017-2018 vintage ("managing total
# assets of Rs 2,70,046 Cr ... as on end of 30th Sep 2017"). Both would poison
# retrieval with confident wrong answers.
# base_expense_ratio is the platform fee alone; the page shows expense_ratio,
# which is that plus the scheme's other charges. Only expense_ratio is ever
# indexed, so the base figure cannot reach a chunk, an answer, or the model.
DENY_KEYS = frozenset(
    {
        "category_info",
        "meta_desc",
        "meta_title",
        "meta_robots",
        "analysis",
        "peerComparison",
        "historic_fund_expense",
        "base_expense_ratio",
        "actions",
        "fund_news",
        "fund_events",
        "nfo_image_url",
        "video_url",
        "logo_url",
    }
)

#: Top-level fields that are stale and must never win. Documented in README.
#: - ``fund_manager`` says "Prashant Jain" while the page shows Rahul Baijal;
#:   ``fund_manager_details[].person_name`` is correct.
#: - ``nfo_risk`` says "Moderately High Riskometer" from the 2013 NFO era
#:   while the live page shows "Very High Risk".
#: - ``launch_date`` is 01-Jan-2013, the Direct-Growth *plan* inception, which
#:   is a different fact from the 10 Dec 1999 fund launch rendered on the page.
STALE_KEYS = frozenset({"fund_manager", "nfo_risk", "description", "benchmark"})
