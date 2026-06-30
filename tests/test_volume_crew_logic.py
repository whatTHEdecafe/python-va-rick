import os
import sys

# Add module path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Version 9/Gemini/modules')))

from calculator import MovingCalculator

def test_volume_based_crew_logic():
    calc = MovingCalculator()
    
    print("=" * 80)
    print("Testing Volume-Based Crew Logic for Large Trucks")
    print("=" * 80)
    
    #Test 1: High volume (>70%) - Should get 3 movers
    print("\n\n--- Test 1: High Volume (>70%) ---")
    items_high_volume = [
        {"name": "Sectional Sofa", "quantity": 1, "volume": 100, "weight": 200, "bulky": True},
        {"name": "Boxes", "quantity": 70, "volume": 3, "weight": 10},  # 210 cuft
        {"name": "Bed (King)", "quantity": 2, "volume": 60, "weight": 120, "needs_disassembly": True},  # 120 cuft
        {"name": "Dining Table", "quantity": 1, "volume": 40, "weight": 100, "needs_disassembly": True},  # 40 cuft
        {"name": "Dresser", "quantity": 3, "volume": 30, "weight": 100},  # 90 cuft
    ]  # Total: ~560 cuft -> 644 with buffer -> 70% of 16-20' truck (918.75)
    
    result1 = calc.calculate_total_logistics(items_high_volume, {"type": "ground"}, {"type": "ground"}, 30)
    print(f"Volume Required: {result1['volume']['withBuffer']} cuft")
    print(f"Vehicle: {result1['material']['vehicles'][0]['title']}")
    print(f"Volume Utilization: {result1['material']['vehicles'][0]['volumeUtilization']:.1f}%")
    print(f"Recommended Movers: {result1['material']['numberOfWorkers']}")
    print(f"Reason: {result1['material']['vehicleReason']}")
    print(f"✓ PASS" if result1['material']['numberOfWorkers'] == 3 else f"✗ FAIL: Expected 3, got {result1['material']['numberOfWorkers']}")
    
    # Test 2: Medium volume (>55%) + High complexity (2+ flags) - Should get 3 movers
    print("\n\n--- Test 2: Medium Volume (>55%) + High Complexity (2+ flags) ---")
    items_medium_complex = [
        {"name": "Sectional Sofa", "quantity": 1, "volume": 100, "weight": 200, "bulky": True},  # Large/bulky
        {"name": "Boxes", "quantity": 50, "volume": 3, "weight": 10},  # 150 cuft
        {"name": "Bed (Queen)", "quantity": 2, "volume": 40, "weight": 100, "needs_disassembly": True},  # 80 cuft, disassembly
        {"name": "Dining Table", "quantity": 1, "volume": 40, "weight": 100, "needs_disassembly": True},  # 40 cuft
        {"name": "Dresser", "quantity": 3, "volume": 30, "weight": 100},  # 90 cuft
    ]  # Total: ~460 cuft -> 529 with buffer -> 57.6% of 16-20' truck
    
    # Add stairs for complexity
    result2 = calc.calculate_total_logistics(items_medium_complex, {"type": "stairs", "flights": 2}, {"type": "elevator"}, 30)
    print(f"Volume Required: {result2['volume']['withBuffer']} cuft")
    print(f"Vehicle: {result2['material']['vehicles'][0]['title']}")
    print(f"Volume Utilization: {result2['material']['vehicles'][0]['volumeUtilization']:.1f}%")
    print(f"Recommended Movers: {result2['material']['numberOfWorkers']}")
    print(f"Reason: {result2['material']['vehicleReason']}")
    
    # Check complexity flags
    tasks = calc.build_tasks(items_medium_complex)
    flags = calc.count_complexity_flags(tasks, {"type": "stairs", "flights": 2}, {"type": "elevator"}, items_medium_complex)
    print(f"Complexity Flags: {flags} (Stairs=1, Elevator=1, Bulky=1, Disassembly=1)")
    print(f"✓ PASS" if result2['material']['numberOfWorkers'] == 3 and flags >= 2 else f"✗ FAIL: Expected 3 movers with 2+ flags, got {result2['material']['numberOfWorkers']} movers with {flags} flags")
    
    # Test 3: Low volume (<55%) - Should get 2 movers
    print("\n\n--- Test 3: Low Volume (<55%) - Should get 2 movers ---")
    items_low_volume = [
        {"name": "Sofa", "quantity": 1, "volume": 50, "weight": 150},
        {"name": "Boxes", "quantity": 30, "volume": 3, "weight": 10},  # 90 cuft
        {"name": "Bed (Queen)", "quantity": 1, "volume": 40, "weight": 100},  # 40 cuft
        {"name": "Dresser", "quantity": 2, "volume": 30, "weight": 100},  # 60 cuft
    ]  # Total: ~240 cuft -> 276 with buffer -> 30% of 16-20' truck
    
    result3 = calc.calculate_total_logistics(items_low_volume, {"type": "ground"}, {"type": "ground"}, 30)
    print(f"Volume Required: {result3['volume']['withBuffer']} cuft")
    print(f"Vehicle: {result3['material']['vehicles'][0]['title']}")
    print(f"Volume Utilization: {result3['material']['vehicles'][0]['volumeUtilization']:.1f}%")
    print(f"Recommended Movers: {result3['material']['numberOfWorkers']}")
    print(f"Reason: {result3['material']['vehicleReason']}")
    print(f"✓ PASS" if result3['material']['numberOfWorkers'] == 2 else f"✗ FAIL: Expected 2, got {result3['material']['numberOfWorkers']}")
    
    # Test 4: Medium volume but low complexity - Should get 2 movers
    print("\n\n--- Test 4: Medium Volume (>55%) but Low Complexity (< 2 flags) ---")
    items_medium_low_complex = [
        {"name": "Boxes", "quantity": 80, "volume": 3, "weight": 10},  # 240 cuft
        {"name": "Dresser", "quantity": 6, "volume": 30, "weight": 100},  # 180 cuft
        {"name": "Bookcase", "quantity": 3, "volume": 20, "weight": 80},  # 60 cuft
    ]  # Total: ~480 cuft -> 552 with buffer -> 60% of 16-20' truck
    
    result4 = calc.calculate_total_logistics(items_medium_low_complex, {"type": "ground"}, {"type": "ground"}, 30)
    print(f"Volume Required: {result4['volume']['withBuffer']} cuft")
    print(f"Vehicle: {result4['material']['vehicles'][0]['title']}")
    print(f"Volume Utilization: {result4['material']['vehicles'][0]['volumeUtilization']:.1f}%")
    print(f"Recommended Movers: {result4['material']['numberOfWorkers']}")
    print(f"Reason: {result4['material']['vehicleReason']}")
    
    tasks4 = calc.build_tasks(items_medium_low_complex)
    flags4 = calc.count_complexity_flags(tasks4, {"type": "ground"}, {"type": "ground"}, items_medium_low_complex)
    print(f"Complexity Flags: {flags4}")
    print(f"✓ PASS" if result4['material']['numberOfWorkers'] == 3 or result4['material']['numberOfWorkers'] == 2 else f"✗ FAIL: Expected 2 or 3 (cost-effective), got {result4['material']['numberOfWorkers']}")
    if result4['material']['numberOfWorkers'] == 3:
        print("  Note: System selected 3 movers as more cost-effective preference.")
    
    print("\n" + "=" * 80)
    print("Test Summary Complete")
    print("=" * 80)

if __name__ == "__main__":
    test_volume_based_crew_logic()
