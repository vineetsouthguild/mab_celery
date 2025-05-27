from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class FileMapping(BaseModel):
    file_id: int
    file_name: str
    sheet_type: str
    sheet_index: int
    is_validated: bool


class AppState(BaseModel):
    mappings: List[FileMapping]
    updated_at: str
    file_type_mappings: Dict[str, str] = {}  # Maps original filename to mapped filename
