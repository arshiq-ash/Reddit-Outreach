"""Shared helpers: config, HTTP session, lead model, text signals."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = os.getenv(
    "LEADGEN_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36",
)

SHEET_COLUMNS = [
    "Lead ID", "Date Found", "Source", "Lead Type", "Company", "Website", "Industry",
    "Rating", "Review Count", "Negative Reviews Replied %", "Pain Signals", "Evidence Quote",
    "Evidence URL", "Lead Score", "Priority", "Matching Case Study", "Suggested Pitch",
    "Contact Email", "Contact Phone", "Location", "Status", "Notes",
]


def load_config(path: str | Path | None = None) -> dict:
    with open(path or ROOT / "config" / "icp.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


def get(s: requests.Session, url: str, *, params=None, headers=None, tries: int = 3, delay: float = 1.5):
    """GET with polite pacing and exponential backoff on 429/5xx. Returns Response or None."""
    for attempt in range(tries):
        try:
            r = s.get(url, params=params, headers=headers, timeout=25)
        except requests.RequestException as e:
            print(f"  ! {url}: {e}")
            r = None
        if r is not None and r.status_code == 200:
            time.sleep(delay)
            return r
        if r is not None and r.status_code not in (429, 500, 502, 503, 504):
            print(f"  ! {url}: HTTP {r.status_code}")
            return None
        time.sleep(delay * 2 ** (attempt + 1))
    return None


def next_data(html: str) -> dict | None:
    """Extract the __NEXT_DATA__ JSON blob embedded in Next.js pages (Trustpilot)."""
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1)) if m else None


def find_phrases(text: str, phrases: list[str]) -> list[str]:
    t = (text or "").lower()
    return [p for p in phrases if re.search(r"\b" + re.escape(p) + r"\b", t)]


def guess_industry(text: str, cfg: dict, default: str | None = None) -> str | None:
    t = (text or "").lower()
    best, hits = default, 0
    for key, ind in cfg["industries"].items():
        n = sum(1 for k in ind.get("keywords", []) if k in t)
        if n > hits:
            best, hits = key, n
    return best


def clean_domain(url_or_domain: str | None) -> str:
    if not url_or_domain:
        return ""
    d = re.sub(r"^https?://", "", url_or_domain.strip().lower()).split("/")[0]
    return d[4:] if d.startswith("www.") else d


def today() -> str:
    return dt.date.today().isoformat()


@dataclass
class Lead:
    source: str
    lead_type: str                 # "Pain" (customers complaining) or "Intent" (owner seeking help)
    company: str
    industry_key: str | None
    evidence_url: str
    website: str = ""
    rating: float | None = None
    review_count: int | None = None
    reply_rate: float | None = None
    pain_signals: list[str] = field(default_factory=list)
    evidence_quote: str = ""
    location: str = ""
    contact_email: str = ""
    contact_phone: str = ""
    score: int = 0
    notes: str = ""
    date_found: str = field(default_factory=today)

    @property
    def key(self) -> str:
        basis = clean_domain(self.website) or self.company.lower().strip() or self.evidence_url
        return hashlib.sha1(f"{self.source}|{basis}".encode()).hexdigest()[:10]

    def to_row(self, cfg: dict) -> dict:
        ind = cfg["industries"].get(self.industry_key or "", {})
        priority = "Hot" if self.score >= 70 else "Warm" if self.score >= 45 else "Cold"
        return {
            "Lead ID": self.key,
            "Date Found": self.date_found,
            "Source": self.source,
            "Lead Type": self.lead_type,
            "Company": self.company,
            "Website": self.website,
            "Industry": ind.get("label", ""),
            "Rating": "" if self.rating is None else round(self.rating, 1),
            "Review Count": "" if self.review_count is None else self.review_count,
            "Negative Reviews Replied %": "" if self.reply_rate is None else round(self.reply_rate * 100),
            "Pain Signals": ", ".join(dict.fromkeys(self.pain_signals)),
            "Evidence Quote": (self.evidence_quote or "")[:400],
            "Evidence URL": self.evidence_url,
            "Lead Score": self.score,
            "Priority": priority,
            "Matching Case Study": ind.get("case_study", ""),
            "Suggested Pitch": ind.get("pitch", ""),
            "Contact Email": self.contact_email,
            "Contact Phone": self.contact_phone,
            "Location": self.location,
            "Status": "New",
            "Notes": self.notes,
        }

    def as_dict(self) -> dict:
        return asdict(self)
