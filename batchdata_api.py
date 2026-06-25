import uuid
import requests
from config import BATCHDATA_API_KEY, APP_BASE_URL

BATCHDATA_API_URL = "https://api.batchdata.com/api/v1"

def search_properties(zip_codes=None, city=None, state=None, listing_type='For Sale By Owner'):
    """
    Initiates an async property search in BatchData.
    Generates a UUID job ID, embeds it in the webhook URLs, and returns it.
    BatchData will POST results to /batchdata-webhook/<job_id> when complete.
    """
    job_id = str(uuid.uuid4())

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

    # Clean up empty dicts
    search_criteria['or'] = [i for i in search_criteria['or'] if i]
    if not search_criteria['or']:
        del search_criteria['or']

    payload = {
        "searchCriteria": search_criteria,
        "listingType": listing_type,
        "options": {
            "webhookUrl": f"{APP_BASE_URL}/batchdata-webhook/{job_id}",
            "errorWebhookUrl": f"{APP_BASE_URL}/batchdata-webhook-error/{job_id}"
        }
    }

    response = requests.post(f"{BATCHDATA_API_URL}/property/search/async", json=payload, headers=headers)
    response.raise_for_status()
    return job_id
