"""
Stage 3: Map AI-detected items to the JSON catalog (weight, volume, baseTime, category).
"""

from typing import Any, Dict, List

from .calculator import MovingCalculator


def enrich_items(calculator: MovingCalculator, raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Attach catalog fields to each detected item without calling Gemini.

    Preserves AI fields (name, quantity, location, disassemble, size hint from model).
    Fills weight, volume, category, resolved size, and baseTime from the catalog when missing.
    """
    enriched: List[Dict[str, Any]] = []

    for item in raw_items:
        row = dict(item)
        name = row.get('name', 'Unknown')
        lookup_key = row.get('category') or name
        cat_def = calculator.find_item_category(lookup_key)
        if not cat_def and lookup_key != name:
            cat_def = calculator.find_item_category(name)

        if cat_def:
            size = row.get('size') if row.get('size') in ('small', 'medium', 'large') else None
            if not size:
                size = calculator.choose_size_for_item(name, cat_def)
            row['size'] = size
            row['category'] = cat_def.get('category', name)

            if 'weight' not in row:
                row['weight'] = cat_def.get('weight', {}).get(size, 0)
            if 'volume' not in row:
                row['volume'] = cat_def.get('volume', {}).get(size, 0)

            base_time = cat_def.get('baseTime', {}).get(size, 5.0)
            row['catalog_base_time'] = base_time
            row['catalog_category'] = cat_def.get('category', name)
        else:
            row.setdefault('size', 'medium')
            row.setdefault('category', 'Unknown')
            row.setdefault('weight', 20)
            row.setdefault('volume', 5)
            row['catalog_base_time'] = 5.0

        enriched.append(row)

    return enriched
