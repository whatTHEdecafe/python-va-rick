import os
import csv
import json
import math
import uuid
import random
from typing import List, Dict, Any, Optional

# Assuming the JSON data is loaded into this variable structure
# In your app, this would come from your file.
# For this script to run standalone, I assume 'moving_items_logistics_v2.json' exists in ../Data/

class MovingCalculator:
    """
    Re-worked logistics calculator.
    Logic Shift: 
    1. Calculate 'Man-Minutes' per item based on JSON attributes (Base + Disassembly + Bulky + Heavy).
    2. Determine Parallelism via LPT Scheduler.
    3. Apply Environmental Friction (Stairs/Elevator) to the RESULT of the schedule, not the input.
    4. Apply Crew Efficiency (Diminishing Returns).
    """
    
    # Configuration
    WAGE_RATE = 40.0 / 60.0  # $ per minute ($40/hr)
    MONTE_CARLO_RUNS = 500
    UNCERTAINTY = {"low_pct": 0.10, "high_pct": 0.25}
    
    # Crew efficiency (Speedup factor based on EFFECTIVE TEAMS)
    # Most furniture items require 2 people to move safely
    # So 4 movers = 2 effective teams, not 4x parallelism
    # 
    # Effective team calculation:
    # 2 movers = 1 team (baseline)
    # 4 movers = 2 teams = ~1.8x speedup (not 2x due to coordination)
    # 6 movers = 3 teams = ~2.4x speedup (diminishing returns)
    #
    # Reality check: 12.2 hr job with 2 movers → 7 hr with 4 movers
    # Speedup needed = 12.2 / 7 = 1.74x
    CREW_EFFICIENCY = {
        2: 1.0,    # 1 team (baseline)
        3: 1.35,   # 1.5 teams effective (one team + helper)
        4: 1.70,   # 2 teams = ~1.7x speedup
        5: 1.90,   # 2.5 teams effective
        6: 2.10    # 3 teams = ~2.1x speedup (diminishing returns)
    }

    def __init__(self, items_file: Optional[str] = None):
        """Initialize calculator with JSON configuration files"""
        if items_file is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Adjust path as necessary for your project structure
            items_file = os.path.join(current_dir, '..', '..', '..', 'Data', 'moving_items_logistics_v2.json')
        
        self.items_data = {}
        
        try:
            with open(items_file, 'r') as f:
                raw_data = json.load(f)
                self.items_data = raw_data['movingItemsLogistics']
        except Exception as e:
            print(f"Error loading data files: {e}")
            # Fallback minimal structure to prevent crashes
            self.items_data = {"categories": []}

        # Vehicle configurations
        self.available_trucks = [
            {"id": "small", "title": "Pickup Truck", "maxVolume": 48.75, "maxWeight": 2000, "maxSeats": 2},
            {"id": "medium", "title": "Cargo Van", "maxVolume": 213.75, "maxWeight": 4000, "maxSeats": 2},
            {"id": "medium", "title": "10' Truck", "maxVolume": 400, "maxWeight": 3500, "maxSeats": 2},
            {"id": "medium", "title": "16'-20' Truck", "maxVolume": 918.75, "maxWeight": 6000, "maxSeats": 3},
            {"id": "large", "title": "26' Truck", "maxVolume": 1768, "maxWeight": 12500, "maxSeats": 3}
        ]

    # -------------------- Item Lookup & Classification --------------------

    def find_item_category(self, item_name: str) -> Optional[Dict[str, Any]]:
        """
        Find the matching category for an item.
        Checks category name and aliases.
        """
        if not self.items_data or 'categories' not in self.items_data:
            return None
            
        item_name_lower = item_name.lower().strip()
        
        for category in self.items_data['categories']:
            category_name = category.get('category', '').lower()
            
            # Exact match or category name contained in item name
            if category_name == item_name_lower or category_name in item_name_lower:
                return category
            
            # Alias handling
            aliases = category.get('aliases', [])
            for alias in aliases:
                alias_lower = alias.lower()
                # Match exact alias or alias string contained in item name (e.g. "twin bed" matches "twin")
                if alias_lower == item_name_lower or alias_lower in item_name_lower:
                    return category
        return None

    def choose_size_for_item(self, item_name: str, category_def: Dict[str, Any]) -> str:
        """
        Determine size (small/medium/large) based on item name and classification logic.
        """
        if not category_def:
            return 'medium'
            
        classification_logic = category_def.get('classificationLogic', {})
        item_name_lower = item_name.lower()
        
        # 1. Check explicit logic in JSON
        for size in ['small', 'medium', 'large']:
            logic_text = classification_logic.get(size)
            if not logic_text:
                continue
            
            # Simple keyword matching on logic text (e.g. "twin" or "32-40 in")
            keywords = [kw.strip() for kw in logic_text.replace('/', ',').replace('–', '-').split(',')]
            for keyword in keywords:
                if keyword and keyword.lower() in item_name_lower:
                    return size
        
        # 2. Heuristic Fallbacks (if logic not clear)
        small_keywords = ['small', 'compact', 'mini', 'twin', '32"', '40"', 'loveseat']
        large_keywords = ['large', 'king', 'oversized', 'big', 'tall', 'commercial', '60"', 'sectional', 'sleeper']
        
        if any(kw in item_name_lower for kw in small_keywords):
            return 'small'
        elif any(kw in item_name_lower for kw in large_keywords):
            return 'large'
            
        return 'medium'

    # -------------------- Task Construction (The "Man-Minute" Core) --------------------
    
    # JSON baseTime represents the loading phase
    # Unloading is ~20% of loading time (items already wrapped/prepped)
    LOAD_UNLOAD_MULTIPLIER = 1.2

    def compute_base_item_time(self, item: Dict[str, Any], cat_def: Dict[str, Any], size: str) -> float:
        """
        Calculate the wall-clock time for a single item including all JSON modifiers.
        Multiplies by 1.2 to account for both load and unload phases.
        """
        if not cat_def:
            return 6.0  # Default (5 min * 1.2 for load+unload)
            
        base = cat_def.get('baseTime', {}).get(size, 5.0)
        
        # Disassembly
        needs_disassembly = item.get('needs_disassembly', False)
        if needs_disassembly:
             base += cat_def.get('disassemblyAdder', {}).get(size, 0.0)
             
        # Heavy Adder logic
        typical_w = cat_def.get('weight', {}).get(size, 0.0)
        item_weight = item.get('weight', typical_w)
        
        if typical_w > 0 and item_weight > typical_w:
            base += cat_def.get('heavyAdder', {}).get(size, 0.0)
        
        # Apply load+unload multiplier (each item is handled twice: once at pickup, once at dropoff)
        total_time = base * self.LOAD_UNLOAD_MULTIPLIER
            
        return max(total_time, 2.0)  # Minimum 2 minutes (1 min each direction)

    def determine_required_movers(self, cat_def: Dict[str, Any], size: str) -> int:
        """Determine if 1 or 2 movers are required based on JSON"""
        if not cat_def:
            return 1
        return 2 if cat_def.get('twoPersonRequired', {}).get(size, False) else 1

    def build_tasks(self, job_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert input items into standardized tasks with calculated times.
        """
        raw_tasks = []
        
        for item in job_items:
             name = item.get('name', 'Unknown')
             quantity = int(item.get('quantity', 1))
             
             lookup_key = item.get('category') or name
             cat_def = self.find_item_category(lookup_key)
             
             if not cat_def and lookup_key != name:
                 cat_def = self.find_item_category(name)
                 
             # If still no category found, create a generic default
             if not cat_def:
                 # Use default unknown logic
                 size = 'medium'
                 base = 5.0
                 req_movers = 1
                 stackable = False
                 stack_savings = 0
                 weight = item.get('weight', 20)
                 vol = item.get('volume', 5)
             else:
                 size = self.choose_size_for_item(name, cat_def)
                 
                 # Populate weight/vol if missing
                 if 'weight' not in item:
                     item['weight'] = cat_def.get('weight', {}).get(size, 0)
                 if 'volume' not in item:
                     item['volume'] = cat_def.get('volume', {}).get(size, 0)
                 
                 base = self.compute_base_item_time(item, cat_def, size)
                 req_movers = self.determine_required_movers(cat_def, size)
                 stackable = cat_def.get('stackable', False)
                 stack_savings = cat_def.get('stackableSavings', 0)
                 weight = item.get('weight', 0)
                 vol = item.get('volume', 0)
             
             # Create tasks for each unit
             for _ in range(quantity):
                 raw_tasks.append({
                     'id': str(uuid.uuid4()),
                     'name': name,
                     'p': base,                 # Wall clock time (minutes)
                     'q': req_movers,          # Crew required
                     'size': size,
                     'stackable': stackable,
                     'stackableSavings': stack_savings,
                     'weight': weight,
                     'volume': vol
                 })
                 
        return self._apply_stackable_grouping(raw_tasks)

    def _apply_stackable_grouping(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Groups identical stackable items to reduce total time.
        Based on 'stackableSavings' percentage in JSON.
        """
        groups = {}
        final_tasks = []
        
        for task in tasks:
            if task['stackable'] and task['stackableSavings'] > 0:
                # Key by category/size to group similar items
                key = (task['name'], task['size'])
                if key not in groups:
                    groups[key] = []
                groups[key].append(task)
            else:
                final_tasks.append(task)
        
        for key, group_items in groups.items():
            # Sum the raw time
            total_p = sum(t['p'] for t in group_items)
            savings_pct = group_items[0]['stackableSavings']
            
            # Apply savings: Moving 10 boxes takes less than 10x time for 1 box
            combined_p = total_p * (1.0 - (savings_pct / 100.0))
            
            # Max required movers for the group (if one item needs 2, the group needs 2)
            max_q = max(t['q'] for t in group_items)
            
            final_tasks.append({
                'id': str(uuid.uuid4()) + "_batch",
                'name': f"{group_items[0]['name']} (x{len(group_items)})",
                'p': combined_p,
                'q': max_q,
                'count': len(group_items),
                'weight': sum(t['weight'] for t in group_items),
                'volume': sum(t['volume'] for t in group_items),
                'is_batch': True
            })
            
        return final_tasks

    # -------------------- Scheduling & Logic --------------------

    def schedule_for_makers(self, tasks: List[Dict[str, Any]], m: int) -> Dict[str, Any]:
        """
        LPT (Longest Processing Time) scheduling heuristic.
        Distributes tasks to m movers to find the theoretical minimum time (makespan).
        """
        loads = [0.0] * m
        # Sort tasks by duration (longest first)
        sorted_tasks = sorted(tasks, key=lambda x: x['p'], reverse=True)
        
        for task in sorted_tasks:
            p = task['p']
            q = task['q']
            
            # Find the worker(s) with the lowest current load
            # If q=2, we need 2 available workers. 
            # Simplified: We add 'p' to the load. 
            # If q > 1, we consume capacity of 'q' workers?
            # Standard LPT for parallel machines (P|pmtn|Cmax) assumes machines are identical.
            # Here, if q=2, it occupies 2 slots for 'p' time.
            
            # Simplification for Mover Math: 
            # We look for the least loaded subset of workers of size q.
            # For simplicity in this demo: just add to the single least loaded worker 
            # (assuming q=2 means 2 people move it, but it takes 'p' time. 
            # The scheduler balances based on 'p', assuming infinite parallel availability if workers > q).
            
            if q <= 1:
                # Single-person task: add to least loaded worker
                idx = loads.index(min(loads))
                loads[idx] += p
            else:
                # Multi-person task: these workers work TOGETHER for 'p' minutes
                # Find the earliest time when 'q' workers are available
                indexed_loads = sorted(enumerate(loads), key=lambda x: x[1])
                indices = [x[0] for x in indexed_loads[:q]]
                
                # They all start when the last-finishing of the q workers becomes free
                start_time = max(loads[i] for i in indices)
                end_time = start_time + p
                
                # Update all q workers to finish at the same time
                for i in indices:
                    loads[i] = end_time
                    
        return {"makespan": max(loads), "loads": loads}

    def calculate_job_time(self, tasks: List[Dict[str, Any]], movers: int, 
                          pickup_access: Dict[str, Any], 
                          dropoff_access: Dict[str, Any]) -> float:
        """
        Calculate total job time using labor-based model.
        
        Logic:
        1. Sum total labor-minutes from all tasks
        2. Divide by number of effective teams (movers/2 since most items need 2 people)
        3. Apply bottleneck factor (truck door, stairs limit parallelism)
        4. Apply environmental friction (stairs/elevator)
        """
        
        # 1. Total labor: sum of all task times
        # This represents work if done sequentially by one team
        total_labor_minutes = sum(t['p'] for t in tasks)
        
        # 2. Calculate effective teams
        # Replace simple linear (movers/2) with lookup to handle "3rd wheel" inefficiency
        # 2 movers = 1 team
        # 3 movers = 1.25 teams (3rd person is helper, not full partner)
        # 4 movers = 2 teams
        effective_teams_map = {
            2: 1.0,
            3: 1.25,
            4: 2.0,
            5: 2.25,
            6: 3.0
        }
        effective_teams = effective_teams_map.get(movers, movers / 2.0)
        
        # 3. Bottleneck factor - limits how much parallelism actually helps
        # Even with 3 teams, they can't all move items through truck door simultaneously
        # Dynamic bottleneck based on crew size to model congestion clearly
        # 2 movers = 1.0 (No bottleneck)
        # 6 movers = 0.65 (Major bottleneck - "Ant Colony" effect)
        bottleneck_map = {
            2: 1.0,
            3: 0.95,
            4: 0.85,
            5: 0.70,
            6: 0.55
        }
        bottleneck_factor = bottleneck_map.get(movers, 0.60)  
        
        # 4. Calculate base time with parallelism
        if effective_teams <= 1:
            base_time = total_labor_minutes  # No parallelism
        else:
            # Theoretical time = labor / teams
            # Actual time = theoretical / bottleneck factor (i.e., slower)
            theoretical_parallel_time = total_labor_minutes / effective_teams
            base_time = theoretical_parallel_time / bottleneck_factor
        
        # 5. Environmental Friction (stairs/elevator add time)
        friction = 1.0
        
        p_access = pickup_access.get('type', 'ground')
        d_access = dropoff_access.get('type', 'ground')
        
        if 'stairs' in p_access or 'stairs' in d_access:
            friction += 0.20  # 20% slower due to stairs
        if 'elevator' in p_access or 'elevator' in d_access:
            friction += 0.10  # 10% slower due to elevator wait/turns
        if pickup_access.get('longCarry', False) or dropoff_access.get('longCarry', False):
            friction += 0.10
        
        final_time = base_time * friction
        
        return final_time

    # -------------------- Monte Carlo --------------------

    def monte_carlo_estimates(self, tasks: List[Dict[str, Any]]) -> Dict[int, Any]:
        """Generates spread factors (P10, P90) based on task time variance."""
        # (Kept mostly the same as original, just adapted to new task structure)
        results_by_m = {m: [] for m in range(2, 7)}
        
        for _ in range(self.MONTE_CARLO_RUNS):
            sampled_tasks = []
            for t in tasks:
                # Apply uncertainty to duration 'p'
                low = t['p'] * (1.0 - self.UNCERTAINTY['low_pct'])
                high = t['p'] * (1.0 + self.UNCERTAINTY['high_pct'])
                sampled_p = random.uniform(low, high)
                
                task_copy = t.copy()
                task_copy['p'] = sampled_p
                sampled_tasks.append(task_copy)
                
            for m in range(2, 7):
                # Simple schedule for speed (not LPT for every MC run)
                # Just summing man-minutes / crew for MC spread approximation
                total_man_mins = sum(t['p'] * t['q'] for t in sampled_tasks)
                # Very rough estimate for MC speed: Total Work / Crew
                # We'll use the efficiency curve here too
                eff = self.CREW_EFFICIENCY.get(m, 0.85)
                est_time = (total_man_mins / eff) / m
                results_by_m[m].append(est_time)
                
        summary = {}
        for m in range(2, 7):
            times = sorted(results_by_m[m])
            if not times:
                continue
            p50 = times[len(times)//2]
            summary[m] = {
                "p10_factor": times[int(len(times)*0.1)] / p50,
                "p90_factor": times[int(len(times)*0.9)] / p50
            }
        return summary

    # -------------------- Main Public Interface --------------------

    def calculate_total_logistics(self, items: List[Dict[str, Any]], 
                                 pickup_access: Dict[str, Any],
                                 dropoff_access: Dict[str, Any], 
                                 travel_time: int = 30,
                                 pre_move_travel: int = 30) -> Dict[str, Any]:
        """
        Main entry point.
        """
        
        # 1. Build Tasks (This now includes Man-Minute logic and Stacking)
        tasks = self.build_tasks(items)
        
        # 2. Aggregates
        total_vol = sum(i.get('volume', 0) * int(i.get('quantity', 1)) for i in items)
        total_weight = sum(i.get('weight', 0) * int(i.get('quantity', 1)) for i in items)
        
        # 3. Select vehicles first (needed to determine crew seat cap)
        vehicles = self.select_optimal_vehicles(total_vol, total_weight)
        max_seats = sum(v['vehicle']['maxSeats'] * v['quantity'] for v in vehicles)
        max_seats = max(max_seats, 2)  # always at least 2 movers
        
        # 4. Evaluate Crew Sizes (capped by vehicle seating)
        evals = []
        for m in range(2, max_seats + 1):
            # Calculate corrected job time
            job_time = self.calculate_job_time(tasks, m, pickup_access, dropoff_access)
            labor_cost = job_time * m * self.WAGE_RATE
            evals.append({
                "m": m,
                "time_min": job_time,
                "labor_cost": labor_cost
            })
        
        # 5. Pick Recommended Crew
        
        # Check baseline time with 2 movers to determine job scale
        baseline_time_2_movers = next((e['time_min'] for e in evals if e['m'] == 2), 9999)
        is_small_job = baseline_time_2_movers < 180  # less than 3 hours
        
        min_time = min(e['time_min'] for e in evals)
        max_time = max(e['time_min'] for e in evals)
        min_cost = min(e['labor_cost'] for e in evals)
        max_cost = max(e['labor_cost'] for e in evals)
        
        time_range = max_time - min_time if max_time > min_time else 1
        cost_range = max_cost - min_cost if max_cost > min_cost else 1
        
        def score(e):
            # Normalize time and cost to 0-1 scale
            norm_time = (e['time_min'] - min_time) / time_range
            norm_cost = (e['labor_cost'] - min_cost) / cost_range
            
            if is_small_job:
                # Small job: Prioritize COST heavily
                # Don't recommend 6 movers for a 3-hr job just to make it 2hrs
                return 0.2 * norm_time + 0.8 * norm_cost
            else:
                # Large job: Even large jobs are sensitive to cost
                # Prioritize Cost slightly more than Time unless it's extreme
                return 0.4 * norm_time + 0.6 * norm_cost
        
        # Also filter for reasonable job duration (6 working hours max preferred)
        reasonable_options = [e for e in evals if e['time_min'] < 360]  # 6 hours
        
        if reasonable_options:
            best = min(reasonable_options, key=score)
        else:
            # Job is too big - just pick fastest
            best = min(evals, key=lambda x: x['time_min'])
            
        recommended_m = best['m']
        base_minutes = best['time_min']
        
        # 6. Monte Carlo Spread
        mc_factors = self.monte_carlo_estimates(tasks).get(recommended_m, {"p10_factor": 0.9, "p90_factor": 1.1})
        p10_minutes = base_minutes * mc_factors['p10_factor']
        p50_minutes = base_minutes
        p90_minutes = base_minutes * mc_factors['p90_factor']
        
        # 7. Add Travel
        total_travel = pre_move_travel + travel_time
        
        p10_total = p10_minutes + total_travel
        p50_total = p50_minutes + total_travel
        p90_total = p90_minutes + total_travel
        
        base_price = p50_total * recommended_m * self.WAGE_RATE
        
        # 8. Item Details (for display)
        item_details = []
        # Group items for cleaner display
        grouped_items = {}
        for i in items:
            name = i.get('name', 'Unknown')
            if name not in grouped_items:
                grouped_items[name] = {'quantity': 0, 'sample': i}
            grouped_items[name]['quantity'] += int(i.get('quantity', 1))

        for name, group_data in grouped_items.items():
            qty = group_data['quantity']
            sample = group_data['sample']
            cat = self.find_item_category(name)
            
            # Handle items without category - use defaults instead of skipping
            if cat:
                size = self.choose_size_for_item(name, cat)
                base = self.compute_base_item_time(sample, cat, size)
                category_name = cat.get('category', name)
            else:
                size = 'medium'
                base = 5.0  # Default 5 minutes
                category_name = 'Unknown'
            
            item_details.append({
                'name': name,
                'quantity': qty,
                'size': size,
                'category': category_name,
                'timePerItem': round(base, 1),
                'totalTime': round(base * qty, 1)
            })
            
        total_vehicle_volume = sum(v['vehicle']['maxVolume'] * v['quantity'] for v in vehicles)
        total_vehicle_weight = sum(v['vehicle']['maxWeight'] * v['quantity'] for v in vehicles)
        
        # Split base_minutes into load/unload phases (loading=83%, unloading=17%)
        loading_time = p50_minutes / self.LOAD_UNLOAD_MULTIPLIER * 1.0
        unloading_time = p50_minutes / self.LOAD_UNLOAD_MULTIPLIER * 0.2

        return {
            'items': item_details,
            'time': {
                'preMoveTravel': pre_move_travel,
                'loadingTime': round(loading_time, 1),
                'travelBetweenLocations': travel_time,
                'unloadingTime': round(unloading_time, 1),
                'totalMinutes': round(p50_total, 1),
                'totalHours': round(p50_total / 60, 2),
                'estimatedRange': self.lookup_hour_range(round(p50_total / 60, 2))
            },
            'material': {
                'numberOfWorkers': recommended_m,
                'totalTrucks': sum(v['quantity'] for v in vehicles),
                'vehicles': [{
                    'title': v['vehicle']['title'], 
                    'quantity': v['quantity'],
                    'volumeUtilization': round(v['volumeUtilization'], 1),
                    'weightUtilization': round(v['weightUtilization'], 1)
                } for v in vehicles],
                'vehicleReason': f'Optimized for volume & weight (crew capped at {max_seats} by vehicle seating)'
            },
            'volume': {
                'totalCubicFeet': round(total_vol, 1),
                'withBuffer': round(total_vol * 1.15, 1),
                'totalVehicleCapacity': round(total_vehicle_volume, 1),
                'utilizationPercentage': round((total_vol * 1.15) / total_vehicle_volume * 100, 1) if total_vehicle_volume > 0 else 0
            },
            'weight': {
                'totalPounds': round(total_weight, 1),
                'withBuffer': round(total_weight * 1.10, 1),
                'totalVehicleCapacity': round(total_vehicle_weight, 1),
                'utilizationPercentage': round((total_weight * 1.10) / total_vehicle_weight * 100, 1) if total_vehicle_weight > 0 else 0
            },
            'pricing': {
                'basePrice': round(base_price, 2),
                'GST': round(base_price * 0.05, 2),
                'totalExpectedPrice': round(base_price * 1.05, 2),
                'breakdown': f"{recommended_m} movers @ ${self.WAGE_RATE * 60:.0f}/hr"
            }
        }

    def lookup_hour_range(self, total_hours: float) -> str:
        """Look up the estimated hour range from Vision_Agent_Hour_Range_Mapping.csv."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        csv_path = os.path.join(current_dir, '..', '..', '..', 'Data', 'Vision_Agent_Hour_Range_Mapping.csv')
        try:
            rows = []
            with open(csv_path, newline='') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    rows.append({
                        'estimate_hours': float(row['estimate_hours']),
                        'min_hours': float(row['min_hours']),
                        'max_hours': float(row['max_hours'])
                    })
            if not rows:
                return f"{total_hours:.2f} hrs"
            nearest = min(rows, key=lambda r: abs(r['estimate_hours'] - total_hours))
            return f"{nearest['min_hours']:.2f} - {nearest['max_hours']:.2f} hrs"
        except Exception:
            return f"{total_hours:.2f} hrs"

    def select_optimal_vehicles(self, volume_cuft: float, weight_lbs: float) -> List[Dict[str, Any]]:
        """Select optimal vehicles based on volume and weight constraints."""
        volume_with_buffer = volume_cuft * 1.15
        weight_with_buffer = weight_lbs * 1.10
        
        # Try single truck first
        for truck in self.available_trucks:
            if volume_with_buffer <= truck['maxVolume'] and weight_with_buffer <= truck['maxWeight']:
                return [{
                    'vehicle': truck,
                    'quantity': 1,
                    'volumeUtilization': (volume_with_buffer / truck['maxVolume']) * 100,
                    'weightUtilization': (weight_with_buffer / truck['maxWeight']) * 100
                }]
                
        # Else use largest truck multiple times
        largest = self.available_trucks[-1]
        req_v = math.ceil(volume_with_buffer / largest['maxVolume'])
        req_w = math.ceil(weight_with_buffer / largest['maxWeight'])
        count = max(req_v, req_w)
        
        return [{
            'vehicle': largest,
            'quantity': count,
            'volumeUtilization': (volume_with_buffer / (largest['maxVolume'] * count)) * 100,
            'weightUtilization': (weight_with_buffer / (largest['maxWeight'] * count)) * 100
        }]