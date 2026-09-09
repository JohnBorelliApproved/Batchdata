"""
Replay a saved BatchData webhook payload through the real `_process_webhook`
handler — no Flask server, and NO BatchData call (it reads a file you already
have), so replaying costs nothing on the BatchData side.

  ./venv/bin/python replay_webhook.py <payload.json> [--dry-run] [--limit N] [job_id]

--dry-run   Build the contacts and print exactly what WOULD be sent to GHL
            (including the customFields payload) without calling GHL at all.
            Zero side effects. Use this to see the Zillow fields being built.

Without --dry-run it hits GHL for real with AGENCY_API_KEY from .env and
creates/updates real contacts + notes. Safe to repeat: GHL upsert dedupes on
phone/email, so re-runs just update the same contacts.
"""
import json
import logging
import sys

import main

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


def install_dry_run_stubs():
    def fake_upsert(contact, api_key=None):
        print("\n--- UPSERT ---")
        print(json.dumps(contact, indent=2))
        handle = contact.get("phone") or contact.get("email") or "unknown"
        return {"contact": {"id": f"dry-{handle}"}}

    def fake_note(contact_id, body, api_key=None):
        print(f"--- NOTE on {contact_id} ---\n{body}")
        return {}

    main.upsert_contact = fake_upsert
    main.create_note = fake_note


def main_cli():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)

    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    limit = None
    if "--limit" in args:
        idx = args.index("--limit")
        limit = int(args[idx + 1])
        del args[idx:idx + 2]

    path = args[0]
    job_id = args[1] if len(args) > 1 else "local-replay"

    with open(path) as payload_file:
        data = json.load(payload_file)

    if limit is not None:
        props = data.get("results", {}).get("properties", [])
        data["results"]["properties"] = props[:limit]
        print(f"limiting to first {limit} of {len(props)} properties")

    if dry_run:
        install_dry_run_stubs()
        print("DRY RUN — no GHL calls will be made\n")

    main._process_webhook(job_id, data)
    print("\njob_store:", json.dumps(main.job_store.get(job_id), indent=2))


if __name__ == "__main__":
    main_cli()
