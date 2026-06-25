# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Flask web app that bridges **BatchData** (property search API) and **GoHighLevel (GHL)** (CRM). It lets an agency owner:
1. Search for FSBO property listings via BatchData and store them as GHL contacts in the agency sub-account.
2. Distribute those contact records (by tag) from the agency sub-account to a target GHL sub-account.

The UI is a two-form page designed to be iframed inside GoHighLevel custom menu items.

## Running Locally

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in your keys
python main.py        # runs on port 5002
```

## Environment Variables (`.env`)

| Variable | Purpose |
|---|---|
| `BATCHDATA_API_KEY` | BatchData API bearer token |
| `GOHIGHLEVEL_API_KEY` | Legacy/fallback GHL API key |
| `AGENCY_API_KEY` | GHL agency-level key (used for tag lookups) |
| `AGENCY_LOCATION_ID` | GHL location ID of the agency's own sub-account |
| `APP_BASE_URL` | Public base URL for BatchData webhook callbacks (default: `https://abeapi.com`) |

## Production Deployment

Served via **Gunicorn** behind **Nginx** on a Linux host. Key files:
- `zillow-ghl.service` — systemd unit file (runs 3 Gunicorn workers, binds to a Unix socket)
- `nginx.conf` — proxies HTTP → the socket, serves `/static` directly
- `deploy.sh` — bootstraps Python/Nginx and installs dependencies into `venv/`

Project path on server: `/home/johnborelli/srv/ZillowGHLIntegration`

## Architecture

```
main.py          Flask app + all route handlers
config.py        Loads env vars via python-dotenv
batchdata_api.py BatchData property search (async job model)
ghl_api.py       GoHighLevel contacts/tags API wrappers
templates/       Jinja2 (index.html — single page, two forms)
static/          script.js, style.css
```

### Key Data Flow

**Property Search (async):**
1. `POST /start-search` → `batchdata_api.search_properties()` generates a UUID job ID, sends async search request to BatchData with webhook URLs embedded.
2. BatchData calls `POST /batchdata-webhook/<job_id>` when done (or `/batchdata-webhook-error/<job_id>` on failure). Raw payloads are written to `webhook_logs/`.
3. **TODO:** The webhook handler currently just logs the payload — it needs to parse results and create GHL contacts.

**Contact Distribution:**
1. `POST /distribute-contacts` accepts `source_location_id`, `location_id`, `sub_account_api_key`, and `tag`.
2. Fetches contacts from the source GHL location by tag using `AGENCY_API_KEY`.
3. Strips identity fields (`id`, `locationId`, `lastUpdated`, `dateAdded`) and upserts each contact into the destination sub-account using the provided `sub_account_api_key`.

### GHL API Notes

- Base URL: `https://services.leadconnectorhq.com/`
- API version header: `Version: 2021-07-28`
- Tag lookup uses `AGENCY_API_KEY` + `AGENCY_LOCATION_ID` (agency-scoped).
- Contact upsert/read to sub-accounts uses the sub-account's own API key, passed at request time.
- `GOHIGHLEVEL_API_KEY` is a legacy fallback key kept for backward compatibility.

### BatchData API Notes

- Base URL: `https://api.batchdata.com/api/v1`
- Searches are **asynchronous** — the app registers webhook URLs and BatchData POSTs results back.
- Default listing type: `For Sale By Owner`.
- Search criteria supports zip codes (array) OR city+state — not both simultaneously.
