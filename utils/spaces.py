import os
import uuid
from datetime import datetime
import boto3
from botocore.client import Config
from dotenv import load_dotenv
import pandas as pd
from typing import Optional, Dict, Any
from utils.logging import get_logger, timing_decorator

# Load environment variables
load_dotenv()

logger = get_logger(__name__)

class DOSpacesHandler:
    """
    Digital Ocean Spaces handler for storing and retrieving files
    """
    
    def __init__(self):
        """Initialize connection to DO Spaces"""
        # Load required environment variables
        self.spaces_key = os.environ.get("DO_SPACES_KEY")
        self.spaces_secret = os.environ.get("DO_SPACES_SECRET")
        self.endpoint_url = os.environ.get("DO_ENDPOINT")
        self.bucket_name = os.environ.get("DO_SPACES_BUCKET")
        
        # Validate required config
        if not all([self.spaces_key, self.spaces_secret, self.endpoint_url, self.bucket_name]):
            raise ValueError("Missing required Digital Ocean Spaces configuration in environment variables")
        
        # Initialize the S3 client with DO Spaces configuration
        self.session = boto3.session.Session()
        self.client = self.session.client(
            's3',
            region_name='blr1',  # Region for Digital Ocean Spaces
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.spaces_key,
            aws_secret_access_key=self.spaces_secret
        )
        
        logger.info(f"Initialized Digital Ocean Spaces connection to bucket: {self.bucket_name}")
        
    @timing_decorator
    def upload_dataframe_as_parquet(self, 
                                   df: pd.DataFrame, 
                                   project_id: int,
                                   sheet_type: str,
                                   folder_path: str = "processed_data") -> Dict[str, Any]:
        """
        Upload a pandas DataFrame as a parquet file to DO Spaces
        
        Args:
            df: The pandas DataFrame to upload
            project_id: The ID of the project
            sheet_type: The type of the sheet
            folder_path: The folder path in the bucket (defaults to "processed_data")
            
        Returns:
            Dict with file URL and metadata
        """
        if df is None or df.empty:
            raise ValueError("Cannot upload empty DataFrame")
        
        # Create a unique filename with timestamp and UUID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for brevity
        
        # Format: project_id/sheet_type/timestamp_uuid.parquet
        filename = f"{project_id}/{sheet_type}/{timestamp}_{unique_id}.parquet"
        full_path = f"{folder_path}/{filename}"
        
        try:
            # Convert DataFrame to parquet bytes
            parquet_buffer = df.to_parquet()
            
            # Upload to DO Spaces
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=full_path,
                Body=parquet_buffer,
                ACL='private',  # Change to 'public-read' if you want it publicly accessible
                ContentType='application/octet-stream'
            )
            
            # Generate the URL for the uploaded file
            file_url = f"{self.endpoint_url}/{self.bucket_name}/{full_path}"
            
            logger.info(f"Successfully uploaded DataFrame as parquet to {file_url}")
            
            # Return metadata about the upload
            return {
                "file_url": file_url,
                "file_path": full_path,
                "project_id": project_id,
                "sheet_type": sheet_type,
                "timestamp": timestamp,
                "unique_id": unique_id,
                "rows": len(df),
                "columns": len(df.columns)
            }
            
        except Exception as e:
            logger.error(f"Error uploading DataFrame to DO Spaces: {str(e)}")
            raise
    
    @timing_decorator
    def download_parquet_as_dataframe(self, file_path: str) -> pd.DataFrame:
        """
        Download a parquet file from DO Spaces and load it as a DataFrame
        
        Args:
            file_path: Path of the file in the bucket
            
        Returns:
            pandas DataFrame
        """
        try:
            # Get the object from DO Spaces
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=file_path
            )
            
            # Read the parquet content into a DataFrame
            parquet_content = response['Body'].read()
            df = pd.read_parquet(parquet_content)
            
            logger.info(f"Successfully downloaded and loaded parquet file from {file_path}")
            return df
            
        except Exception as e:
            logger.error(f"Error downloading parquet file from DO Spaces: {str(e)}")
            raise
    
    def generate_presigned_url(self, file_path: str, expiration: int = 3600) -> str:
        """
        Generate a presigned URL for temporary access to a file
        
        Args:
            file_path: Path of the file in the bucket
            expiration: Expiration time in seconds (default: 1 hour)
            
        Returns:
            Presigned URL string
        """
        try:
            url = self.client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.bucket_name,
                    'Key': file_path
                },
                ExpiresIn=expiration
            )
            return url
        except Exception as e:
            logger.error(f"Error generating presigned URL: {str(e)}")
            raise
