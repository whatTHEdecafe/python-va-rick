# 📊 JSON Data Configuration Files

This directory contains the core data configuration files that power the Moovez Vision Agent's logistics calculations and quote generation system.

---

## 📋 Table of Contents

- [Overview](#overview)
- [File Descriptions](#file-descriptions)
- [Version Comparison](#version-comparison)
- [Data Structure](#data-structure)
- [Usage Guidelines](#usage-guidelines)

---

## 🎯 Overview

The JSON files in this directory serve as the knowledge base for the Vision Agent, containing:
- **Item specifications** (volume, weight, time estimates)
- **Calculation rules** (stairs, elevators, access multipliers)
- **Category definitions** (item classifications and aliases)
- **Logistics parameters** (disassembly, batching, pricing)

These files eliminate the need for AI models to estimate physical properties, resulting in:
- ⚡ **Faster processing** (no API calls for dimensions/weight)
- 💰 **Lower costs** (reduced AI model usage)
- 🎯 **Higher accuracy** (data-driven vs. AI estimates)
- 📊 **Consistency** (standardized values across all quotes)

---

## 📁 File Descriptions

### 1. `moving_items_logistics_v2.json` ⭐ (Recommended)

**Version**: 2.0  
**Last Updated**: December 16, 2025  
**Used By**: Version 3, 4, 5 & 6 implementations  
**Size**: 22 categories, 78+ item types

#### Purpose
Comprehensive database containing detailed specifications for residential moving items. This is the **primary data source** for Version 3+ of the Vision Agent.

#### Key Features
- ✅ **Extensive item coverage**: 22 distinct categories
- ✅ **Pre-calculated metrics**: Volume, weight, time for all sizes
- ✅ **Smart aliases**: Multiple search terms per category
- ✅ **Classification logic**: Rules for size determination
- ✅ **Complete specifications**: Disassembly, bulky/heavy adders, elevator compatibility
- ✅ **Excludes packing materials**: Focuses on furniture and household items only

#### Data Source
Based on "Bob's residential move items catalog" - a professional moving industry standard database.

#### Categories Included
1. Bed (frame)
2. Mattress
3. Box spring
4. Nightstand
5. Dresser
6. Wardrobe
7. Couch / Sofa
8. Recliner
9. Chair
10. Table
11. TVs (flat panels)
12. TV + media stand
13. Shelves (assembled)
14. Cabinets & chests
15. Refrigerator
16. Washer
17. Dryer
18. Office desk
19. Filing cabinet
20. Piano (upright)
21. Exercise equipment
22. Outdoor furniture

---

### 2. `moving_items_logistics.json`

**Version**: 1.0 
**Last Updated**: October 8, 2025  
**Used By**: Version 2 implementations  
**Size**: 14 categories

#### Purpose
Legacy database with basic item categories and time estimates. Used in earlier versions of the system.

#### Key Features
- ✅ Basic category coverage (15 items)
- ✅ Simple time estimates
- ✅ Elevator compatibility flags
- ✅ Classification logic for sizes

#### Differences from V2
- ❌ **No volume/weight data** (requires AI estimation)
- ❌ **Fewer categories** (14 vs 22)
- ❌ **Less detailed** specifications
- ❌ **No aliases** for flexible matching

#### Categories Included
1. Cabinets & chests
2. Shelves (assembled)
3. Table
4. Bed (frame)
5. Mattress
6. Couch / Sofa
7. Chair
8. TVs (flat panels)
9. TV + media stand
10. Appliances (basic)
11. Office desk
12. Piano
13. Exercise equipment
14. Outdoor furniture

---

### 3. `moving_calculation_rules.json`

**Version**: 1.0  
**Last Updated**: October 8, 2025  
**Used By**: All versions (2 & 3)  
**Compatibility**: Universal

#### Purpose
Contains calculation rules and multipliers for various moving scenarios, including access types, batching logic, and pricing formulas.

#### Key Sections

##### **Base Rules**
- Ground floor/main level rates
- Access multipliers philosophy
- Disassembly impact guidelines

##### **Stairs Calculation**
- Time per flight by item size
- Fatigue multipliers (3+ flights)
- Bulky item penalties
- Maximum penalty caps

##### **Elevator Calculation**
- Time per ride by item size
- High floor adders (10+ floors)
- Batching efficiency rules

##### **Unload Multipliers**
- Ground floor: 0.80x
- Elevator: 0.80x
- Stairs: 0.85x

##### **Batching Rules**
- Stackable items optimization
- Chair batching (2-4 per trip)
- Dolly/cart optimization
- Efficiency calculations

##### **Workforce Planning**
- Workers per truck type
- Item requirements (1-person vs 2-person)

##### **Pricing Calculations**
- Hourly rates
- Insurance fees
- GST/tax rates
- Material costs

---

## 📊 Version Comparison

| Feature | `moving_items_logistics.json` (v1.1) | `moving_items_logistics_v2.json` (v2.0) |
|---------|--------------------------------------|------------------------------------------|
| **Categories** | 14 | 22 |
| **Item Types** | ~38 | 78+ |
| **Volume Data** | ❌ No | ✅ Yes (cu ft) |
| **Weight Data** | ❌ No | ✅ Yes (lbs) |
| **Aliases** | ❌ No | ✅ Yes (multi-term) |
| **Classification Logic** | ✅ Basic | ✅ Advanced |
| **Elevator Fit Info** | ✅ Yes | ✅ Yes |
| **Bulky/Heavy Adders** | ✅ Yes | ✅ Yes |
| **Two-Person Flags** | ❌ No | ✅ Yes |
| **Stackable Info** | ✅ Limited | ✅ Yes |
| **AI Model Dependency** | 🔴 High | 🟢 Low |
| **Processing Speed** | 🟡 Medium | 🟢 Fast |
| **Recommended For** | Version 2 | Version 3 ⭐ |

---

## 🔧 Data Structure

### Item Category Structure (v2.0)

```json
{
  "category": "Bed (frame)",
  "aliases": ["twin", "queen", "king", "bed frame", "headboard"],
  "classificationLogic": {
    "small": "twin",
    "medium": "full/queen",
    "large": "king/ornate"
  },
  "volume": {"small": 10, "medium": 18, "large": 28},
  "weight": {"small": 40, "medium": 90, "large": 140},
  "baseTime": {"small": 10, "medium": 16, "large": 28},
  "disassemblyAdder": {"small": 10, "medium": 20, "large": 30},
  "bulkyAdder": {"small": 3, "medium": 6, "large": 12},
  "heavyAdder": {"small": 3, "medium": 6, "large": 12},
  "twoPersonRequired": {"small": false, "medium": true, "large": true},
  "stackable": false,
  "elevatorFit": "Usually fits if disassembled"
}
```

#### Field Definitions

| Field | Type | Description | Units |
|-------|------|-------------|-------|
| `category` | String | Primary item category name | - |
| `aliases` | Array | Alternative names for matching | - |
| `classificationLogic` | Object | Size classification keywords | - |
| `volume` | Object | Space occupied by item | cubic feet |
| `weight` | Object | Item weight estimates | pounds |
| `baseTime` | Object | Ground floor handling time | minutes |
| `disassemblyAdder` | Object | Additional time if disassembly needed | minutes |
| `bulkyAdder` | Object | Penalty for awkward items | minutes |
| `heavyAdder` | Object | Penalty for heavy items | minutes |
| `twoPersonRequired` | Object | Whether 2 movers needed | boolean |
| `stackable` | Boolean | Can be stacked for transport | - |
| `elevatorFit` | String | Elevator compatibility notes | - |

---

### Calculation Rules Structure

```json
{
  "stairsCalculation": {
    "timePerFlight": {
      "large": 4.0,
      "medium": 3.0,
      "small": 2.0
    },
    "fatigueMultiplier": {
      "threshold": 3,
      "baseMultiplier": 1.15,
      "additionalPerFlight": 0.05,
      "maxMultiplier": 1.35
    },
    "bulkyPenalty": {
      "timePerFloor": 0.5,
      "applicableItems": ["sectionals", "wardrobes", "big tables"],
      "cap": {
        "maxPenalty": 10.0
      }
    }
  }
}
```

---

## 📖 Usage Guidelines

### For Developers

#### 1. **Version Selection**
- **Use v2.0** (`moving_items_logistics_v2.json`) for new implementations
- **Use v1.1** only for legacy Version 2 compatibility

#### 2. **Loading Data**

```python
import json

# Load items database (v2)
with open('moving_items_logistics_v2.json', 'r') as f:
    items_data = json.load(f)['movingItemsLogistics']

# Load calculation rules
with open('moving_calculation_rules.json', 'r') as f:
    rules_data = json.load(f)['movingCalculationRules']
```

#### 3. **Accessing Categories**

```python
# Get all categories
categories = items_data['categories']

# Find specific category
def find_category(item_name):
    for category in categories:
        if category['category'].lower() in item_name.lower():
            return category
        # Check aliases
        for alias in category.get('aliases', []):
            if alias.lower() in item_name.lower():
                return category
    return None
```

#### 4. **Size Classification**

```python
def classify_size(item_name, category_info):
    logic = category_info.get('classificationLogic', {})
    item_lower = item_name.lower()
    
    for size in ['small', 'medium', 'large']:
        keywords = logic.get(size, '').lower().split('/')
        if any(kw.strip() in item_lower for kw in keywords):
            return size
    
    return 'medium'  # default
```

#### 5. **Getting Item Specifications**

```python
def get_item_specs(category_info, size):
    return {
        'volume': category_info['volume'][size],
        'weight': category_info['weight'][size],
        'baseTime': category_info['baseTime'][size],
        'disassemblyTime': category_info['disassemblyAdder'][size]
    }
```

---

### For Data Managers

#### Adding New Categories

1. **Choose appropriate file** (`v2.json` recommended)
2. **Follow structure** from existing categories
3. **Include all required fields**:
   - category (string)
   - aliases (array)
   - classificationLogic (object)
   - volume, weight, baseTime (objects with small/medium/large)
   - disassemblyAdder, bulkyAdder, heavyAdder (objects)
   - twoPersonRequired (object)
   - stackable (boolean)
   - elevatorFit (string)

4. **Update metadata**:
   - Increment version if major changes
   - Update `lastUpdated` date
   - Add notes in description if needed

#### Modifying Existing Values

1. **Document changes** in commit messages
2. **Test thoroughly** before deployment
3. **Consider backward compatibility**
4. **Update version numbers** if breaking changes

---

## 🎯 Best Practices

### 1. **Always Use Latest Version**
- Prefer `moving_items_logistics_v2.json` over v1.1
- Better accuracy, more features, faster processing

### 2. **Validate JSON Before Commit**
```bash
# Use Python to validate
python -m json.tool moving_items_logistics_v2.json > /dev/null
```

### 3. **Document Changes**
- Update `lastUpdated` in metadata
- Add comments in commit messages
- Update this README if structure changes

### 4. **Test Thoroughly**
- Run vision agent tests after modifications
- Verify calculations are reasonable
- Check edge cases (very large/small items)

### 5. **Maintain Consistency**
- Use same units throughout (cu ft, lbs, minutes)
- Follow naming conventions
- Keep structure uniform across categories

---

**Last Updated**: October 27, 2025  
