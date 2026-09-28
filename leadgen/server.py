"""Local lead-finder app: python -m leadgen.server [--port 8000] [--daily 07:30]

Runs on your own computer so Trustpilot is fetched over your normal connection (cloud servers
such as GitHub Actions get HTTP 403). Reddit and Yelp go through their official APIs with your
keys. Listens on 127.0.0.1 only; nothing is exposed to the network.
"""
from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import io
import json
import os
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .common import ENV_KEYS, ROOT, STATS, load_config, load_env, save_env, session
from .pipeline import LEAD_SOURCES, SEED_FILES, Options, run
from .scoring import score
from .sources import trustpilot

UI = Path(__file__).with_name("ui.html")
OUT = ROOT / "output" / "leads"


class Job:
    """The single background run (one at a time), with its captured log."""

    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.started = self.finished = None
        self.log: list[str] = []
        self.blocked: list[str] = []
        self.stats: dict = {}
        self.error = ""
        self.summary = ""

    def start(self, opts: Options) -> bool:
        with self.lock:
            if self.running:
                return False
            self.running, self.error, self.summary = True, "", ""
            self.blocked, self.stats, self.log = [], {}, []
            self.started, self.finished = dt.datetime.now().isoformat(timespec="seconds"), None
        threading.Thread(target=self._work, args=(opts,), daemon=True).start()
        return True

    def _work(self, opts: Options) -> None:
        sink = _LogSink(self.log)
        try:
            with contextlib.redirect_stdout(sink):
                result = run(opts)
            self.blocked, self.stats = result.blocked, result.stats
            hot = sum(r.get("Priority") == "Hot" for r in result.rows)
            self.summary = f"{len(result.rows)} leads ({hot} hot)" + (
                f", sheet updated: {result.sheet_url}" if result.sheet_url else "")
        except Exception as e:  # surface the failure in the UI instead of killing the thread silently
            self.error = f"{type(e).__name__}: {e}"
            self.log.append(traceback.format_exc())
        finally:
            self.running = False
            self.finished = dt.datetime.now().isoformat(timespec="seconds")

    def status(self) -> dict:
        return {"running": self.running, "started": self.started, "finished": self.finished,
                "log": self.log[-400:], "blocked": self.blocked, "stats": self.stats,
                "error": self.error, "summary": self.summary}


class _LogSink(io.TextIOBase):
    """stdout replacement that keeps complete lines for the UI and echoes to the terminal."""

    def __init__(self, lines: list[str]):
        self.lines, self.buf = lines, ""

    def write(self, text: str) -> int:
        sys.__stdout__.write(text)
        self.buf += text
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            self.lines.append(line)
        return len(text)


JOB = Job()


def read_leads() -> list[dict]:
    """Latest run's leads; before the first run, the researched seed leads."""
    paths = [Path(str(OUT) + ".csv")]
    if not paths[0].exists():
        paths = [p for p in SEED_FILES if p.exists()]
    rows = []
    for path in paths:
        with open(path, encoding="utf-8") as f:
            rows += list(csv.DictReader(f))
    return rows


def key_status() -> dict:
    return {k: bool(os.getenv(k)) for k in ENV_KEYS}


def options_from(body: dict) -> Options:
    sources = {s for s in body.get("sources", LEAD_SOURCES) if s in LEAD_SOURCES}
    return Options(
        sources=sources,
        sheet_id=os.getenv("GOOGLE_SHEET_ID") if body.get("google_sheet") else None,
        out=str(OUT),
        tp_pages=max(1, min(int(body.get("tp_pages", 3)), 20)),
        reddit_time=body.get("reddit_time", "year"),
        enrich=bool(body.get("enrich", True)),
        include_seed=bool(body.get("include_seed", True)),
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "LeadFinder/1.0"

    # --- helpers -------------------------------------------------------------------------------
    def _local_only(self) -> bool:
        """Reject requests whose Host isn't this machine (guards against DNS rebinding)."""
        host = (self.headers.get("Host") or "").split(":")[0]
        if host in ("localhost", "127.0.0.1"):
            return True
        self._json({"error": "local access only"}, 403)
        return False

    def _json(self, data, code: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict | None:
        # JSON-only POSTs can't be sent cross-site without a CORS preflight, which we never grant.
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            self._json({"error": "expected application/json"}, 415)
            return None
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self._json({"error": "invalid JSON"}, 400)
            return None

    def log_message(self, fmt, *args):  # keep the terminal for run output, not access logs
        pass

    # --- routes --------------------------------------------------------------------------------
    def do_GET(self):
        if not self._local_only():
            return
        url = urlparse(self.path)
        if url.path == "/":
            body = UI.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/api/status":
            self._json({**JOB.status(), "keys": key_status()})
        elif url.path == "/api/leads":
            self._json(read_leads())
        elif url.path == "/api/trustpilot":
            domain = (parse_qs(url.query).get("domain") or [""])[0].strip()
            if not domain:
                return self._json({"error": "domain is required"}, 400)
            if "." not in domain:
                return self._json({"domain": domain, "found": False, "note":
                                   f"Enter the company's website, e.g. {domain}.com, not just its name."})
            cfg = load_config()
            before = dict(STATS.get("www.trustpilot.com", {}))
            lead = trustpilot.analyze_domain(session(), domain, cfg)
            after = STATS.get("www.trustpilot.com", {})
            grew = lambda k: after.get(k, 0) > before.get(k, 0)  # noqa: E731
            if not lead:
                if grew("blocked"):
                    note = ("Trustpilot refused this computer (HTTP 403). Turn off any VPN and try again; "
                            "if it persists, Trustpilot is blocking your connection.")
                elif grew("error") and not grew("ok"):
                    note = "Couldn't reach Trustpilot. Check your internet connection; the terminal shows the error."
                elif grew("notfound") and not grew("ok"):
                    note = (f"No Trustpilot page for {domain}. Check the spelling, or search the company on "
                            "trustpilot.com and use the domain shown in its page address.")
                else:
                    note = "Found on Trustpilot, but fewer than 5 bad reviews in the last 6 months."
                return self._json({"domain": domain, "found": False, "note": note})
            lead.score = score(lead, cfg)
            self._json({"domain": domain, "found": True, "lead": lead.to_row(cfg)})
        elif url.path in ("/download/leads.xlsx", "/download/leads.csv"):
            path = Path(str(OUT) + Path(url.path).suffix)
            if not path.exists():
                return self._json({"error": "no results yet: run the finder first"}, 404)
            data = path.read_bytes()
            ctype = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                     if path.suffix == ".xlsx" else "text/csv")
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition", f'attachment; filename="leads_{dt.date.today()}{path.suffix}"')
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        if not self._local_only():
            return
        body = self._body()
        if body is None:
            return
        path = urlparse(self.path).path
        if path == "/api/run":
            if JOB.start(options_from(body)):
                self._json({"started": True})
            else:
                self._json({"error": "a run is already in progress"}, 409)
        elif path == "/api/settings":
            save_env({k: v for k, v in body.items() if k in ENV_KEYS and isinstance(v, str) and v.strip()})
            self._json({"keys": key_status()})
        else:
            self._json({"error": "not found"}, 404)


def _daily(at: str) -> None:
    """Start a full run every day at HH:MM local time while the app is open."""
    hh, mm = (int(x) for x in at.split(":"))
    while True:
        now = dt.datetime.now()
        nxt = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if nxt <= now:
            nxt += dt.timedelta(days=1)
        time.sleep((nxt - now).total_seconds())
        print(f"[daily] starting scheduled run ({at})")
        # Sources that work from a normal computer: F5Bot alert emails and the Yelp API.
        JOB.start(Options(sources={"reddit_alerts", "yelp"}, out=str(OUT), include_seed=True,
                          sheet_id=os.getenv("GOOGLE_SHEET_ID")))


def _every(hours: float) -> None:
    """Run now, then every N hours while the app is open."""
    while True:
        print(f"[auto] starting scheduled run (every {hours:g}h)")
        JOB.start(Options(sources={"reddit_alerts", "yelp"}, out=str(OUT), include_seed=True,
                          sheet_id=os.getenv("GOOGLE_SHEET_ID")))
        time.sleep(hours * 3600)


def main() -> None:
    ap = argparse.ArgumentParser(description="Local lead-finder app.")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--daily", metavar="HH:MM", help="also run automatically every day at this local time")
    ap.add_argument("--every", type=float, metavar="HOURS", help="run now and then every N hours while the app is open")
    ap.add_argument("--no-browser", action="store_true", help="don't open the page automatically")
    args = ap.parse_args()
    load_env()
    if args.daily:
        threading.Thread(target=_daily, args=(args.daily,), daemon=True).start()
    if args.every:
        threading.Thread(target=_every, args=(max(args.every, 0.5),), daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Lead Finder running at http://localhost:{args.port}  (Ctrl+C to stop)"
          + (f"; daily run at {args.daily}" if args.daily else "")
          + (f"; auto-run every {args.every:g}h" if args.every else ""))
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(f"http://localhost:{args.port}",)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
