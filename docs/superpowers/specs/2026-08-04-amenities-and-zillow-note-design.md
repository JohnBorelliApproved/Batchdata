# Amenities Custom Field + Zillow Link Note — Design

## Purpose

When a BatchData webhook creates GHL contacts from FSBO property search results, each
contact should also get:

1. A multi-line custom field listing the property's amenities/benefits (bed/bath count,
   sqft, lot size, garage, pool, HOA, and any free-text building features like fireplace
   or solar panels).
2. A note on the contact containing a clickable Zillow link for the property.

This applies only to contacts created via the BatchData webhook flow
(`batchdata_webhook` in `main.py`). It does not apply to `/distribute-contacts` —
notes are separate GHL objects and are not currently copied during distribution;
extending distribution to carry notes is out of scope and can be a follow-up if wanted.

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

## Amenities Custom Field

- Field name in GHL: **"Property Amenities"**, type multi-line text. Must already
  exist on the agency location — this is a manual one-time setup step in the GHL UI,
  not created by the app.
- The app looks up the field's ID at runtime via `GET /locations/{id}/customFields`,
  matching by name. Looked up once per webhook invocation (not once per contact) and
  cached in memory for that call.
- Amenities are extracted from the BatchData property payload:
  - `building.bedroomCount` → "X bedrooms"
  - `building.bathroomCount` → "X bathrooms"
  - `building.livingAreaSquareFeet` → "X sq ft"
  - `lot.lotSizeAcres` → "X acre lot"
  - `building.garageParkingSpaceCount` → "X-car garage"
  - `building.pool` (present and not "N"/falsy pool code) → "Pool"
  - `quickLists.hasHoa` → "HOA"
  - `building.features` (list of free-text strings, e.g. "Fireplace", "Solar Panel",
    "Wine Cellar") → each appended as its own line
- Each present amenity becomes one line in the multi-line field value (`"\n"`-joined).
  Missing/absent fields are simply skipped — no placeholder text.
- If the resulting amenities list is empty, `customFields` is omitted from the
  contact payload entirely (not sent as an empty string).

## Data Flow Changes (`batchdata_webhook` in `main.py`)

1. Before the per-property loop: resolve the "Property Amenities" field ID once via
   `get_custom_fields(AGENCY_LOCATION_ID, AGENCY_API_KEY)`. If not found or the call
   fails, log a warning once and proceed with `field_id = None` for the rest of the
   webhook call (contacts still get created, just without the custom field).
2. `_build_contacts_from_property(prop, field_id)` is extended to attach
   `customFields: [{"id": field_id, "value": amenities_string}]` to each contact dict
   when `field_id` is set and amenities is non-empty.
3. After `upsert_contact(...)` succeeds, read the contact `id` from the response and
   call `create_note(contact_id, f'<a href="{zillow_url}">Zillow Property Page</a>',
   api_key=AGENCY_API_KEY)`. GHL note bodies render HTML, so the link shows as
   "Zillow Property Page" text rather than the raw URL.

## New GHL API Functions (`ghl_api.py`)

- `get_custom_fields(location_id, api_key=None)` — `GET /locations/{location_id}/customFields`,
  returns the list of custom field objects (each with `id`, `name`, etc.).
- `create_note(contact_id, body, api_key=None)` — `POST /contacts/{contact_id}/notes`
  with `{"body": body}`.

## Error Handling

- Custom field lookup failure → log warning, proceed without `customFields` for the
  whole webhook call (not per-contact retried).
- Note creation failure → caught per-contact alongside the existing upsert
  try/except in the loop, logged, and counted toward the existing `errors` counter.
  A failed note does not block other contacts in the batch or fail the whole webhook
  request.
- Amenity extraction never raises — missing fields are skipped via `.get()` with
  defaults, consistent with existing `_build_contacts_from_property` patterns.

## Testing

- Unit-style manual check: run `_build_zillow_url` and `_build_amenities` against a
  sample property dict from `webhook_logs/webhook_2a07cc58-3edc-4c53-a125-394431f3a40b.json`
  and inspect output.
- Manual end-to-end: trigger a real webhook against the BatchData sandbox (per
  existing project practice) and verify in GHL that the created contact has the
  "Property Amenities" custom field populated and a note with a working Zillow link.
