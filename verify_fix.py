
import sys
import os
import json

# Add Version 7/Gemini to path
gemini_path = os.path.abspath("Version 7/Gemini")
sys.path.append(gemini_path)

try:
    from modules.calculator import MovingCalculator
except ImportError:
    # Try alternate import if running from root
    sys.path.append(os.path.abspath("Version 7/Gemini"))
    from modules.calculator import MovingCalculator

def verify():
    print("Initializing calculator...")
    calc = MovingCalculator(
        items_file="Data/moving_items_logistics_v2.json",
        rules_file="Data/moving_calculation_rules.json"
    )
    
    # Test item known to have null logic in updated DB (e.g. Mattress)
    item_name = "Mattress"
    print(f"Testing item: {item_name}")
    
    category = calc.find_item_category(item_name)
    if not category:
        print("❌ Category not found!")
        return
        
    print(f"Category found: {category['category']}")
    print(f"Classification Logic: {category.get('classificationLogic')}")
    
    try:
        size = calc.classify_size(item_name, category)
        print(f"✅ Size classified successfully: {size}")
    except Exception as e:
        print(f"❌ Error during classification: {e}")
        raise e

if __name__ == "__main__":
    verify()
