import os
import time
import json
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image

# Load environment variables
load_dotenv()

class MovingCalculatorV2:
    """Handles all moving time and logistics calculations using the v2 JSON configuration with comprehensive item data"""
    
    def __init__(self, items_file=None, rules_file=None):
        """Initialize the calculator with JSON configuration files"""
        # Set default paths relative to this file's location
        if items_file is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            items_file = os.path.join(current_dir, '..', '..', 'Data', 'moving_items_logistics_v2.json')
        
        if rules_file is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            rules_file = os.path.join(current_dir, '..', '..', 'Data', 'moving_calculation_rules.json')
        
        with open(items_file, 'r') as f:
            self.items_data = json.load(f)['movingItemsLogistics']
        
        with open(rules_file, 'r') as f:
            self.rules_data = json.load(f)['movingCalculationRules']
        
        self.available_trucks = [
            {"id": "small", "title": "Pickup Truck", "maxVolume": 48.75, "maxWeight": 2000},
            {"id": "medium", "title": "Cargo Van", "maxVolume": 213.75, "maxWeight": 4000},
            {"id": "medium", "title": "10' Truck", "maxVolume": 400, "maxWeight": 3500},
            {"id": "medium", "title": "16'-20' Truck", "maxVolume": 918.75, "maxWeight": 6000},
            {"id": "large", "title": "26' Truck", "maxVolume": 1768, "maxWeight": 12500}
        ]
    
    def find_item_category(self, item_name):
        """Find the matching category for an item from the logistics file"""
        item_name_lower = item_name.lower()
        
        # Search through all categories and their aliases
        for category in self.items_data['categories']:
            category_name = category['category'].lower()
            
            # Check if item name matches category name
            if category_name in item_name_lower or item_name_lower in category_name:
                return category
            
            # Check aliases
            aliases = category.get('aliases', [])
            for alias in aliases:
                if alias.lower() in item_name_lower or item_name_lower in alias.lower():
                    return category
        
        return None
    
    def classify_size(self, item_name, category_info):
        """
        Classify item as small, medium, or large based on keywords in item name and category logic
        The vision model should provide hints like 'twin bed', 'queen sofa', 'large dresser', etc.
        """
        if not category_info:
            return 'medium'  # Default
        
        classification_logic = category_info.get('classificationLogic', {})
        item_name_lower = item_name.lower()
        
        # Check each size's classification logic
        for size in ['small', 'medium', 'large']:
            logic_text = classification_logic.get(size, '').lower()
            # Split by common delimiters
            keywords = [kw.strip() for kw in logic_text.replace('/', ',').split(',')]
            
            for keyword in keywords:
                if keyword and keyword in item_name_lower:
                    return size
        
        # Check for explicit size keywords in item name
        if any(kw in item_name_lower for kw in ['small', 'compact', 'mini', 'tiny']):
            return 'small'
        elif any(kw in item_name_lower for kw in ['large', 'king', 'oversized', 'big', 'tall', 'commercial']):
            return 'large'
        
        # Default to medium if no specific classification found
        return 'medium'
    
    def calculate_item_time(self, item, pickup_access, dropoff_access):
        """
        Calculate time for moving a single item based on:
        - Item category and size (from JSON)
        - Access type (stairs/elevator) at pickup and dropoff
        - Number of floors
        - Disassembly requirements
        """
        item_name = item.get('name', '')
        category_info = self.find_item_category(item_name)
        
        if not category_info:
            # Default time for unknown items
            return {
                'baseTime': 10,
                'loadTime': 10,
                'unloadTime': 8,
                'totalTime': 18,
                'category': 'Unknown',
                'size': 'medium',
                'volume': 0,
                'weight': 0,
                'breakdown': 'Unknown item - using default estimates'
            }
        
        # Classify size based on item name and category logic
        size = self.classify_size(item_name, category_info)
        
        # Get data from JSON
        base_time = category_info['baseTime'][size]
        volume = category_info['volume'][size]
        weight = category_info['weight'][size]
        
        # Add disassembly time if the item category typically requires it (based on JSON data)
        disassembly_time = 0
        disassembly_adder = category_info['disassemblyAdder'][size]
        if disassembly_adder > 0:
            # Item requires disassembly based on category characteristics
            disassembly_time = disassembly_adder
        
        # Calculate loading time (pickup location)
        load_time = base_time
        pickup_access_time = self._calculate_access_time(
            item, category_info, size, pickup_access, is_loading=True
        )
        load_time = round(base_time + pickup_access_time + disassembly_time, 2)
        
        # Calculate unloading time (dropoff location)
        unload_multiplier = self._get_unload_multiplier(dropoff_access['type'])
        unload_base_time = round(base_time * unload_multiplier, 2)
        dropoff_access_time = self._calculate_access_time(
            item, category_info, size, dropoff_access, is_loading=False
        )
        unload_time = round(unload_base_time + dropoff_access_time, 2)
        
        total_time = round(load_time + unload_time, 2)
        
        return {
            'baseTime': base_time,
            'disassemblyTime': disassembly_time,
            'loadTime': load_time,
            'pickupAccessTime': pickup_access_time,
            'unloadTime': unload_time,
            'dropoffAccessTime': dropoff_access_time,
            'totalTime': total_time,
            'category': category_info['category'],
            'size': size,
            'volume': volume,
            'weight': weight,
            'breakdown': f"Base: {base_time}min, Disassembly: {disassembly_time}min, Pickup access: {pickup_access_time}min, Unload: {unload_time}min, Dropoff access: {dropoff_access_time}min"
        }
    
    def _calculate_access_time(self, item, category_info, size, access_info, is_loading=True):
        """Calculate time for stairs or elevator access"""
        access_type = access_info.get('type', 'ground')  # ground, stairs, elevator
        floors = access_info.get('floors', 0)
        
        if access_type == 'ground' or floors == 0:
            return 0
        
        access_time = 0
        
        if access_type == 'stairs':
            # Get time per flight from rules
            time_per_flight = self.rules_data['stairsCalculation']['timePerFlight'][size]
            access_time = time_per_flight * floors
            
            # Apply fatigue multiplier if applicable
            if floors >= 3:
                fatigue_rules = self.rules_data['stairsCalculation']['fatigueMultiplier']['rules']
                multiplier = fatigue_rules['baseMultiplier']
                extra_flights = floors - fatigue_rules['threshold']
                multiplier += extra_flights * fatigue_rules['additionalPerFlight']
                multiplier = min(multiplier, fatigue_rules['maxMultiplier'])
                access_time *= multiplier
            
            # Add bulky penalty if applicable
            bulky_items = self.rules_data['stairsCalculation']['bulkyPenalty']['applicableItems']
            item_name_lower = item.get('name', '').lower()
            if any(bulky in item_name_lower for bulky in bulky_items):
                bulky_penalty = self.rules_data['stairsCalculation']['bulkyPenalty']['timePerFloor'] * floors
                max_penalty = self.rules_data['stairsCalculation']['bulkyPenalty']['cap']['maxPenalty']
                access_time += min(bulky_penalty, max_penalty)
        
        elif access_type == 'elevator':
            # Get time per ride from rules
            time_per_ride = self.rules_data['elevatorCalculation']['timePerRide'][size]
            access_time = time_per_ride
            
            # Add high floor adder if applicable
            if floors >= 10:
                high_floor_adder = self.rules_data['elevatorCalculation']['highFloorAdder']['additionalTime']['min']
                access_time += high_floor_adder
        
        return access_time
    
    def _get_unload_multiplier(self, access_type):
        """Get the unload multiplier based on destination access type"""
        multipliers = self.rules_data['unloadMultipliers']['multipliers']
        
        if access_type == 'ground':
            return multipliers['mainFloor']['factor']
        elif access_type == 'elevator':
            return multipliers['elevator']['factor']
        elif access_type == 'stairs':
            return multipliers['stairs']['factor']
        
        return 0.80  # Default
    
    def calculate_boxes_time(self, num_boxes, pickup_access, dropoff_access):
        """Calculate time for moving boxes/bins with batching rules"""
        if num_boxes == 0:
            return {'totalTime': 0, 'breakdown': 'No boxes'}
        
        base_time_per_box = self.rules_data['boxesBinsRules']['baseTime']
        
        # Apply volume discount if > 20 boxes
        if num_boxes > 20:
            avg_time = self.rules_data['boxesBinsRules']['volumeDiscount']['averageTime']
            total_base_time = num_boxes * avg_time
        else:
            # Use stackable/dolly time for efficiency
            stackable_time = self.rules_data['boxesBinsRules']['stackableDollyTime']['min']
            total_base_time = num_boxes * stackable_time
        
        # Calculate number of dolly loads (assume 4 boxes per load)
        boxes_per_load = 4
        num_loads = (num_boxes + boxes_per_load - 1) // boxes_per_load
        
        # Add access time per dolly load (not per box)
        pickup_floors = pickup_access.get('floors', 0)
        dropoff_floors = dropoff_access.get('floors', 0)
        
        pickup_access_time = 0
        dropoff_access_time = 0
        
        if pickup_access.get('type') == 'stairs':
            time_per_flight = self.rules_data['stairsCalculation']['timePerFlight']['small']
            pickup_access_time = time_per_flight * pickup_floors * num_loads
        elif pickup_access.get('type') == 'elevator':
            time_per_ride = self.rules_data['elevatorCalculation']['timePerRide']['small']
            pickup_access_time = time_per_ride * num_loads
        
        if dropoff_access.get('type') == 'stairs':
            time_per_flight = self.rules_data['stairsCalculation']['timePerFlight']['small']
            dropoff_access_time = time_per_flight * dropoff_floors * num_loads * 0.85  # unload multiplier
        elif dropoff_access.get('type') == 'elevator':
            time_per_ride = self.rules_data['elevatorCalculation']['timePerRide']['small']
            dropoff_access_time = time_per_ride * num_loads * 0.80  # unload multiplier
        
        total_time = total_base_time + pickup_access_time + dropoff_access_time
        
        return {
            'numBoxes': num_boxes,
            'numLoads': num_loads,
            'baseTime': total_base_time,
            'pickupAccessTime': pickup_access_time,
            'dropoffAccessTime': dropoff_access_time,
            'totalTime': total_time,
            'breakdown': f"{num_boxes} boxes in {num_loads} dolly loads: Base {total_base_time:.1f}min, Pickup access {pickup_access_time:.1f}min, Dropoff access {dropoff_access_time:.1f}min"
        }
    
    def select_optimal_vehicles(self, volume_with_buffer, weight_with_buffer):
        """
        Select optimal vehicle(s) to handle the load
        Returns a list of vehicles with quantities needed
        """
        # Try single vehicle first
        for truck in self.available_trucks:
            if volume_with_buffer <= truck['maxVolume'] and weight_with_buffer <= truck['maxWeight']:
                return [{
                    'vehicle': truck,
                    'quantity': 1,
                    'volumeUtilization': (volume_with_buffer / truck['maxVolume']) * 100,
                    'weightUtilization': (weight_with_buffer / truck['maxWeight']) * 100
                }]
        
        # If single vehicle can't handle, try multiple vehicles
        largest_truck = self.available_trucks[-1]  # 26' Truck
        
        # Calculate how many of the largest trucks needed
        trucks_by_volume = int(volume_with_buffer / largest_truck['maxVolume']) + 1
        trucks_by_weight = int(weight_with_buffer / largest_truck['maxWeight']) + 1
        trucks_needed = max(trucks_by_volume, trucks_by_weight)
        
        # Check if using same truck type is optimal
        same_truck_solution = [{
            'vehicle': largest_truck,
            'quantity': trucks_needed,
            'volumeUtilization': (volume_with_buffer / (largest_truck['maxVolume'] * trucks_needed)) * 100,
            'weightUtilization': (weight_with_buffer / (largest_truck['maxWeight'] * trucks_needed)) * 100
        }]
        
        # Try optimized combination: find best mix of two different truck sizes
        best_combination = same_truck_solution
        best_cost_score = trucks_needed * 1000  # Assume cost proportional to truck size (simplified)
        
        # Try combinations of two different truck types
        for i, truck1 in enumerate(self.available_trucks):
            for truck2 in self.available_trucks[i+1:]:
                # Try different quantities of each truck
                for qty1 in range(1, 4):  # Limit to 3 trucks max per type
                    for qty2 in range(1, 4):
                        total_volume_capacity = (truck1['maxVolume'] * qty1) + (truck2['maxVolume'] * qty2)
                        total_weight_capacity = (truck1['maxWeight'] * qty1) + (truck2['maxWeight'] * qty2)
                        
                        if total_volume_capacity >= volume_with_buffer and total_weight_capacity >= weight_with_buffer:
                            # Calculate cost score (larger trucks = higher cost)
                            truck1_size_score = self.available_trucks.index(truck1) + 1
                            truck2_size_score = self.available_trucks.index(truck2) + 1
                            cost_score = (truck1_size_score * qty1) + (truck2_size_score * qty2)
                            
                            if cost_score < best_cost_score:
                                best_cost_score = cost_score
                                best_combination = [
                                    {
                                        'vehicle': truck1,
                                        'quantity': qty1,
                                        'volumeUtilization': ((volume_with_buffer * (truck1['maxVolume'] * qty1) / total_volume_capacity) / (truck1['maxVolume'] * qty1)) * 100,
                                        'weightUtilization': ((weight_with_buffer * (truck1['maxWeight'] * qty1) / total_weight_capacity) / (truck1['maxWeight'] * qty1)) * 100
                                    },
                                    {
                                        'vehicle': truck2,
                                        'quantity': qty2,
                                        'volumeUtilization': ((volume_with_buffer * (truck2['maxVolume'] * qty2) / total_volume_capacity) / (truck2['maxVolume'] * qty2)) * 100,
                                        'weightUtilization': ((weight_with_buffer * (truck2['maxWeight'] * qty2) / total_weight_capacity) / (truck2['maxWeight'] * qty2)) * 100
                                    }
                                ]
        
        return best_combination
    
    def calculate_total_logistics(self, items, pickup_access, dropoff_access, travel_time=30):
        """
        Calculate complete moving logistics using JSON data for volume/weight
        
        Args:
            items: List of items from Gemini Vision analysis (name, quantity, size hints, location)
            pickup_access: Dict with 'type' (ground/stairs/elevator) and 'floors' (number)
            dropoff_access: Dict with 'type' (ground/stairs/elevator) and 'floors' (number)
            travel_time: Travel time between locations in minutes
        """
        total_load_time = 0
        total_unload_time = 0
        total_volume = 0
        total_weight = 0
        num_boxes = 0
        
        item_details = []
        
        for item in items:
            # Check if it's a box/bin
            item_name = item.get('name', '').lower()
            if 'box' in item_name or 'bin' in item_name or 'tote' in item_name:
                num_boxes += item.get('quantity', 1)
                continue
            
            # Calculate time for this item
            item_time = self.calculate_item_time(item, pickup_access, dropoff_access)
            
            if item_time:
                num_items = item.get('quantity', 1)
                item_total_time = item_time['totalTime'] * num_items
                
                total_load_time += item_time['loadTime'] * num_items
                total_unload_time += item_time['unloadTime'] * num_items
                
                # Get volume and weight from JSON data
                total_volume += item_time['volume'] * num_items
                total_weight += item_time['weight'] * num_items
                
                item_details.append({
                    'name': item.get('name'),
                    'quantity': num_items,
                    'size': item_time['size'],
                    'category': item_time['category'],
                    'volume': item_time['volume'],
                    'weight': item_time['weight'],
                    'timePerItem': item_time['totalTime'],
                    'totalTime': item_total_time,
                    'breakdown': item_time['breakdown']
                })
        
        # Calculate boxes time separately
        boxes_time_data = self.calculate_boxes_time(num_boxes, pickup_access, dropoff_access)
        total_load_time += boxes_time_data.get('baseTime', 0) + boxes_time_data.get('pickupAccessTime', 0)
        total_unload_time += boxes_time_data.get('dropoffAccessTime', 0)
        
        # Add boxes volume/weight (using small box data from JSON)
        if num_boxes > 0:
            box_category = self.find_item_category('box')
            if box_category:
                box_volume = box_category['volume']['small']
                box_weight = box_category['weight']['small']
                total_volume += box_volume * num_boxes
                total_weight += box_weight * num_boxes
                
                item_details.append({
                    'name': 'Boxes/Bins',
                    'quantity': num_boxes,
                    'size': 'small',
                    'category': 'Boxes',
                    'volume': box_volume,
                    'weight': box_weight,
                    'timePerItem': boxes_time_data['totalTime'] / num_boxes if num_boxes > 0 else 0,
                    'totalTime': boxes_time_data['totalTime'],
                    'breakdown': boxes_time_data['breakdown']
                })
        
        # Calculate total time
        pre_move_travel = 30  # 30 minutes to reach pickup location
        total_moving_time = pre_move_travel + total_load_time + travel_time + total_unload_time
        
        # Select vehicle(s) using optimized algorithm
        volume_with_buffer = total_volume * 1.15
        weight_with_buffer = total_weight * 1.10
        
        selected_vehicles = self.select_optimal_vehicles(volume_with_buffer, weight_with_buffer)
        
        # Calculate total vehicle capacity
        total_vehicle_volume = sum(v['vehicle']['maxVolume'] * v['quantity'] for v in selected_vehicles)
        total_vehicle_weight = sum(v['vehicle']['maxWeight'] * v['quantity'] for v in selected_vehicles)
        
        # Calculate number of workers (1 worker per 1250 lbs, max 3 per truck)
        total_trucks = sum(v['quantity'] for v in selected_vehicles)
        workers_per_truck = max(2, min(3, int(weight_with_buffer / (1250 * total_trucks)) + 1))
        workers_needed = workers_per_truck * total_trucks
        
        # Calculate time range using quote range rules
        total_hours = total_moving_time / 60
        time_range = self._calculate_time_range(total_hours)
        
        # Calculate pricing (total hours already includes all travel time)
        mover_rate = 40  # $40 per hour per mover
        total_hours_with_travel = total_hours  # Already includes pre-move travel and between-location travel
        base_price = workers_needed * mover_rate * total_hours_with_travel
        gst = base_price * 0.05  # 5% GST
        insurance_fee = total_weight * 0.10  # $0.10 per lb
        total_price = base_price + gst + insurance_fee
        
        # Format vehicle information
        vehicles_info = []
        for v in selected_vehicles:
            vehicles_info.append({
                'id': v['vehicle']['id'],
                'title': v['vehicle']['title'],
                'quantity': v['quantity'],
                'maxVolume': v['vehicle']['maxVolume'],
                'maxWeight': v['vehicle']['maxWeight'],
                'volumeUtilization': round(v['volumeUtilization'], 1),
                'weightUtilization': round(v['weightUtilization'], 1)
            })
        
        # Create reason for vehicle selection
        if len(selected_vehicles) == 1:
            vehicle_reason = f"Selected {selected_vehicles[0]['quantity']}x {selected_vehicles[0]['vehicle']['title']} based on volume ({volume_with_buffer:.1f} cu ft) and weight ({weight_with_buffer:.1f} lbs)"
        else:
            vehicle_desc = " + ".join([f"{v['quantity']}x {v['vehicle']['title']}" for v in selected_vehicles])
            vehicle_reason = f"Optimized combination: {vehicle_desc} for volume ({volume_with_buffer:.1f} cu ft) and weight ({weight_with_buffer:.1f} lbs)"
        
        return {
            'items': item_details,
            'boxes': {
                'count': num_boxes,
                'details': boxes_time_data
            },
            'time': {
                'preMoveTravel': pre_move_travel,
                'loadingTime': round(total_load_time, 1),
                'travelBetweenLocations': travel_time,
                'unloadingTime': round(total_unload_time, 1),
                'totalMinutes': round(total_moving_time, 1),
                'totalHours': round(total_hours, 2),
                'estimatedRange': time_range
            },
            'material': {
                'numberOfWorkers': workers_needed,
                'totalTrucks': total_trucks,
                'workersPerTruck': workers_per_truck,
                'vehicles': vehicles_info,
                'vehicleReason': vehicle_reason
            },
            'volume': {
                'totalCubicFeet': round(total_volume, 2),
                'withBuffer': round(volume_with_buffer, 2),
                'totalVehicleCapacity': round(total_vehicle_volume, 2),
                'utilizationPercentage': round((volume_with_buffer / total_vehicle_volume) * 100, 1)
            },
            'weight': {
                'totalPounds': round(total_weight, 2),
                'withBuffer': round(weight_with_buffer, 2),
                'totalVehicleCapacity': round(total_vehicle_weight, 2),
                'utilizationPercentage': round((weight_with_buffer / total_vehicle_weight) * 100, 1)
            },
            'pricing': {
                'basePrice': round(base_price, 2),
                'GST': round(gst, 2),
                'insuranceFee': round(insurance_fee, 2),
                'totalExpectedPrice': round(total_price, 2),
                'breakdown': f"{workers_needed} movers × ${mover_rate}/hr × {total_hours_with_travel:.2f} hrs + GST + Insurance"
            }
        }
    
    def _calculate_time_range(self, estimated_hours):
        """Calculate time range based on quote range rules"""
        if estimated_hours < 2.0:
            return f"{estimated_hours:.2f} hours"
        
        ranges = self.rules_data['quoteRangeRules']['ranges']
        
        if estimated_hours <= 5.0:
            percentage = ranges['2.0to5.0hours']['percentage'] / 100
        elif estimated_hours <= 10.0:
            percentage = ranges['5.1to10.0hours']['percentage'] / 100
        else:
            percentage = ranges['10.1to15.0hours']['percentage'] / 100
        
        lower = estimated_hours * (1 - percentage)
        upper = estimated_hours * (1 + percentage)
        
        return f"{lower:.2f} - {upper:.2f} hours"


class MoovEZVisionAnalyzerV5:
    """Gemini Vision API based Analyzer V5 - Uses JSON data for volume/weight"""
    
    def __init__(self):
        """Initialize the MoovEZ Vision Analyzer V5 with Gemini"""
        self.api_key = os.getenv('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        # Initialize the new Gemini client
        self.client = genai.Client(api_key=self.api_key)
        self.model_name = 'gemini-2.5-flash'
        
        # Initialize the moving calculator V2
        self.calculator = MovingCalculatorV2()
        
        self.metrics = {
            "start_time": None,
            "image_analysis_time": 0,
            "calculation_time": 0,
            "total_time": 0
        }
        
        print(f"✅ Gemini Vision Analyzer V5 initialized with model: {self.model_name}")
    
    def _get_vision_prompt(self):
        """Get the system instructions for Gemini vision analysis"""
        # Get all categories from JSON for reference
        categories_list = []
        for category in self.calculator.items_data['categories']:
            cat_name = category['category']
            aliases = ', '.join(category.get('aliases', []))
            logic = category.get('classificationLogic', {})
            size_hints = f"Small: {logic.get('small', '')}, Medium: {logic.get('medium', '')}, Large: {logic.get('large', '')}"
            categories_list.append(f"- {cat_name} ({aliases}) | {size_hints}")
        
        categories_reference = '\n'.join(categories_list)
        
        return f"""
You are a specialized AI assistant for analyzing images of rooms and furniture for a moving company called MoovEZ.

Your task is to identify all movable items in the provided images. Multiple images may show different rooms or angles of the same space. DO NOT estimate dimensions, volume, or weight - these will be looked up from our database.

AVAILABLE ITEM CATEGORIES (with size classification hints):
{categories_reference}

For each item you identify across ALL images, provide:
- Name: Item name WITH SIZE HINT (e.g., "queen mattress", "3-seat sofa", "large dresser", "king bed frame")
  * Include size descriptors like: twin, full, queen, king, small, medium, large, 2-drawer, 4-drawer, etc.
  * Be specific about the size/type you see in the image
- Quantity: Count of identical items (avoid double-counting items that appear in multiple images)
- Location: Where is the item (e.g., "living room", "bedroom", "kitchen")

IMPORTANT RULES:
1. If multiple images are provided, analyze ALL of them and combine the results
2. DO NOT double-count items that appear in multiple images from different angles
3. Include SIZE HINTS in the name (e.g., "queen bed", "large sectional sofa", "4-drawer dresser")
4. Do NOT estimate dimensions, volume, or weight - we have this data in our database
5. Do NOT calculate anything - just identify items
6. Count boxes/bins separately (name them as "box" or "storage bin")
7. Be specific with furniture types (use aliases like "loveseat", "sectional", "armoire", etc.)

CRITICAL: Return your response as STRICTLY VALID JSON in this exact format:

{{
  "items": [
    {{
      "name": "queen mattress",
      "quantity": 1,
      "location": "bedroom"
    }},
    {{
      "name": "large sectional sofa",
      "quantity": 1,
      "location": "living room"
    }},
    {{
      "name": "4-drawer dresser",
      "quantity": 1,
      "location": "bedroom"
    }},
    {{
      "name": "box",
      "quantity": 15,
      "location": "various"
    }}
  ],
  "summary": {{
    "totalItems": 3,
    "totalBoxes": 15,
    "clutterLevel": "moderate",
    "notes": "Master bedroom and living room items visible"
  }}
}}

Return ONLY valid JSON with no markdown formatting, code blocks, or additional text.
"""
    
    def start_timer(self):
        """Start the performance timer"""
        self.metrics["start_time"] = time.time()
        print(f"🕐 Starting MoovEZ Vision Analysis V5 at {time.strftime('%H:%M:%S')}")
    
    def analyze_multiple_images(self, image_paths):
        """Analyze multiple images using a single API call with File API"""
        print(f"\n📸 Analyzing {len(image_paths)} image(s) in a single API call...")
        print("="*80)
        
        analysis_start = time.time()
        
        try:
            # Prepare the content list for the API call
            contents = []
            
            # Add the prompt first
            prompt = self._get_vision_prompt()
            contents.append(prompt)
            
            # Upload and add all images to the contents
            uploaded_files = []
            for idx, image_path in enumerate(image_paths, 1):
                print(f"📤 Uploading image {idx}/{len(image_paths)}: {os.path.basename(image_path)}")
                
                try:
                    # Verify image can be opened
                    image = Image.open(image_path)
                    print(f"   ✅ Image loaded: {image.size}")
                    
                    # Upload the file using the File API
                    uploaded_file = self.client.files.upload(file=image_path)
                    uploaded_files.append(uploaded_file)
                    contents.append(uploaded_file)
                    print(f"   ✅ Uploaded successfully")
                    
                except Exception as e:
                    print(f"   ❌ Error loading/uploading image: {e}")
                    continue
            
            if not uploaded_files:
                print("❌ No images were successfully uploaded")
                return None
            
            print(f"\n🤖 Sending request to Gemini with {len(uploaded_files)} image(s)...")
            
            # Make a single API call with all images
            # Disable thinking by setting thinking_budget to 0 for faster response
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            )
            
            analysis_time = time.time() - analysis_start
            print(f"⏱️ Analysis completed in {analysis_time:.2f} seconds")
            
            # Extract the response text
            response_text = response.text.strip()
            
            # Parse JSON response
            if response_text.startswith("```json"):
                response_text = response_text[7:-3]
            elif response_text.startswith("```"):
                response_text = response_text[3:-3]
            
            items_data = json.loads(response_text)
            
            # Update metrics
            self.metrics["image_analysis_time"] = analysis_time
            self.metrics["api_calls"] = 1  # Only one API call for all images
            
            print("\n" + "="*80)
            print(f"✅ Completed analysis of all images")
            print(f"📊 Total items found: {len(items_data.get('items', []))}")
            
            # Clean up uploaded files
            print("\n🧹 Cleaning up uploaded files...")
            for uploaded_file in uploaded_files:
                try:
                    self.client.files.delete(name=uploaded_file.name)
                    print(f"   ✅ Deleted: {uploaded_file.name}")
                except Exception as e:
                    print(f"   ⚠️ Warning: Could not delete file: {e}")
            
            return items_data
            
        except Exception as e:
            print(f"❌ Error during image analysis: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def calculate_moving_logistics(self, items_data, pickup_access, dropoff_access, travel_time=30):
        """Calculate moving logistics using Python and JSON files (V2 with comprehensive data)"""
        print(f"🧮 Calculating moving logistics using JSON database...")
        
        calc_start = time.time()
        
        items = items_data.get('items', [])
        
        try:
            # Use Python calculator V2
            calculations = self.calculator.calculate_total_logistics(
                items, 
                pickup_access, 
                dropoff_access,
                travel_time
            )
            
            self.metrics["calculation_time"] = time.time() - calc_start
            print(f"⏱️ Calculations completed in {self.metrics['calculation_time']:.2f} seconds")
            print(f"✅ Calculations completed successfully")
            
            return calculations
            
        except Exception as e:
            print(f"❌ Error during calculations: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def display_results(self, items_data, calculations):
        """Display the analysis results in a user-friendly format"""
        print("\n" + "="*80)
        print("🏠 MOOVEZ MOVING ANALYSIS RESULTS (V5 - Gemini + JSON Database)")
        print("="*80)
        
        # Items Summary
        if items_data and 'items' in items_data:
            print(f"\n📦 ITEMS DETECTED: {len(items_data['items'])} items")
            print("-" * 50)
            
            for i, item in enumerate(items_data['items'], 1):
                print(f"{i}. {item.get('name', 'Unknown Item')}")
                print(f"   Quantity: {item.get('quantity', 1)}")
                print(f"   Location: {item.get('location', 'Unknown')}")
                print()
        
        # Summary
        if items_data and 'summary' in items_data:
            summary = items_data['summary']
            print(f"📊 SUMMARY:")
            print(f"  Total Furniture Items: {summary.get('totalItems', 0)}")
            print(f"  Total Boxes: {summary.get('totalBoxes', 0)}")
            print(f"  Clutter Level: {summary.get('clutterLevel', 'Unknown')}")
            print(f"  Notes: {summary.get('notes', 'N/A')}")
            print()
        
        # Detailed Item Calculations
        if calculations and 'items' in calculations:
            print("\n⏱️ TIME & LOGISTICS BREAKDOWN BY ITEM")
            print("-" * 50)
            for item in calculations['items']:
                print(f"• {item['name']} (x{item['quantity']})")
                print(f"  Category: {item['category']} | Size: {item['size']}")
                print(f"  Volume: {item['volume']} cu ft | Weight: {item['weight']} lbs (per item)")
                print(f"  Time per item: {item['timePerItem']:.1f} min")
                print(f"  Total time: {item['totalTime']:.1f} min")
                print(f"  {item['breakdown']}")
                print()
        
        # Calculations Summary
        if calculations:
            print("🚛 MOVING LOGISTICS SUMMARY")
            print("-" * 50)
            
            # Vehicle and Workers
            material = calculations.get('material', {})
            vehicles = material.get('vehicles', [])
            
            if vehicles:
                print("🚚 VEHICLE SELECTION:")
                if len(vehicles) == 1:
                    v = vehicles[0]
                    print(f"  Vehicle: {v['quantity']}x {v['title']}")
                    print(f"  Volume Utilization: {v['volumeUtilization']}%")
                    print(f"  Weight Utilization: {v['weightUtilization']}%")
                else:
                    print("  Multi-Vehicle Solution:")
                    for idx, v in enumerate(vehicles, 1):
                        print(f"  [{idx}] {v['quantity']}x {v['title']}")
                        print(f"      Volume Utilization: {v['volumeUtilization']}%")
                        print(f"      Weight Utilization: {v['weightUtilization']}%")
                
                print(f"  Reason: {material.get('vehicleReason', 'N/A')}")
                print()
            
            print(f"👷 WORKFORCE:")
            print(f"  Total Workers: {material.get('numberOfWorkers', 0)}")
            print(f"  Total Trucks: {material.get('totalTrucks', 0)}")
            print(f"  Workers per Truck: {material.get('workersPerTruck', 0)}")
            print()
            
            # Volume and Weight
            volume = calculations.get('volume', {})
            weight = calculations.get('weight', {})
            print(f"📦 CAPACITY ANALYSIS:")
            print(f"  Volume Required: {volume.get('withBuffer', 0)} cu ft (from JSON database)")
            print(f"  Vehicle Capacity: {volume.get('totalVehicleCapacity', 0)} cu ft")
            print(f"  Volume Utilization: {volume.get('utilizationPercentage', 0)}%")
            print()
            print(f"  Weight Required: {weight.get('withBuffer', 0)} lbs (from JSON database)")
            print(f"  Vehicle Capacity: {weight.get('totalVehicleCapacity', 0)} lbs")
            print(f"  Weight Utilization: {weight.get('utilizationPercentage', 0)}%")
            print()
            
            # Time Estimates
            time_info = calculations.get('time', {})
            print(f"⏱️ TIME BREAKDOWN:")
            print(f"  Pre-Move Travel (to pickup): {time_info.get('preMoveTravel', 0)} minutes")
            print(f"  Loading Time: {time_info.get('loadingTime', 0)} minutes")
            print(f"  Travel Between Locations: {time_info.get('travelBetweenLocations', 0)} minutes")
            print(f"  Unloading Time: {time_info.get('unloadingTime', 0)} minutes")
            print(f"  Total Time: {time_info.get('totalHours', 0)} hours ({time_info.get('totalMinutes', 0)} minutes)")
            print(f"  Estimated Range: {time_info.get('estimatedRange', 'N/A')}")
            print()
            
            # Pricing
            pricing = calculations.get('pricing', {})
            print(f"💰 PRICING BREAKDOWN")
            print(f"Base Price: ${pricing.get('basePrice', 0):.2f}")
            print(f"GST (5%): ${pricing.get('GST', 0):.2f}")
            print(f"Insurance Fee: ${pricing.get('insuranceFee', 0):.2f}")
            print(f"Total Price: ${pricing.get('totalExpectedPrice', 0):.2f}")
            print(f"Details: {pricing.get('breakdown', 'N/A')}")
    
    def display_metrics(self):
        """Display performance metrics"""
        if self.metrics["start_time"]:
            self.metrics["total_time"] = time.time() - self.metrics["start_time"]
        
        print("\n" + "="*80)
        print("⏱️ PERFORMANCE METRICS (V5 - Gemini with File API)")
        print("="*80)
        print(f"Image Analysis Time: {self.metrics['image_analysis_time']:.2f} seconds")
        print(f"Calculation Time: {self.metrics['calculation_time']:.2f} seconds")
        print(f"Total Processing Time: {self.metrics['total_time']:.2f} seconds")
        print(f"Gemini API Calls: {self.metrics.get('api_calls', 1)} (single call for all images)")
        print(f"Calculation Method: Python + JSON Database V2 (comprehensive)")
        print(f"Data Source: moving_items_logistics_v2.json (24 categories, 80+ items)")
        print(f"AI Model: {self.model_name}")
        print("="*80)
    
    def process_moving_request(self, image_paths, pickup_access, dropoff_access, travel_time=30):
        """
        Main method to process a moving request with image analysis
        
        Args:
            image_paths: List of paths to image files or a single image path string
            pickup_access: Dict with 'type' (ground/stairs/elevator) and 'floors'
            dropoff_access: Dict with 'type' (ground/stairs/elevator) and 'floors'
            travel_time: Travel time between locations in minutes (default: 30)
        """
        self.start_timer()
        
        # Convert single path to list
        if isinstance(image_paths, str):
            image_paths = [image_paths]
        
        # Validate all image paths
        valid_paths = []
        for path in image_paths:
            if os.path.exists(path):
                valid_paths.append(path)
            else:
                print(f"⚠️ Warning: Image file not found: {path}")
        
        if not valid_paths:
            print(f"❌ No valid image files found")
            return None
        
        print(f"✅ Found {len(valid_paths)} valid image(s)")
        
        # Step 1: Analyze all images (Gemini Vision - items only, no dimensions/weight)
        items_data = self.analyze_multiple_images(valid_paths)
        if not items_data or not items_data.get('items'):
            print("❌ Failed to analyze images or no items found")
            return None
        
        # Step 2: Calculate moving logistics (Python + JSON V2 database)
        calculations = self.calculate_moving_logistics(items_data, pickup_access, dropoff_access, travel_time)
        if not calculations:
            print("❌ Failed to calculate logistics")
            return None
        
        # Step 3: Display results
        self.display_results(items_data, calculations)
        
        # Step 4: Display performance metrics
        self.display_metrics()
        
        # Return final results
        final_result = {
            "items": items_data.get("items", []),
            "summary": items_data.get("summary", {}),
            "calculations": calculations,
            "metrics": self.metrics,
            "imageCount": len(valid_paths),
            "version": "5.0",
            "aiModel": self.model_name,
            "dataSource": "moving_items_logistics_v2.json",
            "apiMethod": "File API (single call for multiple images)"
        }
        
        return final_result


def get_user_input():
    """Get user input for moving parameters"""
    print("\n📋 Please provide the moving details:")
    print("-" * 60)
    
    # Get the default Test Images folder path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_images_dir = os.path.join(current_dir, '..', '..', 'Test Images')
    default_image = os.path.join(test_images_dir, 'test.jpg')
    
    # Get image paths
    print("🖼️ IMAGE FILES:")
    print("You can enter multiple image paths separated by commas")
    print("Example: image1.jpg, image2.jpg, image3.jpg")
    image_input = input(f"Enter image file path(s) (or press Enter for default 'test.jpg'): ").strip()
    
    if not image_input:
        image_paths = [default_image]
    else:
        # Split by comma and clean up whitespace
        raw_paths = [path.strip() for path in image_input.split(',')]
        image_paths = []
        
        for path in raw_paths:
            # Check if it's an absolute path or contains path separators
            if os.path.isabs(path) or os.sep in path or '/' in path:
                # Use the path as-is
                image_paths.append(path)
            else:
                # It's just a filename, prepend the Test Images directory
                image_paths.append(os.path.join(test_images_dir, path))
    
    print(f"📸 Will process {len(image_paths)} image(s)")
    
    # Get pickup access information
    print("\n🏠 PICKUP LOCATION ACCESS:")
    print("Access type options: 'ground', 'stairs', 'elevator'")
    pickup_type = input("Enter pickup access type (default: ground): ").strip().lower()
    if pickup_type not in ['ground', 'stairs', 'elevator']:
        pickup_type = 'ground'
    
    pickup_floors = 0
    if pickup_type in ['stairs', 'elevator']:
        try:
            pickup_floors = int(input(f"Enter number of floors for {pickup_type} (0 for ground level): ").strip())
        except ValueError:
            pickup_floors = 0
    
    pickup_access = {
        'type': pickup_type,
        'floors': pickup_floors
    }
    
    # Get dropoff access information
    print("\n🏢 DROPOFF LOCATION ACCESS:")
    print("Access type options: 'ground', 'stairs', 'elevator'")
    dropoff_type = input("Enter dropoff access type (default: ground): ").strip().lower()
    if dropoff_type not in ['ground', 'stairs', 'elevator']:
        dropoff_type = 'ground'
    
    dropoff_floors = 0
    if dropoff_type in ['stairs', 'elevator']:
        try:
            dropoff_floors = int(input(f"Enter number of floors for {dropoff_type} (0 for ground level): ").strip())
        except ValueError:
            dropoff_floors = 0
    
    dropoff_access = {
        'type': dropoff_type,
        'floors': dropoff_floors
    }
    
    # Get travel time
    print("\n🚗 TRAVEL TIME:")
    try:
        travel_time = int(input("Enter travel time between locations in minutes (default: 30): ").strip())
    except ValueError:
        travel_time = 30
    
    print("\n" + "="*60)
    print("📝 Summary of your inputs:")
    print(f"  Images: {len(image_paths)} file(s)")
    for idx, path in enumerate(image_paths, 1):
        print(f"    {idx}. {path}")
    print(f"  Pickup: {pickup_type.capitalize()} - {pickup_floors} floor(s)")
    print(f"  Dropoff: {dropoff_type.capitalize()} - {dropoff_floors} floor(s)")
    print(f"  Travel time: {travel_time} minutes")
    print("="*60)
    
    return image_paths, pickup_access, dropoff_access, travel_time


def main():
    """Main function to run the MoovEZ Vision Analyzer V5 with Gemini"""
    print("🚛 Welcome to MoovEZ Moving Bot V5 - Powered by Gemini + JSON Database")
    print("="*80)
    
    # Initialize the analyzer
    try:
        analyzer = MoovEZVisionAnalyzerV5()
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        return
    
    # Get user input for moving parameters
    image_paths, pickup_access, dropoff_access, travel_time = get_user_input()
    
    # Process the moving request
    result = analyzer.process_moving_request(image_paths, pickup_access, dropoff_access, travel_time)
    
    if result:
        print("\n✅ Analysis completed successfully!")
        print(f"📄 Final result contains {len(result['items'])} items")
        print(f"📊 Using comprehensive database: {result['dataSource']}")
        print(f"🤖 AI Model: {result['aiModel']}")
        print(f"🔧 API Method: {result['apiMethod']}")
        
        # Save results to JSON file in Test Results folder
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_results_dir = os.path.join(current_dir, '..', '..', 'Test Results')
        
        # Create Test Results directory if it doesn't exist
        os.makedirs(test_results_dir, exist_ok=True)
        
        # Generate filename with timestamp
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(test_results_dir, f"moving_analysis_result_v5_{timestamp}.json")
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"💾 Results saved to {output_file}")
    else:
        print("\n❌ Analysis failed!")


if __name__ == "__main__":
    main()
