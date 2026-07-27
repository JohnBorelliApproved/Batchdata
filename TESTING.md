# API Endpoint Testing Guide

## Local Test Results (all passing)

| # | Endpoint | Method | Local? | Status |
|---|---|---|---|---|
| 1 | `/` | GET | Yes | ✅ 200 — renders UI |
| 2 | `/get-tags` | GET | Yes | ✅ 200 — returns GHL tags array |
| 3 | `/job-status/<job_id>` | GET | Yes | ✅ 200 known / 404 unknown |
| 4 | `/start-search` | POST | Partial* | ✅ 200 — job created, BatchData accepts request |
| 5 | `/batchdata-webhook/<job_id>` | POST | Yes (simulated) | ✅ 200 — parses payload, creates GHL contacts |
| 6 | `/batchdata-webhook-error/<job_id>` | POST | Yes (simulated) | ✅ 200 — logs error, sets job status |
| 7 | `/distribute-contacts` | POST | Yes | ✅ 200 — fetches by tag, upserts to destination |

*`/start-search` initiation works locally; BatchData's **callback** to your webhook URL requires the production server (public URL).

### Bugs Fixed During Testing

1. **`distribute_contacts` used wrong API key** — `get_contacts_by_tag` was falling back to `LEGACY_API_KEY` instead of `AGENCY_API_KEY`. Fixed in `main.py:65`.

2. **GHL contacts tag-filter broken** — `GET /contacts/?tags=...` returns 422. Fixed `get_contacts_by_tag` in `ghl_api.py` to use `POST /contacts/search` with `filters: [{field: "tags", operator: "contains", value: tag}]` and `pageLimit` cursor pagination.

3. **Upsert rejected search response fields** — `POST /contacts/search` returns computed fields (`address`, `businessName`, `additionalEmails`, etc.) that `POST /contacts/upsert` rejects. Fixed in `distribute_contacts`: strips read-only fields before upserting.

---

## Running Local Tests

```bash
# Start server
source venv/bin/activate
python main.py   # runs on :5002

# In another terminal — test all at once:
curl http://localhost:5002/get-tags
curl http://localhost:5002/job-status/fakeid

curl -X POST http://localhost:5002/start-search \
  -H "Content-Type: application/json" \
  -d '{"zip_codes": ["90210"]}'

# Full webhook pipeline (real BatchData data → GHL contacts)
python test_webhook_sim.py
```

---

## Endpoints That Require Remote Testing

Only one scenario cannot be fully tested locally:

**`POST /batchdata-webhook/<job_id>` called by BatchData itself**

BatchData needs to POST results to a **publicly reachable URL**. When running locally, the webhook URL embedded in the `/start-search` request points to `APP_BASE_URL` (e.g., `https://abeapi.com`), which is the production server — so BatchData calls the production server, not your laptop.

---

## Step-by-Step: Testing the Remote Async Webhook Flow

### Prerequisites

- Production server is running (`systemctl status zillow-ghl`)
- Nginx is proxying correctly (`curl https://abeapi.com/` returns the app UI)
- `.env` on the server has `APP_BASE_URL=https://abeapi.com` (or your domain)
- BatchData sandbox API key is set on the server

### Step 1 — SSH into the production server

```bash
ssh johnborelli@<server-ip>
cd /home/johnborelli/srv/ZillowGHLIntegration
```

### Step 2 — Tail the application log

Open a second terminal and tail logs so you see webhook delivery in real time:

```bash
ssh johnborelli@<server-ip>
sudo journalctl -u zillow-ghl -f
```

### Step 3 — Trigger a real async search

From your **local machine** (or via the app UI at `https://abeapi.com`):

```bash
curl -X POST https://abeapi.com/start-search \
  -H "Content-Type: application/json" \
  -d '{"zip_codes": ["90210"]}'
```

Save the returned `job_id`:
```
{"job_id": "abc-123-...", "batchdata_request_id": "...", "status": "pending"}
```

### Step 4 — Poll job status until BatchData delivers the webhook

BatchData sandbox typically responds within 30–120 seconds.

```bash
# Replace <job_id> with the value from Step 3
watch -n 10 'curl -s https://abeapi.com/job-status/<job_id>'
```

Expected progression:
- `"status": "pending"` — BatchData is processing
- `"status": "complete", "created": N, "errors": 0` — webhook received and GHL contacts created

### Step 5 — Verify the webhook log on the server

```bash
ls -lt /home/johnborelli/srv/ZillowGHLIntegration/webhook_logs/
cat /home/johnborelli/srv/ZillowGHLIntegration/webhook_logs/webhook_<job_id>.json | head -50
```

### Step 6 — Verify contacts in GHL

Log into GoHighLevel → agency sub-account → Contacts. Filter by tag `batchdata-import`. You should see the newly created contacts from the 90210 search.

### Step 7 — Test the error webhook path (optional)

Use a deliberately invalid search to trigger the error callback:

```bash
# An impossible zip code should trigger BatchData's error webhook
curl -X POST https://abeapi.com/start-search \
  -H "Content-Type: application/json" \
  -d '{"zip_codes": ["00000"]}'
```

Then check:
```bash
curl https://abeapi.com/job-status/<job_id>
# Expect: {"status": "error", ...}
ls webhook_logs/webhook_error_<job_id>.json   # on server
```

### Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Job stays `pending` forever | BatchData can't reach `APP_BASE_URL` | Check Nginx config, confirm `https://abeapi.com` is publicly reachable |
| `errors > 0` in job status | GHL upsert failures | Check `journalctl -u zillow-ghl` for the specific contact that failed |
| `webhook_<id>.json` never created | Webhook never delivered | Check BatchData dashboard → request status for that `batchdata_request_id` |
| `/start-search` returns 500 | Bad API key or BatchData sandbox not configured | Check `BATCHDATA_SANDBOX_API_KEY` in `/home/johnborelli/srv/ZillowGHLIntegration/.env` |
