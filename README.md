# OptiFlowCX Lead Finder

Finds brands whose customers are publicly complaining about unreachable or slow support, plus
business owners who are asking for support help. Leads are scored, matched to the closest
[OptiFlowCX portfolio](https://optiflowcx.com/portfolio) case study and written to a Google Sheet.

## Target industries (from the portfolio)

| Industry | Proof point | What we sell them |
|---|---|---|
| E-commerce & DTC | Silksilky: 1 → 6 agents, 24/7, rating 3.4 → 4.4 | WISMO, returns, refunds, exchanges in Shopify + helpdesk |
| Consumer technology | Yarbo: 3 → 15 agents, 24/7 chat/email/phone, L1 → L2 | Pre-sales + technical after-sales |
| 3D printing & hardware | Creality 3D: 4 → 14 agents, email → chat → phone | Technical support that keeps pace with weekly product changes |
| Logistics & delivery | SwiftX: 3 → 6 agents, 90–100 calls/agent/day | Package-status and dispatch call teams |
| Med spas, dental, aesthetic clinics | AI Voice Receptionist + GHL workflows | Never-miss-a-call booking, after-hours coverage |

Edit `config/icp.yaml` to change industries, subreddits, Trustpilot/Yelp categories, pain phrases or scoring.

## Sources

| Source | How | Lead type |
|---|---|---|
| **Trustpilot** | Walks ICP category pages, keeps businesses with TrustScore ≤ 3.5 and 30–20k reviews, then reads their latest 1–2★ reviews for support-pain phrases and checks whether they reply. Also re-checks every domain in `config/watchlist.txt`. Data comes from the page's embedded `__NEXT_DATA__` JSON, so no browser is needed. | Pain |
| **Reddit** | Searches ICP subreddits. In owner communities (r/shopify, r/ecommerce, r/smallbusiness, r/Dentistry…) it looks for *intent* ("outsource customer support", "missed calls", "24/7 support"). In customer communities (r/robotvacuums, r/3Dprinting, r/ebikes…) it looks for complaints and extracts the brand. | Intent + Pain |
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

## Seed leads
`data/seed_leads.xlsx` and `data/seed_leads.csv` hold 33 hand-researched leads from September 2026
Trustpilot and Yelp complaints, across all five industries. Their quotes are summaries of public
reviews, so open the Evidence URL before you reach out. Creality is left out because it is already a client.

## Why custom code rather than an existing repo
The open-source Trustpilot, Yelp and Reddit scrapers on GitHub each cover one site and return raw
reviews. None of them filter for ICP, score leads or write to a sheet. The paid scrapers (Apify
actors and similar) cost money for each run. This project is about 600 lines, uses the official
Reddit and Yelp APIs plus Trustpilot's public JSON, and runs free on GitHub Actions.

## Outreach etiquette
* Reddit **intent** leads: add something useful in the thread before you DM. Don't cold-pitch in comment threads, because most subreddits ban it.
* **Pain** leads: email the company, not the reviewers. Open with one of its own public reviews and the matching case study, e.g. *"Saw customers waiting 2+ weeks for replies on Trustpilot. We took Silksilky from a 3.4 to a 4.4 Google rating by running 24/7 support…"*
* Respect each site's terms and rate limits. The defaults pace requests politely.
