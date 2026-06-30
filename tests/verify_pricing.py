import os
import sys

# Add module path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Version 9/Gemini/modules')))

from calculator import MovingCalculator

def verify_pricing():
    calc = MovingCalculator()
    
    print("=" * 80)
    print("Verifying Pricing: $85/hr per mover (linear scaling)")
    print("=" * 80)
    
    # Simple test job
    items = [
        {"name": "Sofa", "quantity": 1, "volume": 50, "weight": 150},
        {"name": "Boxes", "quantity": 30, "volume": 3, "weight": 10},
    ]
    
    result = calc.calculate_total_logistics(items, {"type": "ground"}, {"type": "ground"}, 30)
    
    print(f"\nJob Details:")
    print(f"  Movers: {result['material']['numberOfWorkers']}")
    print(f"  Total Time: {result['time']['totalHours']} hours")
    print(f"  Base Price: ${result['pricing']['basePrice']:.2f}")
    print(f"  Breakdown: {result['pricing']['breakdown']}")
    
    # Verify calculation
    movers = result['material']['numberOfWorkers']
    hours = result['time']['totalHours']
    expected_price = movers * 85 * hours
    
    print(f"\nVerification:")
    print(f"  Expected: {movers} movers × $85/hr × {hours:.2f} hrs = ${expected_price:.2f}")
    print(f"  Actual: ${result['pricing']['basePrice']:.2f}")
    print(f"  Match: {'✓ PASS' if abs(expected_price - result['pricing']['basePrice']) < 0.01 else '✗ FAIL'}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    verify_pricing()
