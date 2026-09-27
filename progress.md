# Progress

> Living document. Update this as tasks in `plan` below are completed. Don't let `todo.md` be the source of truth going forward — it's stale as of 2026-09-24 (see "Superseded" note).

Last updated: 2026-09-27 (zip ledger foundation)

## Where we are

The **single-agency MVP is done and working**: manual BatchData search → GHL contact creation with full field mapping → manual tag-based distribution to one client sub-account at a time. It's deployed and has been tested against production.

The **next phase is an approved architecture change** (`docs/superpowers/specs/2026-09-13-subscription-based-zip-dedup-redesign-design.md`, status: Approved, pending agency review) that turns this into a multi-client, self-serve, cron-driven product. No implementation has started on it yet — spec only.

## Done (verified against current code, not just todo.md)

- Flask scaffold, env var loading, Gunicorn/Nginx/systemd deploy — in production.
- `POST /start-search` → BatchData async search, `job_store` (in-memory dict) tracks state.
- `POST /batchdata-webhook/<job_id>` — **fully implemented**, not just logging: parses the payload, maps BatchData fields → GHL custom fields (`_build_property_custom_fields`, `_build_amenities`, `_build_zillow_url`), filters to phone-having contacts, tags new contacts (`batchdata-import`), creates GHL contacts + notes. (`main.py:404` `_process_webhook`)
- `GET /job-status/<job_id>` + frontend polling (`static/script.js:46` `pollJobStatus`) — already built, contra todo.md.
- `POST /distribute-contacts` — copies tagged contacts agency → client sub-account, strips read-only fields, remaps custom fields across locations (`_translate_custom_fields`).
- `source_location_id` input **exists** in `templates/index.html:28` and is wired in `script.js:92` — the todo.md bug report is stale; this is not broken.
- GHL contact pagination in `get_contacts_by_tag` (cursor-based, `ghl_api.py`) — handled.
- Custom field write-shape bug fixed: GHL requires `{id, field_value}` not `{id, value}` (commit `93c2c6c`; see [[reference_ghl_customfields_write_shape]] memory).
- Amenities/Zillow-note feature reworked to 5 real custom fields and confirmed working in production as of 2026-09-09 (spec updated same date).
- Dev tooling: `replay_webhook.py` (replay a saved payload through `_process_webhook`, `--dry-run` mode with no GHL side effects) and `ghl_diagnostics.py` (ad-hoc field/contact inspection).
- `test_property_fields.py` — all 9 offline unit tests pass (custom-field mapping, amenities detection, field auto-creation).
- **`/distribute-contacts` now auto-creates missing custom fields on the destination location** instead of silently dropping them (`_translate_custom_fields` in `main.py`, `create_custom_field` in `ghl_api.py`). Only recreates safe scalar dataTypes (`TEXT`, `LARGE_TEXT`, `NUMERICAL`, `PHONE`, `MONETORY`, `DATE`); picklist/option types (`SINGLE_OPTIONS`, etc.) are still skipped and logged since we don't replicate their option lists.
- **`/distribute-contacts` now copies the Zillow property-link note** to the destination contact when the source contact has one (`get_notes` in `ghl_api.py`). Best-effort — failures are logged, not fatal to the distribution run.

## Zip ledger foundation (2026-09-27)

Per the approved 2026-09-13 zip-dedup redesign spec, agency has signed off — this is Stage 1 (data model foundation) only. Plan: `docs/superpowers/plans/2026-09-27-zip-ledger-foundation.md`.

- **SQLite ledger** (`ledger.py`) — `zip_ledger`, `delivered_properties`, `activity_log` tables per the spec, verbatim schema. All read/write helpers offline-tested (`test_ledger.py`, 13 tests): same-day zip re-search overwrites instead of erroring, cross-day property dedup is a safe no-op on retry, activity logging accepts optional fields.
- **Entitlement custom fields** (`entitlements.py`) — `ensure_entitlement_fields()` idempotently creates the 4 client-entitlement fields (`subscribed_zipcodes`, `zip_quota`, `sub_account_location_id`, `sub_account_api_key`) on the agency's own GHL location, skipping ones that already exist, and skipping (logging, not raising) any single field that fails to create so one bad field doesn't block the other three. Offline-tested with mocked GHL calls (`test_entitlements.py`, 4 tests).
- Both are wired into `main.py` startup: `ledger.init_db()` unconditionally, `entitlements.ensure_entitlement_fields()` wrapped in try/except (skippable via `SKIP_STARTUP_PROVISIONING=1`, used by the test suite) so a GHL failure (bad token scope, outage) logs an error instead of crashing every Gunicorn worker at boot.
- **Fixed during final review**: a blank `LEDGER_DB_PATH=` in `.env.example` (as shipped from `cp .env.example .env`) previously caused `sqlite3.connect('')` to silently open an anonymous throwaway temp DB on every call — every ledger read/write would have appeared to work while persisting nothing. `config.py` now falls back on a blank env value (not just an absent one), and `ledger._connect` raises `ValueError` if the resolved path is still empty. `.env.example`'s `LEDGER_DB_PATH` line is now commented out rather than blank.
- **Fixed during final review**: `zillow-ghl.service` now runs Gunicorn with `--preload`, so the entitlement-field provisioning call in `main.py` runs once in the master process before forking 3 workers, instead of racing 3 processes to create the same missing fields independently (which could have created up to 4x duplicate fields with no uniqueness constraint on the GHL side to catch it).
- **Fixed during final review**: the offline test suite no longer makes a live GHL call. `main.py`'s startup provisioning is now gated behind `SKIP_STARTUP_PROVISIONING` (set by test files before importing `main`), tested in `test_main_startup.py` (2 tests).
- **Known issue, not yet resolved**: `AGENCY_API_KEY` currently returns 401 "not authorized for this scope" when creating a custom field — it can read custom fields but not create them. The entitlement fields have **not actually been created** in the real agency GHL location yet. Needs a token with `customFields.write` scope (or equivalent).
- **Open question flagged by review, not yet resolved**: `subscribed_zipcodes` is a GHL `TEXTBOX_LIST` field (per the spec), but `create_custom_field`'s bare `{name, dataType, model}` payload may not be sufficient for option-bearing types — this repo's own `_translate_custom_fields` already refuses to auto-create `SINGLE_OPTIONS`-style fields for the same reason. Once the 401 above is fixed, verify `subscribed_zipcodes` actually creates successfully against real GHL before the next plan (self-serve subscribe flow) depends on it; if it doesn't, either extend `create_custom_field` with the needed options payload or provision that one field by hand.
- **Deferred minors from review** (not fixed, no functional risk): field display names (`subscribed_zipcodes` etc.) don't match the location's existing Title Case custom-field naming convention; `entitlements.py`'s `created['id']` would raise a bare `KeyError` instead of a named error on an unexpected GHL response shape; no `PRAGMA journal_mode=WAL` on the SQLite connection yet (fine at current scale, worth revisiting once the daily cron does bulk writes alongside live web workers); `ledger.init_db()` failures don't include the resolved path in the error message.
- **Not started**: entitlement contact lookup/update by `sub_account_location_id`, the self-serve API-key-entry and zip-subscribe UI, quota enforcement, the daily cron entrypoint, webhook fan-out delivery, reconciliation. Each is a separate subsystem per the spec and needs its own plan.

## Known issues (found while re-indexing, not yet in todo.md)

- ~~`test_property_fields.py` broken~~ **Fixed 2026-09-24**: two calls to `_translate_custom_fields` were missing the `dst_location_id`/`dst_api_key` args added when the function grew field auto-creation, and the test runner only caught `AssertionError` so the first crash hid every test after it. That masked a second real bug: `test_translate_custom_fields_remaps_by_fieldkey`'s fixture passed `id -> fieldKey string` instead of `id -> field dict`. All 7 tests pass now.
- **`test_amenities_zillow.py` fails with 401** — not a code bug; `TEST_SUBACCOUNT_API_KEY` in `.env` is a dead/expired GHL token (see [[project_test_subaccount_key_expired]] memory). This test can't run until that key is refreshed.
- **`test_webhook_sim.py` was not run** — it makes a real, live paid call to BatchData's API. Don't run it casually; only run deliberately when you want to burn a real search credit for an end-to-end check.

## Not started — still real gaps in the current single-agency app

These survive from `todo.md` after verification against the code:

- **BatchData pagination** — no page-handling logic found in `batchdata_api.py`; unclear if BatchData even paginates this endpoint. Needs a docs check before writing code.
- **Duplicate detection** — relies entirely on GHL upsert's own dedup (email/phone); never explicitly verified.
- **Startup validation of `BATCHDATA_API_KEY` / `AGENCY_API_KEY`** — app still starts fine with missing keys and fails later at request time.
- **UI polish** — response container still shows raw JSON, no loading spinner/disabled-button state, no client-side zip/state format validation.
- **Owner notification on search completion** (email/SMS) — never built. **Likely moot**: the zip-dedup redesign replaces manual search-and-wait with automatic daily delivery, so this requirement may not carry forward. Confirm with the agency before building it.

## Not started — the zip-dedup redesign (the real next phase)

See `docs/superpowers/specs/2026-09-13-subscription-based-zip-dedup-redesign-design.md` for full detail. Nothing below is built yet:

- SQLite ledger (`zip_ledger`, `delivered_properties`, `activity_log`) — no DB file, no schema, no migration exists in the repo.
- Client entitlement custom fields on agency-location contacts (`subscribed_zipcodes`, `zip_quota`, `sub_account_location_id`, `sub_account_api_key`) — not created in GHL, no lookup/update helpers written.
- Self-serve API key entry screen + validation call — not built.
- Self-serve zip-subscribe UI + quota enforcement — not built.
- Same-day dedup on subscribe (check ledger before triggering an immediate search) — not built.
- Daily cron entrypoint (active-zip-set build, per-zip search, cross-day dedup, multi-client fan-out delivery, ledger update, reconciliation pass) — not built. No systemd timer exists yet (only `zillow-ghl.service` for the web app).
- Retirement/admin-gating of `/start-search` and `/distribute-contacts` as end-user-facing routes.
- Activity logging schema + writes at each key event.
- New unit + integration tests per the spec's Testing section.

## Unrelated side investigation in this repo (not part of the app roadmap)

- `docs/superpowers/specs/2026-08-06-ssr-seo-scrape-comparison-design.md` + matching plan — a standalone SEO-crawlability research tool (scrapes GHL AI Studio vs. HL Site Builder pages). Plan exists but **zero steps checked off** — not started, not blocking, not part of this app.

## Recommended next steps

1. ~~Fix the broken unit test~~ Done.
2. Get the agency's sign-off on the 2026-09-13 spec (still "pending agency review" per the spec's own header) before starting build — it changes the whole request model (self-serve, quota-capped, cron-driven) and touches billing-adjacent logic (per-zip BatchData cost control).
3. Once approved, start the redesign at its foundation: the SQLite ledger + entitlement custom fields (Stage 1 in the plan below) — everything else (subscribe flow, cron fan-out) depends on that data model existing first.
4. Decide whether the leftover single-agency polish items (pagination, startup validation, UI polish) are worth doing on the *old* flow, or should just be folded into the redesign build since several of those code paths (`/distribute-contacts`, manual polling) are being replaced anyway.
