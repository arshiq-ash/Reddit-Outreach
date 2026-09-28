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
    "Recent Volume", "Bad Reviews (Last 6 Mo)", "Bad Reviews (Prior 6 Mo)", "Trend", "Latest Bad Review",
    "Rating", "Review Count", "Negative Reviews Replied %", "Pain Signals", "Evidence Quote",
    "Evidence URL", "Lead Score", "Priority", "Matching Case Study", "Suggested Pitch", "Suggested Reply",
    "Contact Email", "Contact Phone", "Location", "Status", "Notes",
]


ENV_KEYS = ["REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "YELP_API_KEY",
            "GOOGLE_SHEET_ID", "GOOGLE_APPLICATION_CREDENTIALS",
            "EMAIL_ADDRESS", "EMAIL_APP_PASSWORD", "EMAIL_IMAP_HOST"]
ENV_FILE = ROOT / ".env"


def load_env(path: Path = ENV_FILE) -> None:
    """Load KEY=value lines from .env into os.environ (real environment variables win)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def save_env(updates: dict[str, str], path: Path = ENV_FILE) -> None:
    """Write known keys to .env, keeping existing values for keys not being updated."""
    current = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                current[k.strip()] = v.strip()
    for k, v in updates.items():
        if k in ENV_KEYS and v is not None:
            current[k] = v.strip()
            os.environ[k] = v.strip()
    path.write_text("".join(f"{k}={v}\n" for k, v in current.items() if v), encoding="utf-8")


def load_config(path: str | Path | None = None) -> dict:
    with open(path or ROOT / "config" / "icp.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
    return s


# Per-host request outcomes, so a run can tell "no leads" apart from "blocked".
STATS: dict[str, dict[str, int]] = {}


def _record(url: str, outcome: str) -> None:
    host = _host(url)
    STATS.setdefault(host, {}).setdefault(outcome, 0)
    STATS[host][outcome] += 1


def _host(url: str) -> str:
    return re.sub(r"^https?://", "", url).split("/")[0]


def blocked_hosts() -> list[str]:
    """Hosts that refused (401/403/429) or never answered a single request this run."""
    return [h for h, c in STATS.items() if not c.get("ok") and (c.get("blocked") or c.get("error"))]


def _given_up(url: str, limit: int = 5) -> bool:
    """After `limit` failures and no success, stop hitting a host for the rest of the run."""
    c = STATS.get(_host(url), {})
    return not c.get("ok") and c.get("blocked", 0) + c.get("error", 0) >= limit


def get(s: requests.Session, url: str, *, params=None, headers=None, tries: int = 3, delay: float = 1.5):
    """GET with polite pacing and exponential backoff on 429/5xx. Returns Response or None."""
    if _given_up(url):
        _record(url, "skipped")
        return None
    for attempt in range(tries):
        try:
            r = s.get(url, params=params, headers=headers, timeout=(10, 25))
        except requests.RequestException as e:
            # Connection-level failure: don't retry here; _given_up() stops the host after 5 of these.
            print(f"  ! {url}: {type(e).__name__}")
            _record(url, "error")
            return None
        if r is not None and r.status_code == 200:
            _record(url, "ok")
            time.sleep(delay)
            return r
        if r is not None and r.status_code not in (429, 500, 502, 503, 504):
            _record(url, {401: "blocked", 403: "blocked", 404: "notfound"}.get(r.status_code, "error"))
            print(f"  ! {url}: HTTP {r.status_code}")
            return None
        time.sleep(delay * 2 ** (attempt + 1))
    _record(url, "blocked" if r is not None and r.status_code == 429 else "error")
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


def months_ago(n: int) -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=round(30.4 * n))


def parse_date(value) -> dt.datetime | None:
    """ISO string or unix timestamp → aware datetime."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, dt.timezone.utc)
    try:
        d = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def volume_tier(bad_6m: int | None) -> str:
    if bad_6m is None:
        return ""
    return "High" if bad_6m >= 50 else "Medium" if bad_6m >= 10 else "Low"


def trend_label(recent: int | None, prior: int | None) -> str:
    if recent is None or prior is None:
        return ""
    if prior == 0:
        return "New / rising" if recent else "Flat"
    change = (recent - prior) / prior
    return f"Rising (+{change:.0%})" if change >= 0.2 else f"Falling ({change:.0%})" if change <= -0.2 else "Steady"


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
    bad_6m: int | None = None          # 1–2★ reviews / complaint posts in the last 6 months (key indicator)
    bad_prev_6m: int | None = None     # same count for the 6 months before that, for the trend
    latest_bad: str = ""               # ISO date of the newest bad review
    count_basis: str = ""              # "exact" (scraped) or "sample" (seen via web search)
    suggested_reply: str = ""          # drafted reply for Reddit intent posts (posted by hand)
    volume_tier: str = ""              # High / Medium / Low; derived from bad_6m when not set by hand
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
        basis = clean_domain(self.website) or (self.evidence_url if self.lead_type == "Intent" else "") \
            or self.company.lower().strip() or self.evidence_url
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
            "Recent Volume": self.volume_tier or volume_tier(self.bad_6m),
            "Bad Reviews (Last 6 Mo)": "" if self.bad_6m is None else (
                self.bad_6m if self.count_basis != "sample" else f"{self.bad_6m}+"),
            "Bad Reviews (Prior 6 Mo)": "" if self.bad_prev_6m is None else self.bad_prev_6m,
            "Trend": trend_label(self.bad_6m, self.bad_prev_6m),
            "Latest Bad Review": self.latest_bad,
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
            "Suggested Reply": self.suggested_reply,
            "Contact Email": self.contact_email,
            "Contact Phone": self.contact_phone,
            "Location": self.location,
            "Status": "New",
            "Notes": self.notes,
        }

    def as_dict(self) -> dict:
        return asdict(self)
