import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import config
from db_connector import sync_items_cache
from item_matcher import ItemMatcher
from ai_extractor import AIExtractor
from quotation import QuotationService
from pricing import PricingEngine
from memory import ItemMemory

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("QuotationApp")

BASE_DIR = Path(__file__).resolve().parent
HTML_TEMPLATE_FILE = BASE_DIR / "templates" / "index.html"
CONFIG_FILE = BASE_DIR / "config.py"

app = FastAPI(title="Optech WhatsApp Quotation Bot", version="2.2.0")

matcher: Optional[ItemMatcher] = None
extractor: Optional[AIExtractor] = None
pricing: Optional[PricingEngine] = None
memory: Optional[ItemMemory] = None
quotation_service: Optional[QuotationService] = None


@app.on_event("startup")
def startup_event():
    global matcher, extractor, pricing, memory, quotation_service
    logger.info("Initializing Quotation Bot with Pricing & Memory...")
    memory = ItemMemory()
    pricing = PricingEngine()
    try:
        items = sync_items_cache(force_refresh=False)
        matcher = ItemMatcher(items=items, memory=memory)
    except Exception as e:
        logger.warning(f"Could not load items from SQL/cache on startup: {e}")
        matcher = ItemMatcher(items=[], memory=memory)

    extractor = AIExtractor()
    quotation_service = QuotationService(matcher, extractor, pricing)
    logger.info("Quotation Bot 2.2 initialized successfully.")


class TextQuotationRequest(BaseModel):
    text: str
    pricing_mode: str = "standard"


class LearnItemRequest(BaseModel):
    alias: str
    optech_item_name: str


class MarkupRulesRequest(BaseModel):
    default_markup_percent: float
    groups: Dict[str, float]


class ApiKeyRequest(BaseModel):
    api_key: str


class SaveQuotationRequest(BaseModel):
    customer_name: Optional[str] = ""
    customer_phone: Optional[str] = ""
    pricing_mode: str = "standard"
    gst_rate: str = "18"
    items: list
    whatsapp_message: str
    total_amount: float


class SyncCacheRequest(BaseModel):
    sync_secret: str
    items: list
    memory: Optional[dict] = None
    markup_rules: Optional[dict] = None


@app.get("/", response_class=HTMLResponse)
def index_page():
    if not HTML_TEMPLATE_FILE.exists():
        return HTMLResponse("<h1>Template file not found.</h1>", status_code=500)

    with open(HTML_TEMPLATE_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    total_items = len(matcher.items) if matcher else 0
    learned_count = len(memory.memory) if memory else 0
    has_api_key = bool(extractor and extractor.client)

    html = html.replace("{{TOTAL_ITEMS}}", f"{total_items:,}")
    html = html.replace("{{LEARNED_COUNT}}", str(learned_count))
    html = html.replace("{{HAS_API_KEY}}", "true" if has_api_key else "false")
    return HTMLResponse(content=html)


@app.get("/api/api-key-status")
def get_api_key_status():
    has_key = bool(extractor and extractor.client)
    return {"has_key": has_key}


@app.post("/api/set-api-key")
def set_api_key(req: ApiKeyRequest):
    global extractor, quotation_service
    key = req.api_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty")

    # Update config.py on disk
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg_text = f.read()
        # Replace GEMINI_API_KEY
        new_cfg_text = re.sub(
            r'GEMINI_API_KEY\s*=\s*os\.getenv\(.*?\)',
            f'GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "{key}")',
            cfg_text
        )
        if new_cfg_text == cfg_text:
            new_cfg_text = re.sub(
                r'GEMINI_API_KEY\s*=.*',
                f'GEMINI_API_KEY = "{key}"',
                cfg_text
            )
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(new_cfg_text)
    except Exception as e:
        logger.warning(f"Could not persist API key to config.py: {e}")

    # Re-initialize AIExtractor with new key
    extractor = AIExtractor(api_key=key)
    quotation_service = QuotationService(matcher, extractor, pricing)
    logger.info("Gemini API key updated successfully.")
    return {"status": "success", "has_key": bool(extractor.client)}


@app.get("/api/markup-rules")
def get_markup_rules():
    return pricing.rules


@app.post("/api/markup-rules")
def update_markup_rules(req: MarkupRulesRequest):
    new_rules = {
        "default_markup_percent": req.default_markup_percent,
        "groups": req.groups
    }
    pricing.save_rules(new_rules)
    return {"status": "success", "rules": pricing.rules}


@app.get("/api/search-items")
def search_items(q: str = Query(..., min_length=2)):
    if not matcher:
        return []
    return matcher.search_candidates(q, limit=15)


@app.post("/api/learn-item")
def learn_item(req: LearnItemRequest):
    global matcher
    if not req.alias or not req.optech_item_name:
        raise HTTPException(status_code=400, detail="Alias and Optech item name required")
    memory.learn(req.alias, req.optech_item_name)
    matcher.memory = memory
    return {"status": "success", "total_learned": len(memory.memory)}


HISTORY_FILE = BASE_DIR / "quotations_history.json"


@app.post("/api/save-quotation")
def save_quotation(req: SaveQuotationRequest):
    import datetime
    import json
    history = []
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []

    entry = {
        "id": len(history) + 1,
        "date": datetime.datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "customer_name": req.customer_name or "Walk-in Customer",
        "customer_phone": req.customer_phone or "-",
        "pricing_mode": req.pricing_mode,
        "gst_rate": req.gst_rate,
        "items": req.items,
        "total_amount": req.total_amount,
        "whatsapp_message": req.whatsapp_message
    }
    history.insert(0, entry)
    history = history[:100]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    return {"status": "success", "id": entry["id"], "total_saved": len(history)}


@app.get("/api/quotation-history")
def get_quotation_history():
    import json
    if HISTORY_FILE.exists():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


@app.post("/api/sync-cache")
def api_sync_cache(req: SyncCacheRequest):
    global matcher, memory, pricing, quotation_service
    from config import SYNC_SECRET, ITEMS_CACHE_FILE
    from memory import MEMORY_FILE
    from pricing import RULES_FILE
    import json

    if req.sync_secret != SYNC_SECRET:
        raise HTTPException(status_code=403, detail="Invalid sync secret key")

    # 1. Save updated items
    if req.items:
        with open(ITEMS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(req.items, f, ensure_ascii=False, indent=2)
        logger.info(f"Sync: Updated items_cache.json with {len(req.items):,} items.")

    # 2. Save updated memory if given
    if req.memory:
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(req.memory, f, ensure_ascii=False, indent=2)
        memory = ItemMemory()

    # 3. Save updated markup rules if given
    if req.markup_rules:
        with open(RULES_FILE, "w", encoding="utf-8") as f:
            json.dump(req.markup_rules, f, ensure_ascii=False, indent=2)
        pricing = PricingEngine()

    # Reload matcher in-memory
    items = sync_items_cache(force_refresh=False)
    matcher = ItemMatcher(items=items, memory=memory)
    quotation_service = QuotationService(matcher, extractor, pricing)

    return {
        "status": "success",
        "total_items": len(matcher.items),
        "total_learned": len(memory.memory)
    }


@app.post("/api/sync-sql")
def api_sync_sql():
    global matcher, quotation_service
    import json
    try:
        from db_connector import fetch_items_from_sql, ITEMS_CACHE_FILE
        items = fetch_items_from_sql()
        if items:
            with open(ITEMS_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            matcher = ItemMatcher(items=items, memory=memory)
            quotation_service = QuotationService(matcher, extractor, pricing)
            return {
                "status": "success",
                "source": "sql_server",
                "total_items": len(items),
                "message": f"Successfully synced {len(items):,} items directly from Optech SQL Server!"
            }
        else:
            return {"status": "error", "message": "SQL Server returned 0 items."}
    except Exception as e:
        logger.info(f"Direct SQL sync not available (running on cloud or no local DB driver): {e}")
        total = len(matcher.items) if matcher else 0
        return {
            "status": "cloud_active",
            "source": "cache",
            "total_items": total,
            "message": f"Cloud Database is active with {total:,} items! Live updates auto-sync from your Shop PC every 30 minutes."
        }


@app.post("/api/quotation/text")
def api_process_text(req: TextQuotationRequest):
    if not quotation_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    try:
        return quotation_service.process_text_quotation(req.text, pricing_mode=req.pricing_mode)
    except Exception as e:
        logger.error(f"Error processing text quotation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/quotation/image")
async def api_process_image(file: UploadFile = File(...), pricing_mode: str = Form("standard")):
    if not quotation_service:
        raise HTTPException(status_code=500, detail="Service not initialized")
    image_bytes = await file.read()
    mime_type = file.content_type or "image/jpeg"
    try:
        return quotation_service.process_image_quotation(image_bytes, mime_type=mime_type, pricing_mode=pricing_mode)
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        err_msg = str(e)
        if any(k in err_msg.lower() for k in ["503", "unavailable", "high demand"]):
            status_code = 503
            detail_msg = "Google AI servers are temporarily experiencing high demand (503). Please retry in 10-15 seconds, or type the items in the text box."
        elif "api key" in err_msg.lower():
            status_code = 400
            detail_msg = "Gemini API key is required. Please click 'Gemini API Key' at the top to save your key."
        else:
            status_code = 500
            detail_msg = err_msg
        raise HTTPException(status_code=status_code, detail=detail_msg)


@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: Request):
    payload = await request.json()
    text_content = ""
    if "body" in payload:
        text_content = payload["body"]
    elif "message" in payload and isinstance(payload["message"], dict):
        text_content = payload["message"].get("conversation", "")

    if text_content:
        quote = quotation_service.process_text_quotation(text_content, pricing_mode="standard")
        return {
            "reply": quote["whatsapp_message"],
            "data": quote
        }

    return {"status": "ignored"}


if __name__ == "__main__":
    import uvicorn
    from config import HOST, PORT
    uvicorn.run("app:app", host=HOST, port=PORT, reload=True)
