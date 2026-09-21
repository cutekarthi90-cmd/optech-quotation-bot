"""
Optech Quotation Bot - Automatic 30-Minute Sync Worker
Fetches latest products, rates, and units from Optech SQL Server (Inv_15_002)
and syncs them to GitHub / Render Cloud.
"""
import os
import sys
import time
import json
import subprocess
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

def get_github_token() -> str:
    token_file = BASE_DIR / "git_token.txt"
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    return os.getenv("GITHUB_TOKEN", "")

CLEAN_REMOTE = "https://github.com/cutekarthi90-cmd/optech-quotation-bot.git"

def run_git_sync():
    try:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p")
        subprocess.run(["git", "add", "items_cache.json", "item_memory.json"], cwd=BASE_DIR, check=True, capture_output=True)
        # Check if there are changes to commit
        status = subprocess.run(["git", "status", "--porcelain"], cwd=BASE_DIR, capture_output=True, text=True)
        if "items_cache.json" in status.stdout or "item_memory.json" in status.stdout:
            subprocess.run(["git", "commit", "-m", f"Auto-sync items and memory at {now_str}"], cwd=BASE_DIR, check=True, capture_output=True)
            print(f"[{now_str}] Pushing updated items to GitHub Cloud...")
            token = get_github_token()
            repo_url = f"https://cutekarthi90-cmd:{token}@github.com/cutekarthi90-cmd/optech-quotation-bot.git" if token else CLEAN_REMOTE
            push_res = subprocess.run(["git", "push", repo_url, "main"], cwd=BASE_DIR, capture_output=True, text=True)
            subprocess.run(["git", "remote", "set-url", "origin", CLEAN_REMOTE], cwd=BASE_DIR, capture_output=True)
            if push_res.returncode == 0:
                print(f"[{now_str}] Push successful! Render Cloud is updating automatically.")
                return True
            else:
                print(f"[{now_str}] Push failed: {push_res.stderr}")
                return False
        else:
            print(f"[{now_str}] No changes in items since last sync. Cache is up to date.")
            return True
    except Exception as e:
        print(f"Git sync error: {e}")
        try:
            subprocess.run(["git", "remote", "set-url", "origin", CLEAN_REMOTE], cwd=BASE_DIR, capture_output=True)
        except Exception:
            pass
        return False

def sync_once():
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
    print("=" * 60)
    print(f"[{now_str}] Starting Optech Database Sync...")
    try:
        from db_connector import fetch_items_from_sql, ITEMS_CACHE_FILE
        items = fetch_items_from_sql()
        if not items:
            print(f"[{now_str}] Warning: SQL query returned 0 items. Skipping cache overwrite.")
            return False

        with open(ITEMS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        print(f"[{now_str}] Fetched {len(items):,} items from SQL Server successfully.")

        # Sync to GitHub / Cloud
        run_git_sync()
        return True
    except Exception as e:
        print(f"[{now_str}] Error during sync: {e}")
        return False

def main():
    loop_mode = "--loop" in sys.argv or "-l" in sys.argv
    interval_seconds = 1800  # 30 minutes

    print("========================================================")
    print("      OPTECH QUOTATION BOT - AUTO SYNC WORKER")
    print("      Syncs from SQL Server -> Cloud every 30 minutes")
    print("========================================================\n")

    sync_once()

    if loop_mode:
        print(f"\n[INFO] Auto-sync loop running every 30 minutes (1800s).")
        print("Leave this window open in background. Press Ctrl+C to stop.\n")
        while True:
            try:
                time.sleep(interval_seconds)
                sync_once()
            except KeyboardInterrupt:
                print("\nAuto-sync stopped by user.")
                break
            except Exception as ex:
                print(f"Loop error: {ex}")
                time.sleep(60)

if __name__ == "__main__":
    main()
