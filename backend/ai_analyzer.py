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
MIN_MATCH_COUNT = 12
MIN_INLIER_RATIO = 0.25
DEFAULT_PRODUCT_THRESHOLD = 0.55
DEFAULT_PROMO_THRESHOLD = 0.50
ORB_FEATURE_COUNT = 2000
ORB_RATIO_TEST = 0.75
RANSAC_REPROJECTION_THRESHOLD = 5.0
ALIGNMENT_FAILURE_REASON = "Image is too tilted or shelf cannot be aligned with reference."

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


def alignment_model_score(similarity_score: float, inlier_ratio: float, inlier_count: int) -> float:
    bounded_similarity = max(0.0, min(float(similarity_score), 1.0))
    bounded_inlier_ratio = max(0.0, min(float(inlier_ratio), 1.0))
    inlier_strength = min(float(inlier_count) / max(MIN_MATCH_COUNT * 3, 1), 1.0)
    score = (bounded_similarity * 0.70) + (bounded_inlier_ratio * 0.20) + (inlier_strength * 0.10)
    return round(float(score), 4)


def align_image_to_reference(uploaded_img: np.ndarray, ref_img: np.ndarray) -> Optional[Dict]:
    uploaded_gray = to_gray(uploaded_img)
    ref_gray = to_gray(ref_img)
    orb = cv2.ORB_create(nfeatures=ORB_FEATURE_COUNT)

    uploaded_keypoints, uploaded_descriptors = orb.detectAndCompute(uploaded_gray, None)
    ref_keypoints, ref_descriptors = orb.detectAndCompute(ref_gray, None)

    if uploaded_descriptors is None or ref_descriptors is None:
        return None

    if len(uploaded_keypoints) < MIN_MATCH_COUNT or len(ref_keypoints) < MIN_MATCH_COUNT:
        return None

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    raw_matches = matcher.knnMatch(uploaded_descriptors, ref_descriptors, k=2)
    good_matches = []

    for pair in raw_matches:
        if len(pair) != 2:
            continue

        best_match, next_match = pair
        if best_match.distance < ORB_RATIO_TEST * next_match.distance:
            good_matches.append(best_match)

    if len(good_matches) < MIN_MATCH_COUNT:
        return None

    uploaded_points = np.float32(
        [uploaded_keypoints[match.queryIdx].pt for match in good_matches]
    ).reshape(-1, 1, 2)
    ref_points = np.float32(
        [ref_keypoints[match.trainIdx].pt for match in good_matches]
    ).reshape(-1, 1, 2)

    try:
        homography, mask = cv2.findHomography(
            uploaded_points,
            ref_points,
            cv2.RANSAC,
            RANSAC_REPROJECTION_THRESHOLD,
        )
    except cv2.error:
        return None

    if homography is None or mask is None:
        return None

    inlier_count = int(mask.ravel().sum())
    inlier_ratio = inlier_count / len(good_matches)

    if inlier_count < MIN_MATCH_COUNT or inlier_ratio < MIN_INLIER_RATIO:
        return None

    ref_h, ref_w = ref_img.shape[:2]

    try:
        aligned_img = cv2.warpPerspective(uploaded_img, homography, (ref_w, ref_h))
    except cv2.error:
        return None
    similarity_score = calc_ssim(aligned_img, ref_img)
    score = alignment_model_score(similarity_score, inlier_ratio, inlier_count)

    return {
        "aligned_image": aligned_img,
        "homography": homography,
        "match_count": len(good_matches),
        "inlier_count": inlier_count,
        "inlier_ratio": round(float(inlier_ratio), 4),
        "similarity_score": similarity_score,
        "score": score,
    }


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

    alignments = {}
    scores = {}

    for model_id, ref_img in refs.items():
        alignment = align_image_to_reference(uploaded_img, ref_img)
        if alignment is None:
            continue

        alignments[model_id] = alignment
        scores[model_id] = alignment["score"]

    if not scores:
        return {
            "detected_model": "UNKNOWN",
            "model_score": 0.0,
            "scores": {},
            "message": ALIGNMENT_FAILURE_REASON,
            "reason": ALIGNMENT_FAILURE_REASON,
            "result": "NEED_RETAKE",
        }

    detected_model = max(scores, key=scores.get)
    model_score = scores[detected_model]
    best_alignment = alignments[detected_model]

    if model_score < MODEL_THRESHOLD:
        return {
            "detected_model": "UNKNOWN",
            "model_score": model_score,
            "scores": scores,
            "message": "Best aligned reference score is below threshold.",
        }

    return {
        "detected_model": detected_model,
        "model_score": model_score,
        "scores": scores,
        "message": "success",
        "aligned_image": best_alignment["aligned_image"],
        "reference_image": refs[detected_model],
        "alignment": {
            "match_count": best_alignment["match_count"],
            "inlier_count": best_alignment["inlier_count"],
            "inlier_ratio": best_alignment["inlier_ratio"],
            "similarity_score": best_alignment["similarity_score"],
        },
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
    return f"{text[: max_chars - 3]}..."


def is_promo_slot(slot: Dict) -> bool:
    text = " ".join(
        str(slot.get(key, ""))
        for key in ["slot_id", "product_name", "label", "name", "type"]
    ).lower()
    return "promo" in text or "tag" in text


def slot_kind(slot: Dict) -> str:
    return "promo" if is_promo_slot(slot) else "product"


def slot_threshold(slot: Dict) -> float:
    kind = slot_kind(slot)
    default_threshold = (
        DEFAULT_PROMO_THRESHOLD if kind == "promo" else DEFAULT_PRODUCT_THRESHOLD
    )

    try:
        return float(slot.get("threshold", default_threshold))
    except (TypeError, ValueError):
        return default_threshold


def log_slot_check(
    model_id: str,
    slot: Dict,
    score: float,
    threshold: float,
    passed: bool,
) -> None:
    if model_id != "MODEL_B":
        return

    print(
        "MODEL_B slot check",
        "slot_id=", slot.get("slot_id"),
        "type=", slot.get("type") or slot_kind(slot),
        "score=", round(float(score), 4),
        "threshold=", round(float(threshold), 4),
        "passed=", passed,
    )


def annotation_style(slot: Dict, result: Dict) -> Tuple[str, Tuple[int, int, int]]:
    status = result.get("status", "WARNING")
    code = short_slot_code(result.get("slot_id") or slot.get("slot_id"))
    promo = is_promo_slot(slot)

    if status == "PASS":
        color = PROMO_PASS_COLOR if promo else BOX_COLORS["PASS"]
        return (f"OK {code}" if code else "OK", color)

    if status in ["MISSING", "FAIL", "PROMO_MISSING"]:
        return (f"MISS {code}" if code else "MISS", BOX_COLORS["MISSING"])

    if status in ["LOW_SCORE", "WARNING"]:
        if promo:
            return (f"MISS {code}" if code else "MISS", BOX_COLORS["LOW_SCORE"])
        return (f"LOW {code}" if code else "LOW", BOX_COLORS["LOW_SCORE"])

    return (code or str(status), BOX_COLORS["WARNING"])


def inspect_slots(
    uploaded_img: np.ndarray,
    model_id: str,
    slots: List[Dict],
    ref_img: Optional[np.ndarray] = None,
) -> Tuple[List[Dict], List[Dict]]:
    if ref_img is None:
        ref_path = find_reference_file(model_id)
        if not ref_path:
            return [], []

        ref_img = read_image(ref_path)
        if ref_img is None:
            return [], []
    missing_items = []
    slot_results = []

    for slot in slots:
        threshold = slot_threshold(slot)

        try:
            uploaded_crop = crop_slot(uploaded_img, slot)
            ref_crop = crop_slot(ref_img, slot)
        except (KeyError, TypeError, ValueError):
            log_slot_check(model_id, slot, 0.0, threshold, False)
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
            log_slot_check(model_id, slot, 0.0, threshold, False)
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
        passed = slot_score >= threshold
        log_slot_check(model_id, slot, slot_score, threshold, passed)

        if passed:
            status = "PASS"
            label = "PASS"
        else:
            status = "PROMO_MISSING" if slot_kind(slot) == "promo" else "MISSING"
            label = "PROMO MISSING" if status == "PROMO_MISSING" else "MISSING"
            missing_items.append(
                {
                    "slot_id": slot.get("slot_id"),
                    "product_name": slot_name(slot),
                    "score": slot_score,
                    "status": status,
                }
            )

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


def pass_rate(total: int, missing_count: int) -> float:
    if total <= 0:
        return 1.0

    return round((total - missing_count) / total, 4)


def compliance_summary(slots: List[Dict], slot_results: List[Dict]) -> Dict:
    product_total = 0
    product_missing_count = 0
    promo_total = 0
    promo_missing_count = 0

    for index, slot in enumerate(slots):
        result = slot_results[index] if index < len(slot_results) else {}
        status = result.get("status", "WARNING")
        missing = status != "PASS"

        if slot_kind(slot) == "promo":
            promo_total += 1
            if missing:
                promo_missing_count += 1
        else:
            product_total += 1
            if missing:
                product_missing_count += 1

    total_slots = product_total + promo_total
    total_missing_count = product_missing_count + promo_missing_count
    product_rate = pass_rate(product_total, product_missing_count)
    promo_rate = pass_rate(promo_total, promo_missing_count)
    overall_score = pass_rate(total_slots, total_missing_count)

    return {
        "product_total": product_total,
        "product_missing_count": product_missing_count,
        "product_pass_rate": product_rate,
        "promo_total": promo_total,
        "promo_missing_count": promo_missing_count,
        "promo_pass_rate": promo_rate,
        "overall_compliance_score": overall_score,
    }


def classify_result(summary: Dict) -> str:
    product_pass_rate = float(summary.get("product_pass_rate", 0.0))
    promo_pass_rate = float(summary.get("promo_pass_rate", 0.0))

    if product_pass_rate >= 0.85 and promo_pass_rate >= 0.60:
        return "PASS"

    if product_pass_rate >= 0.70:
        return "WARNING"

    return "FAIL"


def draw_label(
    image: np.ndarray,
    text: str,
    x: int,
    y: int,
    w: int,
    h: int,
    color: Tuple[int, int, int],
) -> None:
    text = truncate_label(text)
    if not text:
        return

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.34
    thickness = 1
    padding = 2

    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    label_width = text_w + padding * 2
    label_height = text_h + baseline + padding * 2

    if label_width > w:
        return

    if y >= label_height:
        label_left = x
        label_top = y - label_height
    elif label_height <= h:
        label_left = x
        label_top = y
    else:
        return

    label_right = label_left + label_width
    label_bottom = label_top + label_height

    if label_right > image.shape[1] or label_bottom > image.shape[0]:
        return

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
        draw_label(annotated, text, x, y, w, h, color)

    return annotated


def save_annotated_image(image: np.ndarray) -> str:
    os.makedirs(ANNOTATED_DIR, exist_ok=True)
    image_name = f"inspection_{uuid.uuid4().hex}_annotated.jpg"
    image_path = os.path.join(ANNOTATED_DIR, image_name)
    cv2.imwrite(image_path, image)
    return image_name


def save_aligned_debug_image(image: np.ndarray, model_id: str) -> str:
    os.makedirs(ANNOTATED_DIR, exist_ok=True)
    image_name = f"aligned_{model_id.lower()}_{uuid.uuid4().hex}_debug.jpg"
    image_path = os.path.join(ANNOTATED_DIR, image_name)
    cv2.imwrite(image_path, image)
    return image_name


def check_missing_items(uploaded_img: np.ndarray, model_id: str) -> List[Dict]:
    planogram = load_planogram(model_id)
    slots = planogram.get("slots", []) or []
    ref_path = find_reference_file(model_id)

    if not ref_path:
        return []

    ref_img = read_image(ref_path)
    if ref_img is None:
        return []

    alignment = align_image_to_reference(uploaded_img, ref_img)
    if alignment is None:
        return []

    missing_items, _ = inspect_slots(
        alignment["aligned_image"],
        model_id,
        slots,
        ref_img=ref_img,
    )
    return missing_items


def analyze_image(image_path: str) -> Dict:
    uploaded_img = read_image(image_path)
    if uploaded_img is None:
        raise ValueError(f"Could not read image: {image_path}")

    model_result = detect_shelf_model(uploaded_img)
    detected_model = model_result["detected_model"]
    model_score = float(model_result["model_score"])

    if model_result.get("result") == "NEED_RETAKE":
        annotated = draw_banner(uploaded_img, "NEED RETAKE", BOX_COLORS["UNKNOWN_MODEL"])
        annotated_image_name = save_annotated_image(annotated)
        return {
            "detected_model": "UNKNOWN",
            "model_score": model_score,
            "result": "NEED_RETAKE",
            "missing_count": 0,
            "missing_items": [],
            "annotated_image_name": annotated_image_name,
            "reason": ALIGNMENT_FAILURE_REASON,
        }

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
            "reason": model_result.get("message"),
        }

    aligned_img = model_result.get("aligned_image", uploaded_img)
    ref_img = model_result.get("reference_image")
    aligned_debug_image_name = save_aligned_debug_image(aligned_img, detected_model)
    planogram = load_planogram(detected_model)
    slots = planogram.get("slots", []) or []

    if not slots:
        annotated = draw_banner(
            aligned_img,
            "NO SLOTS CONFIGURED",
            BOX_COLORS["WARNING"],
        )
        annotated_image_name = save_annotated_image(annotated)
        summary = compliance_summary([], [])
        return {
            "detected_model": detected_model,
            "model_score": model_score,
            "result": "PASS",
            "missing_count": 0,
            "missing_items": [],
            "annotated_image_name": annotated_image_name,
            "aligned_debug_image_name": aligned_debug_image_name,
            **summary,
        }

    missing_items, slot_results = inspect_slots(
        aligned_img,
        detected_model,
        slots,
        ref_img=ref_img,
    )
    summary = compliance_summary(slots, slot_results)
    result = classify_result(summary)
    annotated = draw_yolo_style_boxes(aligned_img, slots, slot_results)
    annotated_image_name = save_annotated_image(annotated)

    return {
        "detected_model": detected_model,
        "model_score": model_score,
        "result": result,
        "missing_count": len(missing_items),
        "missing_items": missing_items,
        "annotated_image_name": annotated_image_name,
        "aligned_debug_image_name": aligned_debug_image_name,
        **summary,
    }
