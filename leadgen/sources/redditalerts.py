"""Reddit via F5Bot keyword alerts: read the alert emails from your inbox and turn them into leads.

F5Bot (https://f5bot.com, free) watches Reddit for your keywords and emails you each new matching
post or comment. This reads those emails over IMAP, so no Reddit API key is needed:

  EMAIL_ADDRESS       the inbox F5Bot sends to (e.g. you@gmail.com)
  EMAIL_APP_PASSWORD  an app password (Gmail: Google Account > Security > App passwords)
  EMAIL_IMAP_HOST     optional, default imap.gmail.com

Only posts where someone describes needing support help are kept (see intent_phrases and
f5bot_keywords in config/icp.yaml). Replies are drafted for you to post by hand; posting is
never automated.
"""
from __future__ import annotations

import datetime as dt
import email
import html
import imaplib
import os
import re
from email.header import decode_header, make_header

from ..common import Lead, find_phrases, guess_industry

SENDER = "f5bot.com"
POST_URL = re.compile(r"https?://(?:www\.|old\.)?reddit\.com/r/([A-Za-z0-9_]+)/comments/[A-Za-z0-9]+[^\s\"'<>)]*")

REPLY_TEMPLATES = {
    "ecommerce_dtc": ("For WISMO/returns volume, the quick wins are macros for the top 10 questions, an order-status "
                      "auto-reply, and a clear handover for refunds. We run 24/7 support for a few DTC brands (one went "
                      "from a 3.4 to a 4.4 Google rating after moving to round-the-clock coverage). Happy to share our "
                      "SOP template if it helps."),
    "consumer_tech": ("What usually fixes this is splitting L1 (order status, setup FAQs) from L2 (real troubleshooting) "
                      "so tickets stop bouncing. We built that for a consumer-tech brand that grew from 3 to 15 agents on "
                      "24/7 chat/email/phone. Glad to share how we structured the escalation path."),
    "hardware_3d": ("With products that change weekly, the trick is a living FAQ/SOP doc and short weekly trainings so "
                    "agents stay current. We did this for a 3D-printer brand across email, chat and phone, 24/7. Happy "
                    "to share the setup."),
    "logistics": ("For package-status and dispatch calls, a dedicated phone team with a simple status-lookup script "
                  "cuts repeat calls a lot. We run 90–100 calls/agent/day for a delivery company. Happy to share how "
                  "we structured it."),
    "appointment_practices": ("Missed calls are usually after-hours and lunch overflow. An AI receptionist that books "
                              "into your calendar, with a human fallback for anything tricky, closes most of that gap. "
                              "We set this up for clinics; happy to share what worked."),
}
DEFAULT_REPLY = ("Happy to share what's worked for us: dedicated agents, documented SOPs and 24/7 shift coverage. "
                 "We run support operations for e-commerce, consumer-tech and logistics brands. Glad to send over "
                 "a checklist if useful.")


def _text(msg) -> str:
    """Plain text of an email, falling back to HTML with tags stripped."""
    parts = msg.walk() if msg.is_multipart() else [msg]
    plain, rich = [], []
    for part in parts:
        ctype = part.get_content_type()
        if ctype not in ("text/plain", "text/html"):
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        (plain if ctype == "text/plain" else rich).append(text)
    if plain:
        return "\n".join(plain)
    body = "\n".join(rich)
    body = re.sub(r"<a [^>]*href=\"([^\"]+)\"[^>]*>(.*?)</a>", r"\2 \1", body, flags=re.S | re.I)
    body = re.sub(r"<(br|/p|/div|/li|/tr)[^>]*>", "\n", body, flags=re.I)
    return html.unescape(re.sub(r"<[^>]+>", "", body))


def parse_alert(body: str) -> list[dict]:
    """Extract {url, subreddit, title, snippet, keyword} for every Reddit link in an F5Bot email."""
    lines = [l.strip() for l in body.splitlines()]
    hits, keyword = [], ""
    for i, line in enumerate(lines):
        m = re.search(r"[Kk]eyword:?\s*[\"“']?([^\"”'\n]+)[\"”']?", line)
        if m and "http" not in line:
            keyword = m.group(1).strip()
        for url_match in POST_URL.finditer(line):
            url = url_match.group(0).rstrip(".,")
            before = line[:url_match.start()].strip(" -:|")
            title = before or next((lines[j] for j in range(i - 1, max(i - 4, -1), -1)
                                    if lines[j] and "http" not in lines[j]), "")
            snippet = " ".join(l for l in lines[i + 1:i + 4] if l and "http" not in l)[:400]
            hits.append({"url": url.split("?")[0], "subreddit": url_match.group(1),
                         "title": re.sub(r"^/?r/\w+/?:?\s*", "", title), "snippet": snippet, "keyword": keyword})
    return hits


def collect(s, cfg: dict, days: int = 7) -> list[Lead]:
    addr, pwd = os.getenv("EMAIL_ADDRESS"), os.getenv("EMAIL_APP_PASSWORD")
    if not (addr and pwd):
        print("[reddit-alerts] EMAIL_ADDRESS / EMAIL_APP_PASSWORD not set — skipping")
        return []
    host = os.getenv("EMAIL_IMAP_HOST") or "imap.gmail.com"
    since = (dt.date.today() - dt.timedelta(days=days)).strftime("%d-%b-%Y")
    print(f"[reddit-alerts] reading F5Bot emails since {since} from {host}")
    try:
        box = imaplib.IMAP4_SSL(host)
        box.login(addr, pwd)
    except (imaplib.IMAP4.error, OSError) as e:
        print(f"  ! email login failed: {e}. Check the address and app password.")
        return []

    leads, seen = [], set()
    try:
        box.select("INBOX", readonly=True)  # never marks your emails as read or moves them
        _, data = box.search(None, "FROM", f'"{SENDER}"', "SINCE", since)
        ids = data[0].split()
        print(f"[reddit-alerts] {len(ids)} alert emails")
        for num in ids:
            _, raw = box.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(raw[0][1])
            sent = email.utils.parsedate_to_datetime(msg["Date"]).date().isoformat() if msg["Date"] else ""
            subject = str(make_header(decode_header(msg.get("Subject", ""))))
            for hit in parse_alert(_text(msg)):
                if hit["url"] in seen:
                    continue
                seen.add(hit["url"])
                text = f"{hit['title']} {hit['snippet']}"
                intent = find_phrases(text, cfg["intent_phrases"])
                pain = find_phrases(text, cfg["pain_phrases"])
                if not intent:
                    continue  # a keyword match without a "we need help" signal is usually noise
                industry = guess_industry(f"{text} {hit['subreddit']}", cfg)
                leads.append(Lead(
                    source=f"Reddit r/{hit['subreddit']} (F5Bot)",
                    lead_type="Intent",
                    company=hit["title"][:80] or f"r/{hit['subreddit']} post",
                    industry_key=industry,
                    evidence_url=hit["url"],
                    pain_signals=intent + pain,
                    evidence_quote=f"{hit['title']} — {hit['snippet']}"[:400],
                    latest_bad=sent,
                    suggested_reply=REPLY_TEMPLATES.get(industry or "", DEFAULT_REPLY),
                    notes=f"Alert: {hit['keyword'] or subject}. Reply in the thread first; follow subreddit rules.",
                ))
    finally:
        try:
            box.logout()
        except Exception:
            pass
    print(f"[reddit-alerts] {len(leads)} posts with a clear need for support help")
    return leads
