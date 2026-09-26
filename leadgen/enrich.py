"""Find a public contact email/phone on a lead's own website (home, /contact, /pages/contact)."""
from __future__ import annotations

import re

from .common import clean_domain, get

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}")
PREFERRED = ("support", "help", "care", "service", "hello", "info", "contact")
JUNK = ("example.", "sentry", "wixpress", "@2x", ".png", ".jpg", "domain.com", "email.com")


def enrich(s, lead) -> None:
    domain = clean_domain(lead.website)
    if not domain or (lead.contact_email and lead.contact_phone):
        return
    emails, phones = [], []
    for path in ("", "/contact", "/pages/contact", "/contact-us", "/pages/contact-us"):
        r = get(s, f"https://{domain}{path}", tries=1, delay=0.5)
        if not r:
            continue
        emails += [e for e in EMAIL_RE.findall(r.text) if not any(j in e.lower() for j in JUNK)]
        phones += PHONE_RE.findall(r.text)
        if emails:
            break
    if emails and not lead.contact_email:
        emails = list(dict.fromkeys(e.lower() for e in emails))
        lead.contact_email = next((e for e in emails if e.split("@")[0] in PREFERRED), emails[0])
    if phones and not lead.contact_phone:
        lead.contact_phone = phones[0].strip()
