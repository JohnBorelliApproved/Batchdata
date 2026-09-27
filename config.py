import os
from dotenv import load_dotenv

load_dotenv()

BATCHDATA_API_KEY = os.getenv("BATCHDATA_API_KEY")
GOHIGHLEVEL_API_KEY = os.getenv("GOHIGHLEVEL_API_KEY")
AGENCY_LOCATION_ID = os.getenv("AGENCY_LOCATION_ID")
AGENCY_API_KEY = os.getenv("AGENCY_API_KEY")
TEST_SUBACCOUNT_API_KEY = os.getenv("TEST_SUBACCOUNT_API_KEY")
LEDGER_DB_PATH = os.getenv("LEDGER_DB_PATH", os.path.join(os.path.dirname(__file__), "ledger.db"))
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://abeapi.com")