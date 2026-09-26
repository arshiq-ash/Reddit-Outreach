"""Yelp: low-rated med spas, dental and aesthetic clinics (the AI Voice Receptionist offer).

Uses the Yelp Fusion API (YELP_API_KEY, from https://www.yelp.com/developers). Scraping
yelp.com directly is blocked aggressively, so the API is the only dependable route.
The reviews endpoint returns up to 3 excerpts per business; when the plan doesn't include it,
we still keep the business as a lead based on its rating.
"""
from __future__ import annotations

import os

from ..common import Lead, find_phrases, get, months_ago, parse_date

API = "https://api.yelp.com/v3"
# Appointment-led businesses lose revenue on missed calls, so phone-related complaints matter most.
PHONE_PAIN = ["voicemail", "never called back", "no one answers", "nobody answers", "on hold",
              "didn't respond", "no response", "can't reach", "rude", "front desk"]


def collect(s, cfg: dict, per_search: int = 50) -> list[Lead]:
    key = os.getenv("YELP_API_KEY")
    if not key:
        print("[yelp] YELP_API_KEY not set — skipping")
        return []
    headers = {"Authorization": f"Bearer {key}"}
    threshold = cfg["scoring"]["low_rating_threshold"]
    leads, seen = [], set()

    for ind_key, ind in cfg["industries"].items():
        for loc in ind.get("yelp_locations", []):
            for cat in ind.get("yelp_categories", []):
                print(f"[yelp] {cat} in {loc}")
                r = get(s, f"{API}/businesses/search", headers=headers, delay=0.3,
                        params={"location": loc, "categories": cat, "limit": per_search, "sort_by": "review_count"})
                for b in (r.json().get("businesses", []) if r else []):
                    if b["id"] in seen or b.get("is_closed") or b.get("rating", 5) > threshold:
                        continue
                    seen.add(b["id"])
                    quote, signals, bad_recent, latest = "", [], 0, None
                    rv = get(s, f"{API}/businesses/{b['id']}/reviews", headers=headers, delay=0.3,
                             params={"limit": 3, "sort_by": "newest"}, tries=1)
                    for review in (rv.json().get("reviews", []) if rv else []):
                        created = parse_date(review.get("time_created", "").replace(" ", "T"))
                        if review.get("rating", 5) <= 2 and created and created >= months_ago(6):
                            bad_recent += 1
                            latest = max(latest or created, created)
                        hits = find_phrases(review.get("text", ""), cfg["pain_phrases"] + PHONE_PAIN)
                        signals += hits
                        if hits and not quote:
                            quote = review.get("text", "")
                    addr = b.get("location", {})
                    leads.append(Lead(
                        source="Yelp",
                        lead_type="Pain",
                        company=b.get("name", ""),
                        industry_key=ind_key,
                        evidence_url=b.get("url", "").split("?")[0],
                        rating=b.get("rating"),
                        review_count=b.get("review_count"),
                        bad_6m=bad_recent,
                        latest_bad=latest.date().isoformat() if latest else "",
                        count_basis="sample",  # Fusion API exposes only 3 review excerpts
                        pain_signals=signals or [f"{b.get('rating')}★ on Yelp"],
                        evidence_quote=quote,
                        location=", ".join(x for x in (addr.get("city"), addr.get("state")) if x),
                        contact_phone=b.get("display_phone", ""),
                        notes=", ".join(c["title"] for c in b.get("categories", [])),
                    ))
    return leads
