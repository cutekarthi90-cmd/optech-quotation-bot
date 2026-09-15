import re
import logging
from typing import List, Dict, Any, Optional, Set, Tuple

try:
    from rapidfuzz import fuzz
except ImportError:
    fuzz = None

from db_connector import sync_items_cache
from memory import ItemMemory

logger = logging.getLogger("ItemMatcher")


def extract_sizes(text: str) -> Set[str]:
    """Extract hardware dimension sizes from text into a standardized set."""
    s = text.lower()
    sizes = set()

    # 1. Compound fractions: e.g. 1 1/2", 1-1/2", 1.1/2", 2 1/2"
    compound = re.findall(r'\b(\d+)[\s\-\.]+(\d+/[1-9]\d*)\s*(?:\"|\'\'|inch|in\b)?', s)
    for whole, frac in compound:
        sizes.add(f"{whole}-{frac}\"")
        s = re.sub(rf'\b{whole}[\s\-\.]+{re.escape(frac)}\s*(?:\"|\'\'|inch|in\b)?', ' ', s)

    # 2. Simple fractions: e.g. 1/2", 3/4", 7/64
    fractions = re.findall(r'\b([1-9]\d*/[1-9]\d*)\s*(?:\"|\'\'|inch|in\b)?', s)
    for frac in fractions:
        sizes.add(f"{frac}\"")
        s = re.sub(rf'\b{re.escape(frac)}\s*(?:\"|\'\'|inch|in\b)?', ' ', s)

    # 3. Millimeters: e.g. 42mm, 25mm, 110mm
    mms = re.findall(r'\b(\d+(?:\.\d+)?)\s*mm\b', s)
    for mm in mms:
        sizes.add(f"{mm}mm")
        s = re.sub(rf'\b{re.escape(mm)}\s*mm\b', ' ', s)

    # 4. Explicit Whole inches: e.g. 1", 2", 4", 1 inch, 4 inch
    inches = re.findall(r'\b(\d+)\s*(?:\"|\'\'|inch|inches|\bin\b)', s)
    for inch in inches:
        sizes.add(f"{inch}\"")

    return sizes


def normalize_text(text: str) -> str:
    """Normalize text for hardware searches."""
    if not text:
        return ""
    s = text.lower()
    s = re.sub(r'\bcut\s*off\b', 'cutoff', s)
    s = re.sub(r'\bn[\.\s]*r[\.\s]*v\b', 'nrv', s)
    s = re.sub(r'\bu[\.\s]*p[\.\s]*v[\.\s]*c\b', 'upvc', s)
    s = re.sub(r'\bc[\.\s]*p[\.\s]*v[\.\s]*c\b', 'cpvc', s)
    s = re.sub(r'\bp[\.\s]*v[\.\s]*c\b', 'pvc', s)
    s = re.sub(r'\bh[\.\s]*s[\.\s]*s\b', 'hss', s)
    s = re.sub(r'\bcouplers?\b', 'coupling', s)
    s = re.sub(r'[\"\'\(\)\[\]\{\},:;\*]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def parse_inch_value(size_str: str) -> float:
    """Convert size string like 1-1/2\", 2-1/2\", 3/4\", 2\" to float inches."""
    s = size_str.rstrip('"').rstrip("'").strip()
    if '-' in s:
        parts = s.split('-')
        try:
            w = float(parts[0])
            frac = parts[1].split('/')
            return w + float(frac[0]) / float(frac[1])
        except (ValueError, IndexError):
            return 0.0
    elif '/' in s:
        frac = s.split('/')
        try:
            return float(frac[0]) / float(frac[1])
        except (ValueError, IndexError):
            return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def get_domain_bonus(query: str, raw_cand_name: str, query_sizes: Set[str]) -> float:
    """
    Shop Merchant Heuristics & Preferences:
    1. PVC COUPLING -> starts with 'CO '
    2. UPVC -> starts with 'UPVC ', <= 2\" ASHIRVAD, > 2\" PRINCE
    3. CPVC -> starts with 'CPVC ', exclusively ASHIRVAD
    4. PVC (general/fittings) -> starts with 'AST '
    5. Drill Bit -> starts with 'DR '
    6. Janatics -> starts with 'JA ' + size
    7. Legrand Mylinc / Myrius Switch -> starts with 'MY '
    8. Taparia brand -> starts with 'TAP '
    9. Green Hose:
       - Full roll: starts with 'GHOSE ', brand SONA / SONY
       - Cut length / meter / feet: starts with 'GR '
    """
    q = query.lower()
    c = raw_cand_name.upper().strip()
    bonus = 0.0

    # 1. PVC COUPLING / COUPLER -> 'CO '
    if ("coupling" in q or "coupler" in q) and "cpvc" not in q and "upvc" not in q:
        if c.startswith("CO "):
            bonus += 35.0
        elif " COUPL" in c:
            bonus += 15.0

    # 2. UPVC -> Starts with 'UPVC ', <= 2\" Ashirvad, > 2\" Prince
    elif "upvc" in q:
        if c.startswith("UPVC "):
            bonus += 20.0
            max_size = 0.0
            for sz in query_sizes:
                val = parse_inch_value(sz)
                if val > max_size:
                    max_size = val
            if max_size > 0:
                if max_size <= 2.0:
                    if "ASHIRVAD" in c:
                        bonus += 25.0
                    elif "ASTRAL" in c:
                        bonus += 15.0
                else:  # > 2"
                    if "PRINCE" in c:
                        bonus += 30.0
            else:
                if "ASHIRVAD" in c:
                    bonus += 15.0

    # 3. CPVC -> Starts with 'CPVC ', Full Ashirvad
    elif "cpvc" in q:
        if c.startswith("CPVC "):
            bonus += 20.0
            if "ASHIRVAD" in c:
                bonus += 25.0

    # 4. PVC: PIPE vs FITTINGS
    # - PVC PIPE -> Starts with 'VI ' (e.g. VI 1" 10KG PVC PIPE (VIJAY))
    # - PVC FITTINGS -> Starts with 'AST ' (e.g. AST 1" ELBOW, AST 1" TEE, AST 1" MTA)
    elif re.search(r'\bpvc\b', q) and not any(k in q for k in ["cpvc", "upvc", "coupling", "coupler"]):
        is_pipe = "pipe" in q and not any(k in q for k in ["elbow", "tee", "mta", "fta", "bend", "union", "bush", "dummy", "reducer", "nipple"])
        is_fitting = any(k in q for k in ["elbow", "tee", "mta", "fta", "bend", "union", "bush", "dummy", "reducer", "nipple", "fitting", "socket", "end cap"])

        if is_pipe:
            if c.startswith("VI ") and "PIPE" in c:
                bonus += 40.0
            elif c.startswith("VI "):
                bonus += 30.0
            elif "PIPE" in c:
                bonus += 15.0
        elif is_fitting:
            if c.startswith("AST "):
                bonus += 40.0
            elif "ASTRAL" in c:
                bonus += 25.0
            if "bend" in q and c.startswith("BE "):
                bonus += 35.0
        else:
            if c.startswith("AST "):
                bonus += 25.0
            elif c.startswith("VI "):
                bonus += 20.0

    # 5. DRILL BIT -> Starts with 'DR '
    if "drill" in q or "bit" in q:
        if c.startswith("DR "):
            bonus += 35.0

    # 6. JANATICS -> Starts with 'JA ' + size
    if "janatics" in q or "janatic" in q:
        if c.startswith("JA "):
            bonus += 35.0

    # 7. LEGRAND MYLINC / MYRIUS SWITCH -> Starts with 'MY '
    if any(k in q for k in ["mylinc", "myrius"]) or ("legrand" in q and "switch" in q):
        if c.startswith("MY "):
            bonus += 35.0

    # 8. TAPARIA -> Starts with 'TAP '
    if "taparia" in q or "tapariya" in q:
        if c.startswith("TAP "):
            bonus += 35.0

    # 9. GREEN HOSE
    if "green hose" in q or "ghose" in q or ("hose" in q and "green" in q):
        is_cut = any(k in q for k in ["cut", "mtr", "meter", "feet", "ft", "feets"])
        if is_cut:
            if c.startswith("GR "):
                bonus += 35.0
        else:
            if c.startswith("GHOSE "):
                bonus += 25.0
            if "SONA" in c or "SONY" in c:
                bonus += 20.0

    return bonus


class ItemMatcher:
    def __init__(self, items: Optional[List[Dict[str, Any]]] = None, memory: Optional[ItemMemory] = None):
        if items is None:
            items = sync_items_cache(force_refresh=False)
        self.items = items
        self.memory = memory or ItemMemory()
        self.item_names = [it["item_name"] for it in items]
        self.normalized_names = [normalize_text(name) for name in self.item_names]
        self.item_sizes = [extract_sizes(name) for name in self.item_names]
        self.index_to_item = {i: it for i, it in enumerate(items)}
        self.items_by_name = {it["item_name"].strip().lower(): it for it in items}
        logger.info(f"ItemMatcher initialized with {len(self.items):,} items and {len(self.memory.memory)} learned memories.")

    def search_candidates(self, keyword: str, limit: int = 15) -> List[Dict[str, Any]]:
        """Search Optech items by keyword for UI autocomplete / mapping."""
        if not keyword or not keyword.strip():
            return []
        norm_kw = normalize_text(keyword)
        words = norm_kw.split()
        kw_sizes = extract_sizes(keyword)
        candidates = []
        for i, norm_name in enumerate(self.normalized_names):
            if all(w in norm_name for w in words):
                item = self.index_to_item[i]
                bonus = get_domain_bonus(keyword, item["item_name"], kw_sizes)
                candidates.append((bonus, item))

        # Sort by domain bonus descending so preferred brands/prefixes appear first
        candidates.sort(key=lambda x: x[0], reverse=True)
        return [it for _, it in candidates[:limit]]

    def match_item(self, query: str, score_cutoff: float = 50.0) -> Optional[Dict[str, Any]]:
        """
        Fuzzy match query with memory lookup, strict hardware size validation, and token ranking.
        """
        if not query or not query.strip():
            return None

        # ----------------------------------------------------
        # 1. CHECK LEARNED MEMORY FIRST (Instant 100% Match):
        # ----------------------------------------------------
        memorized_name = self.memory.get_mapping(query)
        if memorized_name:
            exact_item = self.items_by_name.get(memorized_name.strip().lower())
            if exact_item:
                res = dict(exact_item)
                res["match_score"] = 100.0
                res["memorized"] = True
                res["needs_review"] = False
                return res

        norm_query = normalize_text(query)
        query_sizes = extract_sizes(query)
        query_tokens = set(norm_query.split())

        best_index = -1
        best_score = 0.0

        for i, norm_cand in enumerate(self.normalized_names):
            cand_sizes = self.item_sizes[i]

            # ----------------------------------------------------
            # 2. STRICT SIZE MATCHING:
            # ----------------------------------------------------
            if query_sizes:
                if cand_sizes:
                    if not query_sizes.issubset(cand_sizes) and not cand_sizes.issubset(query_sizes):
                        continue

            # ----------------------------------------------------
            # ----------------------------------------------------
            # 3. MATERIAL CONFLICT FILTER:
            # ----------------------------------------------------
            cand_tokens = set(norm_cand.split())
            if "upvc" in query_tokens and "cpvc" in cand_tokens:
                continue
            if "cpvc" in query_tokens and "upvc" in cand_tokens:
                continue
            if "pvc" in query_tokens and "cpvc" not in query_tokens and "upvc" not in query_tokens:
                if "cpvc" in cand_tokens:
                    continue

            # ----------------------------------------------------
            # 4. PIPE vs FITTING MUTUAL EXCLUSION:
            # ----------------------------------------------------
            query_is_fitting = any(k in query_tokens for k in ["elbow", "tee", "mta", "fta", "bend", "union", "bush", "dummy", "reducer", "nipple"])
            query_is_pipe = ("pipe" in query_tokens) and not query_is_fitting

            cand_is_pipe = ("pipe" in cand_tokens) and not any(k in cand_tokens for k in ["elbow", "tee", "mta", "fta", "bend", "union", "bush", "dummy", "reducer"])
            cand_is_fitting = any(k in cand_tokens for k in ["elbow", "tee", "mta", "fta", "bend", "union", "bush", "dummy", "reducer", "coupling"])

            if query_is_fitting and cand_is_pipe:
                continue
            if query_is_pipe and cand_is_fitting:
                continue

            # Fitting Type Specificity
            fitting_mismatch = False
            for f_key in ["mta", "fta", "elbow", "tee", "bend", "union", "bush", "dummy", "reducer"]:
                if f_key in query_tokens and f_key not in cand_tokens:
                    fitting_mismatch = True
                    break
            if fitting_mismatch:
                continue

            if norm_query == norm_cand:
                res = dict(self.index_to_item[i])
                res["match_score"] = 100.0
                res["memorized"] = False
                res["needs_review"] = False
                return res

            if fuzz:
                set_ratio = fuzz.token_set_ratio(norm_query, norm_cand)
                sort_ratio = fuzz.token_sort_ratio(norm_query, norm_cand)
                partial_ratio = fuzz.partial_ratio(norm_query, norm_cand)
                score = (0.4 * set_ratio) + (0.4 * sort_ratio) + (0.2 * partial_ratio)
            else:
                common = len(query_tokens.intersection(cand_tokens))
                score = (common / max(len(query_tokens), 1)) * 100.0

            matched_words = query_tokens.intersection(cand_tokens)
            coverage = len(matched_words) / max(len(query_tokens), 1)
            score = score * (0.6 + 0.4 * coverage)

            if query_sizes and query_sizes == cand_sizes:
                score += 10.0

            # Domain Rules Bonus (Shop Merchant Heuristics)
            raw_cand_name = self.item_names[i]
            score += get_domain_bonus(query, raw_cand_name, query_sizes)

            for qt in query_tokens:
                if len(qt) <= 3 and qt in cand_tokens:
                    score += 5.0

            if score > best_score:
                best_score = score
                best_index = i

        if best_index >= 0 and best_score >= score_cutoff:
            res = dict(self.index_to_item[best_index])
            res["match_score"] = round(min(best_score, 100.0), 1)
            res["memorized"] = False
            res["needs_review"] = (best_score < 90.0)
            return res

        return None

    def match_multiple(self, query_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        results = []
        for req in query_list:
            query = req.get("item_query") or req.get("item_name") or req.get("name") or ""
            qty = float(req.get("qty", 1) or 1)
            unit = req.get("unit", "Nos")

            matched = self.match_item(query)
            if matched:
                sale_rate = float(matched.get("sale_rate", 0) or 0)
                pur_rate = float(matched.get("purchase_rate", 0) or 0)
                official_unit = matched.get("unit") or unit or "Nos"
                results.append({
                    "requested_name": query,
                    "matched_item_name": matched["item_name"],
                    "group_name": matched.get("group_name", ""),
                    "quantity": qty,
                    "unit": official_unit,
                    "sale_rate": sale_rate,
                    "purchase_rate": pur_rate,
                    "amount": round(qty * sale_rate, 2),
                    "hsn_code": matched.get("hsn_code", ""),
                    "match_score": matched.get("match_score", 0),
                    "memorized": matched.get("memorized", False),
                    "needs_review": matched.get("needs_review", False),
                    "found": True,
                })
            else:
                results.append({
                    "requested_name": query,
                    "matched_item_name": "UNKNOWN ITEM",
                    "group_name": "",
                    "quantity": qty,
                    "unit": unit,
                    "sale_rate": 0.0,
                    "purchase_rate": 0.0,
                    "amount": 0.0,
                    "hsn_code": "",
                    "match_score": 0.0,
                    "memorized": False,
                    "needs_review": True,
                    "found": False,
                })
        return results
