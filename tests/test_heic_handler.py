
import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent directory to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'Version 7', 'Gemini')))

from modules.file_handlers import ImageHandler

class TestImageHandler(unittest.TestCase):
    def setUp(self):
        self.handler = ImageHandler()

    @patch('modules.file_handlers.Image')
    @patch('modules.file_handlers.tempfile')
    @patch('modules.file_handlers.os')
    def test_get_uploadable_path_heic(self, mock_os, mock_tempfile, mock_image):
        # Setup mocks
        mock_tempfile.mkstemp.return_value = (123, '/tmp/test_image.jpg')
        mock_image_instance = MagicMock()
        # Mock convert to return a new mock (or same, but we need to track it)
        mock_converted = MagicMock()
        mock_image_instance.convert.return_value = mock_converted
        mock_image.open.return_value = mock_image_instance
        mock_image_instance.mode = 'RGBA' # Test conversion to RGB
        
        # Test file path
        heic_path = 'test_image.heic'
        mock_os.path.splitext.return_value = ('test_image', '.heic')
        
        # Execute
        path, is_temp = self.handler.get_uploadable_path(heic_path)
        
        # Verify
        self.assertTrue(is_temp)
        self.assertEqual(path, '/tmp/test_image.jpg')
        
        # Verify conversions
        mock_image.open.assert_called_with(heic_path)
        mock_image_instance.convert.assert_called_with('RGB')
        mock_converted.save.assert_called_with('/tmp/test_image.jpg', format='JPEG', quality=90)
        
    def test_get_uploadable_path_jpg(self):
        # Test standard file
        path, is_temp = self.handler.get_uploadable_path('image.jpg')
        self.assertFalse(is_temp)
        self.assertEqual(path, 'image.jpg')

if __name__ == '__main__':
    unittest.main()
