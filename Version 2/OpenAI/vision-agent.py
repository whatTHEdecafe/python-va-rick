import os
import time
import json
import base64
import warnings
from dotenv import load_dotenv
from openai import OpenAI
from PIL import Image

# Load environment variables
load_dotenv()

# Suppress deprecation warnings for Assistants API (it's still functional)
warnings.filterwarnings('ignore', category=DeprecationWarning)

class MovingCalculator:
    """Handles all moving time and logistics calculations using JSON configuration files"""
    
    def __init__(self, items_file='moving_items_logistics.json', rules_file='moving_calculation_rules.json'):
        """Initialize the calculator with JSON configuration files"""
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
        
        # Direct mappings
        category_mappings = {
            'cabinet': 'Cabinets & chests',
            'chest': 'Cabinets & chests',
            'dresser': 'Cabinets & chests',
            'nightstand': 'Cabinets & chests',
            'wardrobe': 'Cabinets & chests',
            'armoire': 'Cabinets & chests',
            'shelf': 'Shelves (assembled)',
            'bookshelf': 'Shelves (assembled)',
            'shelving': 'Shelves (assembled)',
            'table': 'Table',
            'desk': 'Table',
            'chair': 'Chair',
            'stool': 'Chair',
            'couch': 'Couch / Sofa',
            'sofa': 'Couch / Sofa',
            'loveseat': 'Couch / Sofa',
            'sectional': 'Couch / Sofa',
            'bed': 'Bed (frame)',
            'mattress': 'Mattress',
            'box spring': 'Mattress',
            'tv stand': 'TV + media stand',
            'media console': 'TV + media stand',
            'entertainment': 'TV + media stand',
            'tv': 'TVs (flat panels)',
            'television': 'TVs (flat panels)'
        }
        
        # Check for direct matches
        for key, category in category_mappings.items():
            if key in item_name_lower:
                return category
        
        return None
    
    def classify_size(self, item_name, dimensions, weight, category_info):
        """Classify item as small, medium, or large based on dimensions, weight, and category logic"""
        if not category_info:
            # Default classification if category not found
            volume = dimensions.get('width', 0) * dimensions.get('height', 0) * dimensions.get('depth', 0)
            if volume < 5000 or weight < 50:
                return 'small'
            elif volume < 20000 or weight < 150:
                return 'medium'
            else:
                return 'large'
        
        classification_logic = category_info.get('classificationLogic', {})
        
        # Use volume and weight to determine size
        volume = dimensions.get('width', 0) * dimensions.get('height', 0) * dimensions.get('depth', 0)
        
        # Check against classification logic descriptions if available
        item_name_lower = item_name.lower()
        
        for size in ['small', 'medium', 'large']:
            logic_text = classification_logic.get(size, '').lower()
            if any(keyword in item_name_lower for keyword in logic_text.split(',')):
                return size
        
        # Fallback to dimension/weight-based classification
        if volume < 5000 and weight < 50:
            return 'small'
        elif volume < 20000 and weight < 150:
            return 'medium'
        else:
            return 'large'
    
    def calculate_item_time(self, item, pickup_access, dropoff_access):
        """
        Calculate time for moving a single item based on:
        - Item category and size
        - Access type (stairs/elevator) at pickup and dropoff
        - Number of floors
        - Disassembly requirements
        """
        item_name = item.get('name', '')
        category_name = self.find_item_category(item_name)
        
        if not category_name:
            # Default time for unknown items
            return {
                'baseTime': 10,
                'loadTime': 10,
                'unloadTime': 8,
                'totalTime': 18,
                'category': 'Unknown',
                'size': 'medium',
                'breakdown': 'Unknown item - using default estimates'
            }
        
        # Find the category data
        category_info = None
        for cat in self.items_data['categories']:
            if cat['category'] == category_name:
                category_info = cat
                break
        
        if not category_info:
            return None
        
        # Classify size
        size = self.classify_size(
            item_name,
            item.get('dimensions', {}),
            item.get('weightEstimate', 0),
            category_info
        )
        
        # Get base time
        base_time = category_info['baseTime'][size]
        
        # Add disassembly time if needed
        disassembly_time = 0
        if item.get('requiresDisassembly', False):
            disassembly_time = category_info['disassemblyAdder'][size]
        
        # Calculate loading time (pickup location)
        load_time = base_time
        pickup_access_time = self._calculate_access_time(
            item, category_info, size, pickup_access, is_loading=True
        )
        load_time += pickup_access_time + disassembly_time
        
        # Calculate unloading time (dropoff location)
        unload_multiplier = self._get_unload_multiplier(dropoff_access['type'])
        unload_base_time = base_time * unload_multiplier
        dropoff_access_time = self._calculate_access_time(
            item, category_info, size, dropoff_access, is_loading=False
        )
        unload_time = unload_base_time + dropoff_access_time
        
        total_time = load_time + unload_time
        
        return {
            'baseTime': base_time,
            'disassemblyTime': disassembly_time,
            'loadTime': load_time,
            'pickupAccessTime': pickup_access_time,
            'unloadTime': unload_time,
            'dropoffAccessTime': dropoff_access_time,
            'totalTime': total_time,
            'category': category_name,
            'size': size,
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
        Calculate complete moving logistics
        
        Args:
            items: List of items from OpenAI Vision analysis
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
                num_boxes += item.get('numberOfitems', 1)
                continue
            
            # Calculate time for this item
            item_time = self.calculate_item_time(item, pickup_access, dropoff_access)
            
            if item_time:
                num_items = item.get('numberOfitems', 1)
                item_total_time = item_time['totalTime'] * num_items
                
                total_load_time += item_time['loadTime'] * num_items
                total_unload_time += item_time['unloadTime'] * num_items
                
                # Calculate volume and weight
                dims = item.get('dimensions', {})
                volume = dims.get('width', 0) * dims.get('height', 0) * dims.get('depth', 0)
                total_volume += volume * num_items
                total_weight += item.get('weightEstimate', 0) * num_items
                
                item_details.append({
                    'name': item.get('name'),
                    'quantity': num_items,
                    'size': item_time['size'],
                    'category': item_time['category'],
                    'timePerItem': item_time['totalTime'],
                    'totalTime': item_total_time,
                    'breakdown': item_time['breakdown']
                })
        
        # Calculate boxes time separately
        boxes_time_data = self.calculate_boxes_time(num_boxes, pickup_access, dropoff_access)
        total_load_time += boxes_time_data.get('baseTime', 0) + boxes_time_data.get('pickupAccessTime', 0)
        total_unload_time += boxes_time_data.get('dropoffAccessTime', 0)
        
        if num_boxes > 0:
            item_details.append({
                'name': 'Boxes/Bins',
                'quantity': num_boxes,
                'size': 'small',
                'category': 'Boxes',
                'timePerItem': boxes_time_data['totalTime'] / num_boxes if num_boxes > 0 else 0,
                'totalTime': boxes_time_data['totalTime'],
                'breakdown': boxes_time_data['breakdown']
            })
        
        # Calculate total time
        pre_move_travel = 30  # 30 minutes to reach pickup location
        total_moving_time = pre_move_travel + total_load_time + travel_time + total_unload_time
        
        # Select vehicle(s) using optimized algorithm
        total_volume_cuft = total_volume / 1728  # Convert cubic inches to cubic feet
        volume_with_buffer = total_volume_cuft * 1.15
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
                'totalCubicFeet': round(total_volume_cuft, 2),
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


class MoovEZVisionAnalyzerAssistant:
    """OpenAI Assistants API based Vision Analyzer"""
    
    def __init__(self):
        """Initialize the MoovEZ Vision Analyzer with Assistants API"""
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY not found in environment variables")
        
        self.client = OpenAI(api_key=self.api_key)
        
        # Initialize the moving calculator
        self.calculator = MovingCalculator()
        
        self.prohibited_items = [
            "hazardous materials", "explosives", "flammable liquids", 
            "perishable food", "plants", "pets", "personal documents"
        ]
        
        self.metrics = {
            "start_time": None,
            "image_analysis_time": 0,
            "calculation_time": 0,
            "total_time": 0,
            "assistant_id": None,
            "thread_id": None
        }
        
        # Create or retrieve assistant
        self.assistant = self._get_or_create_assistant()
        self.metrics["assistant_id"] = self.assistant.id
        
        print(f"✅ Assistant initialized: {self.assistant.id}")
    
    def _get_or_create_assistant(self):
        """Get existing assistant or create a new one"""
        assistant_name = "MoovEZ Moving Item Analyzer"
        
        # Try to find existing assistant
        try:
            assistants = self.client.beta.assistants.list()
            for asst in assistants.data:
                if asst.name == assistant_name:
                    print(f"♻️  Using existing assistant: {asst.id}")
                    return asst
        except Exception as e:
            print(f"⚠️  Could not retrieve existing assistants: {e}")
        
        # Create new assistant if not found
        print(f"🆕 Creating new assistant...")
        assistant = self.client.beta.assistants.create(
            name=assistant_name,
            instructions=self._get_assistant_instructions(),
            model="gpt-4o",  # Vision-capable model
            tools=[]  # No tools needed for this use case
        )
        
        return assistant
    
    def _get_assistant_instructions(self):
        """Get the system instructions for the assistant"""
        return f"""
You are a specialized AI assistant for analyzing images of rooms and furniture for a moving company called MoovEZ. 

Your task is to identify all movable items in the provided images and extract their physical characteristics. You should ONLY identify items and their properties - DO NOT calculate time, cost, or logistics.

For each item you identify, provide:
- Number Of Items: Count of identical items
- Item Name/Type: Descriptive name (e.g., "sofa", "bookshelf", "dining chair")
- Dimensions: Estimate width, height, and depth in inches
- Weight Estimate: Rough weight in pounds
- Requires Disassembly: Does it need disassembly? (true/false)
- Fragile: Is it fragile? (true/false)
- Bulkiness: Is it bulky, compact, or regular?
- Location: Where is the item (e.g., "living room", "bedroom")
- Movable: Can it be moved? (true/false)
- Prohibited: Is it on the prohibited list? (true/false)
- Pack in Box: Should it be packed in a box? (true/false)

Prohibited Items List:
{json.dumps(self.prohibited_items)}

CRITICAL: Return your response as STRICTLY VALID JSON in this exact format:

{{
  "items": [
    {{
      "name": "Three-seat sofa",
      "numberOfitems": 1,
      "dimensions": {{
        "width": 84,
        "height": 36,
        "depth": 38
      }},
      "weightEstimate": 150,
      "requiresDisassembly": false,
      "fragile": false,
      "bulkiness": "bulky",
      "location": "living room",
      "movable": true,
      "prohibited": false,
      "packInBox": false
    }}
  ],
  "logistics": {{
    "totalItems": 1,
    "clutterLevel": "low",
    "notes": "general observations"
  }}
}}

Return ONLY valid JSON with no markdown formatting, code blocks, or additional text.
"""
    
    def start_timer(self):
        """Start the performance timer"""
        self.metrics["start_time"] = time.time()
        print(f"🕐 Starting MoovEZ Vision Analysis at {time.strftime('%H:%M:%S')}")
    
    def encode_image_to_base64(self, image_path):
        """Encode image to base64 string"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    
    def upload_image_to_openai(self, image_path):
        """Upload image to OpenAI and get file ID"""
        try:
            with open(image_path, "rb") as image_file:
                file = self.client.files.create(
                    file=image_file,
                    purpose='vision'
                )
            print(f"📤 Uploaded image to OpenAI: {file.id}")
            return file.id
        except Exception as e:
            print(f"❌ Could not upload file: {e}")
            return None
    
    def analyze_image(self, image_path, thread_id=None):
        """Analyze a single image using OpenAI Assistants API"""
        print(f"📸 Analyzing image: {image_path}")
        
        analysis_start = time.time()
        
        try:
            # Verify image can be opened
            image = Image.open(image_path)
            print(f"✅ Image loaded successfully: {image.size}")
        except Exception as e:
            print(f"❌ Error loading image: {e}")
            return None, 0, thread_id
        
        try:
            # Create a new thread if not provided
            if thread_id is None:
                thread = self.client.beta.threads.create()
                thread_id = thread.id
                print(f"🧵 Created new thread: {thread_id}")
            
            # Upload image to OpenAI and get file ID
            file_id = self.upload_image_to_openai(image_path)
            
            if not file_id:
                print(f"❌ Failed to upload image")
                return None, 0, thread_id
            
            # Add message to thread with image file
            message = self.client.beta.threads.messages.create(
                thread_id=thread_id,
                role="user",
                content=[
                    {
                        "type": "text",
                        "text": "Analyze this image and identify all movable items. Return the results as JSON following the specified format."
                    },
                    {
                        "type": "image_file",
                        "image_file": {
                            "file_id": file_id
                        }
                    }
                ]
            )
            
            # Run the assistant
            run = self.client.beta.threads.runs.create(
                thread_id=thread_id,
                assistant_id=self.assistant.id
            )
            
            print(f"🏃 Running assistant (Run ID: {run.id})...")
            
            # Wait for completion
            while True:
                run_status = self.client.beta.threads.runs.retrieve(
                    thread_id=thread_id,
                    run_id=run.id
                )
                
                if run_status.status == "completed":
                    break
                elif run_status.status == "failed":
                    print(f"❌ Run failed: {run_status.last_error}")
                    return None, 0, thread_id
                elif run_status.status == "expired":
                    print(f"❌ Run expired")
                    return None, 0, thread_id
                
                time.sleep(1)  # Poll every second
            
            # Get the assistant's response
            messages = self.client.beta.threads.messages.list(
                thread_id=thread_id,
                order="desc",
                limit=1
            )
            
            analysis_time = time.time() - analysis_start
            print(f"⏱️ Image analysis completed in {analysis_time:.2f} seconds")
            
            # Extract the response text
            response_text = messages.data[0].content[0].text.value.strip()
            
            # Parse JSON response
            if response_text.startswith("```json"):
                response_text = response_text[7:-3]
            elif response_text.startswith("```"):
                response_text = response_text[3:-3]
            
            items_data = json.loads(response_text)
            print(f"✅ Found {len(items_data.get('items', []))} items in the image")
            
            return items_data, analysis_time, thread_id
            
        except Exception as e:
            print(f"❌ Error during image analysis: {e}")
            import traceback
            traceback.print_exc()
            return None, 0, thread_id
    
    def analyze_multiple_images(self, image_paths):
        """Analyze multiple images using the same thread for context continuity"""
        print(f"\n📸 Analyzing {len(image_paths)} image(s)...")
        print("="*80)
        
        all_items = []
        total_analysis_time = 0
        api_calls = 0
        combined_logistics = {
            'totalItems': 0,
            'clutterLevel': 'low',
            'notes': []
        }
        
        # Use a single thread for all images to maintain context
        thread_id = None
        
        for idx, image_path in enumerate(image_paths, 1):
            print(f"\n[Image {idx}/{len(image_paths)}]")
            result = self.analyze_image(image_path, thread_id)
            
            if result[0]:  # If analysis was successful
                items_data, analysis_time, thread_id = result
                total_analysis_time += analysis_time
                api_calls += 1
                
                # Add image-specific metadata to items
                for item in items_data.get('items', []):
                    item['imageId'] = f"image_{idx}"
                    item['imageName'] = os.path.basename(image_path)
                    all_items.append(item)
                
                # Combine logistics info
                logistics = items_data.get('logistics', {})
                combined_logistics['totalItems'] += logistics.get('totalItems', 0)
                
                # Track the highest clutter level
                clutter = logistics.get('clutterLevel', 'low')
                if clutter == 'high' or combined_logistics['clutterLevel'] == 'high':
                    combined_logistics['clutterLevel'] = 'high'
                elif clutter == 'moderate':
                    combined_logistics['clutterLevel'] = 'moderate'
                
                if logistics.get('notes'):
                    combined_logistics['notes'].append(f"Image {idx}: {logistics['notes']}")
        
        # Update metrics
        self.metrics["image_analysis_time"] = total_analysis_time
        self.metrics["api_calls"] = api_calls
        self.metrics["thread_id"] = thread_id
        
        print("\n" + "="*80)
        print(f"✅ Completed analysis of all images")
        print(f"📊 Total items found across all images: {len(all_items)}")
        print(f"🧵 Thread ID: {thread_id}")
        
        # Combine notes
        combined_logistics['notes'] = ' | '.join(combined_logistics['notes']) if combined_logistics['notes'] else 'No specific notes'
        
        return {
            'items': all_items,
            'logistics': combined_logistics
        }
    
    def calculate_moving_logistics(self, items_data, pickup_access, dropoff_access, travel_time=30):
        """Calculate moving logistics using Python and JSON files"""
        print(f"🧮 Calculating moving logistics using Python...")
        
        calc_start = time.time()
        
        items = items_data.get('items', [])
        
        try:
            # Use Python calculator
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
        print("🏠 MOOVEZ MOVING ANALYSIS RESULTS (Assistants API)")
        print("="*80)
        
        # Items Summary
        if items_data and 'items' in items_data:
            print(f"\n📦 ITEMS DETECTED: {len(items_data['items'])} items")
            print("-" * 50)
            
            for i, item in enumerate(items_data['items'], 1):
                print(f"{i}. {item.get('name', 'Unknown Item')}")
                print(f"   Quantity: {item.get('numberOfitems', 1)}")
                dims = item.get('dimensions', {})
                print(f"   Dimensions: {dims.get('width', 0)}\" x {dims.get('height', 0)}\" x {dims.get('depth', 0)}\"")
                print(f"   Weight: {item.get('weightEstimate', 0)} lbs")
                print(f"   Fragile: {'Yes' if item.get('fragile', False) else 'No'}")
                print(f"   Requires Disassembly: {'Yes' if item.get('requiresDisassembly', False) else 'No'}")
                print()
        
        # Detailed Item Calculations
        if calculations and 'items' in calculations:
            print("\n⏱️ TIME BREAKDOWN BY ITEM")
            print("-" * 50)
            for item in calculations['items']:
                print(f"• {item['name']} (x{item['quantity']})")
                print(f"  Category: {item['category']} | Size: {item['size']}")
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
            print(f"  Volume Required: {volume.get('withBuffer', 0)} cu ft")
            print(f"  Vehicle Capacity: {volume.get('totalVehicleCapacity', 0)} cu ft")
            print(f"  Volume Utilization: {volume.get('utilizationPercentage', 0)}%")
            print()
            print(f"  Weight Required: {weight.get('withBuffer', 0)} lbs")
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
        print("⏱️ PERFORMANCE METRICS")
        print("="*80)
        print(f"Image Analysis Time: {self.metrics['image_analysis_time']:.2f} seconds")
        print(f"Calculation Time: {self.metrics['calculation_time']:.2f} seconds")
        print(f"Total Processing Time: {self.metrics['total_time']:.2f} seconds")
        print(f"OpenAI API Calls: {self.metrics.get('api_calls', 1)} (for item identification)")
        print(f"Calculation Method: Python + JSON files")
        print(f"Assistant ID: {self.metrics.get('assistant_id', 'N/A')}")
        print(f"Thread ID: {self.metrics.get('thread_id', 'N/A')}")
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
        
        # Step 1: Analyze all images (OpenAI Assistants API - items only)
        items_data = self.analyze_multiple_images(valid_paths)
        if not items_data or not items_data.get('items'):
            print("❌ Failed to analyze images or no items found")
            return None
        
        # Step 2: Calculate moving logistics (Python + JSON files)
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
            "logistics": items_data.get("logistics", {}),
            "calculations": calculations,
            "metrics": self.metrics,
            "imageCount": len(valid_paths)
        }
        
        return final_result


def get_user_input():
    """Get user input for moving parameters"""
    print("\n📋 Please provide the moving details:")
    print("-" * 60)
    
    # Get image paths
    print("🖼️ IMAGE FILES:")
    print("You can enter multiple image paths separated by commas")
    print("Example: image1.jpg, image2.jpg, image3.jpg")
    image_input = input("Enter image file path(s) (or press Enter for default 'test.jpg'): ").strip()
    
    if not image_input:
        image_paths = ["test.jpg"]
    else:
        # Split by comma and clean up whitespace
        image_paths = [path.strip() for path in image_input.split(',')]
    
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
    """Main function to run the MoovEZ Vision Analyzer with Assistants API"""
    print("🚛 Welcome to MoovEZ Moving Bot - Powered by OpenAI Assistants API")
    print("="*60)
    
    # Initialize the analyzer
    try:
        analyzer = MoovEZVisionAnalyzerAssistant()
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
        
        # Optionally save results to JSON file
        output_file = "moving_analysis_result_assistant.json"
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"💾 Results saved to {output_file}")
    else:
        print("\n❌ Analysis failed!")


if __name__ == "__main__":
    main()
