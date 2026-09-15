from typing import List, Dict, Any, Optional
from datetime import datetime
from pricing import PricingEngine


def generate_whatsapp_message(quotation_data: Dict[str, Any], customer_name: str = "Customer") -> str:
    """Format quotation into a clean WhatsApp message."""
    items = quotation_data.get("items", [])
    grand_total = quotation_data.get("grand_total", 0.0)
    pricing_mode = quotation_data.get("pricing_mode", "standard")
    date_str = datetime.now().strftime("%d-%m-%Y %I:%M %p")

    mode_label = "Standard Rates" if pricing_mode == "standard" else "Special Estimate (Markup Applied)"

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📋 *QUOTATION ESTIMATE*",
        f"📅 Date: {date_str}",
        f"⚙️ Type: {mode_label}",
        "━━━━━━━━━━━━━━━━━━━━━━\n"
    ]

    unmatched = []

    for i, it in enumerate(items, 1):
        if it.get("found") and not it.get("needs_review"):
            item_name = it["matched_item_name"]
            group = it.get("group_name", "")
            qty = it["quantity"]
            unit = it.get("unit", "Nos")
            rate = it["effective_rate"]
            amount = it["amount"]
            hsn = it.get("hsn_code", "")

            hsn_str = f" [HSN: {hsn}]" if hsn else ""
            lines.append(f"*{i}. {item_name}*{hsn_str}")
            lines.append(f"   🔢 Qty: {qty} {unit} × ₹{rate:,.2f} = *₹{amount:,.2f}*\n")
        else:
            unmatched.append(it.get("requested_name", "Unknown item"))

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    gst_pct = float(quotation_data.get("gst_percent", 18.0) or 0.0)
    if gst_pct > 0:
        gst_amount = round(grand_total * (gst_pct / 100.0), 2)
        total_with_tax = round(grand_total + gst_amount, 2)
        lines.append(f"Subtotal: ₹{grand_total:,.2f}")
        lines.append(f"GST ({gst_pct:.0f}%): ₹{gst_amount:,.2f}")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append(f"💰 *GRAND TOTAL (Incl. GST): ₹{total_with_tax:,.2f}*")
    else:
        lines.append(f"💰 *TOTAL AMOUNT: ₹{grand_total:,.2f}*")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━")

    if unmatched:
        lines.append("\n⚠️ *Items to verify / confirm manually:*")
        for un in unmatched:
            lines.append(f" • {un}")

    lines.append("\n_Note: Rates subject to final confirmation._")
    return "\n".join(lines)


class QuotationService:
    def __init__(self, matcher, extractor, pricing: Optional[PricingEngine] = None):
        self.matcher = matcher
        self.extractor = extractor
        self.pricing = pricing or PricingEngine()

    def process_items(self, raw_items: List[Dict[str, Any]], pricing_mode: str = "standard") -> Dict[str, Any]:
        matched_items = self.matcher.match_multiple(raw_items)
        grand_total = 0.0

        for it in matched_items:
            # Apply pricing mode (standard sale rate vs group markup)
            rate_info = self.pricing.calculate_rate(it, pricing_mode=pricing_mode)
            effective_rate = rate_info["effective_rate"]
            qty = it.get("quantity", 1.0)
            line_amount = round(qty * effective_rate, 2)

            it["effective_rate"] = effective_rate
            it["amount"] = line_amount
            it["pricing_mode"] = pricing_mode
            it["markup_percent"] = rate_info["markup_percent"]
            it["base_purchase_rate"] = rate_info["base_purchase_rate"]

            if it.get("found") and not it.get("needs_review"):
                grand_total += line_amount

        data = {
            "items": matched_items,
            "pricing_mode": pricing_mode,
            "grand_total": round(grand_total, 2),
            "total_items": len(matched_items),
            "has_unrecognized": any(it.get("needs_review") or not it.get("found") for it in matched_items)
        }
        data["whatsapp_message"] = generate_whatsapp_message(data)
        return data

    def process_text_quotation(self, text: str, pricing_mode: str = "standard") -> Dict[str, Any]:
        raw_items = self.extractor.extract_from_text(text)
        res = self.process_items(raw_items, pricing_mode=pricing_mode)
        res["input_type"] = "text"
        return res

    def process_image_quotation(self, image_bytes: bytes, mime_type: str = "image/jpeg", pricing_mode: str = "standard") -> Dict[str, Any]:
        raw_items = self.extractor.extract_from_image(image_bytes, mime_type=mime_type)
        res = self.process_items(raw_items, pricing_mode=pricing_mode)
        res["input_type"] = "image"
        return res
