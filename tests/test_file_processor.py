import os
import sys
import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import pytest
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from file_processor import FileProcessor


class TestFileProcessor(unittest.TestCase):
    
    def setUp(self):
        self.processor = FileProcessor(base_folder="./data")
        
    @patch('file_processor.DOSpacesHandler')
    def test_convert_to_parquet_and_upload(self, mock_do_spaces):
        # Create a mock DataFrame
        df = pd.DataFrame({'col1': [1, 2], 'col2': ['a', 'b']})
        
        # Setup the mock
        mock_handler = MagicMock()
        mock_do_spaces.return_value = mock_handler
        
        # Mock the upload result
        mock_handler.upload_dataframe_as_parquet.return_value = {
            "file_url": "https://test-bucket.digital-ocean-spaces.com/processed_data/123/test_sheet/20250527_123456_abcd1234.parquet",
            "file_path": "processed_data/123/test_sheet/20250527_123456_abcd1234.parquet",
        }
        
        # Call the method
        result = self.processor.convert_to_parquet_and_upload(df, 123, "test_sheet")
        
        # Assertions
        mock_do_spaces.assert_called_once()
        mock_handler.upload_dataframe_as_parquet.assert_called_once_with(
            df=df,
            project_id=123,
            sheet_type="test_sheet",
            folder_path="processed_data"
        )
        
        self.assertEqual(
            result, 
            "https://test-bucket.digital-ocean-spaces.com/processed_data/123/test_sheet/20250527_123456_abcd1234.parquet"
        )
