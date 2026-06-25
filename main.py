import json
import os
import logging
from flask import Flask, request, jsonify, render_template
from batchdata_api import search_properties
from ghl_api import get_contacts_by_tag, upsert_contact, get_tags

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WEBHOOK_LOG_DIR = os.path.join(os.path.dirname(__file__), 'webhook_logs')
os.makedirs(WEBHOOK_LOG_DIR, exist_ok=True)

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/get-tags', methods=['GET'])
def get_tags_endpoint():
    try:
        tags = get_tags()
        return jsonify({"tags": tags})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/start-search', methods=['POST'])
def start_search():
    data = request.json
    zip_codes = data.get('zip_codes')
    city = data.get('city')
    state = data.get('state')

    if not (zip_codes or (city and state)):
        return jsonify({"error": "Please provide either zip_codes or city and state."}), 400

    try:
        job_id = search_properties(zip_codes=zip_codes, city=city, state=state)
        logger.info(f"BatchData search initiated. job_id={job_id}")
        return jsonify({"job_id": job_id, "status": "pending", "message": "Search initiated. Results will be processed when BatchData completes."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/distribute-contacts', methods=['POST'])
def distribute_contacts():
    data = request.json
    location_id = data.get('location_id')
    tag = data.get('tag')
    source_location_id = data.get('source_location_id')
    sub_account_api_key = data.get('sub_account_api_key')

    if not (location_id and tag and source_location_id and sub_account_api_key):
        return jsonify({"error": "Please provide location_id, source_location_id, tag, and sub_account_api_key."}), 400

    try:
        # Get contacts from the source location using the agency's main API key
        contacts = get_contacts_by_tag(tag, source_location_id)
        
        for contact in contacts:
            # Remove fields that shouldn't be copied to the new location
            contact.pop('id', None)
            contact.pop('locationId', None)
            contact.pop('lastUpdated', None)
            contact.pop('dateAdded', None)

            # Set the new location id
            contact['locationId'] = location_id

            # Upsert contact to the destination location using the provided sub-account API key
            upsert_contact(contact, api_key=sub_account_api_key)

        return jsonify({"message": f"{len(contacts)} contacts distributed successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/batchdata-webhook/<job_id>', methods=['POST'])
def batchdata_webhook(job_id):
    data = request.json
    logger.info(f"BatchData webhook received. job_id={job_id}")

    # Log the raw payload to disk so we can inspect the data shape
    log_path = os.path.join(WEBHOOK_LOG_DIR, f"webhook_{job_id}.json")
    with open(log_path, 'w') as f:
        json.dump(data, f, indent=2)
    logger.info(f"Webhook payload saved to {log_path}")

    # TODO: parse results, create GHL contacts, notify owner
    return jsonify({"status": "received"})


@app.route('/batchdata-webhook-error/<job_id>', methods=['POST'])
def batchdata_webhook_error(job_id):
    data = request.json
    logger.error(f"BatchData error webhook received. job_id={job_id} data={data}")

    log_path = os.path.join(WEBHOOK_LOG_DIR, f"webhook_error_{job_id}.json")
    with open(log_path, 'w') as f:
        json.dump(data, f, indent=2)

    return jsonify({"status": "received"})

if __name__ == '__main__':
    app.run(debug=True, port=5002)
