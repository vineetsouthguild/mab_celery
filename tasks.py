from celery_app import app
from file_processor import FileProcessor
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os
from models.table_models import Project, ProcessingJob, FileMetadata, SheetData
from datetime import datetime

# point this at the same folder you use in api.py
processor = FileProcessor(base_folder="./data")

@app.task(bind=True)
def process_file(self, file_path: str, sheet_index: int, project_id: int = None, sheet_type: str = None):
    """
    1) Save & read the file
    2) Clean it
    3) Convert to parquet and upload to DO Spaces if project_id and sheet_type are provided
    4) Update database with the space_link
    5) Return a small preview + stats for the client
    """
    import logging
    logger = logging.getLogger("tasks")
    
    # Step A: actually read & clean
    df, stats = processor.process_excel_file(file_path, sheet_name=sheet_index)
    
    # Step B: prepare a JSON-serializable preview
    preview = []
    space_link = None
    
    if df is not None:
        preview = df.head(10).to_dict(orient="records")
        logger.warning(f"Preview data generated: {len(preview)} rows")
        
        # Step C: If project_id and sheet_type provided, convert to parquet and upload to DO
        if project_id is not None and sheet_type is not None:
            try:
                # Convert to parquet and upload to DO Spaces
                space_link = processor.convert_to_parquet_and_upload(df, project_id, sheet_type)
                
                # Update database with the space_link
                update_database_with_space_link(project_id, space_link, sheet_type, file_path)
                
                logger.warning(f"File uploaded to DO Spaces: {space_link}")
            except Exception as e:
                logger.error(f"Error uploading to DO Spaces: {str(e)}")
    
    # Step D: format summary for the client UI
    formatted_summary = {
        "total_rows": stats.get("final_rows", 0),
        "total_columns": stats.get("final_cols", 0),
        "processing_time": stats.get("processing_time_seconds", 0),
        "stats": stats,
        "space_link": space_link  # Include the DO Spaces link if available
    }
    
    logger.warning(f"Returning task result with summary and preview data")

    return {
        "preview": preview,
        "summary": formatted_summary,
    }

def update_database_with_space_link(project_id, space_link, sheet_type, file_path):
    """Update database with the space_link"""
    session = None
    try:
        # Get database connection
        database_url = os.getenv('DATABASE_URL')
        engine = create_engine(database_url)
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Update project with space_link
        project = session.query(Project).filter(Project.id == project_id).first()
        if project:
            project.space_link = space_link
            project.updated_at = datetime.utcnow()
        
        # Create or update sheet_data record
        # Find the file metadata for this file path
        filename = os.path.basename(file_path)
        file_meta = session.query(FileMetadata).filter(
            FileMetadata.original_filename == filename,
            FileMetadata.project_id == project_id
        ).first()
        
        if file_meta and file_meta.file_sheets:
            # Get the first sheet (we can enhance this logic as needed)
            sheet = file_meta.file_sheets[0]
            
            # Check if a SheetData record exists
            sheet_data = session.query(SheetData).filter(
                SheetData.sheet_id == sheet.id,
                SheetData.project_id == project_id
            ).first()
            
            # Create or update SheetData record
            if not sheet_data:
                sheet_data = SheetData(
                    sheet_id=sheet.id,
                    project_id=project_id,
                    document_number=f"{project_id}-{sheet_type}",
                    document_date=datetime.utcnow().date(),
                    sheet_space_link=space_link,
                    created_at=datetime.utcnow()
                )
                session.add(sheet_data)
            else:
                sheet_data.sheet_space_link = space_link
                sheet_data.updated_at = datetime.utcnow()
        
        # Commit changes
        session.commit()
        
    except Exception as e:
        logger.error(f"Error updating database with space_link: {str(e)}")
        if session:
            session.rollback()
    finally:
        if session:
            session.close()
