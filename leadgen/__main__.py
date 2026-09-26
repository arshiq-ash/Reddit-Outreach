"""CLI: python -m leadgen [--sources reddit,trustpilot,yelp] [--sheet-id ID] ..."""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

from .common import ROOT, clean_domain, load_config, session
from .enrich import enrich
from .output import write_csv, write_google_sheet, write_xlsx
from .scoring import score
from .sources import reddit, trustpilot, yelp


def main() -> None:
    ap = argparse.ArgumentParser(description="Find CX-outsourcing leads from review sites.")
    ap.add_argument("--sources", default="reddit,trustpilot,yelp")
    ap.add_argument("--sheet-id", default=os.getenv("GOOGLE_SHEET_ID"), help="Google Sheet to upsert into")
    ap.add_argument("--tab", default="Leads")
    ap.add_argument("--out", default=str(ROOT / "output" / "leads"), help="local path prefix for .csv/.xlsx")
    ap.add_argument("--domains", nargs="*", default=[], help="extra Trustpilot domains to analyze")
    ap.add_argument("--domains-file", default=str(ROOT / "config" / "watchlist.txt"))
    ap.add_argument("--tp-pages", type=int, default=3, help="Trustpilot category pages per category")
    ap.add_argument("--reddit-time", default="year", choices=["day", "week", "month", "year", "all"])
    ap.add_argument("--min-score", type=int, default=30)
    ap.add_argument("--no-enrich", action="store_true", help="skip website contact lookup")
    ap.add_argument("--include-seed", action="store_true", help="merge data/seed_leads.csv into the output")
    args = ap.parse_args()

    cfg = load_config()
    s = session()
    wanted = {x.strip() for x in args.sources.split(",") if x.strip()}
    domains = list(args.domains)
    if os.path.exists(args.domains_file):
        domains += [ln.strip() for ln in open(args.domains_file) if ln.strip() and not ln.startswith("#")]

    leads = []
    if "trustpilot" in wanted:
        leads += trustpilot.collect(s, cfg, pages=args.tp_pages, extra_domains=domains)
    if "reddit" in wanted:
        leads += reddit.collect(s, cfg, time_filter=args.reddit_time)
    if "yelp" in wanted:
        leads += yelp.collect(s, cfg)

    for lead in leads:
        lead.score = score(lead, cfg)
    leads = [l for l in leads if l.score >= args.min_score]
    if not args.no_enrich:
        for lead in leads:
            if lead.lead_type == "Pain" and lead.website:
                enrich(s, lead)

    rows = {}
    for lead in sorted(leads, key=lambda l: l.score, reverse=True):
        rows.setdefault(lead.key, lead.to_row(cfg))
    if args.include_seed:
        with open(ROOT / "data" / "seed_leads.csv", encoding="utf-8") as f:
            seeds = list(csv.DictReader(f))
        # A fresh scrape of the same company wins over the hand-researched seed row.
        seen = {clean_domain(r["Website"]) or r["Company"].lower() for r in rows.values()}
        for r in seeds:
            if (clean_domain(r["Website"]) or r["Company"].lower()) not in seen:
                rows.setdefault(r["Lead ID"], r)
    rows = sorted(rows.values(), key=lambda r: int(r.get("Lead Score") or 0), reverse=True)

    print(f"\n{len(rows)} leads "
          f"({sum(r['Priority'] == 'Hot' for r in rows)} hot, {sum(r['Priority'] == 'Warm' for r in rows)} warm)")
    write_csv(rows, Path(args.out + ".csv"))
    # Leads with little recent complaint volume go to a separate tab rather than the main list.
    main_rows = [r for r in rows if r.get("Recent Volume") != "Low"]
    watch_rows = [r for r in rows if r.get("Recent Volume") == "Low"]
    write_xlsx(main_rows, Path(args.out + ".xlsx"), extra_tabs={"Watchlist (low recent volume)": watch_rows})
    print(f"wrote {args.out}.csv and {args.out}.xlsx")
    if args.sheet_id:
        print("google sheet:", write_google_sheet(rows, args.sheet_id, args.tab))


if __name__ == "__main__":
    main()
