import requests
from config import GOHIGHLEVEL_API_KEY as LEGACY_API_KEY, AGENCY_API_KEY, AGENCY_LOCATION_ID

GOHIGHLEVEL_API_URL = "https://services.leadconnectorhq.com/"
API_VERSION = "2021-07-28"

def upsert_contact(contact_data, api_key=None):
    """
    Creates or updates a contact in GoHighLevel.
    Uses the provided api_key, or falls back to the main agency key.
    """
    key_to_use = api_key if api_key else LEGACY_API_KEY
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Version": API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    url = f"{GOHIGHLEVEL_API_URL}contacts/upsert"
    response = requests.post(url, json=contact_data, headers=headers)
    if not response.ok:
        raise Exception(f"GHL upsert failed {response.status_code}: {response.text}")
    return response.json()


def get_contacts_by_tag(tag, location_id, api_key=None):
    """
    Retrieves all contacts from GoHighLevel that have a specific tag.
    Handles pagination automatically — GHL caps each page at 100 results.
    """
    key_to_use = api_key if api_key else LEGACY_API_KEY
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Version": API_VERSION,
        "Accept": "application/json"
    }

    url = f"{GOHIGHLEVEL_API_URL}contacts/"
    all_contacts = []
    params = {
        "locationId": location_id,
        "tags": tag,
        "limit": 100,
        "startAfter": None,
        "startAfterId": None,
    }

    while True:
        # Remove None params so they don't get sent as the string "None"
        active_params = {k: v for k, v in params.items() if v is not None}
        response = requests.get(url, headers=headers, params=active_params)
        response.raise_for_status()
        body = response.json()

        contacts = body.get('contacts', [])
        all_contacts.extend(contacts)

        meta = body.get('meta', {})
        next_page_url = meta.get('nextPageUrl')
        if not next_page_url or len(contacts) < 100:
            break

        params['startAfter'] = meta.get('startAfter')
        params['startAfterId'] = meta.get('startAfterId')

    return all_contacts


def get_tags():
    """
    Retrieves all tags for the agency location defined in .env.
    Uses AGENCY_LOCATION_ID and AGENCY_API_KEY.
    """
    headers = {
        "Authorization": f"Bearer {AGENCY_API_KEY}",
        "Version": API_VERSION,
        "Accept": "application/json"
    }

    url = f"{GOHIGHLEVEL_API_URL}locations/{AGENCY_LOCATION_ID}/tags"
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json().get('tags', [])
