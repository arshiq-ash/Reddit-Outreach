# OptiFlowCX Lead Finder

Finds brands whose customers are publicly complaining about unreachable or slow support, plus
business owners who are asking for support help. Leads are scored, matched to the closest
[OptiFlowCX portfolio](https://optiflowcx.com/portfolio) case study and written to a Google Sheet.

## Quick start: the Lead Finder app (runs on your computer)

Trustpilot and Reddit block cloud servers such as GitHub Actions, so the reliable way to collect
leads is the local app. It runs on your own computer and your normal internet connection.

1. Install Python 3.10+ from python.org. On Windows, tick "Add Python to PATH".
2. Download this repo: **Code → Download ZIP**, then unzip it.
3. Double-click **`start.bat`** on Windows or **`start.command`** on Mac. The first start installs
   everything, then opens **http://localhost:8000** in your browser.
4. Optional: open **Settings: API keys** in the app and paste your Reddit and Yelp keys. They are
   saved to `.env` on your computer only. Without keys, those two sources are skipped.
5. Press **Find leads**. Watch the run log. When it finishes, the table fills in and
   **Download .xlsx** gives you the sheet with the Leads and Watchlist tabs.

**Check one company** reads a single company's Trustpilot reviews, e.g. `uniuni.com`, and shows its
6-month bad-review count and trend.

To run it every morning, keep the app open and start it with `start.bat --daily 07:30`
(or `./start.command --daily 07:30`).
The app only listens on `127.0.0.1`, so nobody else on your network can reach it. Turn off any VPN
if Trustpilot shows as blocked.

## Target industries (from the portfolio)

| Industry | Proof point | What we sell them |
|---|---|---|
| E-commerce & DTC | Silksilky: 1 → 6 agents, 24/7, rating 3.4 → 4.4 | WISMO, returns, refunds, exchanges in Shopify + helpdesk |
| Consumer technology | Yarbo: 3 → 15 agents, 24/7 chat/email/phone, L1 → L2 | Pre-sales + technical after-sales |
| 3D printing & hardware | Creality 3D: 4 → 14 agents, email → chat → phone | Technical support that keeps pace with weekly product changes |
| Logistics & delivery | SwiftX: 3 → 6 agents, 90–100 calls/agent/day | Package-status and dispatch call teams |
| Med spas, dental, aesthetic clinics | AI Voice Receptionist + GHL workflows | Never-miss-a-call booking, after-hours coverage |

Edit `config/icp.yaml` to change industries, subreddits, Trustpilot/Yelp categories, pain phrases or scoring.

## Key indicator: bad reviews in the last 6 months

A lead's rank depends mainly on **how many 1–2★ reviews or complaint posts it received in the last
6 months**, not on its lifetime rating. A 4-star brand whose support has recently collapsed is a
better prospect than a 1-star brand whose complaints are two years old.

| Column | Meaning |
|---|---|
| Recent Volume | **High** is 50 or more bad reviews in 6 months, **Medium** is 10–49 and **Low** is under 10. Low leads go to the *Watchlist* tab |
| Bad Reviews (Last 6 Mo) | Exact count from the scrape. `N+` means a sample (Yelp's API shows only 3 reviews) |
| Bad Reviews (Prior 6 Mo), Trend | The count for the 6 months before that, and whether complaints are Rising, Steady or Falling |
| Latest Bad Review | Date of the newest complaint |

Recent volume is worth up to 55 of the 100 score points, plus 10 if complaints are rising. The rest
comes from the complaints being about support (not the product), the company not replying to
reviews, its rating, its size and ICP fit. Trustpilot businesses with fewer than 5 bad reviews in
6 months are dropped. Tune `min_bad_reviews_6m` and `bad_review_tiers` in `config/icp.yaml`.

## Sources

| Source | How | Lead type |
|---|---|---|
| **Trustpilot** | Walks ICP category pages, keeps businesses rated 4.2 or lower with 30–20k reviews, then pages through their 1–2★ reviews newest-first to count the last 6 months against the prior 6. It also checks the complaints for support-pain phrases and whether the company replies. Also re-checks every domain in `config/watchlist.txt`. Data comes from the page's embedded `__NEXT_DATA__` JSON, so no browser is needed. | Pain |
| **Reddit** | Searches the past year in ICP subreddits. In owner communities (r/shopify, r/ecommerce, r/smallbusiness, r/Dentistry…) it looks for *intent* posts from the last 6 months ("outsource customer support", "missed calls", "24/7 support"). In customer communities (r/robotvacuums, r/3Dprinting, r/ebikes…) it counts complaint posts per brand, split into the last 6 months and the prior 6. | Intent + Pain |
| **Yelp** | Yelp Fusion API: med spas, dentists and aesthetic clinics in 10 US metros rated ≤ 3.5, with review excerpts scanned for phone and booking complaints. | Pain |

Each lead is scored from 0 to 100 on rating, the number and type of pain signals, company size
(growing brands rather than enterprises), whether the company answers its reviews, and ICP fit.
It also gets a contact email and phone from the company's own website.
**Hot** is 70 or more, **Warm** is 45–69 and **Cold** is below 45.

### Sheet columns
`Lead ID, Date Found, Source, Lead Type, Company, Website, Industry, Rating, Review Count, Negative Reviews Replied %, Pain Signals, Evidence Quote, Evidence URL, Lead Score, Priority, Matching Case Study, Suggested Pitch, Contact Email, Contact Phone, Location, Status, Notes`

Re-runs **upsert** rows by Lead ID. `Status`, `Notes` and `Date Found` keep your manual edits.

## Setup (≈15 minutes, all free)

1. **Google Sheet**
   * In Google Cloud Console, create a project, enable the **Google Sheets API** and **Google Drive API**, then create a **service account** and download its JSON key.
   * Create a blank Google Sheet and share it with the service account's `client_email` as **Editor**.
   * The Sheet ID is the long string in its URL: `docs.google.com/spreadsheets/d/<SHEET_ID>/edit`.
2. **Reddit API** (strongly recommended, because anonymous requests are throttled or blocked from cloud IPs): at https://www.reddit.com/prefs/apps, create an app of type **script** and note the client ID and secret.
3. **Yelp API** (needed for med spas and dental): https://www.yelp.com/developers, then create an app and copy the API key.
4. In this repo, open **Settings → Secrets and variables → Actions** and add
   `GOOGLE_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_JSON` (paste the whole key file), `REDDIT_CLIENT_ID`,
   `REDDIT_CLIENT_SECRET`, `YELP_API_KEY`.
5. **Actions → Lead generation → Run workflow.** After that it runs every day on its own. Every run also uploads the CSV and XLSX as a build artifact.

### Run locally
```bash
pip install -r requirements.txt
export GOOGLE_SHEET_ID=... GOOGLE_APPLICATION_CREDENTIALS=service_account.json
export REDDIT_CLIENT_ID=... REDDIT_CLIENT_SECRET=... YELP_API_KEY=...
python -m leadgen --include-seed                  # all sources → sheet + output/leads.{csv,xlsx}
python -m leadgen --sources trustpilot --tp-pages 5
python -m leadgen --sources reddit --reddit-time week
```
Without `GOOGLE_SHEET_ID`, it writes only `output/leads.csv` and `output/leads.xlsx`. You can import
either one into Google Sheets with **File → Import**.

## If a source is blocked

The run fails with `Every request to … was refused` when a site blocks the machine it runs on.
Other sources, and the sheet, are still written.

| Source | What blocks it | Fix |
|---|---|---|
| Reddit | Anonymous requests from cloud IPs (GitHub Actions) get HTTP 403 | Add `REDDIT_CLIENT_ID` / `REDDIT_CLIENT_SECRET`, since the official API is allowed from anywhere |
| Yelp | No key | Add `YELP_API_KEY` |
| Trustpilot | Bot protection returns HTTP 403 to data-centre IPs, including GitHub Actions | Run it from a normal home or office connection (`python -m leadgen`), or route it through a scraping proxy |

## Seed leads (researched 26 Sep 2026)
`data/seed_leads.xlsx` holds 19 leads with **High** or **Medium** complaint volume in the last 6
months. Its *Watchlist* tab (`data/seed_watchlist.csv`) holds 12 more with low or undated recent
volume. Web search shows dated complaints and review totals but not exact counts per period, so
these leads carry a tier rather than a number. The first scheduled run replaces the tiers with exact
counts. To regenerate: `python scripts/build_seed_sheet.py`.

Leads dropped after the re-check:
* Electric Bike Company, which is in Chapter 7 bankruptcy.
* Urtopia, Anycubic, Coprint3d, Sovol and Wallke, whose 2026 reviews are mostly positive.
* DM Fashion, which has about 10 reviews in total.
* Allpowers, whose latest complaint is from January 2026.
* Creality and SILKSILKY, which are existing clients.

## Why custom code rather than an existing repo
The open-source Trustpilot, Yelp and Reddit scrapers on GitHub each cover one site and return raw
reviews. None of them filter for ICP, score leads or write to a sheet. The paid scrapers (Apify
actors and similar) cost money for each run. This project is about 600 lines, uses the official
Reddit and Yelp APIs plus Trustpilot's public JSON, and runs free on GitHub Actions.

## Outreach etiquette
* Reddit **intent** leads: add something useful in the thread before you DM. Don't cold-pitch in comment threads, because most subreddits ban it.
* **Pain** leads: email the company, not the reviewers. Open with one of its own public reviews and the matching case study, e.g. *"Saw customers waiting 2+ weeks for replies on Trustpilot. We took Silksilky from a 3.4 to a 4.4 Google rating by running 24/7 support…"*
* Respect each site's terms and rate limits. The defaults pace requests politely.
