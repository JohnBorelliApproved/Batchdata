import requests
from config import GOHIGHLEVEL_API_KEY

GOHIGHLEVEL_API_URL = "https://services.leadconnectorhq.com/"
API_VERSION = "2021-07-28"

def upsert_contact(contact_data):
    """
    Creates or updates a contact in GoHighLevel.
    """
    headers = {
        "Authorization": f"Bearer {GOHIGHLEVEL_API_KEY}",
        "Version": API_VERSION,
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    url = f"{GOHIGHLEVEL_API_URL}contacts/upsert"
    response = requests.post(url, json=contact_data, headers=headers)
    response.raise_for_status()
    return response.json()


def get_contacts_by_tag(tag, location_id):
    """
    Retrieves contacts from GoHighLevel that have a specific tag.
    """
    headers = {
        "Authorization": f"Bearer {GOHIGHLEVEL_API_KEY}",
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
