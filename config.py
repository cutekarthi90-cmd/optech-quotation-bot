import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# SQL Server Configuration
# Note: On local machine, Windows Authentication (Trusted_Connection=yes)
# or SQL Authentication (sa / password) can be used.
SQL_CONFIG = {
    "server": os.getenv("SQL_SERVER", r"DESKTOP-EHLF755\SQLEXPRESS"),
    "database": os.getenv("SQL_DATABASE", "Inv_15_002"),
    "username": os.getenv("SQL_USER", "sa"),
    "password": os.getenv("SQL_PASSWORD", ""),  # Provide if using SQL Auth
    "trusted_connection": os.getenv("SQL_TRUSTED", "yes"),  # "yes" for Windows Auth, "no" for sa
}

# Cache File for 22,752 items
ITEMS_CACHE_FILE = BASE_DIR / "items_cache.json"

# Google Gemini API Key
# Set via environment variable GEMINI_API_KEY or paste directly here
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Server Settings
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", 8000))

# Cloud Sync Settings
SYNC_SECRET = os.getenv("SYNC_SECRET", "optech_sync_secret_key_2026")
CLOUD_SERVER_URL = os.getenv("CLOUD_SERVER_URL", "")

