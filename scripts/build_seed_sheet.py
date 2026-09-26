"""Build data/seed_leads.{csv,xlsx} from hand research (web searches of Trustpilot/Yelp, 26 Sep 2026).

Key indicator: volume of bad reviews in the last 6 months (≈ 26 Mar – 26 Sep 2026).
Search results expose dated complaints and review totals but not exact per-period counts, so each
lead gets a High / Medium / Low tier. The scheduled pipeline replaces tiers with exact counts.

  High   – large review base that is overwhelmingly negative AND complaints dated in the last 6 months
  Medium – several support complaints dated in the last 6 months
  Low    – few or no dated complaints in the last 6 months → Watchlist tab, not the main list
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from leadgen.common import Lead, find_phrases, load_config  # noqa: E402
from leadgen.output import write_csv, write_xlsx  # noqa: E402
from leadgen.scoring import score  # noqa: E402

TP = "https://www.trustpilot.com/review/"
NOTE = "Researched 26 Sep 2026 via web search. Quote summarises public reviews, so open the link before outreach"

# company, domain, industry, url, tier, latest bad review seen, rating, reviews, evidence, note
RESEARCH = [
    # ---------------- High ----------------
    ("UniUni", "uniuni.com", "logistics", TP + "www.uniuni.com", "High", "Aug 2026", 1.1, 2874,
     "Jul–Aug 2026 reviews: can't get past the AI chatbot; no human customer service; packages ordered 7/3 still missing 8/5; delivery dates pushed back 3 times.",
     "95% of reviews are 1-star. Pitch the SwiftX case study (dispatch/package-status call team)"),
    ("GOFO Express", "gofoexpress.com", "logistics", TP + "gofoexpress.com", "High", "2026 (Jun+)", 1.3, 5516,
     "Routing-policy change in June 2026 caused false 'incorrect address' loops; customer service 'abysmal', refuses to help with lost packages, repeated failed deliveries despite calls.",
     "90% of reviews are 1-star; complaint volume looks to have jumped after the June 2026 policy change"),
    ("OnTrac", "ontrac.com", "logistics", TP + "ontrac.com", "High", "2026", 1.1, 3300,
     "2026 reviews: chat reps disconnect mid-sentence, customer service 'nearly useless', packages repeatedly delivered to wrong addresses, falsified scans.",
     "Regional carrier (ex-LaserShip) and a larger org, so pitch overflow/after-hours coverage"),
    ("ParcelCompare", "parcelcompare.com", "logistics", TP + "parcelcompare.com", "High", "2026", None, 12800,
     "2026 reviews: chatbot 'goes round in circles', sends you to a support email that sends you back to the chatbot; impossible to reach a human; tickets need a tracking number you may not have.",
     "UK shipping broker. The pain is purely no-human-support, which is an ideal fit"),
    ("Mammotion", "mammotion.com", "consumer_tech", TP + "mammotion.com", "High", "16 Sep 2026", 3.6, 2836,
     "Aug–Sep 2026: one customer logged 6 tickets, 8 agents, 30+ emails and 7 chats; others report 20+ hours with support, AI/template replies, wrong replacement parts, hours trying to reach a human.",
     "Robot mower, the closest Yarbo comparable. Replies to 66% of negative reviews, so they care but lack capacity"),
    ("CouriersPlease", "couriersplease.com.au", "logistics", "https://au.trustpilot.com/review/couriersplease.com.au", "High", "Sep 2026", None, None,
     "Collections booked Aug 2026 still not collected late Sep 2026; 'no humans involved', AI bot only; no phone; emails ignored.",
     "Australia; very large review base (thousands of pages). Owned by Australia Post, so this is enterprise-level"),
    ("Xpressbees", "xpressbees.com", "logistics", TP + "xpressbees.com", "High", "Aug 2026", 1.1, 935,
     "Aug 2026 reviews: no way to speak to a live agent, emails unanswered, fake delivery-attempt notifications.",
     "India, large carrier. Pitch offshore 24/7 voice/chat"),
    ("Halara", "thehalara.com", "ecommerce_dtc", TP + "thehalara.com", "High", "2026", None, None,
     "2026 reviews: copy-paste responses, ignored on live chat after 'be patient', no phone, email-only.",
     "Very large DTC activewear brand (14k+ review pages), so pitch overflow and live-chat coverage"),
    # ---------------- Medium ----------------
    ("Dreame Technology", "dreame-technology.com", "consumer_tech", TP + "dreame-technology.com", "Medium", "Jul 2026", None, None,
     "2026: $2,200 robot vacuum bought Jan 2026, 6 months and 68 emails later still no replacement; AI copy-paste replies; repair sent 16 Feb still not back a month later.",
     "Robot vacuums. Pitch Yarbo-style L1/L2 after-sales"),
    ("Ecovacs", "ecovacs.com", "consumer_tech", TP + "ecovacs.com", "Medium", "Aug 2026", None, None,
     "Robot collected for repair 20 Jul 2026, replacement approved 30 Jul, 2+ weeks later no dispatch date and follow-up emails ignored; refunds taking 5 weeks.",
     ""),
    ("VTOMAN", "vtoman.com", "consumer_tech", TP + "vtoman.com", "Medium", "Jul 2026", None, None,
     "2026: 'totally no response from customer service', 9+ days without replies, web-form contacts ignored; Jul 2026 disabled customer reports warranty commitments not honoured.",
     "Portable power stations. Seems to respond only to public bad reviews"),
    ("n+ Bikes", "nplusbikes.com", "consumer_tech", TP + "nplusbikes.com", "Medium", "Jul 2026", None, 217,
     "Refund confirmed 29 Jun 2026, promised in 15 business days, still unpaid after 20 Jul 2026; ship dates pushed 9 times; conflicting information from reps.",
     "Recent reviews mostly negative. Check financial health before pitching"),
    ("Lymow", "lymow.com", "consumer_tech", TP + "lymow.com", "Medium", "2026", 3.9, 263,
     "2026: 'Support is overwhelmed and does not respond within the timeframes they promote'; 'clearly not ready to support a large customer base'; no way to contact.",
     "Robot mower startup that is scaling, the exact Yarbo story. Replies to only 8% of negative reviews"),
    ("ANTHBOT", "anthbot.com", "consumer_tech", TP + "anthbot.com", "Medium", "2026", None, 206,
     "Three weeks with no response from support until a 1-star review; contacting support daily for 10 days about a dead M5; weeks without a return form.",
     "Robot mower, a Yarbo comparable"),
    ("Bestmow", "bestmow.com", "consumer_tech", TP + "bestmow.com", "Medium", "Jul 2026", None, 94,
     "Bought Jun 2026, spent a month talking to a bot before reaching the helpdesk; replacement also dead; support unresponsive. Recurring faults since Mar 2026.",
     "Robot mower with AI-first support that is failing, so pitch humans behind the bot"),
    ("DC Shoes", "dcshoes.com", "ecommerce_dtc", TP + "dcshoes.com", "Medium", "2026", None, None,
     "2026: 6 emails answered only by automated replies; 3+ weeks waiting for customer service; refunds not issued for wrong shoes; 'near impossible to contact'.",
     "Licensed brand, so pitch WISMO/returns team"),
    ("Shysilk", "shysilk.com", "ecommerce_dtc", TP + "shysilk.com", "Medium", "2026", None, None,
     "Numerous 2026 reviews: 'free returns' means shipping to China; team 'trained to avoid refunds'; returned goods claimed not received.",
     "Silk sleepwear, fits the Silksilky case study (but the pain is partly policy, not only capacity)"),
    ("Roborock", "roborock.com", "consumer_tech", TP + "roborock.com", "Medium", "2026", None, None,
     "2026: email-only support, 48h+ between replies, generic answers, months without warranty resolution.",
     "Large brand, so pitch phone/chat channels on top of email"),
    ("Monport Laser", "monportlaser.com", "hardware_3d", TP + "monportlaser.com", "Medium", "2026", None, None,
     "2026: phone numbers never answered, email-only support taking days; 'a 30-minute phone call took weeks by email'.",
     "The company publicly says it is working on live phone support, which is a direct opening for the Creality case study"),
]

WATCHLIST = [  # Low recent volume, or no dated complaints found in the last 6 months
    ("Silkysilky", "silkysilky.com", "ecommerce_dtc", TP + "silkysilky.com", "Low", "2026", None, None,
     "Small profile (~80 reviews). Complaints: 4+ emails needed for a return, 3 months chasing a refund. Some 2026 reviews are positive.",
     "Silk sleepwear. Do NOT confuse with SILKSILKY (silksilky.com), your existing client"),
    ("DT Footwear", "dtfootwear.com", "ecommerce_dtc", TP + "dtfootwear.com", "Low", "28 Jun 2026", None, 46,
     "28 Jun 2026 'worst customer service of ALLTIME'; 23 May 2026 product complaint.", "Small (46 reviews)"),
    ("Eahora Ebike", "eahoraebike.com", "consumer_tech", TP + "eahoraebike.com", "Low", "2026", 3.0, 125,
     "Ghosted on refund request after warranty repair failed; a month trying to reach support.", ""),
    ("Fossibot", "fossibot.com", "consumer_tech", TP + "fossibot.com", "Low", "2026", None, 70,
     "2026 shipping delays and 'very little help' from support; many positive reviews.", "Also check eu.fossibot.com (366 reviews)"),
    ("OMTech", "omtech.com", "hardware_3d", TP + "omtech.com", "Low", "2026", None, None,
     "Mixed: slow/unhelpful technical support vs. good warranty handling (Jan 2026).", ""),
    ("Flashforge", "flashforge.com", "hardware_3d", TP + "flashforge.com", "Low", "2026", None, None,
     "Contacted support 3 times with no reply; no delay notifications. Many positive reviews too.", ""),
    ("Geeetech", "geeetech.com", "hardware_3d", TP + "www.geeetech.com", "Low", "28 Jul 2026", None, None,
     "Recent complaints are about product quality (TPU, glue); spare parts unavailable.", "Product issue more than support"),
    ("Euybike", "euybike.com", "consumer_tech", TP + "euybike.com", "Low", "", 4.3, 154,
     "EU buyers report no warranty service or EU office; otherwise positive.", ""),
    ("Papinelle", "papinelle.com", "ecommerce_dtc", TP + "papinelle.com", "Low", "Apr 2026", 1.9, 32,
     "Only one dated 2026 complaint (product quality). Earlier: 'no one ever responds to messages'.", "Tiny review base"),
    ("Pure Med Spa", "puremedspa.com", "appointment_practices", "https://www.yelp.com/brands/pure-med-spa", "Low", "", None, None,
     "Disconnected phones, 'I HAVE NEVER GOTTEN A HOLD OF ANYONE', locations closed without notice.",
     "Complaints are undated in search. Needs the Yelp API run to count the last 6 months"),
    ("Smile Doctors", "smiledoctors.com", "appointment_practices", "https://www.yelp.com/brands/smile-doctors", "Low", "", None, None,
     "Greeley/Johnstown offices: voicemail every call, multiple messages with no response, emergency line not responding.",
     "Orthodontics DSO. Undated in search, so it needs the Yelp API run"),
    ("Midwest Dental", "midwest-dental.com", "appointment_practices", "https://www.yelp.com/brands/midwest-dental", "Low", "", None, None,
     "'Rarely answer their phone while the office is open and do not pay attention to voicemails.'",
     "Dental DSO. Undated, so it needs the Yelp API run"),
]
# Dropped after re-check: Electric Bike Company (Chapter 7 bankruptcy), Urtopia, Anycubic, Coprint3d,
# Sovol, Wallke (mostly positive 2026 reviews), DM Fashion (≈10 reviews in total), Allpowers (latest
# complaint Jan 2026), Elase / Dtclothing (no recent evidence found), Creality and SILKSILKY (existing clients).


def build(entries):
    cfg = load_config()
    leads = []
    for name, domain, ind, url, tier, latest, rating, reviews, evidence, note in entries:
        lead = Lead(
            source="Yelp (research)" if "yelp.com" in url else "Trustpilot (research)",
            lead_type="Pain", company=name, industry_key=ind, evidence_url=url,
            website=f"https://{domain}", rating=rating, review_count=reviews,
            pain_signals=find_phrases(evidence, cfg["pain_phrases"]), evidence_quote=evidence,
            volume_tier=tier, latest_bad=latest, count_basis="sample",
            notes="; ".join(x for x in (note, NOTE) if x),
        )
        lead.score = score(lead, cfg)
        leads.append(lead)
    order = {"High": 0, "Medium": 1, "Low": 2}
    leads.sort(key=lambda l: (order[l.volume_tier], -l.score))
    return [l.to_row(cfg) for l in leads]


if __name__ == "__main__":
    main_rows, watch_rows = build(RESEARCH), build(WATCHLIST)
    write_csv(main_rows, ROOT / "data" / "seed_leads.csv")
    write_csv(watch_rows, ROOT / "data" / "seed_watchlist.csv")
    write_xlsx(main_rows, ROOT / "data" / "seed_leads.xlsx", extra_tabs={"Watchlist (low recent volume)": watch_rows})
    for r in main_rows + watch_rows:
        print(f'{r["Recent Volume"]:6} {r["Lead Score"]:>3} {r["Priority"]:4} {r["Company"]:22} latest={r["Latest Bad Review"]}')
