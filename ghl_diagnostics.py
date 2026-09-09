"""
Ad-hoc GHL diagnostics. Run with the project venv so `requests` (a project
dep, needed for TLS cert bundling) is importable:

  ./venv/bin/python ghl_diagnostics.py <command> ...

Reads AGENCY_API_KEY / AGENCY_LOCATION_ID from the .env sitting next to this
file, so it works unchanged on the server (/var/www/html) and locally.

Usage:
  python3 ghl_diagnostics.py fields [contact|opportunity|all]
      List custom field definitions on the agency location (name, id, type, key).

  python3 ghl_diagnostics.py contacts [tag] [count]
      Recent contacts with a tag (default tag "batchdata-import", count 5).

  python3 ghl_diagnostics.py contact <contactId>
      Full contact record + its customFields + its notes.

  python3 ghl_diagnostics.py cf-test <contactId> <fieldId> <value>
      Upsert a single custom field value onto an existing contact using the
      GHL write shape {id, field_value}, then read it back. This is the
      "does field_value actually stick" probe.
"""
import json
import os
import sys

import requests

BASE_URL = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    values = {}
    try:
        with open(env_path) as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, raw = line.partition("=")
                values[key.strip()] = raw.strip().strip('"').strip("'")
    except FileNotFoundError:
        pass
    # Allow real environment to override the file.
    for key in ("AGENCY_API_KEY", "AGENCY_LOCATION_ID"):
        if os.environ.get(key):
            values[key] = os.environ[key]
    missing = [k for k in ("AGENCY_API_KEY", "AGENCY_LOCATION_ID") if not values.get(k)]
    if missing:
        sys.exit(f"Missing {', '.join(missing)} in {env_path} (or environment)")
    return values


ENV = load_env()


def request(method, path, body=None):
    headers = {
        "Authorization": f"Bearer {ENV['AGENCY_API_KEY']}",
        "Version": API_VERSION,
        "Accept": "application/json",
    }
    resp = requests.request(method, f"{BASE_URL}{path}", headers=headers, json=body, timeout=30)
    if not resp.ok:
        sys.exit(f"{method} {path} -> {resp.status_code}\n{resp.text}")
    return resp.json()


def cmd_fields(args):
    model = args[0] if args else "contact"
    body = request("GET", f"/locations/{ENV['AGENCY_LOCATION_ID']}/customFields?model={model}")
    fields = body.get("customFields", [])
    print(f"{len(fields)} custom field(s) on {ENV['AGENCY_LOCATION_ID']} (model={model}):\n")
    for field in fields:
        print(f"  {field.get('name')!r:32} type={field.get('dataType'):12} "
              f"key={field.get('fieldKey'):30} id={field.get('id')}")


def cmd_contacts(args):
    tag = args[0] if len(args) > 0 else "batchdata-import"
    count = int(args[1]) if len(args) > 1 else 5
    body = request("POST", "/contacts/search", {
        "locationId": ENV["AGENCY_LOCATION_ID"],
        "filters": [{"field": "tags", "operator": "contains", "value": tag}],
        "pageLimit": count,
        "sort": [{"field": "dateAdded", "direction": "desc"}],
    })
    contacts = body.get("contacts", [])
    print(f"tag={tag!r}  total={body.get('total')}  showing {len(contacts)}:\n")
    for contact in contacts:
        print(f"  id={contact.get('id')}  {contact.get('firstName')} {contact.get('lastName')}"
              f"  phone={contact.get('phone')}  added={contact.get('dateAdded')}")


def _dump_contact(contact):
    print(f"name:   {contact.get('firstName')} {contact.get('lastName')}")
    print(f"phone:  {contact.get('phone')}")
    print(f"email:  {contact.get('email')}")
    print(f"updated:{contact.get('dateUpdated')}")
    print("customFields:")
    print(json.dumps(contact.get("customFields"), indent=2))


def cmd_contact(args):
    if not args:
        sys.exit("usage: contact <contactId>")
    contact_id = args[0]
    contact = request("GET", f"/contacts/{contact_id}").get("contact", {})
    _dump_contact(contact)
    notes = request("GET", f"/contacts/{contact_id}/notes").get("notes", [])
    print(f"\nnotes ({len(notes)}):")
    for note in notes:
        print(f"  {note.get('body')!r}")


def cmd_cf_test(args):
    if len(args) < 3:
        sys.exit("usage: cf-test <contactId> <fieldId> <value>")
    contact_id, field_id, value = args[0], args[1], " ".join(args[2:])

    contact = request("GET", f"/contacts/{contact_id}").get("contact", {})
    dedupe = {}
    if contact.get("phone"):
        dedupe["phone"] = contact["phone"]
    elif contact.get("email"):
        dedupe["email"] = contact["email"]
    else:
        sys.exit("contact has no phone or email to upsert against")

    print(f"upserting field {field_id} = {value!r} via {{id, field_value}} ...")
    request("POST", "/contacts/upsert", {
        "locationId": ENV["AGENCY_LOCATION_ID"],
        **dedupe,
        "customFields": [{"id": field_id, "field_value": value}],
    })

    print("reading back:\n")
    after = request("GET", f"/contacts/{contact_id}").get("contact", {})
    _dump_contact(after)

    hit = next((f for f in (after.get("customFields") or []) if f.get("id") == field_id), None)
    print()
    if hit and str(hit.get("value")) == str(value):
        print(f"RESULT: field_value STUCK — {field_id} now reads {hit.get('value')!r}")
    else:
        print(f"RESULT: field_value did NOT stick (got {hit!r}). "
              f"upsert likely ignores customFields on this path.")


COMMANDS = {
    "fields": cmd_fields,
    "contacts": cmd_contacts,
    "contact": cmd_contact,
    "cf-test": cmd_cf_test,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        sys.exit(1)
    COMMANDS[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
