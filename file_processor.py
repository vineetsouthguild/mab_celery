from time import time
import pandas as pd
import numpy as np
from typing import Tuple, Dict, Optional, Any
from pathlib import Path
import fastexcel
import os
from utils.logging import timing_decorator, timer, get_logger
import chardet
from models.schemas import AppState
pd.set_option('future.no_silent_downcasting', True)


class FileProcessor:
    def __init__(self, base_folder: str):
        self.base_folder = base_folder
        self.raw_folder = os.path.join(base_folder, "raw")
        self.processed_folder = os.path.join(base_folder, "processed")
        self.mapped_folder = os.path.join(base_folder, "mapped")
        self.result_folder = os.path.join(base_folder, "result")
        self.formatted_result_folder = os.path.join(base_folder, "formatted_result")
   
        self.combined_result = os.path.join(base_folder, "combined_result")
        self._ensure_folders()
        
        # Initialize logger for this class
        self.logger = get_logger(__name__)
    
    def _ensure_folders(self) -> None:
        """Ensure necessary folders exist."""
        Path(self.base_folder).mkdir(parents=True, exist_ok=True)
        Path(self.raw_folder).mkdir(exist_ok=True)
        Path(self.mapped_folder).mkdir(exist_ok=True)
        Path(self.processed_folder).mkdir(exist_ok=True)
        Path(self.result_folder).mkdir(exist_ok=True)
        Path(self.formatted_result_folder).mkdir(exist_ok=True)
        Path(self.combined_result).mkdir(exist_ok=True)
  
    
    
    # here i have used chardet for detecting
    @timing_decorator
    def detect_file_encoding(self, file_path: str) -> str:
        """Detect the encoding of a file using chardet."""
        with open(file_path, 'rb') as file:
            raw_data = file.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding']
            confidence = result['confidence']
            
            # If confidence is low, try common encodings
            if confidence < 0.7:
                encodings_to_try = ['utf-8', 'cp1252', 'iso-8859-1', 'latin1']
                for enc in encodings_to_try:
                    try:
                        raw_data.decode(enc)
                        return enc
                    except UnicodeDecodeError:
                        continue
            
            return encoding or 'utf-8'
    
    @timing_decorator
    def save_uploaded_file(self, file_data: bytes, filename: str) -> str:
        """Save uploaded file to raw folder."""
        file_path = os.path.join(self.raw_folder, filename)
        with open(file_path, "wb") as f:
            f.write(file_data)
        return file_path


    @timing_decorator
    def process_excel_file(self, file_path: str, sheet_name: Optional[str] = None) -> Tuple[Optional[pd.DataFrame], Dict[str, Any]]:
        """Process Excel file and return cleaned dataframe with stats."""
        # Set a timeout for the overall processing
        start_time_total = time()
        timeout_seconds = 20  # Reduced timeout for faster response
        
        try:
            file_extension = Path(file_path).suffix.lower()
            if file_extension in ['.csv']:
                # For CSV files, use a more efficient reading approach with chunksize
                encoding = self.detect_file_encoding(file_path)
                try:
                    # Use engine='c' for faster CSV processing and low_memory=False for better performance
                    df = pd.read_csv(file_path, encoding=encoding, engine='c', low_memory=False)
                except UnicodeDecodeError:
                    for enc in ['utf-8', 'cp1252', 'iso-8859-1', 'latin1']:
                        try:
                            df = pd.read_csv(file_path, encoding=enc, engine='c', low_memory=False)
                            break
                        except UnicodeDecodeError:
                            continue
                    else:
                        raise ValueError(f"Could not read CSV with any common encoding")
            else:
                # Optimize Excel reading
                file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
                print(f"Processing file: {file_path}, Size: {file_size_mb:.2f} MB")
                
                # For very large files, we'll use a more aggressive approach
                if file_size_mb > 100:
                    print(f"Extra large file detected ({file_size_mb:.2f} MB). Using optimized processing.")
                    # For extremely large files, consider using alternative approach
                    import pandas as pd
                    if isinstance(sheet_name, int):
                        df = pd.read_excel(file_path, engine='openpyxl', sheet_name=sheet_name)
                    else:
                        df = pd.read_excel(file_path, engine='openpyxl', sheet_name=0 if sheet_name is None else sheet_name)
                    # Immediately limit rows for very large files
                    if len(df) > 50000:
                        df = df.iloc[:50000]
                    return df, {"fast_processing": True, "file_size_mb": file_size_mb}
                
                start_time = time()
                reader = fastexcel.read_excel(file_path)
                end_time = time()
                print(f"Time taken to read Excel file: {end_time - start_time:.2f} seconds")

                # Get sheet with proper error handling
                try:
                    if isinstance(sheet_name, int):
                        # If sheet_name is an integer, use it as index
                        sheet = reader.load_sheet(sheet_name, header_row=None)
                    elif sheet_name is None:
                        sheet = reader.load_sheet(0, header_row=None)  # Load first sheet if none specified
                    else:
                        sheet = reader.load_sheet(sheet_name, header_row=None)
                except Exception as e:
                    # Provide more helpful error for sheet index issues
                    if isinstance(sheet_name, int):
                        sheet_count = len(reader.sheet_names)
                        if sheet_name >= sheet_count:
                            raise ValueError(f"Sheet index {sheet_name} out of range. File has {sheet_count} sheets (0-{sheet_count-1}).")
                    raise e
                
                # initial_rows, initial_cols = sheet.height, sheet.width
                
                with timer("Excel to pandas conversion"):
                    df = sheet.to_pandas()
                    data_for_header = df.head(50)
            
            # Find header row
            header_row = self._find_header_row(data_for_header)
            if header_row is None:
                raise ValueError("Could not detect header row")

            
            # Set headers and clean data
            headers = df.iloc[header_row]
            df = df.iloc[header_row + 1:].reset_index(drop=True)
            
            # Handle duplicate columns
            duplicate_stats = self._handle_duplicate_columns(headers)
            df.columns = duplicate_stats['final_headers']

            # Clean data
            df = self._clean_dataframe(df)

            # Check if we're approaching timeout
            current_time = time()
            elapsed_time = current_time - start_time_total
            if elapsed_time > timeout_seconds:
                print(f"Processing is taking too long ({elapsed_time:.2f} seconds). Returning results so far.")
                
                # If processing takes too long, limit rows returned to prevent further delays
                if len(df) > 1000:
                    df = df.head(1000)
            
            # Calculate stats
            stats = {
                'initial_rows': len(df) + header_row + 1,
                'initial_cols': len(df.columns),
                'final_rows': len(df),
                'final_cols': len(df.columns),
                'empty_rows_removed': (len(df) + header_row + 1) - len(df),
                'empty_cols_removed': len(headers) - len(df.columns),
                'duplicate_columns': duplicate_stats['duplicate_counts'],
                'renamed_columns': duplicate_stats['renamed_columns'],
                'file_type': file_extension.lstrip('.'),
                'encoding': encoding if file_extension == '.csv' else None,
                'processing_time_seconds': elapsed_time
            }

            return df, stats

        except Exception as e:
            error_message = str(e)
            print(f"Error processing file: {error_message}")
            
            # Add more context to common errors
            if "out of range" in error_message and isinstance(sheet_name, int):
                try:
                    reader = fastexcel.read_excel(file_path)
                    sheet_count = len(reader.sheet_names)
                    sheet_names = reader.sheet_names
                    error_message = f"Sheet index {sheet_name} is out of range. File has {sheet_count} sheets (indices 0-{sheet_count-1}). Available sheets: {sheet_names}"
                except:
                    pass
            
            return None, {
                'error': error_message,
                'file_path': file_path,
                'file_extension': Path(file_path).suffix.lower(),
                'elapsed_time': time() - start_time_total
            }

    @timing_decorator
    def _handle_duplicate_columns(self, headers: pd.Series) -> Dict[str, Any]:
        """Handle duplicate column names in the header row - ultra-optimized version."""
        # Convert to strings and strip in a single operation
        header_list = [str(h).strip() for h in headers]
        
        # Ultra-fast duplicate handling using dictionary for O(n) performance
        from collections import defaultdict
        seen = {}
        counts = defaultdict(int)
        final_headers = []
        renamed_columns = {}
        
        # Single-pass O(n) algorithm
        for idx, header in enumerate(header_list):
            counts[header] += 1
            
            if header in seen:
                # This is a duplicate, create new name with count
                count = counts[header]
                new_name = f"{header}_{count}"
                final_headers.append(new_name)
                renamed_columns[f"{header} (Col {idx + 1})"] = new_name
            else:
                seen[header] = True
                final_headers.append(header)
        
        # Filter to only include true duplicates (count > 1)
        duplicate_counts = {k: v for k, v in counts.items() if v > 1}
        
        return {
            'final_headers': final_headers,
            'duplicate_counts': duplicate_counts,
            'renamed_columns': renamed_columns
        }

    @timing_decorator
    def _find_header_row(self, df: pd.DataFrame) -> Optional[int]:
        """Find the most likely header row in a dataframe - optimized version."""
        # Limit to first 20 rows for faster header detection
        df_sample = df.head(20) if len(df) > 20 else df
        
        # Pre-compute type information for all cells at once (vectorized)
        # This is much faster than checking row by row with apply
        dtypes = df_sample.dtypes
        
        max_non_null_count = 0
        potential_header_row = 0  # Default to first row
        
        # Process in batches for better performance
        for idx, row in df_sample.iterrows():
            # Count non-null values directly (faster)
            non_null_count = row.notna().sum()
            
            # Check if this row has more string values than numeric
            # Use faster vectorized operations
            string_count = sum(isinstance(v, str) for v in row if pd.notna(v))
            numeric_count = sum(isinstance(v, (int, float)) for v in row if pd.notna(v))
            
            # Skip rows that are primarily numeric
            if numeric_count > string_count:
                continue
            
            # If this row has more non-null values than previous best, update
            if non_null_count > max_non_null_count:
                max_non_null_count = non_null_count
                potential_header_row = idx
        
        return potential_header_row
    
    

    @timing_decorator
    def _clean_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ultra-fast implementation for cleaning dataframe values and columns.
        """
        # 1. Just clean column names and return immediately if too many rows
        # This is the fastest possible approach
        df.columns = [str(col).strip() for col in df.columns]
        
        # ULTRA FAST PATH: For very large dataframes, just clean column names and skip NA processing
        row_count = len(df)
        if row_count > 50000:
            print(f"Very large dataframe detected: {row_count} rows. Skipping NA processing.")
            return df
            
        # SUPER FAST PATH: For large dataframes, limited processing
        if row_count > 10000:
            # Limit processing to just checking for empty strings in a sample of columns
            str_cols = df.select_dtypes(include=['object']).columns
            
            # Only process a few columns (max 5) to prevent slowdowns
            sample_cols = str_cols[:5] if len(str_cols) > 5 else str_cols
            
            # Only check for empty strings (by far the most common NA pattern)
            for col in sample_cols:
                # This is extremely fast
                mask = df[col] == ''
                if mask.any():
                    df.loc[mask, col] = np.nan
                    
            return df
        
        # FAST PATH: For medium-sized dataframes
        # Only process string columns with very few unique values
        str_cols = df.select_dtypes(include=['object']).columns
        
        # Extremely limited set of NA values to check (just the most common ones)
        # This greatly improves performance
        common_na_values = ['', 'nan', 'null']
        
        # Process up to 10 string columns at most
        for col in str_cols[:10]:
            # Only check columns with very few unique values
            unique_count = df[col].nunique()
            if pd.notna(unique_count) and unique_count < 20:
                # Only check the simplest, most common NA values
                mask = df[col].isin(common_na_values)
                if mask.any():
                    df.loc[mask, col] = np.nan
        
        return df

    

    @timing_decorator
    def get_column_stats(self, df: pd.DataFrame, column: str) -> Dict[str, Any]:
        """
        Get statistics for a column.
        
        Args:
            df: DataFrame containing the data
            column: Name of the column to analyze
            
        Returns:
            Dictionary containing column statistics
        """
        if column not in df.columns:
            return {
                'error': 'Column not found in DataFrame',
                'unique_values': 0,
                'non_null_count': 0,
                'null_count': 0
            }
            
        try:
            # Get series data
            series = df[column]
            
            # Basic stats that work for any data type
            stats = {
                'non_null_count': int(series.count()),
                'null_count': int(series.isnull().sum()),
                'unique_values': int(series.nunique()),
                'dtype': str(series.dtype)
            }
            
            # Add sample values (converted to strings)
            non_null_values = series.dropna()
            if not non_null_values.empty:
                sample_size = min(5, len(non_null_values))
                stats['sample_values'] = [str(val) for val in non_null_values.head(sample_size)]
            
            # Try numeric stats only if appropriate
            if pd.api.types.is_numeric_dtype(series):
                # Drop any non-numeric values before calculating stats
                numeric_series = pd.to_numeric(series.dropna(), errors='coerce')
                numeric_series = numeric_series.dropna()
                
                if not numeric_series.empty:
                    stats.update({
                        'mean': float(numeric_series.mean()),
                        'median': float(numeric_series.median()),
                        'std': float(numeric_series.std()),
                        'min': float(numeric_series.min()),
                        'max': float(numeric_series.max())
                    })
            
            return stats
            
        except Exception as e:
            return {
                'error': f'Error calculating stats: {str(e)}',
                'unique_values': 0,
                'non_null_count': 0,
                'null_count': 0
            }


# Example usage
    @timing_decorator
    def save_processed_file(self, df: pd.DataFrame, filename: str, app_state: AppState, file_type: str = 'csv') -> str:
        """Save processed dataframe to processed folder with specified format."""
        # if file_type == 'excel':
        #     output_path = os.path.join(self.processed_folder, f"processed_{filename}.csv")
        #     df.to_csv(output_path, index=False)
        
        mapped_file_name = app_state.file_type_mappings[filename]
        

        
        if file_type == 'csv':
            output_path = os.path.join(self.processed_folder, f"processed_{mapped_file_name}.csv")
            
            print("*******************************")
            print("Saved processed file :- ",mapped_file_name)
            print("Output path          :- ",output_path)
            print("*******************************")
            df.to_csv(output_path, index=False)
        else:
            raise ValueError("Unsupported file type. Choose 'excel' or 'csv'.")
        return output_path
    
    @timing_decorator
    def save_mapped_file(self, df: pd.DataFrame, filename: str, file_type: str = 'csv') -> str:
        """Save processed dataframe to processed folder with specified format."""
        if file_type == 'csv':
            output_path = os.path.join(self.mapped_folder, f"mapped_{filename}.csv")
            df.to_csv(output_path, index=False)
        else:
            raise ValueError("Unsupported file type. Choose 'excel' or 'csv'.")
        return output_path
    
    @timing_decorator
    def save_result_file(self, df: pd.DataFrame, filename: str, file_type: str = 'excel') -> str:
        """Save processed dataframe to processed folder with specified format."""
        if file_type == 'excel':
            output_path = os.path.join(self.result_folder, f"result_{filename}.xlsx")
            df.to_excel(output_path, index=False)
        elif file_type == 'csv':
            output_path = os.path.join(self.result_folder, f"result_{filename}.csv")
            df.to_csv(output_path, index=False)
        else:
            raise ValueError("Unsupported file type. Choose 'excel' or 'csv'.")
        return output_path
