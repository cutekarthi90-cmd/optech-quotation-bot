import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import pyodbc
except ImportError:
    pyodbc = None

from config import SQL_CONFIG, ITEMS_CACHE_FILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DBConnector")


def get_available_driver() -> str:
    """Detect the best available SQL Server ODBC driver on Windows."""
    if pyodbc is None:
        raise RuntimeError("pyodbc module is not installed. Run: pip install pyodbc")

    installed_drivers = pyodbc.drivers()
    preferred = [
        "ODBC Driver 17 for SQL Server",
        "ODBC Driver 18 for SQL Server",
        "SQL Server Native Client 11.0",
        "SQL Server Native Client 10.0",
        "SQL Server",
    ]
    for drv in preferred:
        if drv in installed_drivers:
            return drv
    if installed_drivers:
        return installed_drivers[0]
    return "SQL Server"


def get_connection_string() -> str:
    """Build connection string based on config."""
    driver = get_available_driver()
    server = SQL_CONFIG["server"]
    database = SQL_CONFIG["database"]

    # Extra options for ODBC Driver 18
    extra = ""
    if "18" in driver:
        extra = ";TrustServerCertificate=yes"

    if SQL_CONFIG.get("trusted_connection", "yes").lower() == "yes":
        return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes{extra};"
    else:
        user = SQL_CONFIG.get("username", "sa")
        pwd = SQL_CONFIG.get("password", "")
        return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={user};PWD={pwd}{extra};"


def fetch_items_from_sql() -> List[Dict[str, Any]]:
    """Fetch all items from Optech SQL database."""
    conn_str = get_connection_string()
    logger.info(f"Connecting to SQL Server with driver: {get_available_driver()}...")

    query = """
    SELECT 
        I.Item_name AS item_name,
        ISNULL(G.ItemGroup_name, '') AS group_name,
        CAST(ISNULL(I.Item_Purcrate, 0) AS FLOAT) AS purchase_rate,
        CAST(ISNULL(I.Item_Salerate, 0) AS FLOAT) AS sale_rate,
        ISNULL(I.ItemHSN_Code, '') AS hsn_code
    FROM Item_Master I
    LEFT JOIN ItemGroup_Master G ON I.ItemGroup_sno = G.ItemGroup_sno
    WHERE ISNULL(I.Item_name, '') <> ''
    ORDER BY I.Item_name;
    """

    try:
        with pyodbc.connect(conn_str, timeout=10) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query)
                columns = [column[0].lower() for column in cursor.description]
                items = []
                for row in cursor.fetchall():
                    item_dict = dict(zip(columns, row))
                    # Clean strings
                    item_dict["item_name"] = str(item_dict["item_name"]).strip()
                    item_dict["group_name"] = str(item_dict["group_name"]).strip()
                    item_dict["hsn_code"] = str(item_dict["hsn_code"]).strip()
                    items.append(item_dict)
                logger.info(f"Successfully fetched {len(items):,} items from SQL Server.")
                return items
    except Exception as e:
        # If trusted connection failed, try with SQL auth if password available
        logger.error(f"SQL Connection failed: {e}")
        raise


def sync_items_cache(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """
    Loads items from local JSON cache if present; otherwise fetches from SQL Server
    and saves to cache file for instant future lookups.
    """
    if not force_refresh and ITEMS_CACHE_FILE.exists():
        try:
            with open(ITEMS_CACHE_FILE, "r", encoding="utf-8") as f:
                items = json.load(f)
            logger.info(f"Loaded {len(items):,} items from local cache ({ITEMS_CACHE_FILE.name}).")
            return items
        except Exception as e:
            logger.warning(f"Failed to read cache file ({e}). Refreshing from SQL...")

    items = fetch_items_from_sql()
    try:
        with open(ITEMS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(items):,} items to cache ({ITEMS_CACHE_FILE}).")
    except Exception as e:
        logger.warning(f"Could not save items cache to disk: {e}")

    return items


if __name__ == "__main__":
    print("Testing SQL Server Connection...")
    try:
        items = sync_items_cache(force_refresh=True)
        print(f"\nSUCCESS! Total Items Loaded: {len(items):,}")
        print("\nSample 5 Items:")
        for it in items[:5]:
            print(f" - {it['item_name']} | Group: {it['group_name']} | Sale Rate: Rs.{it['sale_rate']} | HSN: {it['hsn_code']}")
    except Exception as err:
        print(f"\nERROR: {err}")
