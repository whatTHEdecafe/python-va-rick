"""
AI client abstraction layer
Provides unified interface for different AI services
"""

import time
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types

from .base import BaseAIClient
from .calculator import MovingCalculator


class GeminiClient(BaseAIClient):
    """Gemini AI service client implementation"""
    
    def __init__(self, api_key: str, model_name: str = 'gemini-2.5-flash'):
        """Initialize Gemini client with API key"""
        self._api_key = api_key
        self._model_name = model_name
        self._client = genai.Client(api_key=api_key)
        self._calculator = MovingCalculator()  # For generating prompts
    
    @property
    def model_name(self) -> str:
        """Return the model name being used"""
        return self._model_name
    
    def upload_file(self, file_path: str) -> Any:
        """Upload a file to Gemini service"""
        try:
            uploaded_file = self._client.files.upload(file=file_path)
            return uploaded_file
        except Exception as e:
            raise RuntimeError(f"Failed to upload file to Gemini: {e}")
    
    def wait_for_file_processing(self, file_reference: Any, max_wait: int = 120) -> bool:
        """Wait for file processing to complete (mainly for videos)"""
        start_time = time.time()
        
        while file_reference.state.name == "PROCESSING":
            if time.time() - start_time > max_wait:
                return False
            
            time.sleep(2)
            file_reference = self._client.files.get(name=file_reference.name)
        
        return file_reference.state.name != "FAILED"
    
    def generate_content(self, contents: List[Any], config: Optional[Any] = None) -> Any:
        """Generate content using Gemini model"""
        try:
            if config is None:
                # Default config: disable thinking for faster response
                config = types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=0)
                )
            
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=contents,
                config=config
            )
            
            return response
        except Exception as e:
            raise RuntimeError(f"Failed to generate content with Gemini: {e}")
    
    def cleanup_file(self, file_reference: Any) -> bool:
        """Delete uploaded file from Gemini service"""
        try:
            self._client.files.delete(name=file_reference.name)
            return True
        except Exception as e:
            print(f"Warning: Could not delete file: {e}")
            return False
    
    def get_vision_prompt(self) -> str:
        """Generate the vision analysis prompt for Gemini"""
        # Get all categories from calculator's database
        categories_list = []
        for category in self._calculator.items_data['categories']:
            cat_name = category['category']
            aliases = ', '.join(category.get('aliases', []))
            logic = category.get('classificationLogic', {})
            size_hints = f"Small: {logic.get('small', '')}, Medium: {logic.get('medium', '')}, Large: {logic.get('large', '')}"
            categories_list.append(f"- {cat_name} ({aliases}) | {size_hints}")
        
        categories_reference = '\n'.join(categories_list)
        
        return f"""
You are a specialized AI assistant for analyzing images and videos of rooms and furniture for a moving company.
Your task is to identify all movable/furniture items in the provided media files (images and/or videos). Multiple files may show different rooms or angles of the same space. DO NOT estimate dimensions, volume, or weight - these will be looked up from our database.

For each item you identify across ALL media files, provide:
- Name: Item name WITH SIZE HINT (e.g., "queen mattress", "3-seat sofa", "large dresser", "king bed frame")
  * Include size descriptors like: twin, full, queen, king, small, medium, large, 2-drawer, 4-drawer, etc.
  * Be specific about the size/type you see in the media
- Quantity: Count of identical items (avoid double-counting items that appear in multiple files or video frames)
- Location: Where is the item (e.g., "living room", "bedroom", "kitchen")

IMPORTANT RULES:
1. If multiple files are provided, analyze ALL of them and combine the results
2. For videos, analyze the entire video to identify all unique items
3. DO NOT double-count items that appear in multiple files or video frames from different angles
4. Do NOT include SIZE HINTS in the name (e.g., "queen bed", "large sectional sofa", "4-drawer dresser")
5. Do NOT estimate dimensions, volume, or weight - we have this data in our database
6. Do NOT calculate anything - just identify items
<<<<<<<< HEAD:Version 6/Gemini/modules/ai_client.py
7. Be specific with furniture types (use aliases like "loveseat", "sectional", "armoire", etc.)
8. DO NOT identify or count moving boxes, storage bins, or packing materials
========
7. DO NOT count boxes/bins (including "box" or "storage bin")
8. Be specific with furniture types (use aliases like "loveseat", "sectional", "armoire", etc.)
>>>>>>>> ver9:Version 8/Gemini/modules/ai_client.py

CRITICAL: Return your response as STRICTLY VALID JSON in this exact format:

{{
  "items": [
    {{
      "name": "mattress",
      "quantity": 1,
      "location": "bedroom",
      "size": "medium",
      "imageID": "1"
    }},
    {{
      "name": "sectional sofa",
      "quantity": 1,
      "location": "living room",
      "size": "large",
      "imageID": "2"
    }},
    {{
      "name": "dresser",
      "quantity": 1,
      "location": "bedroom",
      "size": "medium",
      "imageID": "3"
    }}
  ],
  "summary": {{
    "totalItems": 3,
    "clutterLevel": "moderate",
    "notes": "Master bedroom and living room items visible"
  }}
}}

Return ONLY valid JSON with no markdown formatting, code blocks, or additional text.
"""
    
    def parse_response(self, response: Any) -> Dict[str, Any]:
        """Parse Gemini response and extract JSON data"""
        import json
        
        response_text = response.text.strip()
        
        # Remove markdown code blocks if present
        if response_text.startswith("```json"):
            response_text = response_text[7:-3]
        elif response_text.startswith("```"):
            response_text = response_text[3:-3]
        
        try:
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse Gemini response as JSON: {e}")
