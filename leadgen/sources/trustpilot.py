"""Trustpilot: find low-rated businesses in ICP categories, then read their 1–2 star reviews.

Trustpilot is a Next.js site; every page embeds its data as JSON in __NEXT_DATA__, so no
HTML scraping or headless browser is needed.
"""
from __future__ import annotations

from ..common import (STATS, Lead, clean_domain, find_phrases, get, guess_industry, months_ago,
                      next_data, parse_date)

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


def _bad_reviews(s, domain: str, max_pages: int):
    """Yield (pageProps, reviews) for 1–2★ reviews, newest first, until older than 12 months."""
    cutoff = months_ago(12)
    for page in range(1, max_pages + 1):
        r = get(s, f"{BASE}/review/{domain}",
                params={"stars": [1, 2], "sort": "recency", "page": page})
        data = next_data(r.text) if r else None
        if not data:
            return
        props = data.get("props", {}).get("pageProps", {})
        reviews = props.get("reviews", []) or []
        yield props, reviews
        oldest = parse_date((reviews[-1].get("dates") or {}).get("publishedDate")) if reviews else None
        if not reviews or (oldest and oldest < cutoff):
            return


def trustpilot_slug(value: str) -> str:
    """'https://www.UniUni.com/track' -> 'www.uniuni.com' (Trustpilot pages are keyed by domain)."""
    return value.strip().lower().removeprefix("https://").removeprefix("http://").split("/")[0]


def analyze_domain(s, domain: str, cfg: dict, industry_key: str | None = None,
                   max_pages: int = 15) -> Lead | None:
    """Try the domain as given, then with/without 'www.' (Trustpilot lists some companies either way)."""
    domain = trustpilot_slug(domain)
    alt = domain[4:] if domain.startswith("www.") else "www." + domain
    for candidate in (domain, alt):
        before = STATS.get("www.trustpilot.com", {}).get("notfound", 0)
        lead = _analyze(s, candidate, cfg, industry_key, max_pages)
        if lead or STATS.get("www.trustpilot.com", {}).get("notfound", 0) == before:
            return lead  # found, or failed for a reason other than "no such page"
    return None


def _analyze(s, domain: str, cfg: dict, industry_key: str | None, max_pages: int) -> Lead | None:
    """Count a business's 1–2★ reviews in the last 6 months (key indicator) and the 6 before."""
    six, twelve = months_ago(6), months_ago(12)
    bu, recent, prior, oldest, exhausted = {}, [], 0, None, True
    pages = 0
    for props, reviews in _bad_reviews(s, domain, max_pages):
        pages += 1
        bu = bu or props.get("businessUnit", {}) or {}
        if len(reviews) >= 20 and pages == max_pages:
            exhausted = False  # stopped on the page limit, not on the date cutoff or last page
        for rv in reviews:
            published = parse_date((rv.get("dates") or {}).get("publishedDate"))
            if not published:
                continue
            oldest = min(oldest or published, published)
            if published >= six:
                recent.append((published, rv))
            elif published >= twelve:
                prior += 1
    if not bu:
        return None

    signals, best_quote, replied = [], "", 0
    for _, rv in recent:
        text = f"{rv.get('title', '')}. {rv.get('text', '')}"
        hits = find_phrases(text, cfg["pain_phrases"])
        signals += hits
        if hits and len(best_quote) < 40:
            best_quote = text.strip()
        replied += 1 if rv.get("reply") else 0

    min_bad = cfg["scoring"].get("min_bad_reviews_6m", 5)
    if len(recent) < min_bad:
        return None
    contact = bu.get("contactInfo", {}) or {}
    # If we hit the page limit before going back 12 months, the prior count is partial, and before
    # 6 months the recent count is only a lower bound.
    partial_prior = not exhausted and (oldest is None or oldest > twelve)
    partial_recent = not exhausted and (oldest is None or oldest > six)
    return Lead(
        source="Trustpilot",
        lead_type="Pain",
        company=bu.get("displayName") or domain,
        industry_key=industry_key,
        evidence_url=f"{BASE}/review/{domain}?stars=1&stars=2&sort=recency",
        website=bu.get("websiteUrl") or f"https://{domain}",
        rating=bu.get("trustScore"),
        review_count=bu.get("numberOfReviews"),
        reply_rate=(replied / len(recent)) if recent else None,
        bad_6m=len(recent),
        bad_prev_6m=None if partial_prior else prior,
        latest_bad=max(p for p, _ in recent).date().isoformat(),
        count_basis="sample" if partial_recent else "exact",
        pain_signals=signals,
        evidence_quote=best_quote or f"{recent[0][1].get('title', '')}. {recent[0][1].get('text', '')}".strip(),
        location=", ".join(x for x in (contact.get("city"), contact.get("country")) if x),
        contact_email=contact.get("email") or "",
        contact_phone=contact.get("phone") or "",
        notes=f"{len(signals)} support-pain phrases across {len(recent)} bad reviews in 6 months"
              + (" (lower bound: page limit reached)" if partial_recent else ""),
    )


def collect(s, cfg: dict, pages: int = 3, extra_domains: list[str] | None = None) -> list[Lead]:
    # Loose prefilter: a well-rated brand can still be drowning in recent complaints,
    # so the 6-month bad-review count (not the lifetime score) decides.
    threshold = cfg["scoring"].get("category_max_rating", 4.2)
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
