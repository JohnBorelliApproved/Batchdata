"""
Step 1 local test: fetch a real BatchData payload via the sync endpoint,
then POST it to the local webhook handler as if BatchData called us.
This validates parsing + GHL contact creation without needing a public URL.
"""
import uuid
import requests
from dotenv import load_dotenv
import os

load_dotenv()

BATCHDATA_KEY = os.getenv('BATCHDATA_SANDBOX_API_KEY')
LOCAL_BASE = 'http://localhost:5002'

def fetch_batchdata_sample(zip_code='90210', take=2):
    print(f'Fetching {take} properties from BatchData sync endpoint (zip: {zip_code})...')
    resp = requests.post(
        'https://api.batchdata.com/api/v1/property/search',
        json={
            'searchCriteria': {'query': zip_code},
            'options': {'skip': 0, 'take': take}
        },
        headers={
            'Authorization': f'Bearer {BATCHDATA_KEY}',
            'Content-Type': 'application/json'
        }
    )
    resp.raise_for_status()
    data = resp.json()
    count = len(data.get('results', {}).get('properties', []))
    print(f'  Got {count} properties.')
    return data

def simulate_webhook(payload):
    job_id = str(uuid.uuid4())
    print(f'\nPOSTing payload to local webhook (job_id={job_id})...')
    resp = requests.post(
        f'{LOCAL_BASE}/batchdata-webhook/{job_id}',
        json=payload,
        headers={'Content-Type': 'application/json'}
    )
    print(f'  Webhook response: {resp.status_code} {resp.json()}')
    return job_id

def check_job_status(job_id):
    print(f'\nChecking job status...')
    resp = requests.get(f'{LOCAL_BASE}/job-status/{job_id}')
    print(f'  Status response: {resp.json()}')

if __name__ == '__main__':
    payload = fetch_batchdata_sample(zip_code='90210', take=2)
    job_id = simulate_webhook(payload)
    check_job_status(job_id)
    print('\nDone. Check GHL for newly created contacts tagged "batchdata-import".')
