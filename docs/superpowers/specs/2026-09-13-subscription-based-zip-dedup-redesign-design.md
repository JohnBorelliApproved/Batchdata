# Subscription-Based Zipcode Dedup Redesign

Date: 2026-09-13
Status: Approved (pending agency review Monday)

## Background

Today's app is a single-agency tool: an agency owner manually triggers a
BatchData search into their own GHL agency location, then manually clicks
"distribute" to copy tagged contacts into one client sub-account at a time.
There is no persistence beyond an in-memory `job_store` (lost on restart,
unsafe under multiple workers) and no concept of per-client entitlement.

The agency's business model has changed: they now resell FSBO lead delivery
to their own clients, each of whom has a GHL sub-account and a subscription
tier that caps how many zipcodes they can track. Multiple clients may want
the same zipcode, and the agency does not want to pay BatchData for the same
zip more than once per day. Clients should see fresh listings the day they
subscribe, with no backfill of stale historical data, and should keep
receiving new listings for their subscribed zips every day after that.

## Goals

- Each client self-serves their own zipcode subscriptions (up to their quota)
  through the existing iframed UI, without agency staff manually running
  searches or copying contacts.
- A given zipcode is searched via BatchData at most once per day, no matter
  how many clients are subscribed to it.
- Search results are delivered automatically: every property contact (with a
  valid phone number) is created in the agency's own GHL location (their
  master record of everything they've paid to search) and in every
  currently-subscribed client's sub-account, in parallel.
- New subscribers get only what's found from their subscribe date forward —
  no historical backfill of potentially-stale FSBO listings.
- A daily automated job keeps all active zipcodes moving forward without
  agency or client involvement.

## Non-goals (this phase)

- OAuth/Marketplace app integration for automatic sub-account credential
  provisioning. This phase uses self-serve API key entry; the data model is
  built so OAuth can be swapped in later without a redesign.
- Agency-facing reporting/dashboard UI on top of the activity log. Logging is
  structured for future reporting but no UI is built this phase.
- True BatchData incremental/delta search filtering. BatchData's support for
  a request-side "only listings since date X" filter could not be confirmed
  (current `batchdata_api.py` has no such parameter, and BatchData's public
  docs were not machine-readable). Cross-day dedup is done on our side
  instead (see Data Flow).

## Data Model & Storage

**Client entitlement** — one contact record per client, stored in the
agency's own GHL location (single place the agency manages all clients):

| Field | Type | Purpose |
|---|---|---|
| `subscribed_zipcodes` | GHL `LARGE_TEXT` custom field, comma-separated zips | the zips this client currently receives |
| `zip_quota` | number custom field | max zips allowed by their subscription tier |
| `sub_account_location_id` | text custom field | where their leads get delivered |
| `sub_account_api_key` | text custom field (self-serve entered) | credential used to write to their sub-account |

> **2026-09-27 update:** `subscribed_zipcodes` was originally specced as GHL
> `TEXTBOX_LIST`, but implementation found that type requires a predefined,
> fixed set of named text-input slots (`textBoxListOptions`) — it isn't a
> variable-length growable list, and GHL rejects creating one without those
> options. Changed to `LARGE_TEXT` holding a comma-separated zip string,
> which has no slot cap. See `entitlements.py` and `progress.md`.

**Zip ledger** — local SQLite table, backend bookkeeping only, never surfaced
in GHL:

```
zip_ledger(zipcode TEXT PRIMARY KEY, last_searched_at DATE, last_batchdata_request_id TEXT)
delivered_properties(zipcode TEXT, property_key TEXT, delivered_at DATE, PRIMARY KEY (zipcode, property_key))
activity_log(id INTEGER PRIMARY KEY, client_id TEXT, event_type TEXT, zipcode TEXT, detail TEXT, created_at DATETIME)
```

`property_key` is BatchData's property id if present, else a fallback hash of
normalized address + owner name — used for cross-day "already delivered"
dedup (see Data Flow).

**Delivered leads** — no shared "master copy" outside GHL. Every property
contact is written directly to the agency location and to each currently
subscribed client's sub-account at delivery time, reusing the existing
`_translate_custom_fields` remap logic and Zillow-note copy from
`distribute_contacts`.

## Client-Facing Flow

**One-time setup** (per sub-account): a new iframe screen where the client
pastes their own GHL sub-account API key. Stored on their entitlement
contact's `sub_account_api_key` field. Validated at entry time with a
lightweight test call (`get_custom_fields`) so a bad key is caught
immediately, not discovered later during delivery.

**Requesting zipcodes**: client's iframe UI lets them add zips up to their
quota.

1. Look up their entitlement contact by `sub_account_location_id` (from
   iframe context, same as today).
2. Reject if `current subscribed count + requested new zips > zip_quota`,
   with a clear UI error — no partial silent acceptance.
3. Add accepted zips to `subscribed_zipcodes`.
4. For each newly added zip: check `zip_ledger`. If not searched today yet,
   trigger an immediate BatchData search for it now (same-day results, no
   backfill of history). If already searched today (another client's request
   triggered it first), no action — this client joins tomorrow's cron run.

## Daily Automation

Runs once daily via server-side cron (systemd timer, matching current
deployment):

1. Build the **active zip set**: every zip with ≥1 subscribed client, whose
   `zip_ledger.last_searched_at` isn't already today.
2. For each active zip, run one full BatchData search (same shape as today's
   `search_properties` call — no unverified delta parameter assumed).
3. On webhook completion for that zip: filter out any property whose
   `property_key` already exists in `delivered_properties` for that zip
   (cross-day dedup), then filter to phone-having contacts only (existing
   `skipped_no_phone` logic, unchanged).
4. Re-look-up every client **currently** subscribed to this zip (not cached
   from step 1, so someone who unsubscribed mid-run doesn't get billed leads
   they no longer pay for) and write each surviving contact into the agency
   location and every subscribed client's sub-account, in parallel. Record
   each new property into `delivered_properties`.
5. Update `zip_ledger`: `last_searched_at = today`,
   `last_batchdata_request_id = <id>`.
6. Reconciliation pass: for every entitlement contact, recompute
   `len(subscribed_zipcodes)` vs `zip_quota`; log a warning for any client
   over quota (e.g. someone hand-edited the custom field in GHL directly,
   bypassing the app's own check). No auto-correction — flagged for the
   agency to resolve manually.

## Changes to Existing Code

- `/start-search` and its manual iframe form: replaced by the self-serve
  zip-subscribe flow above as the primary client path. May remain as an
  internal/admin-only tool for ad-hoc searches.
- `/distribute-contacts`: replaced by automatic parallel delivery baked into
  the search pipeline. Underlying logic (`_translate_custom_fields`, field
  remapping, Zillow-note copy) is reused, just triggered automatically
  instead of by a manual button.
- `batchdata_webhook` / `_process_webhook`: still the landing point for
  BatchData results, now fans out to every currently-subscribed client's
  sub-account (via the ledger lookup) instead of only ever writing to the
  agency location.
- `job_store` (in-memory dict): replaced by the SQLite-backed ledger, so
  state survives restarts and is queryable by the daily cron job.
- New: entitlement lookup/update helpers, self-serve API key setup screen +
  validation, quota enforcement, daily cron entrypoint script.

## Error Handling

- Per-client delivery isolation: a failure writing to one client's
  sub-account (bad/revoked key, GHL rate limit) is caught and logged without
  blocking delivery to the agency location or any other subscribed client —
  same isolation pattern already used by the note-copy logic today.
- Quota violations return a clear rejection to the client's UI, not a 500.
- BatchData error webhooks mark the ledger row so the zip is retried on the
  next daily run instead of silently going stale.
- Self-serve API key validated at entry time (see Client-Facing Flow).
- Reconciliation drift is logged, not auto-corrected.

## Testing

- Unit tests: quota enforcement (reject over-limit, allow at-limit), ledger
  same-day dedup (second same-day request for an already-searched zip
  doesn't trigger a new BatchData call), cross-day dedup (already-delivered
  `property_key`s are filtered out), phone-required filter (unchanged
  behavior, still covered), per-client delivery isolation (one failure
  doesn't block others).
- Integration-style test extending the existing `replay_webhook.py` dev tool
  to simulate a multi-client fan-out from one BatchData payload.
- Manual smoke test of the daily cron entrypoint against a test sub-account
  before the first production run.

## Activity Logging

Structured `activity_log` table (see Data Model) with one row per key event:
zip search triggered (and why — self-serve vs. daily cron), zip search
skipped (already done today), contacts delivered per client (count,
success/fail), quota rejections, reconciliation drift findings. No reporting
UI this phase — schema is structured now so a future admin view doesn't
require a rework.

## Deferred to a Later Phase

- GHL Marketplace OAuth app: replaces self-serve API key entry with an
  install-and-go flow — client clicks install in their sub-account, GHL
  hands us `location_id` + access/refresh tokens automatically. Data model
  already isolates "how we got this client's credentials" behind the
  entitlement contact's fields, so this is a swap-in, not a rework.
- Agency-facing reporting UI on top of `activity_log`.
- True BatchData incremental/delta search filtering, if confirmed available.
