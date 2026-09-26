"""Score leads 0–100. Key indicator: volume of bad reviews in the last 6 months."""
from __future__ import annotations

from .common import Lead, clean_domain

# Pain that maps directly to what OptiFlowCX sells (capacity / responsiveness / coverage).
HIGH_VALUE = {"no response", "no reply", "never responded", "never replied", "never heard back",
              "never called back", "ignored my emails", "ignored emails", "impossible to reach",
              "impossible to contact", "no one answers", "nobody answers", "voicemail",
              "no live person", "email only", "email-only", "after hours", "on hold",
              "does not respond", "unanswered", "ghosting", "ignored", "uncontactable",
              "no way to contact", "nobody called", "no answer"}


def recent_volume_points(bad_6m: int | None, cfg: dict) -> int:
    """Up to 55 points for the number of bad reviews in the last 6 months."""
    if not bad_6m:
        return 0
    for threshold, pts in cfg["scoring"]["bad_review_tiers"]:
        if bad_6m >= threshold:
            return pts
    return 0


def score(lead: Lead, cfg: dict) -> int:
    sc = cfg["scoring"]
    if clean_domain(lead.website) in sc.get("exclude_domains", []):
        return 0

    if lead.lead_type == "Intent":
        # An owner publicly asking for support help is the warmest lead there is.
        pts = 70 + min(len(lead.pain_signals) * 5, 20)
        return min(100, pts + (10 if lead.industry_key else 0))

    bad = lead.bad_6m
    if bad is None and lead.volume_tier:                          # hand-researched tier, no exact count
        bad = {"High": 50, "Medium": 10, "Low": 1}.get(lead.volume_tier)
    pts = recent_volume_points(bad, cfg)                          # key indicator, max 55
    if lead.bad_6m and lead.bad_prev_6m is not None and lead.bad_6m > lead.bad_prev_6m * 1.2:
        pts += 10                                                 # getting worse
    uniq = set(lead.pain_signals)
    pts += 10 if uniq & HIGH_VALUE else (5 if uniq else 0)        # the complaints are about support
    if lead.reply_rate is not None and lead.reply_rate < 0.2:
        pts += 5                                                  # not answering public reviews either
    if lead.review_count is not None:
        lo, hi = sc["ideal_review_count"]
        pts += 5 if lo <= lead.review_count <= hi else 0          # growing brand, not an enterprise
    if lead.rating is not None and lead.rating <= sc["low_rating_threshold"]:
        pts += 5
    pts += 5 if lead.industry_key else 0
    pts += 5 if (lead.contact_email or lead.contact_phone) else 0
    return max(0, min(100, pts))
