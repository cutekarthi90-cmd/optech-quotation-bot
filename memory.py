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
    s = key.lower().strip()
    # Strip trailing quantity pattern like "- 10ps", "- 10 nos", "-10 set", "10pcs", etc.
    s = re.sub(r'[\s\-]+(\d+)\s*(?:nos|no|set|sets|ps|pcs|pc|mtr|mtrs|meter|meters|feet|ft|kg|gm|pkt|pkts|pack|box|bundle|roll|rolls)?\s*$', '', s, flags=re.IGNORECASE)
    # Strip punctuation but preserve alphanumerics
    s = re.sub(r'[\"\'\(\)\[\]\{\},:;\*\.\-]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


try:
    from rapidfuzz import fuzz
except ImportError:
    try:
        import fuzzywuzzy.fuzz as fuzz
    except ImportError:
        fuzz = None


class ItemMemory:
    def __init__(self):
        self.memory: Dict[str, str] = self.load_memory()

    def load_memory(self) -> Dict[str, str]:
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Normalize keys
                    return {normalize_alias_key(k): str(v).strip() for k, v in data.items() if k and v}
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
        """
        Check if this query has a previously memorized Optech item name.
        Uses 3-stage matching:
        1. Exact normalized match
        2. Token set subset/superset match
        3. High-confidence fuzzy match (>= 80% token_set_ratio)
        """
        if not query:
            return None
        norm_key = normalize_alias_key(query)
        if not norm_key:
            return None

        # 1. Exact match
        if norm_key in self.memory:
            return self.memory[norm_key]

        # 2. Token-set match
        q_tokens = set(norm_key.split())
        best_fuzzy_match = None
        best_fuzzy_score = 0.0

        for mem_alias, optech_name in self.memory.items():
            mem_tokens = set(mem_alias.split())
            if not mem_tokens:
                continue

            # If all query tokens are in memorized alias (or all memorized alias tokens in query)
            if len(mem_tokens) >= 2 and (mem_tokens.issubset(q_tokens) or q_tokens.issubset(mem_tokens)):
                return optech_name

            # 3. Fuzzy similarity
            if fuzz:
                ratio = fuzz.token_set_ratio(norm_key, mem_alias)
                if ratio >= 80.0 and ratio > best_fuzzy_score:
                    best_fuzzy_score = ratio
                    best_fuzzy_match = optech_name

        if best_fuzzy_match and best_fuzzy_score >= 80.0:
            logger.info(f"Fuzzy memory match ({best_fuzzy_score}%): '{query}' => '{best_fuzzy_match}'")
            return best_fuzzy_match

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
