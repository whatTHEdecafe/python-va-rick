import os
import csv
import json
import math
import uuid

from typing import List, Dict, Any, Optional

# Assuming the JSON data is loaded into this variable structure
# In your app, this would come from your file.
# For this script to run standalone, I assume 'converted_items_lowered.json' exists in ../Data/

class MovingCalculator:
    """
    Logistics calculator for moving estimates.

    Flow:
    1. Build per-item tasks from the JSON catalog (base time, optional disassembly adder,
       explicit load+unload times, stackable batching).
    2. calculate_job_time: sum task minutes, apply effective crew teams and a congestion bottleneck,
       then multiply by environmental friction from pickup/dropoff access (ground/stairs/elevator
       and floor counts).
    3. Pick recommended crew size (cost/time score), add travel minutes, derive price from
       wall-clock minutes * crew * wage rate.

    Pricing is proportional to modeled labor time extended by friction; tune via WAGE_RATE and
    *_FRICTION constants below.
    """
    
    # Configuration
    WAGE_RATE = 40.0 / 60.0  # $ per minute ($40/hr)

    # Access friction: stairs remain a percentage multiplier; elevator is additive
    MAX_FLOORS_CAP = 50  # aligns with typical UI caps
    STAIR_BASE_FRICTION = 0.06      # stairs vs ground when type is stairs (even at 0 floors)
    STAIR_PER_FLOOR = 0.035         # incremental penalty per stair flight / story

    # Elevator: additive per-trip model (replaces old percentage multiplier)
    ELEVATOR_FIXED_PER_TRIP = 1.5   # min: walk to elevator, load/unload at door
    ELEVATOR_RIDE_PER_FLOOR = 0.08  # min per floor (~5 sec/floor ride time)
    AVG_ITEMS_PER_ELEVATOR_LOAD = 2.0  # average items carried per elevator trip
    ELEVATOR_PARALLELISM_CAP = 1.5  # max effective teams when elevator is bottleneck
    
    @staticmethod
    def _parse_float(value: Any) -> float:
        try:
            if value is None or str(value).strip() == '':
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _parse_bool(value: Any) -> bool:
        return str(value or '').strip().lower() == 'yes'

    @staticmethod
    def _parse_two_person(value: Any) -> Dict[str, bool]:
        normalized = str(value or '').strip().lower()
        if normalized == 'yes':
            return {"small": True, "medium": True, "large": True}
        if normalized == 'maybe':
            return {"small": False, "medium": True, "large": True}
        return {"small": False, "medium": False, "large": False}

    @staticmethod
    def _size_map(row: Dict[str, Any], small_key: str, medium_key: str, large_key: str) -> Dict[str, float]:
        return {
            "small": MovingCalculator._parse_float(row.get(small_key)),
            "medium": MovingCalculator._parse_float(row.get(medium_key)),
            "large": MovingCalculator._parse_float(row.get(large_key)),
        }

    def _load_csv_items_data(self, csv_path: str) -> Dict[str, Any]:
        """Load a CSV item catalog into the same structure used by JSON catalogs."""
        categories = []
        with open(csv_path, 'r', newline='', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                canonical_item = (row.get('CanonicalItem') or '').strip()
                if not canonical_item:
                    continue

                aliases = [
                    alias.strip()
                    for alias in (row.get('Aliases') or '').split(';')
                    if alias.strip()
                ]
                if canonical_item.lower() not in {alias.lower() for alias in aliases}:
                    aliases.insert(0, canonical_item)

                categories.append({
                    "category": canonical_item,
                    "aliases": aliases,
                    "classificationLogic": {
                        "small": None,
                        "medium": None,
                        "large": None
                    },
                    "volume": self._size_map(row, 'CuFtS', 'CuFtM', 'CuFtL'),
                    "weight": self._size_map(row, 'WeightSLb', 'WeightMLb', 'WeightLLb'),
                    "baseTime": self._size_map(row, 'BaseTimeSMin', 'BaseTimeMMin', 'BaseTimeLMin'),
                    "disassemblyAdder": self._size_map(
                        row,
                        'DisassemblyAdderSMin',
                        'DisassemblyAdderMMin',
                        'DisassemblyAdderLMin'
                    ),
                    "bulkyAdder": self._size_map(row, 'BulkyAdderSMin', 'BulkyAdderMMin', 'BulkyAdderLMin'),
                    "heavyAdder": self._size_map(row, 'HeavyAdderSMin', 'HeavyAdderMMin', 'HeavyAdderLMin'),
                    "twoPersonRequired": self._parse_two_person(row.get('TwoPersonFlag')),
                    "stackable": self._parse_bool(row.get('StackableFlag')),
                    "stackableSavings": self._parse_float(row.get('StackableSavingsPct')),
                    "elevatorFit": (row.get('FitsElevatorHint') or '').strip(),
                    "sourceId": (row.get('Id') or '').strip(),
                    "createdAt": (row.get('CreatedAt') or '').strip(),
                    "updatedAt": (row.get('UpdatedAt') or '').strip(),
                    "stairsAdderPerFlight": self._size_map(
                        row,
                        'StairsAdderPerFlightSMin',
                        'StairsAdderPerFlightMMin',
                        'StairsAdderPerFlightLMin'
                    ),
                    "elevatorAdderPerRide": self._size_map(
                        row,
                        'ElevatorAdderPerRideSMin',
                        'ElevatorAdderPerRideMMin',
                        'ElevatorAdderPerRideLMin'
                    ),
                    "unloadMultiplier": {
                        "mainFloor": self._parse_float(row.get('UnloadMultiplierMainFloor')),
                        "elevator": self._parse_float(row.get('UnloadMultiplierElevator')),
                        "stairs": self._parse_float(row.get('UnloadMultiplierStairs')),
                    },
                    "notes": (row.get('ClassificationLogicNotes') or '').strip(),
                })

        return {
            "metadata": {
                "description": "Moving logistics database loaded from CSV",
                "version": "csv-runtime",
                "source": os.path.basename(csv_path),
                "units": {
                    "volume": "cubic feet",
                    "weight": "pounds",
                    "time": "minutes",
                    "sizes": ["small", "medium", "large"]
                }
            },
            "categories": categories
        }

    def __init__(self, items_file: Optional[str] = None):
        """Initialize calculator with JSON or CSV item database files"""
        if items_file is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            # Adjust path as necessary for your project structure
            items_file = os.path.join(current_dir, '..', '..', '..', 'Data', 'converted_items_lowered.json')

        self.items_file = os.path.abspath(items_file)
        
        self.items_data = {}
        
        try:
            _, ext = os.path.splitext(self.items_file)
            if ext.lower() == '.csv':
                self.items_data = self._load_csv_items_data(self.items_file)
            else:
                with open(self.items_file, 'r') as f:
                    raw_data = json.load(f)
                    self.items_data = raw_data['movingItemsLogistics']
        except Exception as e:
            print(f"Error loading data files: {e}")
            # Fallback minimal structure to prevent crashes
            self.items_data = {"categories": []}

        MAX_MOVERS = 6  # hard cap for user override (slider); algorithm recommends within cab_seats
        self.MAX_MOVERS = MAX_MOVERS

        # Vehicle configurations
        self.available_trucks = [
            {"id": "small", "title": "Pickup Truck", "maxVolume": 48.75, "maxWeight": 2000, "maxSeats": 2},
            {"id": "medium", "title": "Cargo Van", "maxVolume": 213.75, "maxWeight": 4000, "maxSeats": 2},
            {"id": "medium", "title": "10' Truck", "maxVolume": 400, "maxWeight": 3500, "maxSeats": 2},
            {"id": "medium", "title": "16'-20' Truck", "maxVolume": 918.75, "maxWeight": 6000, "maxSeats": 3},
            {"id": "large", "title": "26' Truck", "maxVolume": 1768, "maxWeight": 12500, "maxSeats": 3}
        ]

    @staticmethod
    def _normalize_floors(access: Dict[str, Any]) -> int:
        try:
            f = int(access.get('floors', 0) or 0)
        except (TypeError, ValueError):
            f = 0
        return max(0, min(f, MovingCalculator.MAX_FLOORS_CAP))

    def _access_friction_delta(self, access: Dict[str, Any]) -> float:
        """Non-negative friction delta for one leg (pickup or dropoff).
        Elevator returns 0.0 here; elevator time is handled via additive model
        in _compute_elevator_adder."""
        typ = (access.get('type') or 'ground').lower().strip()
        floors = self._normalize_floors(access)
        if typ == 'ground':
            return 0.0
        if typ == 'stairs':
            return self.STAIR_BASE_FRICTION + self.STAIR_PER_FLOOR * floors
        # Elevator friction is no longer percentage-based; handled additively
        return 0.0

    def _compute_elevator_adder(self, access: Dict[str, Any], num_items: int) -> float:
        """Additive wall-clock minutes for one elevator leg.
        Returns 0.0 for non-elevator access types."""
        typ = (access.get('type') or 'ground').lower().strip()
        if typ != 'elevator':
            return 0.0
        floors = self._normalize_floors(access)
        trip_time = self.ELEVATOR_FIXED_PER_TRIP + self.ELEVATOR_RIDE_PER_FLOOR * floors
        trips = math.ceil(num_items / self.AVG_ITEMS_PER_ELEVATOR_LOAD)
        return trips * trip_time

    @staticmethod
    def _has_elevator(pickup_access: Dict[str, Any], dropoff_access: Dict[str, Any]) -> bool:
        """True if either leg uses an elevator."""
        for acc in (pickup_access, dropoff_access):
            if (acc.get('type') or 'ground').lower().strip() == 'elevator':
                return True
        return False

    @staticmethod
    def _item_wants_disassembly(item: Dict[str, Any]) -> bool:
        """True if AI/tests use needs_disassembly or UI uses disassemble."""
        return bool(item.get('needs_disassembly', False) or item.get('disassemble', False))

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

    def _resolve_match_debug(self, lookup_key: str) -> Dict[str, Any]:
        """Read-only match resolution mirroring find_item_category order."""
        if not self.items_data or 'categories' not in self.items_data:
            return {'category': None, 'matchMethod': None, 'matchedCategoryId': None}

        item_name_lower = lookup_key.lower().strip()

        for category in self.items_data['categories']:
            category_name = category.get('category', '').lower()
            if category_name == item_name_lower or category_name in item_name_lower:
                return {
                    'category': category,
                    'matchMethod': 'category',
                    'matchedCategoryId': category.get('category'),
                }
            for alias in category.get('aliases', []):
                alias_lower = alias.lower()
                if alias_lower == item_name_lower or alias_lower in item_name_lower:
                    return {
                        'category': category,
                        'matchMethod': 'alias',
                        'matchedCategoryId': category.get('category'),
                    }
        return {'category': None, 'matchMethod': 'unknown/fallback', 'matchedCategoryId': None}

    def _debug_item_matching(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Per-item catalog matching details (read-only; mirrors build_tasks lookup)."""
        matching = []
        for item in items:
            name = item.get('name', 'Unknown')
            input_category = item.get('category')
            lookup_key = input_category or name
            resolved = self._resolve_match_debug(lookup_key)
            cat_def = resolved['category']
            match_method = resolved['matchMethod']

            if not cat_def and lookup_key != name:
                lookup_key = name
                resolved = self._resolve_match_debug(name)
                cat_def = resolved['category']
                match_method = resolved['matchMethod']

            unknown_fallback = cat_def is None
            size = self.choose_size_for_item(name, cat_def) if cat_def else 'medium'

            matching.append({
                'inputName': name,
                'inputCategory': input_category,
                'lookupKey': lookup_key,
                'matchedCategoryName': cat_def.get('category') if cat_def else 'Unknown',
                'matchedCategoryId': resolved.get('matchedCategoryId'),
                'matchMethod': match_method,
                'selectedSize': size,
                'quantity': int(item.get('quantity', 1)),
                'unknownFallbackUsed': unknown_fallback,
            })
        return matching

    def _debug_item_times(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Per-item time breakdown for debug (read-only)."""
        item_times = []
        for item in items:
            name = item.get('name', 'Unknown')
            qty = int(item.get('quantity', 1))
            lookup_key = item.get('category') or name
            cat_def = self.find_item_category(lookup_key)
            if not cat_def and lookup_key != name:
                cat_def = self.find_item_category(name)

            if not cat_def:
                size = 'medium'
                load_time = 5.0
                unload_ratio = self.DEFAULT_UNLOAD_RATIO
                unload_time = load_time * unload_ratio
                base_time = load_time
                disassembly_adder = None
                heavy_adder = None
                stackable = False
                stackable_savings = None
                required_movers = None
                weight_used = item.get('weight', 20)
                volume_used = item.get('volume', 5)
            else:
                size = self.choose_size_for_item(name, cat_def)
                time_info = self.compute_base_item_time(item, cat_def, size)
                load_time = time_info['load_time']
                unload_time = time_info['unload_time']
                unload_ratio = self._get_unload_ratio(cat_def, size)
                base_time = cat_def.get('baseTime', {}).get(size, 5.0)
                disassembly_adder = (
                    cat_def.get('disassemblyAdder', {}).get(size, 0.0)
                    if self._item_wants_disassembly(item) else 0.0
                )
                heavy_adder = cat_def.get('heavyAdder', {}).get(size, 0.0)
                stackable = cat_def.get('stackable', False)
                stackable_savings = cat_def.get('stackableSavings', 0)
                required_movers = cat_def.get('requiredMovers', {}).get(size)
                weight_used = item.get('weight', cat_def.get('weight', {}).get(size, 0))
                volume_used = item.get('volume', cat_def.get('volume', {}).get(size, 0))

            total_per_item = load_time + unload_time
            item_times.append({
                'name': name,
                'quantity': qty,
                'size': size,
                'baseTimeUsed': round(base_time, 2),
                'disassemblyAdderUsed': round(disassembly_adder, 2) if disassembly_adder else None,
                'heavyAdderUsed': round(heavy_adder, 2) if heavy_adder else None,
                'loadTime': round(load_time, 2),
                'unloadRatio': round(unload_ratio, 3) if cat_def else round(self.DEFAULT_UNLOAD_RATIO, 3),
                'unloadTime': round(unload_time, 2),
                'totalTimePerItem': round(total_per_item, 2),
                'totalTimeAfterQuantity': round(total_per_item * qty, 2),
                'requiredMovers': required_movers,
                'stackable': stackable,
                'stackableSavings': stackable_savings,
                'weightUsed': weight_used,
                'volumeUsed': volume_used,
            })
        return item_times

    def _debug_task_entries(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Task/batch-level debug from built tasks (read-only)."""
        entries = []
        for task in tasks:
            entries.append({
                'taskName': task.get('name'),
                'taskQuantity': task.get('count', 1),
                'taskLoadTime': round(task.get('load_time', 0), 2),
                'taskUnloadTime': round(task.get('unload_time', 0), 2),
                'taskCombinedTime': round(task.get('p', 0), 2),
                'isStackable': bool(task.get('stackable', False)),
                'batchingApplied': bool(task.get('is_batch', False)),
                'stackableSavings': task.get('stackableSavings'),
            })
        return entries

    def _build_calculation_debug(
        self,
        items: List[Dict[str, Any]],
        pickup_access: Dict[str, Any],
        dropoff_access: Dict[str, Any],
        travel_time: int,
        pre_move_travel: int,
        forced_movers: Optional[int],
        tasks: List[Dict[str, Any]],
        total_vol: float,
        total_weight: float,
        vehicles: List[Dict[str, Any]],
        cab_seats: int,
        evals: List[Dict[str, Any]],
        is_small_job: bool,
        baseline_time_2_movers: float,
        auto_recommended_m: int,
        recommended_m: int,
        labor_minutes: float,
        total_time_minutes: float,
        base_price: float,
        min_hours: float,
        max_hours: float,
        min_base_price: float,
        max_base_price: float,
        algorithm_breakdown: Dict[str, Any],
        pricing_breakdown: str,
    ) -> Dict[str, Any]:
        """Assemble read-only calculationDebug from values already computed."""
        categories = self.items_data.get('categories', []) if self.items_data else []
        catalog_filename = os.path.basename(self.items_file) if self.items_file else None

        crew_evals = []
        if evals:
            min_time = min(e['time_min'] for e in evals)
            max_time = max(e['time_min'] for e in evals)
            min_cost = min(e['labor_cost'] for e in evals)
            max_cost = max(e['labor_cost'] for e in evals)
            time_range = max_time - min_time if max_time > min_time else 1
            cost_range = max_cost - min_cost if max_cost > min_cost else 1

            def _score(e):
                norm_time = (e['time_min'] - min_time) / time_range
                norm_cost = (e['labor_cost'] - min_cost) / cost_range
                if is_small_job:
                    return round(0.2 * norm_time + 0.8 * norm_cost, 4)
                return round(0.4 * norm_time + 0.6 * norm_cost, 4)

            for e in evals:
                crew_evals.append({
                    'movers': e['m'],
                    'laborMinutes': round(e['time_min'], 2),
                    'laborCost': round(e['labor_cost'], 2),
                    'score': _score(e),
                })

        volume_with_buffer = total_vol * 1.15
        weight_with_buffer = total_weight * 1.10
        total_vehicle_volume = sum(v['vehicle']['maxVolume'] * v['quantity'] for v in vehicles)
        total_vehicle_weight = sum(v['vehicle']['maxWeight'] * v['quantity'] for v in vehicles)

        selected_vehicles = []
        for v in vehicles:
            selected_vehicles.append({
                'title': v['vehicle']['title'],
                'id': v['vehicle'].get('id'),
                'quantity': v['quantity'],
                'maxSeats': v['vehicle']['maxSeats'],
                'maxVolume': v['vehicle'].get('maxVolume'),
                'maxWeight': v['vehicle'].get('maxWeight'),
                'volumeUtilization': round(v['volumeUtilization'], 2),
                'weightUtilization': round(v['weightUtilization'], 2),
            })

        vehicle_titles = ', '.join(
            f"{v['quantity']}x {v['vehicle']['title']}" for v in vehicles
        )

        matching = self._debug_item_matching(items)
        item_times = self._debug_item_times(items)
        warnings: List[str] = []

        if not items:
            warnings.append('No items detected for calculation.')
        if not catalog_filename:
            warnings.append('Catalog filename missing or unclear.')
        if not categories:
            warnings.append('Catalog loaded with no categories.')

        for m in matching:
            if m.get('unknownFallbackUsed'):
                warnings.append(
                    f"Unknown fallback used for item '{m.get('inputName')}' (lookup: {m.get('lookupKey')})."
                )

        if recommended_m > cab_seats:
            warnings.append(
                f"Final movers ({recommended_m}) exceed vehicle cab seats ({cab_seats}); follow car may be needed."
            )

        for it in item_times:
            if it.get('weightUsed') in (None, 0):
                warnings.append(f"Missing or zero weight for item '{it.get('name')}'.")
            if it.get('volumeUsed') in (None, 0):
                warnings.append(f"Missing or zero volume for item '{it.get('name')}'.")

        return {
            'inputs': {
                'items': [dict(i) for i in items],
                'pickupAccess': dict(pickup_access),
                'dropoffAccess': dict(dropoff_access),
                'travelTime': travel_time,
                'preMoveTravel': pre_move_travel,
                'forcedMovers': forced_movers,
            },
            'catalog': {
                'itemsFilePath': self.items_file,
                'filename': catalog_filename,
                'categoryCount': len(categories),
            },
            'matching': matching,
            'itemTimes': item_times,
            'taskDebug': self._debug_task_entries(tasks),
            'access': {
                'pickupStairDelta': algorithm_breakdown.get('pickupStairDelta'),
                'dropoffStairDelta': algorithm_breakdown.get('dropoffStairDelta'),
                'stairFrictionMultiplier': algorithm_breakdown.get('stairFrictionMultiplier'),
                'elevatorMinutesPickup': algorithm_breakdown.get('elevatorMinutesPickup'),
                'elevatorMinutesDropoff': algorithm_breakdown.get('elevatorMinutesDropoff'),
                'elevatorMinutesTotal': algorithm_breakdown.get('elevatorMinutesTotal'),
                'elevatorCappedTeams': algorithm_breakdown.get('elevatorCappedTeams'),
                'pickupAccess': algorithm_breakdown.get('pickupAccess'),
                'dropoffAccess': algorithm_breakdown.get('dropoffAccess'),
                'effectiveTeams': algorithm_breakdown.get('effectiveTeams'),
                'bottleneckFactor': algorithm_breakdown.get('bottleneckFactor'),
                'jobLaborMinutes': algorithm_breakdown.get('jobLaborMinutes'),
            },
            'vehicle': {
                'totalVolumeBeforeBuffer': round(total_vol, 2),
                'totalWeightBeforeBuffer': round(total_weight, 2),
                'volumeWithBuffer': round(volume_with_buffer, 2),
                'weightWithBuffer': round(weight_with_buffer, 2),
                'selectedVehicles': selected_vehicles,
                'vehicleTitle': vehicle_titles,
                'vehicleId': selected_vehicles[0]['id'] if selected_vehicles else None,
                'quantity': sum(v['quantity'] for v in vehicles),
                'maxSeats': cab_seats,
                'maxVolume': round(total_vehicle_volume, 2),
                'maxWeight': round(total_vehicle_weight, 2),
                'volumeUtilization': round(
                    (volume_with_buffer / total_vehicle_volume * 100) if total_vehicle_volume > 0 else 0, 2
                ),
                'weightUtilization': round(
                    (weight_with_buffer / total_vehicle_weight * 100) if total_vehicle_weight > 0 else 0, 2
                ),
                'cabSeats': cab_seats,
                'vehicleReason': (
                    f'Recommended crew fits vehicle ({cab_seats} seats); up to {self.MAX_MOVERS} with follow car'
                ),
            },
            'crew': {
                'autoMoverOptionsEvaluated': crew_evals,
                'autoRecommendedMovers': auto_recommended_m,
                'forcedMoversReceived': forced_movers,
                'finalMoversUsed': recommended_m,
                'forcedOverrideUsed': forced_movers is not None,
                'finalMoversExceedCabSeats': recommended_m > cab_seats,
                'baseline2MoverTimeMinutes': round(baseline_time_2_movers, 2),
                'smallJobFlag': is_small_job,
            },
            'pricing': {
                'laborMinutes': round(labor_minutes, 2),
                'preMoveTravel': pre_move_travel,
                'travelTime': travel_time,
                'totalTimeMinutes': round(total_time_minutes, 2),
                'totalHours': round(total_time_minutes / 60, 2),
                'wageRatePerMinute': self.WAGE_RATE,
                'wageRatePerHourPerMover': round(self.WAGE_RATE * 60, 2),
                'moversUsed': recommended_m,
                'basePriceBeforeGst': round(base_price, 2),
                'gstAmount': round(base_price * 0.05, 2),
                'finalTotalExpectedPrice': round(base_price * 1.05, 2),
                'minHours': min_hours,
                'maxHours': max_hours,
                'totalExpectedPriceMin': round(min_base_price * 1.05, 2),
                'totalExpectedPriceMax': round(max_base_price * 1.05, 2),
                'pricingBreakdown': pricing_breakdown,
            },
            'warnings': warnings,
        }

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

    # -------------------- Task construction & per-item time --------------------
    
    # Per-category unload time ratios relative to load time.
    # Unloading is faster than loading (pre-wrapped, no truck Tetris) but slowed
    # by placement decisions, unwrapping, and mover fatigue.
    # Disassembly items need reassembly at dropoff (slower).
    # Stackable items (boxes) are grab-and-go (much faster).
    # Fragile items need careful placement (slower).
    UNLOAD_RATIOS = {
        'box': 0.90,           # Boxes, totes, bins — grab-and-go
        'totes': 0.90,
        'bin': 0.90,
        'crate': 0.90,
        'container': 0.90,
        'refrigerator': 0.55,   # Heavy appliances — positioning difficulty
        'fridge': 0.55,
        'washer': 0.55,
        'dryer': 0.55,
        'dishwasher': 0.55,
        'stove': 0.55,
        'oven': 0.55,
        'television': 0.80,    # Fragile — careful placement
        'tv': 0.80,
        'mirror': 0.80,
        'glass': 0.80,
        'artwork': 0.80,
        'picture': 0.80,
        'piano': 0.55,         # Heavy + awkward positioning
        'keyboard': 0.55,
        'treadmill': 0.55,     # Heavy + awkward positioning
        'exercise': 0.55,
        'grandfather': 0.80,   # Fragile delicate item
    }
    DEFAULT_UNLOAD_RATIO = 0.65  # Standard furniture

    def _get_unload_ratio(self, cat_def: Dict[str, Any], size: str) -> float:
        """Determine unload time ratio relative to load time based on item category."""
        if not cat_def:
            return self.DEFAULT_UNLOAD_RATIO
        
        category = cat_def.get('category', '').lower()
        
        # Direct category name pattern match
        for pattern, ratio in self.UNLOAD_RATIOS.items():
            if pattern in category:
                return ratio
        
        # Stackable items (boxes, totes, bins) unload much faster
        if cat_def.get('stackable', False):
            return self.UNLOAD_RATIOS.get('box', self.DEFAULT_UNLOAD_RATIO)
        
        # Items requiring disassembly typically need reassembly at dropoff
        disassembly_adder = cat_def.get('disassemblyAdder', {}).get(size, 0.0)
        if disassembly_adder > 0:
            return 0.50  # Reassembly is significant time
        
        return self.DEFAULT_UNLOAD_RATIO

    def compute_base_item_time(self, item: Dict[str, Any], cat_def: Dict[str, Any], size: str) -> Dict[str, float]:
        """
        Calculate the wall-clock time for a single item including all JSON modifiers.
        Returns explicit load time, unload time, and total.
        """
        if not cat_def:
            load_time = 5.0
            unload_time = load_time * self.DEFAULT_UNLOAD_RATIO
            return {
                'total': max(load_time + unload_time, 2.0),
                'load_time': load_time,
                'unload_time': unload_time
            }
            
        base = cat_def.get('baseTime', {}).get(size, 5.0)
        
        # Disassembly (UI: disassemble; tests/legacy: needs_disassembly)
        needs_disassembly = self._item_wants_disassembly(item)
        if needs_disassembly:
             base += cat_def.get('disassemblyAdder', {}).get(size, 0.0)

        # Calculate explicit load and unload times
        load_time = base
        unload_ratio = self._get_unload_ratio(cat_def, size)
        unload_time = base * unload_ratio
        
        total_time = load_time + unload_time
        
        return {
            'total': max(total_time, 2.0),
            'load_time': load_time,
            'unload_time': unload_time
        }

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
                 load_time = 5.0
                 unload_time = 5.0 * self.DEFAULT_UNLOAD_RATIO
                 base = load_time + unload_time
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
                 
                 time_info = self.compute_base_item_time(item, cat_def, size)
                 base = time_info['total']
                 load_time = time_info['load_time']
                 unload_time = time_info['unload_time']
                 stackable = cat_def.get('stackable', False)
                 stack_savings = cat_def.get('stackableSavings', 0)
                 weight = item.get('weight', 0)
                 vol = item.get('volume', 0)
             
             # Create tasks for each unit
             for _ in range(quantity):
                raw_tasks.append({
                    'id': str(uuid.uuid4()),
                    'name': name,
                    'p': base,                  # Wall clock time (minutes)
                    'load_time': load_time,
                    'unload_time': unload_time,
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
            # Sum the raw times
            total_p = sum(t['p'] for t in group_items)
            total_load = sum(t.get('load_time', t['p'] * 0.606) for t in group_items)
            total_unload = sum(t.get('unload_time', t['p'] * 0.394) for t in group_items)
            savings_pct = group_items[0]['stackableSavings']
            
            # Apply savings proportionally to load and unload
            combined_p = total_p * (1.0 - (savings_pct / 100.0))
            combined_load = total_load * (1.0 - (savings_pct / 100.0))
            combined_unload = total_unload * (1.0 - (savings_pct / 100.0))

            final_tasks.append({
                'id': str(uuid.uuid4()) + "_batch",
                'name': f"{group_items[0]['name']} (x{len(group_items)})",
                'p': combined_p,
                'load_time': combined_load,
                'unload_time': combined_unload,
                'count': len(group_items),
                'weight': sum(t['weight'] for t in group_items),
                'volume': sum(t['volume'] for t in group_items),
                'is_batch': True
            })
            
        return final_tasks

    # -------------------- Scheduling & Logic --------------------

    def _job_time_breakdown(self, tasks: List[Dict[str, Any]], movers: int,
                            pickup_access: Dict[str, Any],
                            dropoff_access: Dict[str, Any]) -> Dict[str, Any]:
        """Step-by-step job time for UI breakdown (mirrors calculate_job_time)."""
        total_labor_minutes = sum(t['p'] for t in tasks)
        num_items = len(tasks)

        effective_teams_map = {
            2: 1.0, 3: 1.25, 4: 2.0, 5: 2.25, 6: 3.0
        }
        effective_teams = effective_teams_map.get(movers, movers / 2.0)
        effective_teams_before_elevator = effective_teams

        has_elev = self._has_elevator(pickup_access, dropoff_access)
        if has_elev:
            effective_teams = min(effective_teams, self.ELEVATOR_PARALLELISM_CAP)

        bottleneck_map = {
            2: 1.0, 3: 0.95, 4: 0.85, 5: 0.70, 6: 0.55
        }
        bottleneck_factor = bottleneck_map.get(movers, 0.60)

        if effective_teams <= 1:
            parallel_base = total_labor_minutes
        else:
            theoretical_parallel_time = total_labor_minutes / effective_teams
            parallel_base = theoretical_parallel_time / bottleneck_factor

        pickup_stair_delta = self._access_friction_delta(pickup_access)
        dropoff_stair_delta = self._access_friction_delta(dropoff_access)
        stair_friction_multiplier = 1.0 + pickup_stair_delta + dropoff_stair_delta
        minutes_after_stairs = parallel_base * stair_friction_multiplier

        elevator_pickup = self._compute_elevator_adder(pickup_access, num_items)
        elevator_dropoff = self._compute_elevator_adder(dropoff_access, num_items)
        elevator_total = elevator_pickup + elevator_dropoff
        job_labor_minutes = minutes_after_stairs + elevator_total

        def _access_summary(access: Dict[str, Any]) -> Dict[str, Any]:
            return {
                'type': (access.get('type') or 'ground').lower().strip(),
                'floors': self._normalize_floors(access),
            }

        return {
            'totalLaborMinutes': round(total_labor_minutes, 1),
            'numTasks': num_items,
            'movers': movers,
            'effectiveTeams': round(effective_teams, 2),
            'effectiveTeamsBeforeElevatorCap': round(effective_teams_before_elevator, 2),
            'elevatorCappedTeams': has_elev,
            'bottleneckFactor': bottleneck_factor,
            'parallelBaseMinutes': round(parallel_base, 1),
            'pickupStairDelta': round(pickup_stair_delta, 3),
            'dropoffStairDelta': round(dropoff_stair_delta, 3),
            'stairFrictionMultiplier': round(stair_friction_multiplier, 3),
            'minutesAfterStairs': round(minutes_after_stairs, 1),
            'elevatorMinutesPickup': round(elevator_pickup, 1),
            'elevatorMinutesDropoff': round(elevator_dropoff, 1),
            'elevatorMinutesTotal': round(elevator_total, 1),
            'jobLaborMinutes': round(job_labor_minutes, 1),
            'pickupAccess': _access_summary(pickup_access),
            'dropoffAccess': _access_summary(dropoff_access),
        }

    def calculate_job_time(self, tasks: List[Dict[str, Any]], movers: int, 
                          pickup_access: Dict[str, Any], 
                          dropoff_access: Dict[str, Any]) -> float:
        """
        Calculate total job time using a labor-based model.
        
        1. Sum task minutes (already load+unload-scaled per task).
        2. Effective teams vs mover count (diminishing returns for odd crew sizes).
           - Capped by ELEVATOR_PARALLELISM_CAP when elevator is involved.
        3. Congestion bottleneck factor (limits effective parallelism at the truck).
        4. Stairs friction: percentage multiplier (scales with effort per flight).
        5. Elevator time: additive per-trip minutes (fixed wait + ride, not proportional
           to item complexity). Added after parallelism division because elevator wait
           is wall-clock time that cannot be parallelized.
        """
        return self._job_time_breakdown(tasks, movers, pickup_access, dropoff_access)['jobLaborMinutes']

    # -------------------- Main Public Interface --------------------

    def calculate_total_logistics(self, items: List[Dict[str, Any]], 
                                 pickup_access: Dict[str, Any],
                                 dropoff_access: Dict[str, Any], 
                                 travel_time: int = 30,
                                 pre_move_travel: int = 30,
                                 forced_movers: Optional[int] = None) -> Dict[str, Any]:
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
        cab_seats = sum(v['vehicle']['maxSeats'] * v['quantity'] for v in vehicles)
        cab_seats = max(cab_seats, 2)  # always at least 2 movers
        
        # 4. Evaluate Crew Sizes (within vehicle cab capacity for auto-recommendation)
        evals = []
        for m in range(2, cab_seats + 1):
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
            
        auto_recommended_m = best['m']  # what the algorithm would pick
        
        # 5b. Apply forced_movers override (clamped to MAX_MOVERS, not cab_seats)
        if forced_movers is not None:
            clamped = max(2, min(int(forced_movers), self.MAX_MOVERS))
            recommended_m = clamped
            forced_eval = next((e for e in evals if e['m'] == clamped), None)
            if forced_eval:
                base_minutes = forced_eval['time_min']
            else:
                base_minutes = self.calculate_job_time(tasks, clamped, pickup_access, dropoff_access)
        else:
            recommended_m = auto_recommended_m
            base_minutes = best['time_min']
        
        # 6. Add Travel
        labor_minutes = base_minutes
        total_travel = pre_move_travel + travel_time
        total_time_minutes = labor_minutes + total_travel
        
        base_price = total_time_minutes * recommended_m * self.WAGE_RATE
        
        # Compute price range from hour range
        min_hours, max_hours = self._get_hour_range_data(total_time_minutes / 60)
        min_total_minutes = min_hours * 60
        max_total_minutes = max_hours * 60
        min_base_price = min_total_minutes * recommended_m * self.WAGE_RATE
        max_base_price = max_total_minutes * recommended_m * self.WAGE_RATE
        
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
                time_info = self.compute_base_item_time(sample, cat, size)
                base = time_info['total']
                category_name = cat.get('category', name)
                
                # Calculate detailed time components
                load_time = time_info['load_time']
                unload_time = time_info['unload_time']
                disassembly_adder = cat.get('disassemblyAdder', {}).get(size, 0.0)
                if self._item_wants_disassembly(sample) and disassembly_adder > 0:
                    disassembly_time = disassembly_adder
                else:
                    disassembly_time = 0.0
            else:
                size = 'medium'
                load_time = 5.0
                unload_time = 5.0 * self.DEFAULT_UNLOAD_RATIO
                base = load_time + unload_time
                category_name = 'Unknown'
                disassembly_time = 0.0
            
            item_details.append({
                'name': name,
                'quantity': qty,
                'size': size,
                'category': category_name,
                'timePerItem': round(base, 1),
                'totalTime': round(base * qty, 1),
                'loadTime': round(load_time, 1),
                'unloadTime': round(unload_time, 1),
                'disassemblyTime': round(disassembly_time, 1) if disassembly_time > 0 else 'N/A'
            })
            
        total_vehicle_volume = sum(v['vehicle']['maxVolume'] * v['quantity'] for v in vehicles)
        total_vehicle_weight = sum(v['vehicle']['maxWeight'] * v['quantity'] for v in vehicles)
        
        # Calculate explicit load/unload split from task times
        base_load = sum(t.get('load_time', t['p'] * 0.606) for t in tasks)
        base_unload = sum(t.get('unload_time', t['p'] * 0.394) for t in tasks)
        base_total = base_load + base_unload
        
        # Split total labor proportionally (friction + elevator apply proportionally to load/unload)
        if base_total > 0:
            load_ratio = base_load / base_total
        else:
            load_ratio = 0.606  # default fallback
        loading_time = labor_minutes * load_ratio
        unloading_time = labor_minutes * (1 - load_ratio)

        algorithm_breakdown = self._job_time_breakdown(
            tasks, recommended_m, pickup_access, dropoff_access
        )
        algorithm_breakdown['baseLoadMinutes'] = round(base_load, 1)
        algorithm_breakdown['baseUnloadMinutes'] = round(base_unload, 1)
        algorithm_breakdown['loadRatio'] = round(load_ratio, 3)
        algorithm_breakdown['loadingMinutes'] = round(loading_time, 1)
        algorithm_breakdown['unloadingMinutes'] = round(unloading_time, 1)
        algorithm_breakdown['preMoveTravel'] = pre_move_travel
        algorithm_breakdown['travelBetweenLocations'] = travel_time
        algorithm_breakdown['totalMinutes'] = round(total_time_minutes, 1)

        pricing_breakdown = f"{recommended_m} movers @ ${self.WAGE_RATE * 60:.0f}/hr"
        calculation_debug = self._build_calculation_debug(
            items=items,
            pickup_access=pickup_access,
            dropoff_access=dropoff_access,
            travel_time=travel_time,
            pre_move_travel=pre_move_travel,
            forced_movers=forced_movers,
            tasks=tasks,
            total_vol=total_vol,
            total_weight=total_weight,
            vehicles=vehicles,
            cab_seats=cab_seats,
            evals=evals,
            is_small_job=is_small_job,
            baseline_time_2_movers=baseline_time_2_movers,
            auto_recommended_m=auto_recommended_m,
            recommended_m=recommended_m,
            labor_minutes=labor_minutes,
            total_time_minutes=total_time_minutes,
            base_price=base_price,
            min_hours=min_hours,
            max_hours=max_hours,
            min_base_price=min_base_price,
            max_base_price=max_base_price,
            algorithm_breakdown=algorithm_breakdown,
            pricing_breakdown=pricing_breakdown,
        )

        return {
            'items': item_details,
            'time': {
                'preMoveTravel': pre_move_travel,
                'loadingTime': round(loading_time, 1),
                'travelBetweenLocations': travel_time,
                'unloadingTime': round(unloading_time, 1),
                'totalMinutes': round(total_time_minutes, 1),
                'totalHours': round(total_time_minutes / 60, 2),
                'estimatedRange': self.lookup_hour_range(round(total_time_minutes / 60, 2)),
                'algorithmBreakdown': algorithm_breakdown,
            },
            'material': {
                'numberOfWorkers': recommended_m,
                'recommendedWorkers': auto_recommended_m,
                'totalTrucks': sum(v['quantity'] for v in vehicles),
                'vehicles': [{
                    'title': v['vehicle']['title'], 
                    'quantity': v['quantity'],
                    'maxSeats': v['vehicle']['maxSeats'],
                    'volumeUtilization': round(v['volumeUtilization'], 1),
                    'weightUtilization': round(v['weightUtilization'], 1)
                } for v in vehicles],
                'cabSeats': cab_seats,
                'vehicleReason': f'Recommended crew fits vehicle ({cab_seats} seats); up to {self.MAX_MOVERS} with follow car'
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
                'basePriceMin': round(min_base_price, 2),
                'basePriceMax': round(max_base_price, 2),
                'GST': round(base_price * 0.05, 2),
                'GSTMin': round(min_base_price * 0.05, 2),
                'GSTMax': round(max_base_price * 0.05, 2),
                'totalExpectedPrice': round(base_price * 1.05, 2),
                'totalExpectedPriceMin': round(min_base_price * 1.05, 2),
                'totalExpectedPriceMax': round(max_base_price * 1.05, 2),
                'breakdown': pricing_breakdown
            },
            'calculationDebug': calculation_debug,
        }

    def _get_hour_range_data(self, total_hours: float):
        """Look up raw min/max hours from Vision_Agent_Hour_Range_Mapping.csv."""
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
                return total_hours, total_hours
            rounded_hours = round(total_hours * 4) / 4
            nearest = min(rows, key=lambda r: abs(r['estimate_hours'] - rounded_hours))
            return nearest['min_hours'], nearest['max_hours']
        except Exception:
            return total_hours, total_hours

    def lookup_hour_range(self, total_hours: float) -> str:
        """Look up the estimated hour range from Vision_Agent_Hour_Range_Mapping.csv."""
        min_h, max_h = self._get_hour_range_data(total_hours)
        return f"{min_h:.2f} - {max_h:.2f} hrs"

    def select_optimal_vehicles(self, volume_cuft: float, weight_lbs: float) -> List[Dict[str, Any]]:
        """Select optimal vehicles based on volume and weight constraints."""
        volume_with_buffer = volume_cuft * 1.15
        weight_with_buffer = weight_lbs * 1.10
        
        UPSIZE_THRESHOLD = 0.70  # If volume utilization > 70%, recommend next size up
        
        # Try single truck first
        for idx, truck in enumerate(self.available_trucks):
            if volume_with_buffer <= truck['maxVolume'] and weight_with_buffer <= truck['maxWeight']:
                vol_util = volume_with_buffer / truck['maxVolume']
                # If volume is tight and a larger truck exists, upsize
                if vol_util > UPSIZE_THRESHOLD and idx + 1 < len(self.available_trucks):
                    bigger = self.available_trucks[idx + 1]
                    return [{
                        'vehicle': bigger,
                        'quantity': 1,
                        'volumeUtilization': (volume_with_buffer / bigger['maxVolume']) * 100,
                        'weightUtilization': (weight_with_buffer / bigger['maxWeight']) * 100
                    }]
                return [{
                    'vehicle': truck,
                    'quantity': 1,
                    'volumeUtilization': vol_util * 100,
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
