from celery_app import app
from file_processor import FileProcessor

# point this at the same folder you use in api.py
processor = FileProcessor(base_folder="./data")

@app.task(bind=True)
def process_file(self, file_path: str, sheet_index: int):
    """
    1) Save & read the file
    2) Clean it
    3) Return a small preview + stats for the client
    """
    import logging
    logger = logging.getLogger("tasks")
    
    # Step A: actually read & clean
    df, stats = processor.process_excel_file(file_path, sheet_name=sheet_index)

    # Step B: prepare a JSON-serializable preview
    preview = []
    if df is not None:
        preview = df.head(10).to_dict(orient="records")
        logger.warning(f"Preview data generated: {len(preview)} rows")

    # Step C: format summary for the client UI
    formatted_summary = {
        "total_rows": stats.get("final_rows", 0),
        "total_columns": stats.get("final_cols", 0),
        "processing_time": stats.get("processing_time_seconds", 0),
        "stats": stats
    }
    
    logger.warning(f"Returning task result with summary and preview data")

    return {
        "preview": preview,
        "summary": formatted_summary,
    }
