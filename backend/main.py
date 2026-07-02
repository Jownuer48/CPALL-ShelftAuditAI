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
    get_pending_inspections,
    init_db,
    mark_inspection_failed,
    reset_inspection_for_retry,
    update_inspection_status,
)
from queue_client import SHELF_QUEUE_NAME, publish_job

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ANNOTATED_DIR = os.path.join(BASE_DIR, "annotated")
REFERENCE_DIR = os.path.join(BASE_DIR, "reference")
PLANOGRAM_DIR = os.path.join(BASE_DIR, "planograms")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ADMIN_MARK_FAILED_MESSAGE = "Marked failed by admin action because job was stuck or could not complete."

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


@app.get("/api/admin/inspections/pending")
def admin_pending_inspections(limit: int = Query(default=100, ge=1, le=500)):
    inspections = get_pending_inspections(limit=limit)
    return {
        "count": len(inspections),
        "inspections": inspections,
    }


@app.post("/api/admin/inspections/{inspection_id}/mark-failed")
def admin_mark_inspection_failed(inspection_id: int):
    inspection = get_inspection(inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")

    updated = mark_inspection_failed(
        inspection_id,
        ADMIN_MARK_FAILED_MESSAGE,
    )
    print(f"[ADMIN] mark-failed inspection_id={inspection_id}")
    return {
        "message": "Inspection marked FAILED by admin action.",
        "inspection": updated,
    }


@app.post("/api/admin/inspections/{inspection_id}/retry")
def admin_retry_inspection(inspection_id: int):
    inspection = get_inspection(inspection_id)
    if inspection is None:
        raise HTTPException(status_code=404, detail="Inspection not found")

    image_name = os.path.basename(str(inspection.get("image_name") or ""))
    if not image_name:
        raise HTTPException(
            status_code=400,
            detail="Inspection has no uploaded image_name to retry.",
        )

    image_path = os.path.abspath(os.path.join(UPLOAD_DIR, image_name))
    upload_root = os.path.abspath(UPLOAD_DIR)
    if not image_path.startswith(upload_root + os.sep):
        raise HTTPException(status_code=400, detail="Invalid uploaded image path.")

    if not os.path.exists(image_path):
        raise HTTPException(
            status_code=404,
            detail=f"Uploaded image not found for retry: {image_name}",
        )

    reset_inspection_for_retry(inspection_id)

    try:
        publish_job({"inspection_id": inspection_id, "image_path": image_path})
    except Exception as exc:
        error_message = f"Admin retry failed because RabbitMQ publish failed: {exc}"
        mark_inspection_failed(inspection_id, error_message)
        print(f"[ADMIN] retry failed inspection_id={inspection_id}: {exc}")
        raise HTTPException(
            status_code=503,
            detail={
                "inspection_id": inspection_id,
                "status": "FAILED",
                "message": "Retry reset the inspection but RabbitMQ publish failed.",
                "error": str(exc),
            },
        ) from exc

    updated = get_inspection(inspection_id)
    print(f"[ADMIN] retry queued inspection_id={inspection_id}")
    return {
        "message": "Inspection retry queued.",
        "queue": SHELF_QUEUE_NAME,
        "inspection": updated,
    }


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
