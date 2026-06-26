import uuid
import requests
from config import BATCHDATA_SANDBOX_API_KEY, BATCHDATA_API_KEY, APP_BASE_URL

# Use sandbox key for testing; fall back to legacy key if not set
_ACTIVE_KEY = BATCHDATA_SANDBOX_API_KEY or BATCHDATA_API_KEY

BATCHDATA_API_URL = "https://api.batchdata.com/api/v1"

def search_properties(zip_codes=None, city=None, state=None):
    """
    Initiates an async property search in BatchData.
    Generates a UUID job ID, embeds it in the webhook URLs, and returns it.
    BatchData will POST results to /batchdata-webhook/<job_id> when complete.
    """
    job_id = str(uuid.uuid4())

    headers = {
        "Authorization": f"Bearer {_ACTIVE_KEY}",
        "Content-Type": "application/json"
    }

    if zip_codes:
        query = ", ".join(zip_codes)
    else:
        query = f"{city}, {state}"

    payload = {
        "searchCriteria": {
            "query": query
        },
        "options": {
            "skip": 0,
            "take": 25,
            "webhookUrl": f"{APP_BASE_URL}/batchdata-webhook/{job_id}",
            "errorWebhookUrl": f"{APP_BASE_URL}/batchdata-webhook-error/{job_id}"
        }
    }

    response = requests.post(f"{BATCHDATA_API_URL}/property/search/async", json=payload, headers=headers)
    response.raise_for_status()
    result = response.json()
    batchdata_request_id = result.get('requestId')
    return job_id, batchdata_request_id
