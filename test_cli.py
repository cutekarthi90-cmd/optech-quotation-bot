import sys
from db_connector import sync_items_cache
from item_matcher import ItemMatcher
from ai_extractor import AIExtractor
from quotation import QuotationService

def main():
    print("=" * 60)
    print("  OPTECH WHATSAPP QUOTATION TEST CLI")
    print("=" * 60)

    print("\n1. Connecting to SQL Server and loading items...")
    try:
        items = sync_items_cache(force_refresh=False)
        print(f"   ✓ Successfully loaded {len(items):,} items from Optech database.")
    except Exception as e:
        print(f"   ✗ Error connecting to database: {e}")
        return

    print("\n2. Initializing Item Matcher & AI Extractor...")
    matcher = ItemMatcher(items=items)
    extractor = AIExtractor()
    service = QuotationService(matcher, extractor)
    print("   ✓ Ready!")

    # Test Sample
    sample_inquiry = """
    Send quote for:
    1. 4 inch cutoff wheel 20 nos
    2. 1 1/2 nrv yash horizontal 5 pcs
    3. totem drill bit 7/64 10 nos
    4. pipe cutter 42mm 1 no
    """
    print("\n3. Testing with Sample Customer Inquiry:")
    print("-" * 40)
    print(sample_inquiry.strip())
    print("-" * 40)

    print("\n4. Processing & Matching against 22,752 items...")
    quote = service.process_text_quotation(sample_inquiry)

    print("\n5. RESULT - WHATSAPP MESSAGE SENT TO CUSTOMER:")
    print(quote["whatsapp_message"])
    print("\n" + "=" * 60)
    print("Test completed successfully!")

if __name__ == "__main__":
    main()
