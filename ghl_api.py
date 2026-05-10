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
    response.raise_for_status()
    return response.json()


def get_contacts_by_tag(tag, location_id, api_key=None):
    """
    Retrieves contacts from GoHighLevel that have a specific tag.
    Uses the provided api_key, or falls back to the main agency key.
    """
    key_to_use = api_key if api_key else LEGACY_API_KEY
    headers = {
        "Authorization": f"Bearer {key_to_use}",
        "Version": API_VERSION,
        "Accept": "application/json"
    }

    params = {
        "locationId": location_id,
        "tags": tag
    }

    url = f"{GOHIGHLEVEL_API_URL}contacts/"
    response = requests.get(url, headers=headers, params=params)
    response.raise_for_status()
    return response.json().get('contacts', [])


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
