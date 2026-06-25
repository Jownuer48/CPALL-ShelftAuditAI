import json
import os
import shutil
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Tuple

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from skimage.metrics import structural_similarity as ssim


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
REFERENCE_DIR = os.path.join(BASE_DIR, "reference")
PLANOGRAM_DIR = os.path.join(BASE_DIR, "planograms")
DB_PATH = os.path.join(BASE_DIR, "shelf_audit.db")

IMAGE_SIZE = (800, 600)

MODEL_THRESHOLD = 0.45
SLOT_THRESHOLD = 0.62

REFERENCE_MODELS = {
    "MODEL_A": "model_a.jpg",
    "MODEL_B": "model_b.jpg",
    "MODEL_C": "model_c.jpg",
    "MODEL_D": "model_d.jpg",
}

PLANOGRAM_FILES = {
    "MODEL_A": "model_a.json",
    "MODEL_B": "model_b.json",
    "MODEL_C": "model_c.json",
    "MODEL_D": "model_d.json",
}

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(REFERENCE_DIR, exist_ok=True)
os.makedirs(PLANOGRAM_DIR, exist_ok=True)


app = FastAPI(title="Shelf Audit AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS inspections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        branch_code TEXT NOT NULL,
        image_name TEXT NOT NULL,
        detected_model TEXT NOT NULL,
        model_score REAL NOT NULL,
        result TEXT NOT NULL,
        missing_count INTEGER NOT NULL,
        missing_items_json TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def read_image(path: str):
    img = cv2.imread(path)
    if img is None:
        return None

    img = cv2.resize(img, IMAGE_SIZE)
    return img


def to_gray(img):
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def calc_ssim(img_a, img_b) -> float:
    gray_a = to_gray(img_a)
    gray_b = to_gray(img_b)
    score = ssim(gray_a, gray_b)
    return round(float(score), 4)


def load_reference_images() -> Dict[str, np.ndarray]:
    refs = {}

    for model_id, filename in REFERENCE_MODELS.items():
        path = os.path.join(REFERENCE_DIR, filename)

        if os.path.exists(path):
            img = read_image(path)
            if img is not None:
                refs[model_id] = img

    return refs


def detect_shelf_model(uploaded_img) -> Dict:
    refs = load_reference_images()

    if not refs:
        return {
            "detected_model": "UNKNOWN",
            "model_score": 0.0,
            "scores": {},
            "message": "ยังไม่มี reference image ในโฟลเดอร์ reference"
        }

    scores = {}

    for model_id, ref_img in refs.items():
        scores[model_id] = calc_ssim(uploaded_img, ref_img)

    detected_model = max(scores, key=scores.get)
    model_score = scores[detected_model]

    if model_score < MODEL_THRESHOLD:
        return {
            "detected_model": "UNKNOWN",
            "model_score": model_score,
            "scores": scores,
            "message": "คะแนนต่ำเกินไป อาจไม่ตรงกับ reference 4 แบบ"
        }

    return {
        "detected_model": detected_model,
        "model_score": model_score,
        "scores": scores,
        "message": "success"
    }


def load_planogram(model_id: str) -> Dict:
    filename = PLANOGRAM_FILES.get(model_id)

    if not filename:
        return {"model_id": model_id, "slots": []}

    path = os.path.join(PLANOGRAM_DIR, filename)

    if not os.path.exists(path):
        return {"model_id": model_id, "slots": []}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalized_to_pixel(slot: Dict) -> Tuple[int, int, int, int]:
    img_w, img_h = IMAGE_SIZE

    x = int(slot["x"] * img_w)
    y = int(slot["y"] * img_h)
    w = int(slot["w"] * img_w)
    h = int(slot["h"] * img_h)

    x = max(0, x)
    y = max(0, y)
    w = max(1, w)
    h = max(1, h)

    if x + w > img_w:
        w = img_w - x

    if y + h > img_h:
        h = img_h - y

    return x, y, w, h


def crop_slot(img, slot: Dict):
    x, y, w, h = normalized_to_pixel(slot)
    return img[y:y + h, x:x + w]


def check_missing_items(uploaded_img, model_id: str) -> List[Dict]:
    ref_filename = REFERENCE_MODELS.get(model_id)
    if not ref_filename:
        return []

    ref_path = os.path.join(REFERENCE_DIR, ref_filename)
    ref_img = read_image(ref_path)

    if ref_img is None:
        return []

    planogram = load_planogram(model_id)
    slots = planogram.get("slots", [])

    missing_items = []

    for slot in slots:
        uploaded_crop = crop_slot(uploaded_img, slot)
        ref_crop = crop_slot(ref_img, slot)

        if uploaded_crop.size == 0 or ref_crop.size == 0:
            continue

        uploaded_crop = cv2.resize(uploaded_crop, (160, 160))
        ref_crop = cv2.resize(ref_crop, (160, 160))

        slot_score = calc_ssim(uploaded_crop, ref_crop)

        if slot_score < SLOT_THRESHOLD:
            missing_items.append({
                "slot_id": slot.get("slot_id"),
                "product_name": slot.get("product_name"),
                "score": slot_score,
                "status": "MISSING_OR_WRONG"
            })

    return missing_items


def save_inspection(
    branch_code: str,
    image_name: str,
    detected_model: str,
    model_score: float,
    result: str,
    missing_items: List[Dict],
) -> None:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO inspections
    (
        branch_code,
        image_name,
        detected_model,
        model_score,
        result,
        missing_count,
        missing_items_json,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        branch_code,
        image_name,
        detected_model,
        model_score,
        result,
        len(missing_items),
        json.dumps(missing_items, ensure_ascii=False),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()


@app.on_event("startup")
def startup_event():
    init_db()


@app.get("/")
def root():
    return {
        "message": "Shelf Audit AI API is running",
        "docs": "/docs",
        "required_reference": list(REFERENCE_MODELS.values())
    }


@app.post("/upload")
async def upload_image(
    branch_code: str = Form(...),
    file: UploadFile = File(...)
):
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in [".jpg", ".jpeg", ".png"]:
        return {
            "success": False,
            "message": "รองรับเฉพาะไฟล์ .jpg .jpeg .png"
        }

    image_name = f"{uuid.uuid4().hex}{file_ext}"
    save_path = os.path.join(UPLOAD_DIR, image_name)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    uploaded_img = read_image(save_path)

    if uploaded_img is None:
        return {
            "success": False,
            "message": "อ่านรูปที่อัปโหลดไม่ได้"
        }

    model_result = detect_shelf_model(uploaded_img)

    detected_model = model_result["detected_model"]
    model_score = model_result["model_score"]

    if detected_model == "UNKNOWN":
        missing_items = []
        final_result = "UNKNOWN_MODEL"
    else:
        missing_items = check_missing_items(uploaded_img, detected_model)
        final_result = "PASS" if len(missing_items) == 0 else "FAIL"

    save_inspection(
        branch_code=branch_code,
        image_name=image_name,
        detected_model=detected_model,
        model_score=model_score,
        result=final_result,
        missing_items=missing_items
    )

    return {
        "success": True,
        "branch_code": branch_code,
        "image_name": image_name,
        "image_url": f"/uploads/{image_name}",
        "detected_model": detected_model,
        "model_score": model_score,
        "model_scores": model_result["scores"],
        "result": final_result,
        "missing_count": len(missing_items),
        "missing_items": missing_items,
        "message": model_result["message"]
    }


@app.get("/results")
def get_results():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        branch_code,
        image_name,
        detected_model,
        model_score,
        result,
        missing_count,
        missing_items_json,
        created_at
    FROM inspections
    ORDER BY id DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    results = []

    for row in rows:
        results.append({
            "id": row["id"],
            "branch_code": row["branch_code"],
            "image_name": row["image_name"],
            "image_url": f"/uploads/{row['image_name']}",
            "detected_model": row["detected_model"],
            "model_score": row["model_score"],
            "result": row["result"],
            "missing_count": row["missing_count"],
            "missing_items": json.loads(row["missing_items_json"]),
            "created_at": row["created_at"]
        })

    return results