import asyncio
import json
import os
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from starlette.staticfiles import StaticFiles
from celery.result import AsyncResult

from file_processor import FileProcessor
from models.schemas import AppState, FileMapping
from tasks import process_file

app = FastAPI()
processor = FileProcessor(base_folder="./data")

# serve a simple client if you like
app.mount("/static", StaticFiles(directory="static"), name="static")
@app.get("/")
def index():
    return FileResponse("static/client.html")


def load_config() -> AppState:
    try:
        with open("test.json") as f:
            return AppState(**json.load(f))
    except FileNotFoundError:
        # Create a default configuration if file doesn't exist
        default_config = {
            "mappings": [
                {
                    "file_id": 1,
                    "file_name": "SAP 3.xlsx",
                    "sheet_type": "SAP",
                    "sheet_index": 0,
                    "is_validated": True
                }
            ],
            "updated_at": datetime.now().isoformat(),
            "file_type_mappings": {}
        }
        # Save the default configuration
        with open("test.json", "w") as f:
            json.dump(default_config, f, indent=2)
        return AppState(**default_config)


def get_file_mapping(app_state: AppState, filename: str) -> FileMapping:
    for m in app_state.mappings:
        if m.file_name == filename:
            return m
    raise HTTPException(400, f"No mapping for {filename}")


def sse_event(event: str, data: dict):
    payload = json.dumps(data)
    # Standard SSE format without the event field (using data only)
    return f"data: {payload}\n\n"


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    contents = await file.read()
    filename = file.filename

    # 1) save to disk
    file_path = processor.save_uploaded_file(contents, filename)

    # 2) decide which sheet to use
    app_state = load_config()
    mapping = get_file_mapping(app_state, filename)
    sheet_index = mapping.sheet_index

    # 3) enqueue a Celery job
    task = process_file.delay(file_path, sheet_index)

    # 4) stream back status via SSE
    async def event_stream():
        # initial queued event
        yield sse_event("queued",      {"status": "uploaded", "task_id": task.id, "percentage": 10, "filename": filename})
        yield sse_event("started",     {"status": "reading", "task_id": task.id, "percentage": 20})

        while True:
            res = AsyncResult(task.id)
            state = res.state

            if state == "PENDING":
                # still waiting for a worker
                await asyncio.sleep(0.5)
                continue

            if state == "STARTED":
                yield sse_event("processing", {"status": "processing", "task_id": task.id, "percentage": 50})

            if state == "SUCCESS":
                payload = res.result or {}
                yield sse_event("done",      {
                    "status": "done",
                    "task_id": task.id,
                    "percentage": 100,
                    "preview": payload.get("preview", []),
                    "summary": payload.get("summary", {}),
                })
                break

            if state == "FAILURE":
                yield sse_event("error",     {
                    "status": "error",
                    "task_id": task.id,
                    "message": str(res.result),
                })
                break

            # other states (RETRY, etc)
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
