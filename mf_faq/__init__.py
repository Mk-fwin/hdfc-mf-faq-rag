"""mf_faq - Mutual Fund FAQ assistant over 5 HDFC Direct-Growth scheme pages.

Step 1 (this package): ingestion only -- load, normalize, chunk, embed, store.
Query, guards and UI land in later steps.
"""

__all__ = ["config", "fetch", "normalize", "chunkers", "embed", "store"]
