"""Reddit: two kinds of leads.

* Intent — a business owner asking for help with support volume, 24/7 coverage, missed calls
  (r/shopify, r/ecommerce, r/smallbusiness, r/Dentistry ...). These are the warmest leads.
* Pain — customers complaining that a brand's support is unreachable. The brand is the lead.

Uses the official API via OAuth (REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET, free "script" app at
https://www.reddit.com/prefs/apps) when configured — it is far more reliable than the anonymous
JSON endpoints, which Reddit rate-limits and often blocks from cloud IPs.
"""
from __future__ import annotations

import os
import re

from ..common import Lead, find_phrases, get, guess_industry, months_ago, parse_date

PAIN_QUERIES = [
    '"customer service" "no response"',
    '"customer service" "never responded"',
    '"customer support" ignored emails',
    '"impossible to reach" support',
    '"still waiting" refund support',
    '"no one answers" phone',
]
INTENT_QUERIES = [
    "outsource customer support",
    "overwhelmed support tickets",
    "24/7 customer support",
    "hire customer service agents",
    "missed calls receptionist",
    "answering service after hours",
]
INTENT_SUBS = {"shopify", "ecommerce", "smallbusiness", "entrepreneur", "dentistry", "logistics", "couriers"}
# "Brand X support is awful" / "avoid Brand X" — pull a likely brand name out of a title.
BRAND_PATTERNS = [
    r"\b(?i:avoid|about|from|with|ordered from|bought from|purchased from)\s+([A-Z][\w&'.-]+(?:\s+[A-Z][\w&'.-]+){0,2})",
    r"^([A-Z][\w&'.-]+(?:\s+[A-Z][\w&'.-]+){0,2})\s+(?:customer service|support|refund|warranty)",
]
STOP = {"I", "My", "The", "A", "An", "Is", "Anyone", "Has", "Why", "What", "How", "PSA", "Help", "Update", "Just", "This"}


def _token(s) -> str | None:
    cid, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
    if not (cid and secret):
        return None
    r = s.post(
        "https://www.reddit.com/api/v1/access_token",
        auth=(cid, secret),
        data={"grant_type": "client_credentials"},
        timeout=20,
    )
    return r.json().get("access_token") if r.ok else None


def _search(s, token, sub: str, query: str, limit: int, time_filter: str):
    base = "https://oauth.reddit.com" if token else "https://www.reddit.com"
    headers = {"Authorization": f"bearer {token}"} if token else None
    params = {"q": query, "restrict_sr": 1, "sort": "new", "t": time_filter, "limit": limit}
    r = get(s, f"{base}/r/{sub}/search.json", params=params, headers=headers, delay=1.0 if token else 2.5)
    if not r:
        return []
    return [c["data"] for c in r.json().get("data", {}).get("children", [])]


def extract_brand(title: str) -> str | None:
    for pat in BRAND_PATTERNS:
        m = re.search(pat, title)
        if m:
            name = m.group(1).strip(" .'")
            if name.split()[0] not in STOP:
                return name
    return None


def collect(s, cfg: dict, limit: int = 100, time_filter: str = "year") -> list[Lead]:
    token = _token(s)
    print(f"[reddit] using {'OAuth API' if token else 'anonymous JSON (set REDDIT_CLIENT_ID for reliability)'}")
    six, twelve = months_ago(6), months_ago(12)
    leads, seen, brands = [], set(), {}
    for key, ind in cfg["industries"].items():
        for sub in ind.get("subreddits", []):
            queries = INTENT_QUERIES if sub.lower() in INTENT_SUBS else PAIN_QUERIES
            for q in queries:
                for post in _search(s, token, sub, q, limit, time_filter):
                    created = parse_date(post.get("created_utc"))
                    if post["id"] in seen or not created or created < twelve:
                        continue
                    seen.add(post["id"])
                    title, body = post.get("title", ""), post.get("selftext", "")
                    text = f"{title}\n{body}"
                    url = "https://www.reddit.com" + post.get("permalink", "")
                    intent = find_phrases(text, cfg["intent_phrases"])
                    pain = find_phrases(text, cfg["pain_phrases"])
                    if intent and created >= six:
                        leads.append(Lead(
                            source=f"Reddit r/{post.get('subreddit', sub)}",
                            lead_type="Intent",
                            company=f"u/{post.get('author', '?')}",
                            industry_key=guess_industry(text, cfg, key),
                            evidence_url=url,
                            pain_signals=intent + pain,
                            evidence_quote=f"{title} — {body[:250]}",
                            latest_bad=created.date().isoformat(),
                            notes="Business owner asking for support help — reply in thread / DM",
                        ))
                    elif pain and (brand := extract_brand(title)):
                        b = brands.setdefault(brand.lower(), {
                            "name": brand, "key": guess_industry(text, cfg, key), "recent": 0, "prior": 0,
                            "latest": created, "url": url, "quote": f"{title} — {body[:250]}",
                            "signals": [], "subs": set()})
                        b["recent" if created >= six else "prior"] += 1
                        b["signals"] += pain
                        b["subs"].add(post.get("subreddit", sub))
                        if created > b["latest"]:
                            b.update(latest=created, url=url, quote=f"{title} — {body[:250]}")

    # One lead per brand; only brands with complaints in the last 6 months.
    for b in brands.values():
        if not b["recent"]:
            continue
        leads.append(Lead(
            source="Reddit " + ", ".join(f"r/{x}" for x in sorted(b["subs"])),
            lead_type="Pain",
            company=b["name"],
            industry_key=b["key"],
            evidence_url=b["url"],
            pain_signals=b["signals"],
            evidence_quote=b["quote"],
            bad_6m=b["recent"],
            bad_prev_6m=b["prior"],
            latest_bad=b["latest"].date().isoformat(),
            count_basis="exact",
            notes=f"{b['recent']} complaint posts in 6 months (link = newest)",
        ))
    return leads
