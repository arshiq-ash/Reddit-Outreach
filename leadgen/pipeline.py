"""One lead-generation run, shared by the CLI (python -m leadgen) and the local app (leadgen.server)."""
from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from pathlib import Path

from .common import ROOT, STATS, blocked_hosts, clean_domain, load_config, session
from .enrich import enrich
from .output import write_csv, write_google_sheet, write_xlsx
from .scoring import score
from .sources import reddit, trustpilot, yelp

SEED_FILES = [ROOT / "data" / "seed_leads.csv", ROOT / "data" / "seed_watchlist.csv"]
LEAD_SOURCES = ("trustpilot", "reddit", "yelp")


@dataclass
class Options:
    sources: set[str] = field(default_factory=lambda: set(LEAD_SOURCES))
    sheet_id: str | None = None
    tab: str = "Leads"
    out: str = str(ROOT / "output" / "leads")
    domains: list[str] = field(default_factory=list)
    domains_file: str = str(ROOT / "config" / "watchlist.txt")
    tp_pages: int = 3
    reddit_time: str = "year"
    min_score: int = 30
    enrich: bool = True
    include_seed: bool = False


@dataclass
class Result:
    rows: list[dict]
    blocked: list[str]            # lead-source hosts that refused every request
    stats: dict                   # per-host request outcomes
    files: list[Path]
    sheet_url: str = ""


def run(opts: Options) -> Result:
    cfg = load_config()
    s = session()
    STATS.clear()
    domains = list(opts.domains)
    if opts.domains_file and os.path.exists(opts.domains_file):
        domains += [ln.strip() for ln in open(opts.domains_file) if ln.strip() and not ln.startswith("#")]

    leads = []
    if "trustpilot" in opts.sources:
        leads += trustpilot.collect(s, cfg, pages=opts.tp_pages, extra_domains=domains)
    if "reddit" in opts.sources:
        leads += reddit.collect(s, cfg, time_filter=opts.reddit_time)
    if "yelp" in opts.sources:
        leads += yelp.collect(s, cfg)

    for lead in leads:
        lead.score = score(lead, cfg)
    leads = [l for l in leads if l.score >= opts.min_score]
    if opts.enrich:
        for lead in leads:
            if lead.lead_type == "Pain" and lead.website:
                enrich(s, lead)

    rows = {}
    for lead in sorted(leads, key=lambda l: l.score, reverse=True):
        rows.setdefault(lead.key, lead.to_row(cfg))
    if opts.include_seed:
        # A fresh scrape of the same company wins over the hand-researched seed row.
        seen = {clean_domain(r["Website"]) or r["Company"].lower() for r in rows.values()}
        for path in SEED_FILES:
            if path.exists():
                with open(path, encoding="utf-8") as f:
                    for r in csv.DictReader(f):
                        if (clean_domain(r["Website"]) or r["Company"].lower()) not in seen:
                            rows.setdefault(r["Lead ID"], r)
    rows = sorted(rows.values(), key=lambda r: int(r.get("Lead Score") or 0), reverse=True)

    print(f"\n{len(rows)} leads "
          f"({sum(r['Priority'] == 'Hot' for r in rows)} hot, {sum(r['Priority'] == 'Warm' for r in rows)} warm)")
    csv_path, xlsx_path = Path(opts.out + ".csv"), Path(opts.out + ".xlsx")
    write_csv(rows, csv_path)
    # Leads with little recent complaint volume go to a separate tab rather than the main list.
    main_rows = [r for r in rows if r.get("Recent Volume") != "Low"]
    watch_rows = [r for r in rows if r.get("Recent Volume") == "Low"]
    write_xlsx(main_rows, xlsx_path, extra_tabs={"Watchlist (low recent volume)": watch_rows})
    print(f"wrote {csv_path} and {xlsx_path}")

    sheet_url = ""
    if opts.sheet_id:
        sheet_url = write_google_sheet(rows, opts.sheet_id, opts.tab)
        print("google sheet:", sheet_url)

    print("\nrequests per host:", STATS)
    # Only the lead sources matter here; company websites refusing the contact lookup is normal.
    blocked = [h for h in blocked_hosts() if any(k in h for k in LEAD_SOURCES)]
    if blocked:
        print(f"\nWARNING: {', '.join(blocked)} refused or never answered (HTTP 401/403/429 or no connection). "
              "These sources produced no data this run. See README > 'If a source is blocked'.")
    return Result(rows=rows, blocked=blocked, stats={h: dict(c) for h, c in STATS.items()},
                  files=[csv_path, xlsx_path], sheet_url=sheet_url)
