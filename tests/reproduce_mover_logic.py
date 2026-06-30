import sys
import os
import json

# Add module path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Version 9/Gemini/modules')))

from calculator import MovingCalculator

def run_test():
    calc = MovingCalculator()
    
    # Create a mock job fitting a 10'-12' truck (~400 cuft)
    # 10'-12' truck max volume is 400 cuft
    
    # Let's add items to just fit in 400 cuft but require labor
    items = [
        {"name": "Plastic storage bin (filled)", "quantity": 10, "volume": 3, "weight": 40}, # 30 cuft
        {"name": "Sofa", "quantity": 1, "volume": 50, "weight": 150, "bulky": True}, # 50 cuft
        {"name": "Bed (Queen)", "quantity": 1, "volume": 40, "weight": 100, "needs_disassembly": True}, # 40 cuft
        {"name": "Dresser", "quantity": 2, "volume": 30, "weight": 100}, # 60 cuft
        {"name": "Bookcase", "quantity": 2, "volume": 20, "weight": 80}, # 40 cuft
        {"name": "Boxes", "quantity": 20, "volume": 3, "weight": 10}, # 60 cuft
         # Total Volume: ~280 cuft (Fits in 10'-12' Truck)
    ]
    
    pickup = {"type": "stairs", "flights": 1} # Add friction
    dropoff = {"type": "elevator"} 
    
    print("--- Running Reproduction Test (Small Vehicle) ---")
    result = calc.calculate_total_logistics(items, pickup, dropoff)
    
    movers = result['material']['numberOfWorkers']
    trucks = result['material']['totalTrucks']
    vehicles = result['material']['vehicles']
    time_p50 = result['time']['totalHours']
    price = result['pricing']['totalExpectedPrice']
    base_price = result['pricing']['basePrice']
    
    print(f"Recommended Movers: {movers}")
    print(f"Total Trucks: {trucks}")
    print(f"Vehicles: {vehicles}")
    print(f"Estimated Time (P50): {time_p50} hours")
    print(f"Base Price: ${base_price}")
    print(f"Total Price: ${price}")

    # Manual verification calc
    # Base Price = Total Hours * Movers * $85
    expected_base = time_p50 * movers * 85
    print(f"Expected Base Price ({time_p50} * {movers} * 85): ${expected_base:.2f}")

    if abs(expected_base - base_price) < 1.0:
        print("SUCCESS: Price matches $85/hr/mover rate")
    else:
        print("FAIL: Price calculation mismatch")
    
    # Detailed efficiency check
    print("\n--- Efficiency Check (Internal) ---")
    
    vehicle_title = vehicles[0]['title'] if vehicles else "None"
    
    if "10'-12' Truck" in vehicle_title:
         print(f"SUCCESS: Vehicle renamed correctly to {vehicle_title}")
    else:
         print(f"FAIL: Vehicle title incorrect: {vehicle_title}")

    if movers <= 2:
        print(f"SUCCESS: Small vehicle ({vehicle_title}) restricted to {movers} movers (matches requirement)")
    else:
        print(f"FAIL: Small vehicle ({vehicle_title}) has {movers} movers (should be max 2)")
    
    print("\n--- Time Breakdown Verification ---")
    time_info = result['time']
    print(f"Pre-Move Travel: {time_info.get('preMoveTravel')} min")
    print(f"Loading Time: {time_info.get('loadingTime')} min")
    print(f"Driving Time: {time_info.get('travelBetweenLocations')}")
    print(f"Unloading Time: {time_info.get('unloadingTime')} min")
    print(f"Total Minutes: {time_info.get('totalMinutes')} min")
    
    # Check if Total Minutes = Loading + Unloading + Pre-Move
    calculated_total = time_info.get('loadingTime', 0) + time_info.get('unloadingTime', 0) + time_info.get('preMoveTravel', 0)
    print(f"Calculated Sum: {calculated_total} min")
    if abs(calculated_total - time_info.get('totalMinutes', 0)) < 0.2:
        print("SUCCESS: Total minutes matches Loading + Unloading + 30m Pre-Move")
    else:
        print("FAIL: Total minutes does NOT match the components")
    
    # Detailed efficiency check
    print("\n--- Efficiency Check (Internal) ---")
    # We can't easily peek inside without modifying the class, 
    # but we can infer from the output.
    
    if movers == 4 and trucks == 1:
        print("FAIL: Recommends 4 movers for a single truck job (Current Behavior)")
    elif movers == 3 and trucks == 1:
        print("SUCCESS: Recommends 3 movers for a single truck job")
    else:
        print(f"Result: {movers} movers, {trucks} trucks")

if __name__ == "__main__":
    run_test()
