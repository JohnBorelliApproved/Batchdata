from flask import Flask, request, jsonify
from batchdata_api import search_properties
from ghl_api import get_contacts_by_tag, upsert_contact

app = Flask(__name__)

@app.route('/')
def home():
    return "ZillowGHLIntegration is running!"

@app.route('/start-search', methods=['POST'])
def start_search():
    data = request.json
    zip_codes = data.get('zip_codes')
    city = data.get('city')
    state = data.get('state')

    if not (zip_codes or (city and state)):
        return jsonify({"error": "Please provide either zip_codes or city and state."}), 400

    try:
        result = search_properties(zip_codes=zip_codes, city=city, state=state)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/distribute-contacts', methods=['POST'])
def distribute_contacts():
    data = request.json
    location_id = data.get('location_id')
    tag = data.get('tag')
    source_location_id = data.get('source_location_id') # The agency's location id

    if not (location_id and tag and source_location_id):
        return jsonify({"error": "Please provide location_id, source_location_id, and tag."}), 400

    try:
        contacts = get_contacts_by_tag(tag, source_location_id)
        
        for contact in contacts:
            # Remove fields that shouldn't be copied to the new location
            contact.pop('id', None)
            contact.pop('locationId', None)
            contact.pop('lastUpdated', None)
            contact.pop('dateAdded', None)

            # Set the new location id
            contact['locationId'] = location_id

            upsert_contact(contact)

        return jsonify({"message": f"{len(contacts)} contacts distributed successfully."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/batchdata-webhook', methods=['POST'])
def batchdata_webhook():
    data = request.json
    # Process the data from Batchdata's Smart Search
    # This is where you'll get new listings and add them to GHL
    print("Received data from Batchdata:", data)

    # Here you would extract the property data and call
    # ghl_api.upsert_contact to add it to your agency sub-account.

    return jsonify({"status": "received"})

if __name__ == '__main__':
    app.run(debug=True, port=5001)
