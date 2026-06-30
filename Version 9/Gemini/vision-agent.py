"""
Moovez Vision Analyzer 9 - New furniture DB
Based off ver8
Changes in calculator.py:
- Cap on movers in smaller trucks
- Heuristics based 3 mover selection for large trucks
- Now uses converted_items_lowered.json as furniture database
"""

import os
import time
from typing import List, Dict, Any, Optional, Union
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor, as_completed

# Import modular components
from modules import (
    FileHandlerFactory,
    MovingCalculator,
    GeminiClient,
    enrich_items as _enrich_items,
)

# Load environment variables
load_dotenv()


class MoovEZVisionAnalyzerV7:
    """
    Main analyzer class with modular architecture
    Orchestrates file handling, AI analysis, and logistics calculation
    """
    
    def __init__(self, ai_client: Optional[Any] = None, items_file: Optional[str] = None):
        """
        Initialize the Vision Analyzer V6
        Initialize the Vision Analyzer V6
        
        Args:
            ai_client: Optional AI client instance (defaults to GeminiClient)
            items_file: Optional path to the items JSON database file
        """
        # Initialize AI client
        if ai_client is None:
            api_key = os.getenv('GEMINI_API_KEY')
            if not api_key:
                raise ValueError("GEMINI_API_KEY not found in environment variables")
            self.ai_client = GeminiClient(api_key=api_key)
        else:
            self.ai_client = ai_client
        
        # Initialize file handler factory
        self.file_factory = FileHandlerFactory()
        
        # Initialize calculator
        self.calculator = MovingCalculator(items_file=items_file)
        self.ai_client._calculator = self.calculator

        # Performance metrics
        self.metrics = {
            "start_time": None,
            "file_analysis_time": 0,
            "calculation_time": 0,
            "total_time": 0,
            "images_processed": 0,
            "videos_processed": 0,
            "api_calls": 0
        }
        
        print(f"✅ MoovEZ Vision Analyzer V6 initialized")
        print(f"✅ MoovEZ Vision Analyzer V6 initialized")
        print(f"🤖 AI Model: {self.ai_client.model_name}")
        print(f"📹 Video support: ENABLED")
    
    def start_timer(self):
        """Start the performance timer"""
        self.metrics["start_time"] = time.time()
        print(f"🕐 Starting analysis at {time.strftime('%H:%M:%S')}")
    
    def analyze_media(self, file_paths: List[str]) -> Optional[Dict[str, Any]]:
        """
        Stages 1-2: Gemini vision only (detect items from images/videos).

        Returns:
            VisionResult-shaped dict: items, summary, metrics (vision subset)
        """
        items_data = self.analyze_multiple_files(file_paths)
        if not items_data:
            return None
        return {
            'items': items_data.get('items', []),
            'summary': items_data.get('summary', {}),
            'metrics': {
                'file_analysis_time': self.metrics.get('file_analysis_time', 0),
                'api_calls': self.metrics.get('api_calls', 0),
                'images_processed': self.metrics.get('images_processed', 0),
                'videos_processed': self.metrics.get('videos_processed', 0),
            },
        }

    def analyze_multiple_files(self, file_paths: List[str]) -> Optional[Dict[str, Any]]:
        """
        Analyze multiple images and/or videos using a single API call
        
        Args:
            file_paths: List of paths to image/video files
            
        Returns:
            Dictionary containing detected items and summary
        """
        print(f"\n📁 Analyzing {len(file_paths)} file(s) in a single API call...")
        print("="*80)
        
        analysis_start = time.time()
        
        try:
            # Classify files by type using polymorphic file handlers
            classified = self.file_factory.classify_files(file_paths)
            
            image_files = classified['images']
            video_files = classified['videos']
            unsupported_files = classified['unsupported']
            
            print(f"📸 Images: {len(image_files)}")
            print(f"📹 Videos: {len(video_files)}")
            
            if unsupported_files:
                print(f"⚠️ Unsupported files: {len(unsupported_files)}")
                for file_path in unsupported_files:
                    print(f"   - {os.path.basename(file_path)}")
            
            # Prepare content list for API call
            contents = []
            
            # Add the vision prompt
            prompt = self.ai_client.get_vision_prompt()
            contents.append(prompt)
            
            # Upload and process all files
            uploaded_files = []
            local_temp_files = []  # Track local temp files (converted HEICs)
            total_files = len(image_files) + len(video_files)
            current_file = 0
            
            # Process images
            for image_path in image_files:
                current_file += 1
                print(f"📤 Uploading image {current_file}/{total_files}: {os.path.basename(image_path)}")
                
                try:
                    handler = self.file_factory.get_handler(image_path)
                    file_info = handler.get_file_info(image_path)
                    print(f"   ✅ Image loaded: {file_info.get('dimensions', 'unknown')}")
                    
                    # Get uploadable path (may be converted temp file)
                    upload_path = image_path
                    if hasattr(handler, 'get_uploadable_path'):
                        try:
                            result = handler.get_uploadable_path(image_path)
                            if result and isinstance(result, tuple) and len(result) == 2:
                                upload_path, is_temp = result
                                if is_temp:
                                    local_temp_files.append(upload_path)
                                    print(f"   🔄 Converted HEIC/HEIF to JPEG for upload")
                            else:
                                print(f"   ⚠️ Unexpected return from get_uploadable_path: {result}")
                        except Exception as e:
                            print(f"   ⚠️ Error getting uploadable path: {e}")
                    
                    # Upload file
                    uploaded_file = self.ai_client.upload_file(upload_path)
                    uploaded_files.append(uploaded_file)
                    contents.append(uploaded_file)
                    print(f"   ✅ Uploaded successfully")
                    self.metrics["images_processed"] += 1
                    
                except Exception as e:
                    print(f"   ❌ Error processing image: {e}")
                    continue
            
            # Process videos
            for video_path in video_files:
                current_file += 1
                print(f"📤 Uploading video {current_file}/{total_files}: {os.path.basename(video_path)}")
                
                try:
                    handler = self.file_factory.get_handler(video_path)
                    file_info = handler.get_file_info(video_path)
                    print(f"   📊 Video size: {file_info.get('size_mb', 0):.2f} MB")
                    
                    # Upload file
                    uploaded_file = self.ai_client.upload_file(video_path)
                    uploaded_files.append(uploaded_file)
                    contents.append(uploaded_file)
                    print(f"   ✅ Uploaded successfully")
                    
                    # Wait for video processing
                    print(f"   ⏳ Waiting for video processing...")
                    if self.ai_client.wait_for_file_processing(uploaded_file):
                        print(f"   ✅ Video processed and ready")
                        self.metrics["videos_processed"] += 1
                    else:
                        print(f"   ❌ Video processing failed or timed out")
                        continue
                    
                except Exception as e:
                    print(f"   ❌ Error processing video: {e}")
                    continue
            
            if not uploaded_files:
                print("❌ No files were successfully uploaded")
                return None
            
            print(f"\n🤖 Sending request to {self.ai_client.model_name}...")
            
            # Make single API call with all files
            response = self.ai_client.generate_content(contents)
            
            analysis_time = time.time() - analysis_start
            print(f"⏱️ Analysis completed in {analysis_time:.2f} seconds")
            
            # Parse response
            items_data = self.ai_client.parse_response(response)
            
            # Update metrics
            self.metrics["file_analysis_time"] = analysis_time
            self.metrics["api_calls"] = 1
            
            print("\n" + "="*80)
            print(f"✅ Completed analysis of all files")
            print(f"📊 Total items found: {len(items_data.get('items', []))}")
            
            # Clean up uploaded files
            print("\n🧹 Cleaning up uploaded files...")
            for uploaded_file in uploaded_files:
                if self.ai_client.cleanup_file(uploaded_file):
                    print(f"   ✅ Deleted: {uploaded_file.name}")
            
            # Clean up local temporary files
            if local_temp_files:
                print(f"🧹 Cleaning up {len(local_temp_files)} local temporary files...")
                for temp_path in local_temp_files:
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                            print(f"   ✅ Removed temp file: {os.path.basename(temp_path)}")
                    except Exception as e:
                        print(f"   ⚠️ Failed to remove temp file {temp_path}: {e}")
            
            return items_data
            
        except Exception as e:
            print(f"❌ Error during file analysis: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def enrich_items(self, raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Stage 3: attach catalog weight, volume, size, baseTime (no Gemini)."""
        return _enrich_items(self.calculator, raw_items)

    def compute_logistics(
        self,
        items: List[Dict[str, Any]],
        pickup_access: Dict[str, Any],
        dropoff_access: Dict[str, Any],
        travel_time: int = 30,
        pre_move_travel: int = 30,
        forced_movers: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Stage 4: logistics only (movers, trucks, loading times, pricing).
        """
        print(f"🧮 Calculating moving logistics using JSON database...")
        calc_start = time.time()
        try:
            calculations = self.calculator.calculate_total_logistics(
                items,
                pickup_access,
                dropoff_access,
                travel_time,
                pre_move_travel,
                forced_movers=forced_movers,
            )
            self.metrics["calculation_time"] = time.time() - calc_start
            print(f"⏱️ Calculations completed in {self.metrics['calculation_time']:.2f} seconds")
            return calculations
        except Exception as e:
            print(f"❌ Error during calculations: {e}")
            import traceback
            traceback.print_exc()
            return None

    def calculate_moving_logistics(
        self,
        items_data: Dict[str, Any],
        pickup_access: Dict[str, Any],
        dropoff_access: Dict[str, Any],
        travel_time: int = 30,
        pre_move_travel: int = 30,
        forced_movers: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """Backward-compatible wrapper around compute_logistics."""
        items = items_data.get('items', []) if isinstance(items_data, dict) else items_data
        return self.compute_logistics(
            items, pickup_access, dropoff_access, travel_time, pre_move_travel, forced_movers
        )
    
    def display_results(self, items_data: Dict[str, Any], calculations: Dict[str, Any]):
        """Display analysis results in user-friendly format"""
        print("\n" + "="*80)
        print("🏠 MOOVEZ MOVING ANALYSIS RESULTS (V6 - Modular Architecture)")
        print("🏠 MOOVEZ MOVING ANALYSIS RESULTS (V6 - Modular Architecture)")
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
                print(f"• {item.get('name', 'Unknown')} (x{item.get('quantity', 1)})")
                print(f"  Category: {item.get('category', 'Unknown')} | Size: {item.get('size', 'medium')}")
                if 'volume' in item and 'weight' in item:
                    print(f"  Volume: {item.get('volume', 0)} cu ft | Weight: {item.get('weight', 0)} lbs (per item)")
                print(f"  Time per item: {item.get('timePerItem', 0):.1f} min")
                print(f"  Total time: {item.get('totalTime', 0):.1f} min")
                if 'breakdown' in item:
                    print(f"  {item.get('breakdown', '')}")
                print()
        
        # Logistics Summary
        if calculations:
            print("🚛 MOVING LOGISTICS SUMMARY")
            print("-" * 50)
            
            # Vehicle and Workers
            material = calculations.get('material', {})
            vehicles = material.get('vehicles', [])
            
            if vehicles:
                print("🚚 VEHICLE SELECTION:")
                for idx, v in enumerate(vehicles, 1):
                    print(f"  [{idx}] {v.get('quantity', 1)}x {v.get('title', 'Truck')}")
                    # Only show utilization if present
                    if 'volumeUtilization' in v:
                        print(f"      Volume Utilization: {v['volumeUtilization']:.1f}%")
                    if 'weightUtilization' in v:
                        print(f"      Weight Utilization: {v['weightUtilization']:.1f}%")
                
                if 'vehicleReason' in material:
                    print(f"  Reason: {material.get('vehicleReason', 'N/A')}")
                print()
            
            print(f"👷 WORKFORCE:")
            print(f"  Total Workers: {material.get('numberOfWorkers', 0)}")
            print(f"  Total Trucks: {material.get('totalTrucks', 0)}")
            if 'workersPerTruck' in material:
                print(f"  Workers per Truck: {material.get('workersPerTruck', 0)}")
            print()
            
            # Volume and Weight (only if present)
            volume = calculations.get('volume', {})
            weight = calculations.get('weight', {})
            if volume or weight:
                print(f"📦 CAPACITY ANALYSIS:")
                if volume:
                    print(f"  Volume Required: {volume.get('withBuffer', 0)} cu ft")
                    print(f"  Vehicle Capacity: {volume.get('totalVehicleCapacity', 0)} cu ft")
                    print(f"  Volume Utilization: {volume.get('utilizationPercentage', 0)}%")
                    print()
                if weight:
                    print(f"  Weight Required: {weight.get('withBuffer', 0)} lbs")
                    print(f"  Vehicle Capacity: {weight.get('totalVehicleCapacity', 0)} lbs")
                    print(f"  Weight Utilization: {weight.get('utilizationPercentage', 0)}%")
                    print()
            
            # Time Estimates
            time_info = calculations.get('time', {})
            print(f"⏱️ TIME BREAKDOWN:")
            if 'preMoveTravel' in time_info:
                print(f"  Pre-Move Travel: {time_info.get('preMoveTravel', 0)} minutes")
            if 'loadingTime' in time_info:
                print(f"  Loading Time: {time_info.get('loadingTime', 0)} minutes")
            if 'travelBetweenLocations' in time_info:
                print(f"  Travel Between Locations: {time_info.get('travelBetweenLocations', 0)} minutes")
            if 'unloadingTime' in time_info:
                print(f"  Unloading Time: {time_info.get('unloadingTime', 0)} minutes")
            print(f"  Total Time: {time_info.get('totalHours', 0)} hours ({time_info.get('totalMinutes', 0)} minutes)")
            print(f"  Estimated Range: {time_info.get('estimatedRange', 'N/A')}")
            print()
            
            # Pricing
            pricing = calculations.get('pricing', {})
            print(f"💰 PRICING BREAKDOWN")
            print(f"Base Price: ${pricing.get('basePrice', 0):.2f}")
            if 'GST' in pricing:
                print(f"GST (5%): ${pricing.get('GST', 0):.2f}")
            print(f"Total Price: ${pricing.get('totalExpectedPrice', 0):.2f}")
            print(f"Details: {pricing.get('breakdown', 'N/A')}")
    
    def display_metrics(self):
        """Display performance metrics"""
        if self.metrics["start_time"]:
            self.metrics["total_time"] = time.time() - self.metrics["start_time"]
        
        print("\n" + "="*80)
        print("⏱️ PERFORMANCE METRICS (V6 - Modular Architecture)")
        print("⏱️ PERFORMANCE METRICS (V6 - Modular Architecture)")
        print("="*80)
        print(f"File Analysis Time: {self.metrics['file_analysis_time']:.2f} seconds")
        print(f"Calculation Time: {self.metrics['calculation_time']:.2f} seconds")
        print(f"Total Processing Time: {self.metrics['total_time']:.2f} seconds")
        print(f"API Calls: {self.metrics.get('api_calls', 1)} (single call for all files)")
        print(f"Images Processed: {self.metrics['images_processed']}")
        print(f"Videos Processed: {self.metrics['videos_processed']}")
        print(f"AI Model: {self.ai_client.model_name}")
        print(f"Architecture: Modular (abstraction + inheritance + polymorphism)")
        print("="*80)
    
    def process_moving_request(self, file_paths: Union[str, List[str]], 
                              pickup_access: Dict[str, Any], 
                              dropoff_access: Dict[str, Any], 
                              travel_time: int = 30,
                              pre_move_travel: int = 30) -> Optional[Dict[str, Any]]:
        """
        Main method to process a moving request
        
        Args:
            file_paths: Single file path or list of file paths
            pickup_access: Dict with 'type' and 'floors'
            dropoff_access: Dict with 'type' and 'floors'
            travel_time: Travel time in minutes
            
        Returns:
            Complete analysis results with items, calculations, and metrics
        """
        self.start_timer()
        
        # Convert single path to list
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        
        # Validate file paths
        valid_paths = [p for p in file_paths if os.path.exists(p)]
        
        if not valid_paths:
            print(f"❌ No valid files found")
            return None
        
        print(f"✅ Found {len(valid_paths)} valid file(s)")
        
        vision = self.analyze_media(valid_paths)
        if not vision or not vision.get('items'):
            print("❌ Failed to analyze files or no items found")
            return None

        enriched = self.enrich_items(vision['items'])
        calculations = self.compute_logistics(
            enriched, pickup_access, dropoff_access, travel_time, pre_move_travel
        )
        if not calculations:
            print("❌ Failed to calculate logistics")
            return None

        items_data = {'items': enriched, 'summary': vision.get('summary', {})}
        self.display_results(items_data, calculations)
        self.display_metrics()

        return {
            "items": enriched,
            "summary": vision.get("summary", {}),
            "vision": vision,
            "calculations": calculations,
            "metrics": self.metrics,
            "fileCount": len(valid_paths),
            "imagesProcessed": self.metrics["images_processed"],
            "videosProcessed": self.metrics["videos_processed"],
            "version": "9.0",
            "architecture": "modular",
            "aiModel": self.ai_client.model_name,
            "dataSource": "converted_items_lowered.json",
            "apiMethod": "File API (single call for multiple images/videos)",
            "features": ["image_support", "video_support", "multi_file_upload", "modular_architecture", "pipeline_split"],
        }


# Maintain backward compatibility alias
MoovEZVisionAnalyzerV5 = MoovEZVisionAnalyzerV7


def get_user_input():
    """Get user input for moving parameters"""
    print("\n📋 Please provide the moving details:")
    print("-" * 60)
    
    # Get the default Test Images folder path
    current_dir = os.path.dirname(os.path.abspath(__file__))
    test_images_dir = os.path.join(current_dir, '..', '..', 'Test Images')
    default_file = os.path.join(test_images_dir, 'test.jpg')
    
    # Get file paths
    print("🖼️ MEDIA FILES (Images and/or Videos):")
    print("Supported formats:")
    print("  Images: .jpg, .jpeg, .png, .gif, .bmp, .webp, .tiff, .heic, .heif")
    print("  Videos: .mp4, .mov, .avi, .mkv, .webm, .flv, .wmv, .m4v")
    file_input = input(f"Enter file path(s) (comma-separated, or Enter for default): ").strip()
    
    if not file_input:
        file_paths = [default_file]
    else:
        raw_paths = [path.strip() for path in file_input.split(',')]
        file_paths = []
        
        for path in raw_paths:
            if os.path.isabs(path) or os.sep in path or '/' in path:
                file_paths.append(path)
            else:
                file_paths.append(os.path.join(test_images_dir, path))
    
    print(f"📁 Will process {len(file_paths)} file(s)")
    
    # Get pickup access
    print("\n🏠 PICKUP LOCATION ACCESS:")
    pickup_type = input("Access type (ground/stairs/elevator, default: ground): ").strip().lower()
    if pickup_type not in ['ground', 'stairs', 'elevator']:
        pickup_type = 'ground'
    
    pickup_floors = 0
    if pickup_type in ['stairs', 'elevator']:
        try:
            pickup_floors = int(input(f"Number of floors (0 for ground): ").strip())
        except ValueError:
            pickup_floors = 0
    
    pickup_access = {'type': pickup_type, 'floors': pickup_floors}
    
    # Get dropoff access
    print("\n🏢 DROPOFF LOCATION ACCESS:")
    dropoff_type = input("Access type (ground/stairs/elevator, default: ground): ").strip().lower()
    if dropoff_type not in ['ground', 'stairs', 'elevator']:
        dropoff_type = 'ground'
    
    dropoff_floors = 0
    if dropoff_type in ['stairs', 'elevator']:
        try:
            dropoff_floors = int(input(f"Number of floors (0 for ground): ").strip())
        except ValueError:
            dropoff_floors = 0
    
    dropoff_access = {'type': dropoff_type, 'floors': dropoff_floors}
    
    # Get travel time
    print("\n🚗 TRAVEL TIME:")
    try:
        travel_time = int(input("Travel time between locations in minutes (default: 30): ").strip())
    except ValueError:
        travel_time = 30
    
    print("\n" + "="*60)
    print("📝 Summary:")
    print(f"  Files: {len(file_paths)} file(s)")
    print(f"  Pickup: {pickup_type.capitalize()} - {pickup_floors} floor(s)")
    print(f"  Dropoff: {dropoff_type.capitalize()} - {dropoff_floors} floor(s)")
    print(f"  Travel time: {travel_time} minutes")
    print("="*60)
    
    return file_paths, pickup_access, dropoff_access, travel_time


def main():
    """Main function to run the MoovEZ Vision Analyzer V6"""
    print("🚛 Welcome to MoovEZ Moving Bot V6")
    """Main function to run the MoovEZ Vision Analyzer V6"""
    print("🚛 Welcome to MoovEZ Moving Bot V6")
    print("="*80)
    
    # Initialize analyzer
    try:
        analyzer = MoovEZVisionAnalyzerV7()
    except ValueError as e:
        print(f"❌ Configuration Error: {e}")
        return
    
    # Get user input
    file_paths, pickup_access, dropoff_access, travel_time = get_user_input()
    
    # Process the moving request
    result = analyzer.process_moving_request(file_paths, pickup_access, dropoff_access, travel_time)
    
    if result:
        print("\n✅ Analysis completed successfully!")
        print(f"📄 Result contains {len(result['items'])} items")
        print(f"🏗️ Architecture: {result['architecture']}")
        print(f"🤖 AI Model: {result['aiModel']}")
        print(f"📸 Images: {result['imagesProcessed']} | Videos: {result['videosProcessed']}")
        
        # Save results
        import json
        current_dir = os.path.dirname(os.path.abspath(__file__))
        test_results_dir = os.path.join(current_dir, '..', '..', 'Test Results')
        os.makedirs(test_results_dir, exist_ok=True)
        
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        output_file = os.path.join(test_results_dir, f"moving_analysis_result_v6_{timestamp}.json")
        
        with open(output_file, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"💾 Results saved to {output_file}")
    else:
        print("\n❌ Analysis failed!")


if __name__ == "__main__":
    main()
