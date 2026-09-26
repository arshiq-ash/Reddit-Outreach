"""Score leads 0–100 by how likely they are to buy 24/7 outsourced CX."""
from __future__ import annotations

from .common import Lead, clean_domain

# Pain that maps directly to what OptiFlowCX sells (capacity / responsiveness / coverage).
HIGH_VALUE = {"no response", "no reply", "never responded", "never replied", "never heard back",
              "never called back", "ignored my emails", "ignored emails", "impossible to reach",
              "impossible to contact", "no one answers", "nobody answers", "voicemail",
              "no live person", "email only", "email-only", "after hours", "on hold",
              "does not respond", "unanswered", "ghosting", "ignored", "uncontactable",
              "no way to contact", "nobody called", "no answer"}


def score(lead: Lead, cfg: dict) -> int:
    sc = cfg["scoring"]
    if clean_domain(lead.website) in sc.get("exclude_domains", []):
        return 0

    if lead.lead_type == "Intent":
        # An owner publicly asking for support help is the warmest lead there is.
        pts = 70 + min(len(lead.pain_signals) * 5, 20)
        return min(100, pts + (10 if lead.industry_key else 0))

    pts = 0
    if lead.rating is not None:  # lower rating → more urgency
        pts += max(0, int((sc["low_rating_threshold"] + 0.5 - lead.rating) * 12))
    uniq = set(lead.pain_signals)
    pts += min(len(uniq) * 6, 30)
    pts += 10 if uniq & HIGH_VALUE else 0
    if lead.review_count is not None:  # growing brands are the sweet spot
        lo, hi = sc["ideal_review_count"]
        pts += 15 if lo <= lead.review_count <= hi else 0
    if lead.reply_rate is not None and lead.reply_rate < 0.2:
        pts += 10  # not even answering public reviews → no CX capacity
    pts += 10 if lead.industry_key else 0
    pts += 5 if (lead.contact_email or lead.contact_phone) else 0
    return max(0, min(100, pts))
