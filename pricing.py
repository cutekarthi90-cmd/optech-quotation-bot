import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("PricingEngine")
RULES_FILE = Path(__file__).resolve().parent / "markup_rules.json"

DEFAULT_RULES = {
    "default_markup_percent": 15.0,
    "groups": {
        "ELECTRICAL": 18.0,
        "PLUMBING": 20.0,
        "HARDWARE": 15.0,
        "PAINT": 12.0,
        "PAINT ACCESSORIES": 15.0
    }
}


class PricingEngine:
    def __init__(self):
        self.rules = self.load_rules()

    def load_rules(self) -> Dict[str, Any]:
        if RULES_FILE.exists():
            try:
                with open(RULES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to read markup_rules.json: {e}")
        return dict(DEFAULT_RULES)

    def save_rules(self, new_rules: Dict[str, Any]) -> None:
        self.rules = new_rules
        try:
            with open(RULES_FILE, "w", encoding="utf-8") as f:
                json.dump(new_rules, f, indent=2, ensure_ascii=False)
            logger.info("Markup rules updated successfully.")
        except Exception as e:
            logger.error(f"Failed to save markup rules: {e}")

    def get_markup_percent(self, group_name: str) -> float:
        grp = (group_name or "").strip().upper()
        groups = {k.strip().upper(): v for k, v in self.rules.get("groups", {}).items()}

        # 1. Exact match
        if grp in groups:
            return float(groups[grp])

        # 2. Smart Core Category Mapping
        if "PAINT ACCESS" in grp and "PAINT ACCESSORIES" in groups:
            return float(groups["PAINT ACCESSORIES"])
        if "PAINT" in grp and "PAINT" in groups:
            return float(groups["PAINT"])
        if ("ELECT" in grp or "ELECTRICALS" in grp) and "ELECTRICAL" in groups:
            return float(groups["ELECTRICAL"])
        if ("HARDWARE" in grp or "ACCESSORIES" in grp) and "HARDWARE" in groups:
            return float(groups["HARDWARE"])
        if "PLUMB" in grp and "PLUMBING" in groups:
            return float(groups["PLUMBING"])

        return float(self.rules.get("default_markup_percent", 15.0))

    def calculate_rate(self, item: Dict[str, Any], pricing_mode: str = "standard") -> Dict[str, Any]:
        sale_rate = float(item.get("sale_rate", 0.0) or 0.0)
        pur_rate = float(item.get("purchase_rate", 0.0) or 0.0)
        group_name = item.get("group_name", "")

        if pricing_mode.lower() == "markup":
            markup_pct = self.get_markup_percent(group_name)
            if pur_rate > 0:
                calc_rate = round(pur_rate * (1.0 + (markup_pct / 100.0)), 2)
            else:
                calc_rate = sale_rate

            return {
                "effective_rate": calc_rate,
                "pricing_mode": "markup",
                "markup_percent": markup_pct,
                "base_purchase_rate": pur_rate
            }
        else:
            return {
                "effective_rate": sale_rate,
                "pricing_mode": "standard",
                "markup_percent": 0.0,
                "base_purchase_rate": pur_rate
            }
