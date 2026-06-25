# Project Todo

## Done

- [x] Flask app scaffold (`main.py`, `config.py`)
- [x] Environment variable loading via `python-dotenv` (`config.py`)
- [x] BatchData async search endpoint (`POST /start-search`) — sends request to BatchData with webhook URLs embedded
- [x] BatchData webhook receiver (`POST /batchdata-webhook/<job_id>`) — logs raw payload to `webhook_logs/`
- [x] BatchData error webhook receiver (`POST /batchdata-webhook-error/<job_id>`) — logs error payload
- [x] GHL upsert contact helper (`ghl_api.upsert_contact`)
- [x] GHL get contacts by tag helper (`ghl_api.get_contacts_by_tag`)
- [x] GHL get tags helper (`ghl_api.get_tags`) — pulls tags from agency location
- [x] `/get-tags` endpoint — feeds tags dropdown in the UI
- [x] `/distribute-contacts` endpoint — copies tagged contacts from agency sub-account to destination sub-account
- [x] Two-form UI (`templates/index.html`) — Step 1: search, Step 2: distribute
- [x] JS form handling (`static/script.js`) — zip/city mutual exclusion, tag dropdown population, form submissions
- [x] Basic CSS styling (`static/style.css`)
- [x] Gunicorn systemd service file (`zillow-ghl.service`)
- [x] Nginx config (`nginx.conf`)
- [x] Deploy script (`deploy.sh`)
- [x] `requirements.txt` with Flask, dotenv, requests, gunicorn

---

## Remaining

### Critical — core feature gap

- [ ] **Parse BatchData webhook payload** (`main.py:89`) — webhook currently only logs to disk; it needs to extract property records from the payload and create GHL contacts in the agency sub-account
- [ ] **Map BatchData property fields → GHL contact fields** — define which BatchData fields (address, owner name, phone, email, etc.) map to which GHL contact fields; this drives the parser above
- [ ] **Add a tag to newly created contacts** — when contacts are created from BatchData results, apply a consistent tag (e.g. `batchdata-import` or date-stamped) so the agency owner can find and segment them in Step 2

### Search UX — async result flow

- [ ] **Job status tracking** — `/start-search` returns a `job_id` but the UI shows a static "pending" message with no way to know when it's done; store job state (pending/complete/error) server-side (file, SQLite, or in-memory dict)
- [ ] **`GET /job-status/<job_id>` endpoint** — let the frontend poll for completion
- [ ] **Frontend polling** — after search is initiated, poll `/job-status/<job_id>` every 30–60 seconds and update the UI when complete (the original spec says 5-minute polling; pick an interval that fits the UI context)
- [ ] **Owner notification on completion** — send an email or GHL message/SMS to the agency owner when results are processed (step 3 from original spec); needs a notification mechanism (email via SMTP/SendGrid, or GHL conversation API)

### Distribute form — UI bug

- [ ] **`source_location_id` field is missing from the HTML** — `script.js:72` reads `#source_location_id` but there is no such input in `index.html`; the distribute form will always send `undefined` for this value

### Data quality / edge cases

- [ ] **BatchData pagination** — the search result payload may return paginated results; the webhook handler needs to handle multi-page responses or ensure BatchData is configured to return all results in one call
- [ ] **GHL contact pagination** — `get_contacts_by_tag` uses a single GET with no pagination; GHL caps results at 100 per page; add pagination loop for large contact sets
- [ ] **Duplicate detection** — if the same search is run twice, contacts will be upserted again; verify that GHL upsert deduplicates on email/phone or add a guard

### Config / security

- [ ] **`.env.example` file** — doesn't exist yet (referenced in `CLAUDE.md`); create it with placeholder values for all five env vars
- [ ] **Validate `BATCHDATA_API_KEY` and `AGENCY_API_KEY` on startup** — app currently starts fine with missing keys and only fails at request time; add a startup check with a clear error message

### Testing

- [ ] **Test BatchData webhook parsing** — write a test that feeds a sample BatchData payload through the webhook handler and asserts GHL contacts are created correctly
- [ ] **Test distribute-contacts pagination** — mock a GHL response with >100 contacts and verify all pages are fetched
- [ ] **Test zip/city mutual exclusion** in the search payload builder

### Polish / nice-to-have

- [ ] **Response container feedback** — currently shows raw JSON; consider a human-readable success/error message in the UI
- [ ] **Loading state on buttons** — disable submit buttons and show a spinner while requests are in flight
- [ ] **Input validation** — enforce zip code format (5 digits) and state abbreviation (2 letters) on the frontend before submitting
