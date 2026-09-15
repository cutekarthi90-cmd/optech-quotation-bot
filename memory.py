import json
import re
import logging
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger("ItemMemory")
MEMORY_FILE = Path(__file__).resolve().parent / "item_memory.json"


def normalize_alias_key(key: str) -> str:
    """Normalize alias for robust memory lookup."""
    if not key:
        return ""
    s = key.lower()
    # Normalize common abbreviations
    s = re.sub(r'[\"\'\(\)\[\]\{\},:;\*\.\-]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


class ItemMemory:
    def __init__(self):
        self.memory: Dict[str, str] = self.load_memory()

    def load_memory(self) -> Dict[str, str]:
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Normalize keys
                    return {normalize_alias_key(k): v for k, v in data.items()}
            except Exception as e:
                logger.warning(f"Failed to read item_memory.json: {e}")
        return {}

    def save_memory(self) -> None:
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.memory)} learned item mappings to disk.")
        except Exception as e:
            logger.error(f"Failed to save item memory: {e}")

    def get_mapping(self, query: str) -> Optional[str]:
        """Check if this query has a previously memorized Optech item name."""
        norm_key = normalize_alias_key(query)
        if norm_key in self.memory:
            return self.memory[norm_key]
        return None

    def learn(self, alias: str, optech_item_name: str) -> None:
        """Learn and persist a new mapping."""
        norm_key = normalize_alias_key(alias)
        if norm_key and optech_item_name:
            self.memory[norm_key] = optech_item_name.strip()
            self.save_memory()
            logger.info(f"Learned mapping: '{norm_key}' => '{optech_item_name.strip()}'")

    def forget(self, alias: str) -> bool:
        norm_key = normalize_alias_key(alias)
        if norm_key in self.memory:
            del self.memory[norm_key]
            self.save_memory()
            return True
        return False

    def get_all(self) -> Dict[str, str]:
        return dict(self.memory)
