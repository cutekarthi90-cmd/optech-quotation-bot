"""
One-click Cloud Sync Utility for Optech Quotation Bot
Uploads latest 22,752 items, learned memories, and markup rules
from local Shop PC / SQL Server to your 24/7 Cloud Server.
"""
import json
import urllib.request
import urllib.error
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from config import SYNC_SECRET, CLOUD_SERVER_URL, ITEMS_CACHE_FILE
    from db_connector import sync_items_cache
except ImportError:
    print("Please run this script inside the optech_quotation_bot directory.")
    sys.exit(1)

def main():
    print("========================================================")
    print("    OPTECH QUOTATION BOT -> CLOUD SYNC UTILITY")
    print("========================================================\n")

    cloud_url = CLOUD_SERVER_URL.strip().rstrip("/")
    if not cloud_url:
        print("Cloud Server URL is not configured in config.py yet.")
        cloud_url = input("Enter your Cloud Server URL (e.g. https://my-quote.onrender.com): ").strip().rstrip("/")
        if not cloud_url:
            print("Sync cancelled: Cloud URL required.")
            return

    print("[1/3] Fetching latest items from local SQL Server / cache...")
    try:
        items = sync_items_cache(force_refresh=False)
        print(f"      Loaded {len(items):,} items successfully.")
    except Exception as e:
        print(f"      Warning: Could not connect to SQL, using local items_cache.json ({e})")
        if ITEMS_CACHE_FILE.exists():
            with open(ITEMS_CACHE_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
        else:
            print("Error: No items found to sync.")
            return

    # Load memory
    mem_file = BASE_DIR / "item_memory.json"
    memory = json.load(open(mem_file, "r", encoding="utf-8")) if mem_file.exists() else {}

    # Load markup rules
    rules_file = BASE_DIR / "markup_rules.json"
    markup_rules = json.load(open(rules_file, "r", encoding="utf-8")) if rules_file.exists() else {}

    print(f"[2/3] Preparing sync payload ({len(items):,} items, {len(memory)} memories)...")
    payload = {
        "sync_secret": SYNC_SECRET,
        "items": items,
        "memory": memory,
        "markup_rules": markup_rules
    }
    data = json.dumps(payload).encode("utf-8")

    target_endpoint = f"{cloud_url}/api/sync-cache"
    print(f"[3/3] Uploading to Cloud Server: {target_endpoint}...")

    req = urllib.request.Request(
        target_endpoint,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            print("\n========================================================")
            print("🎉 SUCCESS! Cloud Server is 100% Synced and Up-to-Date!")
            print(f"   Total Items on Cloud: {res_data.get('total_items', len(items)):,}")
            print(f"   Total Memories on Cloud: {res_data.get('total_learned', len(memory))}")
            print("========================================================")
    except urllib.error.HTTPError as e:
        print(f"\n❌ Sync failed (HTTP {e.code}): {e.read().decode('utf-8', errors='ignore')}")
    except Exception as e:
        print(f"\n❌ Sync failed: {e}")

if __name__ == "__main__":
    main()
