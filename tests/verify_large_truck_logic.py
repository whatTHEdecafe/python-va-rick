import os
import sys

# Add module path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Version 9/Gemini/modules')))

from calculator import MovingCalculator

def verify_large_truck_preference():
    calc = MovingCalculator()
    
    print("=" * 80)
    print("Verifying Large Truck (26') Planner Logic")
    print("=" * 80)
    print("Scenario: Large Truck (26'), Medium volume (e.g. 40%), Low complexity")
    print("Efficiency Factors: 2 movers = 1.0, 3 movers = 1.6")
    print("Target: Should prefer 3 movers if cheaper/faster, but currently forces 2?")
    
    # Create items for ~56% of 26' truck (approx 1000 cuft with buffer)
    # 16-20' truck max = 918.75 cuft
    # We need > 918.75 cuft to force 26' truck
    items = [
        {"name": "Boxes", "quantity": 290, "volume": 3, "weight": 10}, # 870 cuft
    ] # Total 870 cuft -> ~1000 with buffer -> ~56.5% of 26' truck
    
    # Run calculation
    result = calc.calculate_total_logistics(items, {"type": "ground"}, {"type": "ground"}, 30)
    
    print(f"\nResults:")
    print(f"  Volume: {result['volume']['totalCubicFeet']} cuft ({result['volume']['utilizationPercentage']}%)")
    print(f"  Vehicle: {result['material']['vehicles'][0]['title']}")
    print(f"  Recommended Crew: {result['material']['numberOfWorkers']}")
    print(f"  Reason: {result['material']['vehicleReason']}")
    print(f"  Price: ${result['pricing']['totalExpectedPrice']}")
    
    if result['material']['numberOfWorkers'] == 2:
        print("\nanalysis: System recommended 2 movers.")
        print("hypothesis: This is due to the hard-coded 'Else -> 2 movers' rule.")
    else:
        print(f"\nanalysis: System recommended {result['material']['numberOfWorkers']} movers.")

if __name__ == "__main__":
    verify_large_truck_preference()
