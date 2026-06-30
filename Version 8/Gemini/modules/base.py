"""
Base abstract classes for the MoovEZ Vision Agent
Defines interfaces for extensibility and maintainability
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class BaseFileHandler(ABC):
    """Abstract base class for handling different file types"""
    
    @abstractmethod
    def validate(self, file_path: str) -> bool:
        """Validate if the file can be processed"""
        pass
    
    @abstractmethod
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get metadata about the file"""
        pass
    
    @abstractmethod
    def prepare_for_upload(self, file_path: str) -> Any:
        """Prepare file for AI processing"""
        pass
    
    @property
    @abstractmethod
    def supported_extensions(self) -> List[str]:
        """Return list of supported file extensions"""
        pass
    
    @property
    @abstractmethod
    def file_type(self) -> str:
        """Return the type of file this handler processes"""
        pass


class BaseCalculator(ABC):
    """Abstract base class for logistics calculations"""
    
    @abstractmethod
    def calculate_item_time(self, item: Dict[str, Any], 
                           pickup_access: Dict[str, Any], 
                           dropoff_access: Dict[str, Any]) -> Dict[str, Any]:
        """Calculate time for moving a single item"""
        pass
    
    @abstractmethod
    def calculate_total_logistics(self, items: List[Dict[str, Any]], 
                                 pickup_access: Dict[str, Any],
                                 dropoff_access: Dict[str, Any], 
                                 travel_time: int) -> Dict[str, Any]:
        """Calculate complete moving logistics"""
        pass
    
    @abstractmethod
    def find_item_category(self, item_name: str) -> Optional[Dict[str, Any]]:
        """Find the category information for an item"""
        pass


class BaseAIClient(ABC):
    """Abstract base class for AI service clients"""
    
    @abstractmethod
    def upload_file(self, file_path: str) -> Any:
        """Upload a file to the AI service"""
        pass
    
    @abstractmethod
    def generate_content(self, contents: List[Any], config: Optional[Any] = None) -> Any:
        """Generate content using the AI model"""
        pass
    
    @abstractmethod
    def cleanup_file(self, file_reference: Any) -> bool:
        """Clean up uploaded files"""
        pass
    
    @property
    @abstractmethod
    def model_name(self) -> str:
        """Return the model name being used"""
        pass
