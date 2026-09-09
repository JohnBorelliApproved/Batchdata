# Amenities Custom Field + Zillow Link Note — Design

> **Updated 2026-09-09:** the original single "Property Amenities" field was
> never populated in production — the agency location has no field by that name.
> Reworked into five real fields (see below), the Zillow note link now opens in
> a new tab, and `/distribute-contacts` carries the fields across locations.

## Purpose 

When a BatchData webhook creates GHL contacts from FSBO property search results, each
contact should also get:

1. Property detail custom fields — `Square Footage`, `Bathrooms`, `Floors`,
   `Number of Rooms`, and a multi-line `Local Ammenities` field for the remaining
   signals (pool, HOA, lot size, year built, garage, free-text features).
2. A note on the contact containing a clickable Zillow link for the property.

The custom fields (item 1) are set on the webhook flow **and** carried across by
`/distribute-contacts`. The Zillow note (item 2) is webhook-only — notes are
separate GHL objects and are not copied during distribution; adding that is a
possible follow-up.

## Zillow Link

BatchData does not return a reliable Zillow listing URL for FSBO/off-market
properties (confirmed by inspecting sample webhook payloads — `listing.listingUrl`
exists but is often absent or points to a non-Zillow source). Instead, the link is
constructed from the property address using Zillow's public address-search URL
pattern:

```
https://www.zillow.com/homes/<street>-<city>-<state>-<zip>_rb/
```

Address components are taken from `prop['address']` (`street`, `city`, `state`,
`zip`), URL-slugified (spaces → `-`, non-alphanumeric characters stripped). This
always produces a usable link; it lands on Zillow's search results for that
address rather than a guaranteed single listing page.

## Property Custom Fields

Five custom fields must already exist on the agency location (manual one-time
setup in the GHL UI, not created by the app). Names are matched **exactly** —
note "Local Ammenities" is spelled that way in GHL:

| GHL field | GHL type | BatchData source |
|---|---|---|
| `Local Ammenities` | multi-line text | see amenities list below |
| `Square Footage` | text | `building.livingAreaSquareFeet`, else `building.totalBuildingAreaSquareFeet` (sent as a string) |
| `Bathrooms` | number | `building.bathroomCount` |
| `Floors` | number | `building.storyCount` |
| `Number of Rooms` | number | `building.bedroomCount` — BatchData returns no total room count for these FSBO records; bedroom count is the client-agreed stand-in |

- Field IDs are resolved by name at runtime via `GET /locations/{id}/customFields`,
  once per webhook invocation. Any field not found is logged by name and skipped
  for that run; the others still populate.
- Per contact, only fields with a resolved ID **and** a non-empty value are sent.
  If none qualify, `customFields` is omitted from the payload entirely.

### `Local Ammenities` contents

Covers only signals that don't have their own field. Each present item is one
line, `"\n"`-joined; absent items are skipped (no placeholders):

- `building.pool` — BatchData sends this as free text (e.g. `"Pool - Yes"`), no
  `poolCode` key. Any value that isn't an explicit "no" → `"Pool"`.
- `quickLists.hasHoa` → `"HOA"`
- `lot.lotSizeAcres` → `"X acre lot"`
- `building.yearBuilt` → `"Built YYYY"`
- `building.garageParkingSpaceCount` → `"X-car garage"` (not seen in current
  sandbox payloads, kept for when it appears)
- `building.features` (free-text list) → each string on its own line

## Data Flow — webhook (`_process_webhook` in `main.py`)

1. Before the per-property loop: `_resolve_custom_field_ids(AGENCY_LOCATION_ID,
   AGENCY_API_KEY, PROPERTY_CUSTOM_FIELD_NAMES)` returns `{name: id}` for the
   fields that exist. Missing names are logged; a total failure logs a warning
   and proceeds with an empty map (contacts still get created, without fields).
2. `_build_property_custom_fields(prop, field_map)` builds the `customFields`
   list; `_build_contacts_from_property(prop, field_map)` attaches it when
   non-empty.
3. After `upsert_contact(...)` succeeds, `create_note(contact_id,
   f'<a href="{zillow_url}" target="_blank" rel="noopener">Zillow Property Page</a>',
   api_key=AGENCY_API_KEY)`. GHL note bodies render the anchor as clickable
   "Zillow Property Page" text; `target="_blank"` opens it in a new tab so it
   doesn't navigate the GHL iframe away.

## Data Flow — distribution (`distribute_contacts` in `main.py`)

Custom-field IDs are per-location, so source `customFields` can't be copied
verbatim. For each contact the route:

1. Builds `{source id → fieldKey}` and `{fieldKey → dest id}` maps once, from
   `get_custom_fields` on the source (agency key) and destination (sub-account
   key) locations.
2. Calls `get_contact(source_id, AGENCY_API_KEY)` — `/contacts/search` doesn't
   reliably hydrate `customFields` values, but the single-contact GET does.
3. `_translate_custom_fields(...)` rewrites each entry to the destination's ID
   via the shared fieldKey; entries with no destination counterpart or an empty
   value are dropped.

> Distribution is synchronous and makes ~2 sequential GHL calls per contact
> (GET + upsert). Acceptable for current batch sizes; revisit (e.g. background
> thread, as the webhook already does) if large tag lists become common.

## New GHL API Functions (`ghl_api.py`)

- `get_custom_fields(location_id, api_key=None)` — `GET /locations/{location_id}/customFields`,
  returns the list of custom field objects (each with `id`, `name`, `fieldKey`, etc.).
- `create_note(contact_id, body, api_key=None)` — `POST /contacts/{contact_id}/notes`
  with `{"body": body}`.
- `get_contact(contact_id, api_key=None)` — `GET /contacts/{contact_id}`, returns
  the full contact including populated `customFields`.

## Error Handling

- Custom field lookup failure → log warning, proceed with an empty field map for
  the whole webhook call (not per-contact retried). Individual fields missing by
  name are logged and skipped; the rest still populate.
- Note creation failure → caught per-contact alongside the existing upsert
  try/except in the loop, logged, and counted toward the existing `errors` counter.
  A failed note does not block other contacts in the batch or fail the whole webhook
  request.
- Amenity extraction never raises — missing fields are skipped via `.get()` with
  defaults, consistent with existing `_build_contacts_from_property` patterns.

## Testing

- `test_property_fields.py` — offline assertions (no network) for
  `_build_amenities`, `_build_property_custom_fields`, `_translate_custom_fields`,
  and `_build_zillow_url` against saved payloads in `webhook_logs/`.
- Manual end-to-end (webhook): POST a property payload to the local
  `/batchdata-webhook/<job_id>`, then `get_contact` the created record and confirm
  all five fields are set and the note anchor carries `target="_blank"`. Verified
  2026-09-09 against the agency location.
- Distribution end-to-end is **not yet verified** — the `TEST_SUBACCOUNT_API_KEY`
  in `.env` is an expired token. Needs a valid destination sub-account key to
  confirm the fieldKey remap round-trips.
