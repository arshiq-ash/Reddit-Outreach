"""Trustpilot: find low-rated businesses in ICP categories, then read their 1–2 star reviews.

Trustpilot is a Next.js site; every page embeds its data as JSON in __NEXT_DATA__, so no
HTML scraping or headless browser is needed.
"""
from __future__ import annotations

from ..common import Lead, clean_domain, find_phrases, get, guess_industry, next_data

BASE = "https://www.trustpilot.com"


def _businesses_in_category(s, category: str, pages: int):
    for page in range(1, pages + 1):
        r = get(s, f"{BASE}/categories/{category}", params={"page": page, "sort": "reviews_count"})
        data = next_data(r.text) if r else None
        if not data:
            return
        props = data.get("props", {}).get("pageProps", {})
        units = props.get("businessUnits", {})
        items = units.get("businesses", units) if isinstance(units, dict) else units
        if not items:
            return
        yield from items


def analyze_domain(s, domain: str, cfg: dict, industry_key: str | None = None) -> Lead | None:
    """Read a business's 1–2 star reviews and build a lead from its support-related pain."""
    r = get(s, f"{BASE}/review/{domain}", params={"stars": [1, 2], "sort": "recency"})
    data = next_data(r.text) if r else None
    if not data:
        return None
    props = data.get("props", {}).get("pageProps", {})
    bu = props.get("businessUnit", {}) or {}
    reviews = props.get("reviews", []) or []
    contact = bu.get("contactInfo", {}) or {}

    signals, best_quote, replied = [], "", 0
    for rv in reviews:
        text = f"{rv.get('title', '')}. {rv.get('text', '')}"
        hits = find_phrases(text, cfg["pain_phrases"])
        signals += hits
        if hits and len(best_quote) < 40:
            best_quote = text.strip()
        replied += 1 if rv.get("reply") else 0

    if not signals:
        return None
    name = bu.get("displayName") or domain
    return Lead(
        source="Trustpilot",
        lead_type="Pain",
        company=name,
        industry_key=industry_key,
        evidence_url=f"{BASE}/review/{domain}?stars=1&stars=2",
        website=bu.get("websiteUrl") or f"https://{domain}",
        rating=bu.get("trustScore"),
        review_count=bu.get("numberOfReviews"),
        reply_rate=(replied / len(reviews)) if reviews else None,
        pain_signals=signals,
        evidence_quote=best_quote,
        location=", ".join(x for x in (contact.get("city"), contact.get("country")) if x),
        contact_email=contact.get("email") or "",
        contact_phone=contact.get("phone") or "",
        notes=f"{len(signals)} support-pain mentions in latest {len(reviews)} negative reviews",
    )


def collect(s, cfg: dict, pages: int = 3, extra_domains: list[str] | None = None) -> list[Lead]:
    threshold = cfg["scoring"]["low_rating_threshold"]
    lo, hi = cfg["scoring"]["ideal_review_count"]
    excluded = set(cfg["scoring"].get("exclude_domains", []))
    leads, seen = [], set()

    targets: list[tuple[str, str | None]] = [(d, None) for d in (extra_domains or [])]
    for key, ind in cfg["industries"].items():
        for cat in ind.get("trustpilot_categories", []):
            print(f"[trustpilot] category {cat}")
            for b in _businesses_in_category(s, cat, pages):
                domain = clean_domain(b.get("identifyingName") or b.get("websiteUrl"))
                score = b.get("trustScore") or 0
                count = b.get("numberOfReviews") or 0
                if domain and score and score <= threshold and lo <= count <= hi:
                    targets.append((domain, key))

    for domain, key in targets:
        domain = clean_domain(domain)
        if not domain or domain in seen or domain in excluded:
            continue
        seen.add(domain)
        print(f"[trustpilot] reviews {domain}")
        lead = analyze_domain(s, domain, cfg, key)
        if lead:
            if not lead.industry_key:
                lead.industry_key = guess_industry(f"{lead.company} {lead.evidence_quote}", cfg)
            leads.append(lead)
    return leads
