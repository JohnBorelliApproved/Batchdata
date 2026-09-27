import os
from dotenv import load_dotenv

load_dotenv()

BATCHDATA_API_KEY = os.getenv("BATCHDATA_API_KEY")
GOHIGHLEVEL_API_KEY = os.getenv("GOHIGHLEVEL_API_KEY")
AGENCY_LOCATION_ID = os.getenv("AGENCY_LOCATION_ID")
AGENCY_API_KEY = os.getenv("AGENCY_API_KEY")
TEST_SUBACCOUNT_API_KEY = os.getenv("TEST_SUBACCOUNT_API_KEY")
LEDGER_DB_PATH = os.getenv("LEDGER_DB_PATH") or os.path.join(os.path.dirname(__file__), "ledger.db")

# Set (e.g. "1") to skip the live GHL entitlement-field provisioning call at
# app startup — used by test files that import main.py so the offline test
# suite doesn't make a network call to production GHL on every run.
SKIP_STARTUP_PROVISIONING = os.getenv("SKIP_STARTUP_PROVISIONING", "").lower() in ("1", "true", "yes")
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://abeapi.com")