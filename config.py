import os
from dotenv import load_dotenv

load_dotenv()

BATCHDATA_API_KEY = os.getenv("BATCHDATA_API_KEY")
GOHIGHLEVEL_API_KEY = os.getenv("GOHIGHLEVEL_API_KEY")
AGENCY_LOCATION_ID = os.getenv("AGENCY_LOCATION_ID")
AGENCY_API_KEY = os.getenv("AGENCY_API_KEY")
