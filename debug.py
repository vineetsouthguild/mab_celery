# Add this to the end of your api.py file

@app.post("/upload-debug")
async def upload_debug(file: UploadFile = File(...)):
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
        yield "data: " + json.dumps({"status": "uploaded", "task_id": task.id, "percentage": 10, "filename": filename}) + "\n\n"
        yield "data: " + json.dumps({"status": "reading", "task_id": task.id, "percentage": 20}) + "\n\n"

        # Wait for the task to complete
        while True:
            res = AsyncResult(task.id)
            state = res.state

            if state == "PENDING":
                # still waiting for a worker
                yield "data: " + json.dumps({"status": "pending", "task_id": task.id, "percentage": 30, "message": "Waiting for worker..."}) + "\n\n"
                await asyncio.sleep(0.5)
                continue

            if state == "STARTED":
                yield "data: " + json.dumps({"status": "processing", "task_id": task.id, "percentage": 50, "message": "Processing file..."}) + "\n\n"
                await asyncio.sleep(1)

            if state == "SUCCESS":
                payload = res.result or {}
                preview_data = payload.get("preview", [])
                summary_data = payload.get("summary", {})
                
                # Add debug information to the payload
                debug_payload = {
                    "status": "done",
                    "task_id": task.id,
                    "percentage": 100,
                    "preview": preview_data,
                    "summary": summary_data,
                    "debug_info": {
                        "result_type": str(type(res.result)),
                        "preview_type": str(type(preview_data)),
                        "preview_length": len(preview_data) if isinstance(preview_data, list) else 0,
                        "summary_type": str(type(summary_data)),
                        "summary_keys": list(summary_data.keys()) if isinstance(summary_data, dict) else []
                    }
                }
                
                yield "data: " + json.dumps(debug_payload) + "\n\n"
                break

            if state == "FAILURE":
                yield "data: " + json.dumps({
                    "status": "error",
                    "task_id": task.id,
                    "message": str(res.result),
                }) + "\n\n"
                break

            # other states (RETRY, etc)
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
