"""CLI: python -m leadgen [--sources reddit,trustpilot,yelp] [--sheet-id ID] ..."""
from __future__ import annotations

import argparse
import os
import sys

from .common import load_env
from .pipeline import Options, run


def main() -> None:
    load_env()
    d = Options()
    ap = argparse.ArgumentParser(description="Find CX-outsourcing leads from review sites.")
    ap.add_argument("--sources", default=",".join(sorted(d.sources)))
    ap.add_argument("--sheet-id", default=os.getenv("GOOGLE_SHEET_ID"), help="Google Sheet to upsert into")
    ap.add_argument("--tab", default=d.tab)
    ap.add_argument("--out", default=d.out, help="local path prefix for .csv/.xlsx")
    ap.add_argument("--domains", nargs="*", default=[], help="extra Trustpilot domains to analyze")
    ap.add_argument("--domains-file", default=d.domains_file)
    ap.add_argument("--tp-pages", type=int, default=d.tp_pages, help="Trustpilot category pages per category")
    ap.add_argument("--reddit-time", default=d.reddit_time, choices=["day", "week", "month", "year", "all"])
    ap.add_argument("--min-score", type=int, default=d.min_score)
    ap.add_argument("--no-enrich", action="store_true", help="skip website contact lookup")
    ap.add_argument("--include-seed", action="store_true", help="merge the researched seed leads into the output")
    a = ap.parse_args()

    result = run(Options(
        sources={x.strip() for x in a.sources.split(",") if x.strip()},
        sheet_id=a.sheet_id, tab=a.tab, out=a.out, domains=a.domains, domains_file=a.domains_file,
        tp_pages=a.tp_pages, reddit_time=a.reddit_time, min_score=a.min_score,
        enrich=not a.no_enrich, include_seed=a.include_seed,
    ))
    if result.blocked:
        print("::error::lead source blocked: " + ", ".join(result.blocked))
        sys.exit(2)


if __name__ == "__main__":
    main()
