
import csv
import json
import os
import datetime

def parse_sml_string(value_str):
    """
    Parses strings like "S: twin; M: full/queen; L: king" 
    or "S: no / M: yes / L: yes" into a dictionary.
    """
    value_str = value_str.strip()
    if not value_str:
        return {"small": None, "medium": None, "large": None}
    
    # Check if it's a simple Yes/No for all
    if value_str.lower() == "yes":
        return {"small": True, "medium": True, "large": True}
    if value_str.lower() == "no":
        return {"small": False, "medium": False, "large": False}
        
    result = {"small": None, "medium": None, "large": None}
    
    # Try splitting by semicolon first (common for notes)
    parts = []
    if ';' in value_str:
        parts = value_str.split(';')
    elif '/' in value_str and ('S:' in value_str or 'M:' in value_str):
        # Handle "S: yes / M: no" style
        parts = value_str.split('/')
    else:
        # Fallback treat as single value if no separators
        # But wait, looking at CSV: "S: twin; M: full/queen..." use semicolons usually
        pass

    # Normalized parsing
    # Strategy: Find "S:", "M:", "L:" positions
    s_idx = value_str.find("S:")
    m_idx = value_str.find("M:")
    l_idx = value_str.find("L:")
    
    # Helper to extract value between indices
    def extract(start, end):
        if start == -1: return None
        val = value_str[start+2:end].strip(" ;/.,")
        # Boolean conversion
        if val.lower() in ['yes', 'true']: return True
        if val.lower() in ['no', 'false']: return False
        if val.lower() == 'maybe': return 'maybe' # Special case, treat as True or string? Protocol says bool in JSON usually.
        # If the target is boolean, 'maybe' usually implies special handling. 
        # Existing JSON has "twoPersonRequired": {"small": false...}
        # CSV has "S: maybe". We might map maybe -> True or False? 
        # Let's keep it as string if it's not strictly yes/no, OR map "maybe" to True for safety?
        # Re-reading existing JSON: "twoPersonRequired": {"small": false...}
        # Let's strict parse booleans if possible.
        return val

    # Determine order
    indices = sorted([('small', s_idx), ('medium', m_idx), ('large', l_idx)], key=lambda x: x[1])
    
    for i, (key, idx) in enumerate(indices):
        if idx != -1:
            end = indices[i+1][1] if i < 2 and indices[i+1][1] != -1 else len(value_str)
            val = extract(idx, end)
            
            # Post-process booleans
            if isinstance(val, str):
                if val.lower() == 'yes': val = True
                elif val.lower() == 'no': val = False
            
            result[key] = val
            
    # Fallback if parsing failed but simple string key present (e.g. just "S: x")
    if result['small'] is None and result['medium'] is None and result['large'] is None:
         # Maybe it's a single value for all?
         pass

    return result

def parse_float(val):
    try:
        return float(val)
    except:
        return 0.0

def parse_int(val):
    try:
        return int(float(val)) # handle "1.0"
    except:
        return 0

def main():
    csv_path = 'Data/Object Database (Dec. 16) - updated categories & disassembly.xlsm - residential_move_items.csv'
    json_path = 'Data/moving_items_logistics_v2.json'
    
    categories = []
    
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        # Verify reader fieldnames
        # headers: canonical_item,aliases,classification_logic_notes,cu_ft_s,cu_ft_m,cu_ft_l,...
        
        # Skip the second header row (the one with units/descriptions if DictReader didn't catch it?)
        # Wait, the file has:
        # Line 1: ITEM,ITEM,,DIMENSIONS...
        # Line 2: canonical_item,aliases...
        # DictReader uses the first line by default.
        # We need to skip line 1 and use line 2 as headers.
        pass
    
    # Re-open to handle header manually
    with open(csv_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # Line 0 is the super-header, Line 1 is the actual keys
    header_line = lines[1].strip()
    keys = header_line.split(',')
    
    # Parse data lines
    data_lines = csv.DictReader(lines[2:], fieldnames=keys)
    
    for row in data_lines:
        if not row['canonical_item']: continue
        
        # Filter out Boxes as per user request
        if row['canonical_item'].startswith('Boxes'):
            continue

        if row['canonical_item'] == 'Wardrobe moving box':
            continue
            
        # Aliases
        aliases = [a.strip() for a in row['aliases'].split(';') if a.strip()]
        
        # Classification Logic
        cls_logic_str = row['classification_logic_notes']
        cls_logic = parse_sml_string(cls_logic_str)
        
        # 2-person
        two_person_str = row['two_person_flag']
        two_person = parse_sml_string(two_person_str)
        # Handle "maybe" -> True for safety
        for k in two_person:
            if two_person[k] == 'maybe': two_person[k] = False # Default strict? Or True? 
            # Existing data had "false" for small. Let's assume False unless "Yes".
        
        item_entry = {
            "category": row['canonical_item'],
            "aliases": aliases,
            "classificationLogic": cls_logic,
            "volume": {
                "small": parse_float(row['cu_ft_s']),
                "medium": parse_float(row['cu_ft_m']),
                "large": parse_float(row['cu_ft_l'])
            },
            "weight": {
                "small": parse_float(row['weight_s_lb']),
                "medium": parse_float(row['weight_m_lb']),
                "large": parse_float(row['weight_l_lb'])
            },
            "baseTime": {
                "small": parse_float(row['load_time_s_min']),
                "medium": parse_float(row['load_time_m_min']),
                "large": parse_float(row['load_time_l_min'])
            },
            "disassemblyAdder": {
                "small": parse_float(row['disassembly_adder_s_min']),
                "medium": parse_float(row['disassembly_adder_m_min']),
                "large": parse_float(row['disassembly_adder_l_min'])
            },
            "bulkyAdder": {
                "small": parse_float(row['bulky_adder_s_min']),
                "medium": parse_float(row['bulky_adder_m_min']),
                "large": parse_float(row['bulky_adder_l_min'])
            },
            "heavyAdder": {
                "small": parse_float(row['heavy_adder_s_min']),
                "medium": parse_float(row['heavy_adder_m_min']),
                "large": parse_float(row['heavy_adder_l_min'])
            },
            "twoPersonRequired": two_person,
            "stackable": row['stackable_flag'].lower() == 'yes',
            "stackableSavings": parse_int(row['stackable_savings_pct']),
            "elevatorFit": row['fits_elevator_hint']
        }
        
        categories.append(item_entry)
        
    # Construct final JSON
    final_data = {
        "movingItemsLogistics": {
            "metadata": {
                "description": "Complete moving logistics database from Bob's residential move items catalog",
                "version": "2.1",
                "lastUpdated": datetime.date.today().isoformat(),
                "source": "Object Database (Dec. 16) - updated categories & disassembly.xlsm - residential_move_items.csv",
                "units": {
                    "volume": "cubic feet",
                    "weight": "pounds",
                    "time": "minutes",
                    "sizes": ["small", "medium", "large"]
                }
            },
            "categories": categories
        }
    }
    
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(final_data, f, indent=2)
        
    print(f"Successfully updated {json_path} with {len(categories)} items.")

if __name__ == "__main__":
    main()
