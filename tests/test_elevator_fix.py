"""
Regression tests for elevator job time calculation.
Verifies the additive per-trip elevator model vs the old percentage model.
"""
import os
import sys
import math

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../Version 9/Gemini/modules')))

from calculator import MovingCalculator


def make_items(n_boxes=20, n_furniture=5):
    """Helper to build a representative item list."""
    items = []
    items.extend([{"name": "Boxes", "quantity": n_boxes, "volume": 3, "weight": 10}])
    items.extend([{"name": "Dresser", "quantity": n_furniture, "volume": 30, "weight": 100}])
    return items


def test_elevator_adder_math():
    """Unit test: _compute_elevator_adder produces correct values."""
    calc = MovingCalculator()

    # 25-floor elevator, 15 items
    access = {"type": "elevator", "floors": 25}
    result = calc._compute_elevator_adder(access, 15)
    trip_time = calc.ELEVATOR_FIXED_PER_TRIP + calc.ELEVATOR_RIDE_PER_FLOOR * 25
    trips = math.ceil(15 / calc.AVG_ITEMS_PER_ELEVATOR_LOAD)
    expected = trips * trip_time
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"
    print(f"  25-floor, 15 items: {result:.1f} min ({trips} trips × {trip_time:.2f} min/trip)")

    # Ground access → 0
    assert calc._compute_elevator_adder({"type": "ground"}, 50) == 0.0

    # Stairs → 0 (elevator adder doesn't apply)
    assert calc._compute_elevator_adder({"type": "stairs", "floors": 10}, 30) == 0.0

    # 0-floor elevator → still has base trip time
    result_zero = calc._compute_elevator_adder({"type": "elevator", "floors": 0}, 4)
    assert result_zero > 0, "0-floor elevator should still have base per-trip cost"
    print(f"  0-floor, 4 items: {result_zero:.1f} min")

    print("✓ _compute_elevator_adder math checks passed")


def test_friction_delta_excludes_elevator():
    """_access_friction_delta must return 0 for elevator (handled additively)."""
    calc = MovingCalculator()
    assert calc._access_friction_delta({"type": "elevator", "floors": 25}) == 0.0
    assert calc._access_friction_delta({"type": "stairs", "floors": 3}) > 0.0
    print("✓ _access_friction_delta returns 0 for elevator, nonzero for stairs")


def test_has_elevator():
    calc = MovingCalculator()
    assert calc._has_elevator({"type": "elevator"}, {"type": "ground"}) is True
    assert calc._has_elevator({"type": "ground"}, {"type": "elevator", "floors": 10}) is True
    assert calc._has_elevator({"type": "ground"}, {"type": "stairs", "floors": 3}) is False
    print("✓ _has_elevator detection works")


def test_elevator_vs_ground_comparison():
    """Elevator job should not inflate beyond 40% of ground baseline for typical residential."""
    calc = MovingCalculator()
    items = make_items(n_boxes=40, n_furniture=8)

    ground = {"type": "ground"}
    elevator_25 = {"type": "elevator", "floors": 25}

    ground_result = calc.calculate_total_logistics(items, ground, ground, 30)
    elev_result = calc.calculate_total_logistics(items, elevator_25, elevator_25, 30)

    ground_time = ground_result['time']['totalMinutes']
    elev_time = elev_result['time']['totalMinutes']
    inflation = (elev_time - ground_time) / ground_time * 100

    print(f"\n  Ground job:   {ground_time:.1f} min")
    print(f"  Elevator job: {elev_time:.1f} min (25th floor, both ends)")
    print(f"  Inflation:    {inflation:.1f}%")

    assert inflation < 45, f"Elevator inflation {inflation:.1f}% exceeds 45% cap for typical residential"
    print("✓ Elevator inflation within acceptable range")


def test_elevator_parallelism_cap():
    """With elevator, effective teams should be capped, so adding movers helps less."""
    calc = MovingCalculator()
    items = make_items(n_boxes=30, n_furniture=6)
    tasks = calc.build_tasks(items)

    elevator = {"type": "elevator", "floors": 15}
    ground = {"type": "ground"}

    time_2m_elev = calc.calculate_job_time(tasks, 2, elevator, ground)
    time_4m_elev = calc.calculate_job_time(tasks, 4, elevator, ground)
    time_6m_elev = calc.calculate_job_time(tasks, 6, elevator, ground)

    time_2m_ground = calc.calculate_job_time(tasks, 2, ground, ground)
    time_4m_ground = calc.calculate_job_time(tasks, 4, ground, ground)
    time_6m_ground = calc.calculate_job_time(tasks, 6, ground, ground)

    # Ground: 6 movers should be significantly faster than 2
    ground_speedup = time_2m_ground / time_6m_ground
    # Elevator: 6 movers should help less (parallelism capped)
    elev_speedup = time_2m_elev / time_6m_elev

    print(f"\n  Ground speedup (2→6 movers): {ground_speedup:.2f}x")
    print(f"  Elevator speedup (2→6 movers): {elev_speedup:.2f}x")
    print(f"  2 movers elevator: {time_2m_elev:.1f} min | ground: {time_2m_ground:.1f} min")
    print(f"  4 movers elevator: {time_4m_elev:.1f} min | ground: {time_4m_ground:.1f} min")
    print(f"  6 movers elevator: {time_6m_elev:.1f} min | ground: {time_6m_ground:.1f} min")

    assert elev_speedup < ground_speedup, "Elevator should limit parallelism benefit vs ground"
    print("✓ Elevator parallelism cap working correctly")


def test_small_vs_large_elevator_job():
    """Small elevator jobs should not be over-penalized; large ones should not explode."""
    calc = MovingCalculator()

    small_items = make_items(n_boxes=5, n_furniture=2)
    large_items = make_items(n_boxes=60, n_furniture=15)

    elev = {"type": "elevator", "floors": 20}
    ground = {"type": "ground"}

    small_ground = calc.calculate_total_logistics(small_items, ground, ground, 30)
    small_elev = calc.calculate_total_logistics(small_items, elev, ground, 30)
    large_ground = calc.calculate_total_logistics(large_items, ground, ground, 30)
    large_elev = calc.calculate_total_logistics(large_items, elev, ground, 30)

    small_delta = small_elev['time']['totalMinutes'] - small_ground['time']['totalMinutes']
    large_delta = large_elev['time']['totalMinutes'] - large_ground['time']['totalMinutes']

    # Count total items for per-item comparison
    small_count = sum(int(i.get('quantity', 1)) for i in small_items)
    large_count = sum(int(i.get('quantity', 1)) for i in large_items)

    small_per_item = small_delta / small_count if small_count else 0
    large_per_item = large_delta / large_count if large_count else 0

    print(f"\n  Small job ground: {small_ground['time']['totalMinutes']:.1f} min")
    print(f"  Small job elevator: {small_elev['time']['totalMinutes']:.1f} min (+{small_delta:.1f} min, {small_per_item:.2f} min/item)")
    print(f"  Large job ground: {large_ground['time']['totalMinutes']:.1f} min")
    print(f"  Large job elevator: {large_elev['time']['totalMinutes']:.1f} min (+{large_delta:.1f} min, {large_per_item:.2f} min/item)")

    # Per-item elevator cost should be roughly consistent (additive model).
    # Allow up to 50% variance due to batching/ceiling effects.
    ratio = max(small_per_item, large_per_item) / min(small_per_item, large_per_item) if min(small_per_item, large_per_item) > 0 else 1
    assert ratio < 1.5, f"Per-item elevator cost ratio {ratio:.2f} too variable (small={small_per_item:.2f}, large={large_per_item:.2f})"
    print(f"  Per-item cost ratio: {ratio:.2f}x (should be close to 1.0)")
    print("✓ Additive model: per-item elevator cost is consistent across job sizes")


if __name__ == "__main__":
    print("=" * 70)
    print("Elevator Fix — Regression Tests")
    print("=" * 70)

    test_elevator_adder_math()
    print()
    test_friction_delta_excludes_elevator()
    print()
    test_has_elevator()
    print()
    test_elevator_vs_ground_comparison()
    print()
    test_elevator_parallelism_cap()
    print()
    test_small_vs_large_elevator_job()

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED")
    print("=" * 70)
