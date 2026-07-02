import os
import shutil
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ai_analyzer import reference_status_items
from database import (
    create_inspection,
    get_all_inspections,
    get_connection as get_db_connection,
    get_database_backend,
    get_inspection,
    get_pending_inspections,
    init_db,
    mark_inspection_failed,
    reset_inspection_for_retry,
    update_inspection_status,
)
from queue_client import (
    RABBITMQ_HOST,
    RABBITMQ_PORT,
    SHELF_QUEUE_NAME,
    get_connection as get_rabbitmq_connection,
    publish_job,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
ANNOTATED_DIR = os.path.join(BASE_DIR, "annotated")
REFERENCE_DIR = os.path.join(BASE_DIR, "reference")
PLANOGRAM_DIR = os.path.join(BASE_DIR, "planograms")
YOLO_MODELS_DIR = os.path.join(BASE_DIR, "yolo_models")

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ADMIN_MARK_FAILED_MESSAGE = "Marked failed by admin action because job was stuck or could not complete."
REQUIRED_MODEL_FILES = [
    ("sku110k_product", os.path.join(YOLO_MODELS_DIR, "experiments", "sku110k_product.pt")),
    ("shelf_yolo", os.path.join(YOLO_MODELS_DIR, "shelf_yolo.pt")),
]

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


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def health_db_status() -> Dict[str, Any]:
    try:
        mode = get_database_backend()
        with get_db_connection() as conn:
            row = conn.execute("SELECT 1 AS ok").fetchone()

        if row is None:
            return {
                "status": "error",
                "mode": mode,
                "message": "Database query returned no rows.",
            }

        return {
            "status": "ok",
            "mode": mode,
            "message": "Database connectivity ok.",
        }
    except Exception as exc:
        try:
            mode = get_database_backend()
        except Exception:
            mode = "unknown"
        return {
            "status": "error",
            "mode": mode,
            "message": str(exc),
        }


def health_rabbitmq_status() -> Dict[str, Any]:
    connection = None
    try:
        connection = get_rabbitmq_connection()
        channel = connection.channel()
        channel.queue_declare(queue=SHELF_QUEUE_NAME, durable=True)
        channel.close()
        return {
            "status": "ok",
            "host": RABBITMQ_HOST,
            "port": RABBITMQ_PORT,
            "queue": SHELF_QUEUE_NAME,
            "message": "RabbitMQ connectivity ok.",
        }
    except Exception as exc:
        return {
            "status": "error",
            "host": RABBITMQ_HOST,
            "port": RABBITMQ_PORT,
            "queue": SHELF_QUEUE_NAME,
            "message": str(exc),
        }
    finally:
        if connection and connection.is_open:
            connection.close()


def health_models_status() -> Dict[str, Any]:
    models = []
    missing = []

    for name, path in REQUIRED_MODEL_FILES:
        exists = os.path.exists(path)
        size_bytes = os.path.getsize(path) if exists else 0
        ok = exists and size_bytes > 0
        relative_path = os.path.relpath(path, os.path.dirname(BASE_DIR))
        model = {
            "name": name,
            "path": relative_path.replace("\\", "/"),
            "exists": exists,
            "size_bytes": size_bytes,
            "status": "ok" if ok else "error",
        }
        models.append(model)
        if not ok:
            missing.append(model["path"])

    return {
        "status": "ok" if not missing else "error",
        "models": models,
        "missing": missing,
        "message": (
            "All required model files are present."
            if not missing
            else "Required model files are missing or empty."
        ),
    }


def overall_health_status(*components: Dict[str, Any]) -> str:
    statuses = [str(component.get("status", "error")) for component in components]
    if any(status == "error" for status in statuses):
        return "error"
    if any(status == "degraded" for status in statuses):
        return "degraded"
    return "ok"


@app.get("/health/db")
def health_db():
    return health_db_status()


@app.get("/health/rabbitmq")
def health_rabbitmq():
    return health_rabbitmq_status()


@app.get("/health/models")
def health_models():
    return health_models_status()


@app.get("/health")
def health():
    database = health_db_status()
    rabbitmq = health_rabbitmq_status()
    models = health_models_status()
    return {
        "status": overall_health_status(database, rabbitmq, models),
        "timestamp": utc_timestamp(),
        "analysis_mode": os.getenv("SHELF_AUDIT_ANALYSIS_MODE", "hybrid"),
        "database": database,
        "rabbitmq": rabbitmq,
        "models": models,
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
