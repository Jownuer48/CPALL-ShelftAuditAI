import json
import os
import uuid
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
from skimage.metrics import structural_similarity as ssim

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REFERENCE_DIR = os.path.join(BASE_DIR, "reference")
PLANOGRAM_DIR = os.path.join(BASE_DIR, "planograms")
ANNOTATED_DIR = os.path.join(BASE_DIR, "annotated")

IMAGE_SIZE = (800, 600)
MODEL_THRESHOLD = 0.30
SLOT_THRESHOLD = 0.62
SLOT_WARNING_THRESHOLD = 0.72

ACTIVE_MODELS = ["MODEL_A", "MODEL_B", "MODEL_C"]

REFERENCE_MODELS = {
    "MODEL_A": "model_a",
    "MODEL_B": "model_b",
    "MODEL_C": "model_c",
}

PLANOGRAM_FILES = {
    "MODEL_A": "model_a.json",
    "MODEL_B": "model_b.json",
    "MODEL_C": "model_c.json",
}

REFERENCE_EXTENSIONS = (".jpg", ".jpeg", ".png")

BOX_COLORS = {
    "PASS": (0, 190, 0),
    "LOW_SCORE": (0, 190, 255),
    "WARNING": (0, 190, 255),
    "MISSING": (0, 0, 255),
    "FAIL": (0, 0, 255),
    "PROMO_MISSING": (0, 0, 255),
    "UNKNOWN_MODEL": (0, 0, 255),
}
PROMO_PASS_COLOR = (0, 140, 255)
MAX_LABEL_CHARS = 28


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

    for model_id in ACTIVE_MODELS:
        base_name = REFERENCE_MODELS[model_id]
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

    for model_id in ACTIVE_MODELS:
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

    scores = {
        model_id: calc_ssim(uploaded_img, ref_img)
        for model_id, ref_img in refs.items()
    }
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
        with open(path, "r", encoding="utf-8-sig") as f:
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


def slot_to_pixel(image: np.ndarray, slot: Dict) -> Tuple[int, int, int, int]:
    image_h, image_w = image.shape[:2]

    x = int(float(slot["x"]) * image_w)
    y = int(float(slot["y"]) * image_h)
    w = int(float(slot["w"]) * image_w)
    h = int(float(slot["h"]) * image_h)

    x = max(0, min(x, image_w - 1))
    y = max(0, min(y, image_h - 1))
    w = max(1, w)
    h = max(1, h)

    if x + w > image_w:
        w = image_w - x

    if y + h > image_h:
        h = image_h - y

    return x, y, w, h


def crop_slot(img: np.ndarray, slot: Dict) -> np.ndarray:
    x, y, w, h = normalized_to_pixel(slot)
    return img[y:y + h, x:x + w]


def slot_name(slot: Dict) -> str:
    return (
        slot.get("product_name")
        or slot.get("label")
        or slot.get("name")
        or slot.get("slot_id")
        or ""
    )


def short_slot_code(slot_id):
    if not slot_id:
        return ""

    parts = str(slot_id).upper().split("_")

    if len(parts) >= 3 and parts[0]:
        prefix = "P" if "PROMO" in parts else parts[0][0]
        number = parts[-1]
        try:
            return f"{prefix}{int(number):02d}"
        except ValueError:
            return f"{prefix}{number}"

    return str(slot_id).upper()


def truncate_label(text: str, max_chars: int = MAX_LABEL_CHARS) -> str:
    text = " ".join(str(text).split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 1]}…"


def is_promo_slot(slot: Dict) -> bool:
    text = " ".join(
        str(slot.get(key, ""))
        for key in ["slot_id", "product_name", "label", "name", "type"]
    ).lower()
    return "promo" in text or "tag" in text


def annotation_style(slot: Dict, result: Dict) -> Tuple[str, Tuple[int, int, int]]:
    status = result.get("status", "WARNING")
    name = result.get("product_name") or slot_name(slot)
    code = short_slot_code(result.get("slot_id") or slot.get("slot_id"))
    promo = is_promo_slot(slot)

    if status == "PASS":
        if promo:
            return (f"OK {code}" if code else "PROMO OK", PROMO_PASS_COLOR)
        return (f"OK {code}" if code else "OK", BOX_COLORS["PASS"])

    if status in ["MISSING", "FAIL", "PROMO_MISSING"]:
        label = "PROMO MISSING" if status == "PROMO_MISSING" else "MISSING"
        detail = name or code
        text = f"{label}: {detail}" if detail else label
        return (truncate_label(text), BOX_COLORS["MISSING"])

    if status in ["LOW_SCORE", "WARNING"]:
        detail = code or name
        text = f"LOW: {detail}" if detail else "LOW"
        return (truncate_label(text), BOX_COLORS["LOW_SCORE"])

    return (truncate_label(status), BOX_COLORS["WARNING"])


def inspect_slots(
    uploaded_img: np.ndarray,
    model_id: str,
    slots: List[Dict],
) -> Tuple[List[Dict], List[Dict]]:
    ref_path = find_reference_file(model_id)
    if not ref_path:
        return [], []

    ref_img = read_image(ref_path)
    if ref_img is None:
        return [], []

    missing_items = []
    slot_results = []

    for slot in slots:
        try:
            uploaded_crop = crop_slot(uploaded_img, slot)
            ref_crop = crop_slot(ref_img, slot)
        except (KeyError, TypeError, ValueError):
            slot_results.append(
                {
                    "slot": slot,
                    "slot_id": slot.get("slot_id"),
                    "product_name": slot_name(slot),
                    "score": 0.0,
                    "status": "WARNING",
                    "label": "WARNING",
                }
            )
            continue

        if uploaded_crop.size == 0 or ref_crop.size == 0:
            slot_results.append(
                {
                    "slot": slot,
                    "slot_id": slot.get("slot_id"),
                    "product_name": slot_name(slot),
                    "score": 0.0,
                    "status": "WARNING",
                    "label": "WARNING",
                }
            )
            continue

        uploaded_crop = cv2.resize(uploaded_crop, (160, 160))
        ref_crop = cv2.resize(ref_crop, (160, 160))
        slot_score = calc_ssim(uploaded_crop, ref_crop)

        if slot_score < SLOT_THRESHOLD:
            status = "PROMO_MISSING" if is_promo_slot(slot) else "MISSING"
            label = "PROMO MISSING" if status == "PROMO_MISSING" else "MISSING"
            missing_items.append(
                {
                    "slot_id": slot.get("slot_id"),
                    "product_name": slot_name(slot),
                    "score": slot_score,
                    "status": status,
                }
            )
        elif slot_score < SLOT_WARNING_THRESHOLD:
            status = "LOW_SCORE"
            label = "LOW SCORE"
        else:
            status = "PASS"
            label = "PASS"

        slot_results.append(
            {
                "slot": slot,
                "slot_id": slot.get("slot_id"),
                "product_name": slot_name(slot),
                "score": slot_score,
                "status": status,
                "label": label,
            }
        )

    return missing_items, slot_results


def draw_label(
    image: np.ndarray,
    text: str,
    x: int,
    y: int,
    color: Tuple[int, int, int],
) -> None:
    text = truncate_label(text)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.45
    thickness = 1
    padding = 3

    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    label_width = min(text_w + padding * 2, image.shape[1] - 1)
    label_height = text_h + baseline + padding * 2
    label_left = max(0, min(x, image.shape[1] - label_width - 1))
    label_top = max(0, y - label_height)
    label_right = min(image.shape[1] - 1, label_left + label_width)
    label_bottom = min(image.shape[0] - 1, label_top + label_height)

    cv2.rectangle(
        image,
        (label_left, label_top),
        (label_right, label_bottom),
        color,
        -1,
    )
    cv2.putText(
        image,
        text,
        (label_left + padding, label_bottom - baseline - padding),
        font,
        font_scale,
        (0, 0, 0),
        thickness,
        cv2.LINE_AA,
    )


def draw_banner(
    image: np.ndarray,
    text: str,
    color: Tuple[int, int, int],
) -> np.ndarray:
    annotated = image.copy()
    cv2.rectangle(annotated, (0, 0), (annotated.shape[1], 46), color, -1)
    cv2.putText(
        annotated,
        text,
        (14, 31),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (0, 0, 0),
        2,
        cv2.LINE_AA,
    )
    return annotated


def draw_yolo_style_boxes(
    image: np.ndarray,
    slots: List[Dict],
    slot_results: List[Dict],
) -> np.ndarray:
    annotated = image.copy()

    for index, slot in enumerate(slots):
        result = slot_results[index] if index < len(slot_results) else {}
        text, color = annotation_style(slot, result)

        try:
            x, y, w, h = slot_to_pixel(annotated, slot)
        except (KeyError, TypeError, ValueError):
            continue

        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, 3)
        draw_label(annotated, text, x, y, color)

    return annotated


def save_annotated_image(image: np.ndarray) -> str:
    os.makedirs(ANNOTATED_DIR, exist_ok=True)
    image_name = f"inspection_{uuid.uuid4().hex}_annotated.jpg"
    image_path = os.path.join(ANNOTATED_DIR, image_name)
    cv2.imwrite(image_path, image)
    return image_name


def check_missing_items(uploaded_img: np.ndarray, model_id: str) -> List[Dict]:
    planogram = load_planogram(model_id)
    slots = planogram.get("slots", []) or []
    missing_items, _ = inspect_slots(uploaded_img, model_id, slots)
    return missing_items


def analyze_image(image_path: str) -> Dict:
    uploaded_img = read_image(image_path)
    if uploaded_img is None:
        raise ValueError(f"Could not read image: {image_path}")

    model_result = detect_shelf_model(uploaded_img)
    detected_model = model_result["detected_model"]
    model_score = float(model_result["model_score"])

    if detected_model == "UNKNOWN":
        annotated = draw_banner(uploaded_img, "UNKNOWN MODEL", BOX_COLORS["UNKNOWN_MODEL"])
        annotated_image_name = save_annotated_image(annotated)
        return {
            "detected_model": "UNKNOWN",
            "model_score": model_score,
            "result": "UNKNOWN_MODEL",
            "missing_count": 0,
            "missing_items": [],
            "annotated_image_name": annotated_image_name,
        }

    planogram = load_planogram(detected_model)
    slots = planogram.get("slots", []) or []

    if not slots:
        annotated = draw_banner(
            uploaded_img,
            "NO SLOTS CONFIGURED",
            BOX_COLORS["WARNING"],
        )
        annotated_image_name = save_annotated_image(annotated)
        return {
            "detected_model": detected_model,
            "model_score": model_score,
            "result": "PASS",
            "missing_count": 0,
            "missing_items": [],
            "annotated_image_name": annotated_image_name,
        }

    missing_items, slot_results = inspect_slots(uploaded_img, detected_model, slots)
    result = "PASS" if len(missing_items) == 0 else "FAIL"
    annotated = draw_yolo_style_boxes(uploaded_img, slots, slot_results)
    annotated_image_name = save_annotated_image(annotated)

    return {
        "detected_model": detected_model,
        "model_score": model_score,
        "result": result,
        "missing_count": len(missing_items),
        "missing_items": missing_items,
        "annotated_image_name": annotated_image_name,
    }
