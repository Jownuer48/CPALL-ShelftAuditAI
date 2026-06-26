import os
import shutil
import uuid
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai_analyzer import reference_status_items
from database import (
    create_inspection,
    get_all_inspections,
    get_inspection,
    init_db,
    update_inspection_status,
)
from queue_client import SHELF_QUEUE_NAME, publish_job

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ANNOTATED_DIR = os.path.join(BASE_DIR, "annotated")
REFERENCE_DIR = os.path.join(BASE_DIR, "reference")
PLANOGRAM_DIR = os.path.join(BASE_DIR, "planograms")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ANNOTATED_DIR, exist_ok=True)
os.makedirs(REFERENCE_DIR, exist_ok=True)
os.makedirs(PLANOGRAM_DIR, exist_ok=True)

app = FastAPI(title="Shelf Audit AI API", description="Queue-based shelf audit backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/files/uploads", StaticFiles(directory=UPLOAD_DIR), name="files_uploads")
app.mount(
    "/files/annotated",
    StaticFiles(directory=ANNOTATED_DIR),
    name="files_annotated",
)


@app.on_event("startup")
def startup_event() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(ANNOTATED_DIR, exist_ok=True)
    os.makedirs(REFERENCE_DIR, exist_ok=True)
    os.makedirs(PLANOGRAM_DIR, exist_ok=True)
    init_db()


@app.get("/")
def root():
    return {
        "message": "Shelf Audit AI API is running in queue mode",
        "docs": "/docs",
        "queue": SHELF_QUEUE_NAME,
        "results": "/results",
    }


@app.post("/upload")
async def upload_image(
    branch_code: str = Form(...),
    file: UploadFile = File(...),
):
    original_filename = file.filename or "upload.jpg"
    file_ext = os.path.splitext(original_filename)[1].lower()

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="รองรับเฉพาะไฟล์ .jpg .jpeg .png .webp",
        )

    image_name = f"{uuid.uuid4().hex}{file_ext}"
    save_path = os.path.abspath(os.path.join(UPLOAD_DIR, image_name))

    try:
        with open(save_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"บันทึกรูปไม่สำเร็จ: {exc}") from exc

    inspection_id = create_inspection(branch_code=branch_code, image_name=image_name)

    try:
        publish_job({"inspection_id": inspection_id, "image_path": save_path})
    except Exception as exc:
        update_inspection_status(inspection_id, "FAILED", str(exc))
        raise HTTPException(
            status_code=503,
            detail={
                "inspection_id": inspection_id,
                "status": "FAILED",
                "message": "Upload saved, but RabbitMQ publish failed.",
                "error": str(exc),
            },
        ) from exc

    return {
        "inspection_id": inspection_id,
        "id": inspection_id,
        "status": "PENDING",
        "result": "PENDING",
        "detected_model": None,
        "model_score": None,
        "missing_count": 0,
        "missing_items": [],
        "image_name": image_name,
        "image_url": f"/files/uploads/{image_name}",
        "annotated_image_name": None,
        "annotated_image_url": None,
        "message": "Upload received. Analysis is queued.",
    }


@app.get("/results")
def results(limit: int = Query(default=100, ge=1, le=500)):
    return get_all_inspections(limit=limit)


@app.get("/inspections/{inspection_id}")
def inspection_detail(inspection_id: int):
    inspection = get_inspection(inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")

    return inspection


@app.get("/reference/status")
def reference_status():
    items = reference_status_items()
    return {
        "complete": all(item["exists"] for item in items),
        "items": items,
    }


@app.get("/queue/health")
def queue_health():
    try:
        publish_job({"type": "health_check"})
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"ok": False, "queue": SHELF_QUEUE_NAME, "error": str(exc)},
        ) from exc

    return {"ok": True, "queue": SHELF_QUEUE_NAME, "message": "RabbitMQ accepted health check."}
