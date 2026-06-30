"""
File handler implementations for different media types
Uses polymorphism to handle images and videos uniformly
"""

import os
import mimetypes
import tempfile
from typing import List, Dict, Any, Tuple
from PIL import Image

# Import HEIC support for iPhone images
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORT = True
except ImportError:
    HEIC_SUPPORT = False

from .base import BaseFileHandler


class ImageHandler(BaseFileHandler):
    """Handler for image files"""
    
    def __init__(self):
        self._supported_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', 
            '.webp', '.tiff', '.tif', '.heic', '.heif'
        ]
    
    @property
    def supported_extensions(self) -> List[str]:
        return self._supported_extensions
    
    @property
    def file_type(self) -> str:
        return "image"
    
    def validate(self, file_path: str) -> bool:
        """Validate if file is a valid image"""
        if not os.path.exists(file_path):
            return False
        
        # Check extension
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in self.supported_extensions:
            return False
        
        # Check MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and not mime_type.startswith('image/'):
            # HEIC files might have application/octet-stream MIME type
            if file_ext not in ['.heic', '.heif']:
                return False
        
        return True
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get image metadata"""
        try:
            image = Image.open(file_path)
            return {
                'type': self.file_type,
                'path': file_path,
                'name': os.path.basename(file_path),
                'size': os.path.getsize(file_path),
                'dimensions': image.size,
                'format': image.format,
                'mode': image.mode
            }
        except Exception as e:
            return {
                'type': self.file_type,
                'path': file_path,
                'name': os.path.basename(file_path),
                'error': str(e)
            }
    
    def prepare_for_upload(self, file_path: str) -> Any:
        """Prepare image for upload - verify it can be opened"""
        try:
            image = Image.open(file_path)
            return image
        except Exception as e:
            raise ValueError(f"Failed to prepare image: {e}")

    def get_uploadable_path(self, file_path: str) -> Tuple[str, bool]:
        """
        Get a path capable of being uploaded to Gemini
        Returns (path, is_temporary) tuple
        """
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Convert HEIC/HEIF to JPEG
        if file_ext in ['.heic', '.heif']:
            try:
                # Create a temporary file
                jpeg_path = self._convert_to_jpeg(file_path)
                return jpeg_path, True
            except Exception as e:
                print(f"Warning: Failed to convert {file_ext} file: {e}")
                return file_path, False
                
        return file_path, False
    
    def _convert_to_jpeg(self, heic_path: str) -> str:
        """Convert HEIC image to JPEG temporary file"""
        try:
            # Register HEIF opener if needed (should be done at module level but safe to re-ensure)
            if 'pillow_heif' in globals():
                 pillow_heif.register_heif_opener()
            
            image = Image.open(heic_path)
            
            # Create temp file
            fd, temp_path = tempfile.mkstemp(suffix='.jpg')
            os.close(fd)
            
            # Convert to RGB (in case of RGBA/P etc) and save
            if image.mode != 'RGB':
                image = image.convert('RGB')
                
            image.save(temp_path, format='JPEG', quality=90)
            return temp_path
            
        except Exception as e:
            raise RuntimeError(f"HEIC conversion failed: {e}")


class VideoHandler(BaseFileHandler):
    """Handler for video files"""
    
    def __init__(self):
        self._supported_extensions = [
            '.mp4', '.mov', '.avi', '.mkv', '.webm', 
            '.flv', '.wmv', '.m4v'
        ]
    
    @property
    def supported_extensions(self) -> List[str]:
        return self._supported_extensions
    
    @property
    def file_type(self) -> str:
        return "video"
    
    def validate(self, file_path: str) -> bool:
        """Validate if file is a valid video"""
        if not os.path.exists(file_path):
            return False
        
        # Check extension
        file_ext = os.path.splitext(file_path)[1].lower()
        if file_ext not in self.supported_extensions:
            return False
        
        # Check MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type and not mime_type.startswith('video/'):
            return False
        
        return True
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get video metadata"""
        try:
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            return {
                'type': self.file_type,
                'path': file_path,
                'name': os.path.basename(file_path),
                'size': file_size,
                'size_mb': round(file_size_mb, 2)
            }
        except Exception as e:
            return {
                'type': self.file_type,
                'path': file_path,
                'name': os.path.basename(file_path),
                'error': str(e)
            }
    
    def prepare_for_upload(self, file_path: str) -> Any:
        """Prepare video for upload - verify file exists and is readable"""
        if not os.path.exists(file_path):
            raise ValueError(f"Video file not found: {file_path}")
        
        if not os.access(file_path, os.R_OK):
            raise ValueError(f"Video file not readable: {file_path}")
        
        return file_path


class FileHandlerFactory:
    """Factory class to create appropriate file handlers"""
    
    def __init__(self):
        self._handlers = [
            ImageHandler(),
            VideoHandler()
        ]
    
    def get_handler(self, file_path: str) -> BaseFileHandler:
        """Get the appropriate handler for a file"""
        for handler in self._handlers:
            if handler.validate(file_path):
                return handler
        
        raise ValueError(f"No handler found for file: {file_path}")
    
    def classify_files(self, file_paths: List[str]) -> Dict[str, List[str]]:
        """Classify files by type"""
        classified = {
            'images': [],
            'videos': [],
            'unsupported': []
        }
        
        for file_path in file_paths:
            try:
                handler = self.get_handler(file_path)
                if handler.file_type == 'image':
                    classified['images'].append(file_path)
                elif handler.file_type == 'video':
                    classified['videos'].append(file_path)
            except ValueError:
                classified['unsupported'].append(file_path)
        
        return classified
    
    def get_all_supported_extensions(self) -> Dict[str, List[str]]:
        """Get all supported extensions by type"""
        extensions = {}
        for handler in self._handlers:
            extensions[handler.file_type] = handler.supported_extensions
        return extensions
