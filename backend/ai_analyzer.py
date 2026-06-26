import json
import os
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REFERENCE_DIR = os.path.join(BASE_DIR, "reference")
PLANOGRAM_DIR = os.path.join(BASE_DIR, "planograms")

IMAGE_SIZE = (800, 600)
MODEL_THRESHOLD = 0.45
SLOT_THRESHOLD = 0.62

REFERENCE_MODELS = {
    "MODEL_A": "model_a",
    "MODEL_B": "model_b",
    "MODEL_C": "model_c",
    "MODEL_D": "model_d",
}

PLANOGRAM_FILES = {
    "MODEL_A": "model_a.json",
    "MODEL_B": "model_b.json",
    "MODEL_C": "model_c.json",
    "MODEL_D": "model_d.json",
}

REFERENCE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def read_image(path: str) -> Optional[np.ndarray]:
    img = cv2.imread(path)
    if img is None:
        return None

    return cv2.resize(img, IMAGE_SIZE)


def to_gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def calc_ssim(img_a: np.ndarray, img_b: np.ndarray) -> float:
    gray_a = to_gray(img_a)
    gray_b = to_gray(img_b)
    score = ssim(gray_a, gray_b)
    return round(float(score), 4)


def find_reference_file(model_key: str) -> Optional[str]:
    base_name = REFERENCE_MODELS[model_key]

    for ext in REFERENCE_EXTENSIONS:
        path = os.path.join(REFERENCE_DIR, f"{base_name}{ext}")
        if os.path.exists(path):
            return path

    return None


def reference_status_items() -> List[Dict]:
    items = []

    for model_id, base_name in REFERENCE_MODELS.items():
        found_path = find_reference_file(model_id)
        items.append(
            {
                "model_id": model_id,
                "exists": found_path is not None,
                "file": os.path.basename(found_path) if found_path else None,
                "expected": [f"{base_name}{ext}" for ext in REFERENCE_EXTENSIONS],
            }
        )

    return items


def load_reference_images() -> Dict[str, np.ndarray]:
    refs = {}

    for model_id in REFERENCE_MODELS:
        path = find_reference_file(model_id)
        if not path:
            continue

        img = read_image(path)
        if img is not None:
            refs[model_id] = img

    return refs


def detect_shelf_model(uploaded_img: np.ndarray) -> Dict:
    refs = load_reference_images()

    if not refs:
        return {
            "detected_model": "UNKNOWN",
            "model_score": 0.0,
            "scores": {},
            "message": "No reference images found.",
        }

    scores = {model_id: calc_ssim(uploaded_img, ref_img) for model_id, ref_img in refs.items()}
    detected_model = max(scores, key=scores.get)
    model_score = scores[detected_model]

    if model_score < MODEL_THRESHOLD:
        return {
            "detected_model": "UNKNOWN",
            "model_score": model_score,
            "scores": scores,
            "message": "Best reference score is below threshold.",
        }

    return {
        "detected_model": detected_model,
        "model_score": model_score,
        "scores": scores,
        "message": "success",
    }


def load_planogram(model_id: str) -> Dict:
    filename = PLANOGRAM_FILES.get(model_id)
    if not filename:
        return {"model_id": model_id, "slots": []}

    path = os.path.join(PLANOGRAM_DIR, filename)
    if not os.path.exists(path):
        return {"model_id": model_id, "slots": []}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"model_id": model_id, "slots": []}


def normalized_to_pixel(slot: Dict) -> Tuple[int, int, int, int]:
    img_w, img_h = IMAGE_SIZE

    x = int(float(slot["x"]) * img_w)
    y = int(float(slot["y"]) * img_h)
    w = int(float(slot["w"]) * img_w)
    h = int(float(slot["h"]) * img_h)

    x = max(0, min(x, img_w - 1))
    y = max(0, min(y, img_h - 1))
    w = max(1, w)
    h = max(1, h)

    if x + w > img_w:
        w = img_w - x

    if y + h > img_h:
        h = img_h - y

    return x, y, w, h


def crop_slot(img: np.ndarray, slot: Dict) -> np.ndarray:
    x, y, w, h = normalized_to_pixel(slot)
    return img[y:y + h, x:x + w]


def check_missing_items(uploaded_img: np.ndarray, model_id: str) -> List[Dict]:
    ref_path = find_reference_file(model_id)
    if not ref_path:
        return []

    ref_img = read_image(ref_path)
    if ref_img is None:
        return []

    planogram = load_planogram(model_id)
    slots = planogram.get("slots", []) or []
    missing_items = []

    for slot in slots:
        try:
            uploaded_crop = crop_slot(uploaded_img, slot)
            ref_crop = crop_slot(ref_img, slot)
        except (KeyError, TypeError, ValueError):
            continue

        if uploaded_crop.size == 0 or ref_crop.size == 0:
            continue

        uploaded_crop = cv2.resize(uploaded_crop, (160, 160))
        ref_crop = cv2.resize(ref_crop, (160, 160))
        slot_score = calc_ssim(uploaded_crop, ref_crop)

        if slot_score < SLOT_THRESHOLD:
            missing_items.append(
                {
                    "slot_id": slot.get("slot_id"),
                    "product_name": slot.get("product_name"),
                    "score": slot_score,
                    "status": "MISSING_OR_WRONG",
                }
            )

    return missing_items


def analyze_image(image_path: str) -> Dict:
    uploaded_img = read_image(image_path)
    if uploaded_img is None:
        raise ValueError(f"Could not read image: {image_path}")

    model_result = detect_shelf_model(uploaded_img)
    detected_model = model_result["detected_model"]
    model_score = float(model_result["model_score"])

    if detected_model == "UNKNOWN":
        return {
            "detected_model": "UNKNOWN",
            "model_score": model_score,
            "result": "UNKNOWN_MODEL",
            "missing_count": 0,
            "missing_items": [],
        }

    missing_items = check_missing_items(uploaded_img, detected_model)
    result = "PASS" if len(missing_items) == 0 else "FAIL"

    return {
        "detected_model": detected_model,
        "model_score": model_score,
        "result": result,
        "missing_count": len(missing_items),
        "missing_items": missing_items,
    }
