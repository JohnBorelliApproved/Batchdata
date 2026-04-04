import requests
from config import BATCHDATA_API_KEY

BATCHDATA_API_URL = "https://api.batchdata.com/api/v1"

def search_properties(zip_codes=None, city=None, state=None, listing_type='For Sale By Owner'):
    """
    Initiates a property search in Batchdata.
    """
    headers = {
        "Authorization": f"Bearer {BATCHDATA_API_KEY}",
        "Content-Type": "application/json"
    }

    search_criteria = {
        "or": [
            {"in": {"property.location.zipCode": zip_codes}} if zip_codes else {},
            {"and": [
                {"eq": {"property.location.city": city}},
                {"eq": {"property.location.state": state}}
            ]} if city and state else {}
        ]
    }

    payload = {
        "searchCriteria": search_criteria,
        "listingType": listing_type
    }

    # Clean up empty dicts from the payload
    payload['searchCriteria']['or'] = [i for i in payload['searchCriteria']['or'] if i]
    if not payload['searchCriteria']['or']:
        del payload['searchCriteria']['or']


    response = requests.post(f"{BATCHDATA_API_URL}/property/search", json=payload, headers=headers)
    response.raise_for_status()
    return response.json()

def get_search_status(job_id):
    """
    Gets the status of a Batchdata search job.
    """
    headers = {
        "Authorization": f"Bearer {BATCHDATA_API_KEY}"
    }
    response = requests.get(f"{BATCHDATA_API_URL}/jobs/{job_id}", headers=headers)
    response.raise_for_status()
    return response.json()
