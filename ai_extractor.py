import os
import json
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None

from config import GEMINI_API_KEY

logger = logging.getLogger("AIExtractor")

EXTRACTION_PROMPT = """
You are an expert OCR and quotation item extractor for an Indian hardware, electrical, and plumbing supply business.
Analyze the provided input (image or text) representing a customer's quotation inquiry or bill.
The list may be handwritten, typed, printed, or informal message text in English or Tanglish.

For each item mentioned, extract:
1. "item_query": Clean product name/description with dimensions and brand (e.g. "BL 4 inch JB cutoff wheel", "CO 1 inch pvc coupling"). Strip trailing quantities.
2. "qty": Quantity as a numeric float/integer (default to 1 if not specified).
3. "unit": Unit of measurement (e.g. "Nos", "Pcs", "Mtr", "Box", "Set").

CRITICAL: Return ONLY valid JSON in this exact structure without markdown formatting or code blocks:
[
  {
    "item_query": "Product name and size",
    "qty": 10,
    "unit": "Nos"
  }
]
"""


def parse_line_qty_and_item(line: str) -> Tuple[str, float, str]:
    """
    Extract quantity, unit, and clean item name from an informal line.
    Handles:
      - 'BL 4" JB CUTOFF WHEEL-10PS' -> ('BL 4" JB CUTOFF WHEEL', 10.0, 'Pcs')
      - 'CO 1" PVC COUPLING-10' -> ('CO 1" PVC COUPLING', 10.0, 'Nos')
      - '1 1/2 NRV 5 PCS' -> ('1 1/2 NRV', 5.0, 'Pcs')
      - '10 NOS 4" CUTOFF WHEEL' -> ('4" CUTOFF WHEEL', 10.0, 'Nos')
    """
    clean_line = line.strip()
    # Remove leading numbering like "1.", "1)", "1 -", etc.
    clean_line = re.sub(r"^[\d\.\-\*\)]+\s*", "", clean_line).strip()

    qty = 1.0
    unit = "Nos"

    # 1. Trailing quantity (e.g. -10PS, -10ps, -10 pcs, *10, x10, -10, 10 nos)
    trailing = re.search(
        r"[-–*x/:\s]+(\d+(?:\.\d+)?)\s*(ps|pcs|pc|nos|no|pkt|pkts|box|bx|mtr|m|set|sets|roll|rolls|bag|bags)?\s*$",
        clean_line,
        re.IGNORECASE
    )
    if trailing and trailing.start() > 2:
        val_str = trailing.group(1)
        u_str = trailing.group(2)
        prefix = clean_line[:trailing.start()]
        # Ensure we didn't accidentally catch a dimension (like 42mm or 4")
        if not re.search(r'[\"\'\d/]\s*$', prefix):
            try:
                qty = float(val_str)
                if u_str:
                    u_lower = u_str.lower()
                    if u_lower in ("ps", "pc", "pcs"):
                        unit = "Pcs"
                    elif u_lower in ("no", "nos"):
                        unit = "Nos"
                    else:
                        unit = u_str.capitalize()
                clean_line = prefix.strip().rstrip("-–*x/:").strip()
                return clean_line, qty, unit
            except ValueError:
                pass

    # 2. Leading quantity (e.g. 10 nos 4" cutoff wheel, 10x coupling)
    leading = re.match(
        r"^\s*(\d+(?:\.\d+)?)\s*(ps|pcs|pc|nos|no|pkt|pkts|box|bx|mtr|m|set|sets|roll|rolls|bag|bags)?\s*[-–*x/:]*\s+",
        clean_line,
        re.IGNORECASE
    )
    if leading:
        try:
            qty = float(leading.group(1))
            u_str = leading.group(2)
            if u_str:
                u_lower = u_str.lower()
                if u_lower in ("ps", "pc", "pcs"):
                    unit = "Pcs"
                elif u_lower in ("no", "nos"):
                    unit = "Nos"
                else:
                    unit = u_str.capitalize()
            clean_line = clean_line[leading.end():].strip()
        except ValueError:
            pass

    return clean_line, qty, unit


class AIExtractor:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", "")
        self.client = None
        if self.api_key and genai:
            try:
                self.client = genai.Client(api_key=self.api_key)
                logger.info("Gemini AI Client initialized successfully.")
            except Exception as e:
                logger.warning(f"Could not initialize Gemini client: {e}")

    def extract_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract item list from text message."""
        if not text or not text.strip():
            return []

        if self.client:
            for model_name in ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]:
                try:
                    prompt = f"{EXTRACTION_PROMPT}\n\nCustomer Message:\n{text}"
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                    )
                    items = self._parse_json_response(response.text)
                    if items:
                        return items
                except Exception as e:
                    logger.warning(f"Model {model_name} failed for text: {e}")
                    continue

        # Robust rule-based line parser
        return self._fallback_text_parser(text)

    def extract_from_image(self, image_bytes: bytes, mime_type: str = "image/jpeg") -> List[Dict[str, Any]]:
        """Extract item list from image (photo of handwritten note/bill)."""
        if not self.client:
            raise RuntimeError(
                "Gemini API key is required for image OCR. Please set GEMINI_API_KEY in config.py."
            )

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        last_err = None
        for model_name in ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-flash-latest"]:
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=[image_part, EXTRACTION_PROMPT],
                )
                items = self._parse_json_response(response.text)
                if items:
                    return items
            except Exception as e:
                logger.warning(f"Model {model_name} failed for image OCR: {e}")
                last_err = e
                continue

        logger.error(f"All Gemini models failed for image OCR: {last_err}")
        if last_err:
            raise last_err
        return []

    def _parse_json_response(self, response_text: str) -> List[Dict[str, Any]]:
        """Clean and parse JSON from model output."""
        cleaned = re.sub(r"```json\s*", "", response_text)
        cleaned = re.sub(r"```\s*", "", cleaned).strip()
        try:
            data = json.loads(cleaned)
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "items" in data:
                return data["items"]
            return []
        except Exception as e:
            logger.error(f"Failed to parse JSON response: {cleaned} - {e}")
            return []

    def _fallback_text_parser(self, text: str) -> List[Dict[str, Any]]:
        """Line-by-line parser with enhanced Indian hardware quantity handling."""
        items = []
        lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
        for line in lines:
            item_name, qty, unit = parse_line_qty_and_item(line)
            if item_name:
                items.append({
                    "item_query": item_name,
                    "qty": qty,
                    "unit": unit
                })
        return items
