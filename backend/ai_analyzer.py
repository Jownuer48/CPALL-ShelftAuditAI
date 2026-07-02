import json
import os
import uuid
from functools import lru_cache
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
ANALYSIS_MODE = os.getenv("SHELF_AUDIT_ANALYSIS_MODE", "hybrid")
SUPPORTED_ANALYSIS_MODES = {"yolo_only", "hybrid", "slot_similarity", "sku110k_planogram"}
HYBRID_MODEL_IDS = ["MODEL_A", "MODEL_B"]
USE_YOLO_ONLY_MODE = ANALYSIS_MODE == "yolo_only"
SKU110K_PLANOGRAM_MODEL_PATH = os.path.join(
    BASE_DIR,
    "yolo_models",
    "experiments",
    "sku110k_product.pt",
)
SKU110K_PLANOGRAM_DISPLAY_MODEL_PATH = (
    "backend/yolo_models/experiments/sku110k_product.pt"
)
SKU110K_PLANOGRAM_CONFIDENCE_THRESHOLD = 0.15
SKU110K_SLOT_COVERAGE_THRESHOLD = 0.25
SKU110K_SLOT_IOU_THRESHOLD = 0.15
YOLO_PRODUCT_PASS_MIN = 10
YOLO_PROMO_PASS_MIN = 3
YOLO_PRODUCT_WARNING_MIN = 5
YOLO_CONFIDENCE_THRESHOLD = 0.25
YOLO_PRODUCT_MIN_CONF = 0.60
YOLO_PROMO_MIN_CONF = 0.45
PRODUCT_SLOT_MIN_COVERAGE = 0.45
PROMO_SLOT_MIN_COVERAGE = 0.30
DETECTION_INSIDE_SLOT_MIN_RATIO = 0.60
SLOT_APPEARANCE_MIN_SIMILARITY_PRODUCT = 0.45
SLOT_APPEARANCE_MIN_SIMILARITY_PROMO = 0.35
COUNT_SENSITIVE_GROUP_MIN_SIMILARITY = 0.65
USE_SLOT_APPEARANCE_CHECK = True
YOLO_SUPPORTED_MODELS = {"MODEL_A", "MODEL_B"}
YOLO_IOU_THRESHOLD = 0.15
HYBRID_SLOT_IOU_THRESHOLD = 0.10

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


def compute_crop_similarity(reference_crop: np.ndarray, uploaded_crop: np.ndarray) -> float:
    if reference_crop is None or uploaded_crop is None:
        return 0.0

    if reference_crop.size == 0 or uploaded_crop.size == 0:
        return 0.0

    try:
        ref_resized = cv2.resize(reference_crop, (128, 128))
        uploaded_resized = cv2.resize(uploaded_crop, (128, 128))
    except cv2.error:
        return 0.0

    ref_hsv = cv2.cvtColor(ref_resized, cv2.COLOR_BGR2HSV)
    uploaded_hsv = cv2.cvtColor(uploaded_resized, cv2.COLOR_BGR2HSV)
    ref_hist = cv2.calcHist([ref_hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    uploaded_hist = cv2.calcHist([uploaded_hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    cv2.normalize(ref_hist, ref_hist, 0, 1, cv2.NORM_MINMAX)
    cv2.normalize(uploaded_hist, uploaded_hist, 0, 1, cv2.NORM_MINMAX)
    hist_score = cv2.compareHist(ref_hist, uploaded_hist, cv2.HISTCMP_CORREL)
    hist_score = max(0.0, min((float(hist_score) + 1.0) / 2.0, 1.0))

    ref_gray = cv2.cvtColor(ref_resized, cv2.COLOR_BGR2GRAY)
    uploaded_gray = cv2.cvtColor(uploaded_resized, cv2.COLOR_BGR2GRAY)
    try:
        ssim_score = ssim(ref_gray, uploaded_gray, data_range=255)
    except (ValueError, ZeroDivisionError):
        ssim_score = 0.0
    ssim_score = max(0.0, min(float(ssim_score), 1.0))

    return round(float((hist_score * 0.55) + (ssim_score * 0.45)), 4)

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


def log_reference_load_failure(model_id: str, path: str, imread_success: bool) -> None:
    print(
        "[REFERENCE] load failed",
        "model_id=", model_id,
        "selected_reference_path=", path,
        "exists=", os.path.exists(path),
        "cv2_imread_success=", imread_success,
    )


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


def load_reference_images(model_ids: Optional[List[str]] = None) -> Dict[str, np.ndarray]:
    refs = {}
    active_models = list(model_ids) if model_ids is not None else ACTIVE_MODELS

    for model_id in active_models:
        path = find_reference_file(model_id)
        if not path:
            base_name = REFERENCE_MODELS[model_id]
            expected_path = os.path.join(REFERENCE_DIR, f"{base_name}{REFERENCE_EXTENSIONS[0]}")
            log_reference_load_failure(model_id, expected_path, False)
            continue

        img = read_image(path)
        if img is not None:
            refs[model_id] = img
        else:
            log_reference_load_failure(model_id, path, False)

    return refs


def detect_shelf_model(
    uploaded_img: np.ndarray,
    model_ids: Optional[List[str]] = None,
) -> Dict:
    refs = load_reference_images(model_ids)

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
    product_missing_count = int(summary.get("product_missing_count", 0) or 0)
    promo_missing_count = int(summary.get("promo_missing_count", 0) or 0)

    if product_missing_count > 0:
        return "FAIL"

    if promo_missing_count > 0:
        return "WARNING"

    return "PASS"


def box_iou(box_a: Tuple[int, int, int, int], box_b: Tuple[int, int, int, int]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0, inter_x2 - inter_x1)
    inter_h = max(0, inter_y2 - inter_y1)
    intersection = inter_w * inter_h

    area_a = max(0, ax2 - ax1) * max(0, ay2 - ay1)
    area_b = max(0, bx2 - bx1) * max(0, by2 - by1)
    union = area_a + area_b - intersection

    if union <= 0:
        return 0.0

    return float(intersection / union)


def detection_box(detection: Dict) -> Tuple[int, int, int, int]:
    return (
        int(detection["x1"]),
        int(detection["y1"]),
        int(detection["x2"]),
        int(detection["y2"]),
    )


def detection_center_inside_slot(
    detection: Dict,
    slot_box: Tuple[int, int, int, int],
) -> bool:
    x1, y1, x2, y2 = slot_box
    det_x1, det_y1, det_x2, det_y2 = detection_box(detection)
    center_x = (det_x1 + det_x2) / 2.0
    center_y = (det_y1 + det_y2) / 2.0
    return x1 <= center_x <= x2 and y1 <= center_y <= y2


def best_matching_detection(
    slot_box: Tuple[int, int, int, int],
    slot_type: str,
    detections: List[Dict],
    iou_threshold: float = YOLO_IOU_THRESHOLD,
) -> Optional[Tuple[Dict, float]]:
    best_detection = None
    best_overlap = 0.0
    best_confidence = -1.0

    for detection in detections:
        if detection.get("class_name") != slot_type:
            continue

        overlap = box_iou(slot_box, detection_box(detection))
        center_inside = detection_center_inside_slot(detection, slot_box)
        if overlap < iou_threshold and not center_inside:
            continue

        confidence = float(detection.get("confidence", 0.0))
        if overlap > best_overlap or (
            overlap == best_overlap and confidence > best_confidence
        ):
            best_detection = detection
            best_overlap = overlap
            best_confidence = confidence

    if best_detection is None:
        return None

    return best_detection, best_overlap


def inspect_slots_with_yolo(
    aligned_img: np.ndarray,
    model_id: str,
    slots: List[Dict],
) -> Optional[Tuple[List[Dict], List[Dict]]]:
    if model_id not in YOLO_SUPPORTED_MODELS:
        return None

    try:
        from yolo_detector import YOLO_MODEL_PATH, detect_objects

        if os.path.exists(YOLO_MODEL_PATH):
            print("[YOLO] Using YOLO detector")

        detections = detect_objects(
            aligned_img,
            confidence_threshold=YOLO_CONFIDENCE_THRESHOLD,
        )
    except Exception as exc:
        print(f"[YOLO] Fallback to similarity check: {exc}")
        return None

    missing_items = []
    slot_results = []

    for slot in slots:
        slot_type = slot_kind(slot)

        try:
            x, y, w, h = slot_to_pixel(aligned_img, slot)
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

        slot_box_xyxy = (x, y, x + w, y + h)
        match = best_matching_detection(slot_box_xyxy, slot_type, detections)

        if match is None:
            status = "PROMO_MISSING" if slot_type == "promo" else "MISSING"
            label = "PROMO MISSING" if status == "PROMO_MISSING" else "MISSING"
            score = 0.0
            missing_items.append(
                {
                    "slot_id": slot.get("slot_id"),
                    "product_name": slot_name(slot),
                    "score": score,
                    "status": status,
                }
            )
        else:
            detection, overlap = match
            score = round(float(detection.get("confidence", 0.0)), 4)
            status = "PASS"
            label = "PASS"

        slot_results.append(
            {
                "slot": slot,
                "slot_id": slot.get("slot_id"),
                "product_name": slot_name(slot),
                "score": score,
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

def draw_yolo_detection_boxes(
    image: np.ndarray,
    detections: List[Dict],
) -> np.ndarray:
    annotated = image.copy()
    image_h, image_w = annotated.shape[:2]

    for detection in detections:
        class_name = detection.get("class_name")
        if class_name not in {"product", "promo"}:
            continue

        try:
            confidence = float(detection.get("confidence", 0.0))
            x1 = int(detection.get("x1", 0))
            y1 = int(detection.get("y1", 0))
            x2 = int(detection.get("x2", 0))
            y2 = int(detection.get("y2", 0))
        except (TypeError, ValueError):
            continue

        x1 = max(0, min(x1, image_w - 1))
        y1 = max(0, min(y1, image_h - 1))
        x2 = max(0, min(x2, image_w - 1))
        y2 = max(0, min(y2, image_h - 1))

        if x2 <= x1 or y2 <= y1:
            continue

        color = PROMO_PASS_COLOR if class_name == "promo" else BOX_COLORS["PASS"]
        label = f"{class_name} {confidence:.2f}"
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        draw_label(annotated, label, x1, y1, x2 - x1, y2 - y1, color)

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

def filter_yolo_only_detections(detections: List[Dict]) -> List[Dict]:
    useful_detections = []

    for detection in detections:
        class_name = detection.get("class_name")
        if class_name not in {"product", "promo"}:
            continue

        try:
            confidence = float(detection.get("confidence", 0.0))
        except (TypeError, ValueError):
            continue

        if confidence < YOLO_CONFIDENCE_THRESHOLD:
            continue

        normalized_detection = dict(detection)
        normalized_detection["confidence"] = confidence
        useful_detections.append(normalized_detection)

    return useful_detections


def count_yolo_detections(detections: List[Dict]) -> Tuple[int, int, int]:
    product_count = sum(
        1 for detection in detections if detection.get("class_name") == "product"
    )
    promo_count = sum(
        1 for detection in detections if detection.get("class_name") == "promo"
    )
    return product_count, promo_count, product_count + promo_count


def detection_confidence(detection: Dict) -> float:
    try:
        return float(detection.get("confidence", 0.0))
    except (TypeError, ValueError):
        return 0.0


def detection_min_confidence(class_name: str) -> float:
    return YOLO_PROMO_MIN_CONF if class_name == "promo" else YOLO_PRODUCT_MIN_CONF


def filter_hybrid_detections(
    detections: List[Dict],
    roi: Optional[Tuple[int, int, int, int]] = None,
    slot_boxes: Optional[List[Tuple[int, int, int, int]]] = None,
) -> List[Dict]:
    filtered = []

    for detection in detections:
        class_name = detection.get("class_name")
        if class_name not in {"product", "promo"}:
            continue

        confidence = detection_confidence(detection)
        if confidence < detection_min_confidence(class_name):
            continue

        center_x, center_y = detection_center(detection)
        if roi is not None and not point_inside_box(center_x, center_y, roi):
            continue

        if slot_boxes:
            center_inside_slot = any(
                point_inside_box(center_x, center_y, slot_box)
                for slot_box in slot_boxes
            )
            union_ratio = detection_slot_union_inside_ratio(detection, slot_boxes)
            if (
                not center_inside_slot
                and union_ratio < DETECTION_INSIDE_SLOT_MIN_RATIO
            ):
                continue

        normalized_detection = dict(detection)
        normalized_detection["confidence"] = confidence
        filtered.append(normalized_detection)

    return filtered

def box_area(box: Tuple[int, int, int, int]) -> int:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def intersection_area(
    box_a: Tuple[int, int, int, int],
    box_b: Tuple[int, int, int, int],
) -> int:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    return max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)


def detection_center(detection: Dict) -> Tuple[float, float]:
    x1, y1, x2, y2 = detection_box(detection)
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def point_inside_box(
    x: float,
    y: float,
    box: Tuple[int, int, int, int],
) -> bool:
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


def detection_inside_slot_ratio(
    slot_box: Tuple[int, int, int, int],
    detection: Dict,
) -> float:
    detection_area = box_area(detection_box(detection))
    if detection_area <= 0:
        return 0.0

    return float(intersection_area(slot_box, detection_box(detection)) / detection_area)


def detection_slot_union_inside_ratio(
    detection: Dict,
    slot_boxes: List[Tuple[int, int, int, int]],
) -> float:
    detection_area = box_area(detection_box(detection))
    if detection_area <= 0:
        return 0.0

    covered_area = sum(intersection_area(slot_box, detection_box(detection)) for slot_box in slot_boxes)
    covered_area = min(covered_area, detection_area)
    return float(covered_area / detection_area)


def valid_slot_boxes(
    image: np.ndarray,
    slots: List[Dict],
) -> List[Tuple[int, int, int, int]]:
    boxes = []

    for slot in slots:
        try:
            boxes.append(slot_box_xyxy(image, slot))
        except (KeyError, TypeError, ValueError):
            continue

    return boxes


def target_shelf_roi(
    image: np.ndarray,
    slots: List[Dict],
) -> Tuple[int, int, int, int]:
    image_h, image_w = image.shape[:2]
    boxes = valid_slot_boxes(image, slots)
    if not boxes:
        return 0, 0, image_w, image_h

    min_x = min(box[0] for box in boxes)
    min_y = min(box[1] for box in boxes)
    max_x = max(box[2] for box in boxes)
    max_y = max(box[3] for box in boxes)
    pad_x = int(round(image_w * 0.03))
    pad_y = int(round(image_h * 0.03))

    return (
        max(0, min_x - pad_x),
        max(0, min_y - pad_y),
        min(image_w, max_x + pad_x),
        min(image_h, max_y + pad_y),
    )


def mask_image_to_roi(
    image: np.ndarray,
    roi: Tuple[int, int, int, int],
) -> np.ndarray:
    x1, y1, x2, y2 = roi
    masked = np.zeros_like(image)
    masked[y1:y2, x1:x2] = image[y1:y2, x1:x2]
    return masked

def slot_detection_coverage(
    slot_box: Tuple[int, int, int, int],
    detection: Dict,
) -> float:
    slot_area = box_area(slot_box)
    if slot_area <= 0:
        return 0.0

    return float(intersection_area(slot_box, detection_box(detection)) / slot_area)


def slot_min_coverage(slot_type: str) -> float:
    return PROMO_SLOT_MIN_COVERAGE if slot_type == "promo" else PRODUCT_SLOT_MIN_COVERAGE


def parse_slot_count(value) -> Optional[int]:
    if value in [None, ""]:
        return None

    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def slot_count_requirements(slot: Dict) -> Tuple[Optional[int], Optional[int], int]:
    expected_count = parse_slot_count(slot.get("expected_count"))
    min_count = parse_slot_count(slot.get("min_count"))
    required_count = min_count if min_count is not None else expected_count

    if required_count is None:
        required_count = 1

    return expected_count, min_count, required_count


def parse_slot_bool(value) -> bool:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value != 0

    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}

    return False


def slot_requires_appearance_check(
    slot: Dict,
    expected_count: Optional[int] = None,
    min_count: Optional[int] = None,
) -> bool:
    has_expected_count = (
        expected_count is not None
        if expected_count is not None
        else parse_slot_count(slot.get("expected_count")) is not None
    )
    has_min_count = (
        min_count is not None
        if min_count is not None
        else parse_slot_count(slot.get("min_count")) is not None
    )

    return (
        has_expected_count
        or has_min_count
        or parse_slot_bool(slot.get("requires_appearance_check"))
    )


def hybrid_detection_matches_slot(
    slot_box: Tuple[int, int, int, int],
    slot_type: str,
    detection: Dict,
) -> Tuple[bool, float, float]:
    if detection.get("class_name") != slot_type:
        return False, 0.0, 0.0

    if detection_confidence(detection) < detection_min_confidence(slot_type):
        return False, 0.0, 0.0

    coverage = slot_detection_coverage(slot_box, detection)
    inside_ratio = detection_inside_slot_ratio(slot_box, detection)
    center_x, center_y = detection_center(detection)
    center_inside = point_inside_box(center_x, center_y, slot_box)
    center_and_inside = center_inside and inside_ratio >= DETECTION_INSIDE_SLOT_MIN_RATIO
    coverage_match = coverage >= slot_min_coverage(slot_type)
    return center_and_inside or coverage_match, coverage, inside_ratio

def slot_appearance_threshold(slot_type: str) -> float:
    return (
        SLOT_APPEARANCE_MIN_SIMILARITY_PROMO
        if slot_type == "promo"
        else SLOT_APPEARANCE_MIN_SIMILARITY_PRODUCT
    )


def crop_box(image: Optional[np.ndarray], box: Tuple[int, int, int, int]) -> Optional[np.ndarray]:
    if image is None:
        return None

    image_h, image_w = image.shape[:2]
    x1, y1, x2, y2 = box
    x1 = max(0, min(x1, image_w - 1))
    y1 = max(0, min(y1, image_h - 1))
    x2 = max(0, min(x2, image_w))
    y2 = max(0, min(y2, image_h))
    if x2 <= x1 or y2 <= y1:
        return None

    return image[y1:y2, x1:x2]


def detection_key(detection: Dict) -> Tuple:
    return (
        detection.get("class_name"),
        int(detection.get("x1", 0)),
        int(detection.get("y1", 0)),
        int(detection.get("x2", 0)),
        int(detection.get("y2", 0)),
        round(detection_confidence(detection), 4),
    )


def unique_detections(detections: List[Dict]) -> List[Dict]:
    unique = []
    seen = set()

    for detection in detections:
        key = detection_key(detection)
        if key in seen:
            continue
        seen.add(key)
        unique.append(detection)

    return unique


def matching_hybrid_detections(
    slot_box: Tuple[int, int, int, int],
    slot_type: str,
    detections: List[Dict],
) -> Tuple[List[Dict], float, float, float]:
    matches = []
    best_match_confidence = 0.0
    best_match_coverage = 0.0
    best_match_inside_ratio = 0.0
    best_candidate_confidence = 0.0
    best_candidate_coverage = 0.0
    best_candidate_inside_ratio = 0.0

    for detection in detections:
        if detection.get("class_name") != slot_type:
            continue

        confidence = detection_confidence(detection)
        matched, coverage, inside_ratio = hybrid_detection_matches_slot(
            slot_box,
            slot_type,
            detection,
        )

        if coverage > best_candidate_coverage or (
            coverage == best_candidate_coverage and confidence > best_candidate_confidence
        ):
            best_candidate_coverage = coverage
            best_candidate_confidence = confidence
            best_candidate_inside_ratio = inside_ratio

        if not matched:
            continue

        matches.append(detection)
        if coverage > best_match_coverage or (
            coverage == best_match_coverage and confidence > best_match_confidence
        ):
            best_match_coverage = coverage
            best_match_confidence = confidence
            best_match_inside_ratio = inside_ratio

    if matches:
        return matches, best_match_confidence, best_match_coverage, best_match_inside_ratio

    return matches, best_candidate_confidence, best_candidate_coverage, best_candidate_inside_ratio


def hybrid_slot_detection_counts(
    slot_box: Tuple[int, int, int, int],
    slot_type: str,
    detections: List[Dict],
) -> Tuple[int, float, float, float]:
    detected_count = 0
    best_match_confidence = 0.0
    best_match_coverage = 0.0
    best_match_inside_ratio = 0.0
    best_candidate_confidence = 0.0
    best_candidate_coverage = 0.0
    best_candidate_inside_ratio = 0.0

    for detection in detections:
        if detection.get("class_name") != slot_type:
            continue

        confidence = detection_confidence(detection)
        matched, coverage, inside_ratio = hybrid_detection_matches_slot(
            slot_box,
            slot_type,
            detection,
        )

        if coverage > best_candidate_coverage or (
            coverage == best_candidate_coverage and confidence > best_candidate_confidence
        ):
            best_candidate_coverage = coverage
            best_candidate_confidence = confidence
            best_candidate_inside_ratio = inside_ratio

        if not matched:
            continue

        detected_count += 1
        if coverage > best_match_coverage or (
            coverage == best_match_coverage and confidence > best_match_confidence
        ):
            best_match_coverage = coverage
            best_match_confidence = confidence
            best_match_inside_ratio = inside_ratio

    if detected_count > 0:
        return detected_count, best_match_confidence, best_match_coverage, best_match_inside_ratio

    return detected_count, best_candidate_confidence, best_candidate_coverage, best_candidate_inside_ratio

def best_hybrid_slot_detection(
    slot_box: Tuple[int, int, int, int],
    slot_type: str,
    detections: List[Dict],
) -> Tuple[Optional[Dict], float, float]:
    best_match = None
    best_match_coverage = 0.0
    best_match_confidence = 0.0
    best_candidate_coverage = 0.0
    best_candidate_confidence = 0.0
    min_confidence = detection_min_confidence(slot_type)
    min_coverage = slot_min_coverage(slot_type)

    for detection in detections:
        if detection.get("class_name") != slot_type:
            continue

        confidence = detection_confidence(detection)
        coverage = slot_detection_coverage(slot_box, detection)

        if coverage > best_candidate_coverage or (
            coverage == best_candidate_coverage and confidence > best_candidate_confidence
        ):
            best_candidate_coverage = coverage
            best_candidate_confidence = confidence

        if confidence < min_confidence:
            continue

        center_inside = detection_center_inside_slot(detection, slot_box)
        if not center_inside and coverage < min_coverage:
            continue

        if coverage > best_match_coverage or (
            coverage == best_match_coverage and confidence > best_match_confidence
        ):
            best_match = detection
            best_match_coverage = coverage
            best_match_confidence = confidence

    if best_match is not None:
        return best_match, best_match_confidence, best_match_coverage

    return None, best_candidate_confidence, best_candidate_coverage

def classify_yolo_only_result(
    product_count: int,
    promo_count: int,
    total_count: int,
) -> Tuple[str, Optional[str]]:
    if total_count == 0:
        return (
            "NEED_RETAKE",
            "No shelf products or promo tags detected. Please retake the photo.",
        )

    if product_count >= YOLO_PRODUCT_PASS_MIN and promo_count >= YOLO_PROMO_PASS_MIN:
        return "PASS", None

    if product_count >= YOLO_PRODUCT_WARNING_MIN:
        return "WARNING", None

    return "FAIL", None


def yolo_only_metric_fields(
    product_count: int,
    promo_count: int,
    total_count: int,
) -> Dict:
    product_rate = min(product_count / max(YOLO_PRODUCT_PASS_MIN, 1), 1.0)
    promo_rate = min(promo_count / max(YOLO_PROMO_PASS_MIN, 1), 1.0)
    expected_total = YOLO_PRODUCT_PASS_MIN + YOLO_PROMO_PASS_MIN
    overall_score = min(total_count / max(expected_total, 1), 1.0)

    return {
        "product_total": product_count,
        "product_missing_count": 0,
        "product_pass_rate": round(float(product_rate), 4),
        "promo_total": promo_count,
        "promo_missing_count": 0,
        "promo_pass_rate": round(float(promo_rate), 4),
        "overall_compliance_score": round(float(overall_score), 4),
    }


def analyze_yolo_only(
    uploaded_img: np.ndarray,
    model_result: Dict,
    detected_model: str,
    model_score: float,
) -> Optional[Dict]:
    print("[YOLO_ONLY] Running YOLO-only detection")

    aligned_img = model_result.get("aligned_image")
    use_aligned_image = (
        detected_model in YOLO_SUPPORTED_MODELS and aligned_img is not None
    )

    if use_aligned_image:
        yolo_img = aligned_img
        response_model = detected_model
        print("[YOLO_ONLY] Using aligned image")
    else:
        yolo_img = uploaded_img
        response_model = "YOLO_ONLY"
        print("[YOLO_ONLY] Using original uploaded image")

    try:
        from yolo_detector import detect_objects

        detections = detect_objects(
            yolo_img,
            confidence_threshold=YOLO_CONFIDENCE_THRESHOLD,
        )
    except Exception as exc:
        print(f"[YOLO] Fallback to similarity check: {exc}")
        return None

    useful_detections = filter_yolo_only_detections(detections)
    product_count, promo_count, total_count = count_yolo_detections(useful_detections)
    result, reason = classify_yolo_only_result(
        product_count,
        promo_count,
        total_count,
    )

    print(
        f"[YOLO_ONLY] product_count={product_count} "
        f"promo_count={promo_count} total={total_count}"
    )
    print(f"[YOLO_ONLY] result={result}")

    if total_count == 0:
        annotated = draw_banner(
            yolo_img,
            "NEED RETAKE",
            BOX_COLORS["UNKNOWN_MODEL"],
        )
    else:
        annotated = draw_yolo_detection_boxes(yolo_img, useful_detections)

    annotated_image_name = save_annotated_image(annotated)
    response = {
        "detected_model": response_model,
        "model_score": model_score,
        "result": result,
        "missing_count": 0,
        "missing_items": [],
        "annotated_image_name": annotated_image_name,
        "analysis_mode": "yolo_only",
        "product_count": product_count,
        "promo_count": promo_count,
        "yolo_detection_count": total_count,
        **yolo_only_metric_fields(product_count, promo_count, total_count),
    }

    if use_aligned_image:
        response["aligned_debug_image_name"] = save_aligned_debug_image(
            yolo_img,
            response_model,
        )

    if reason:
        response["reason"] = reason

    return response


def selected_analysis_mode() -> str:
    mode = str(ANALYSIS_MODE).strip().lower()
    if mode in SUPPORTED_ANALYSIS_MODES:
        return mode

    return "hybrid"


def ensure_sku110k_ultralytics_config_dir() -> None:
    if os.environ.get("YOLO_CONFIG_DIR"):
        return

    config_dir = os.path.join(BASE_DIR, "debug", "sku110k", "ultralytics_config")
    os.makedirs(config_dir, exist_ok=True)
    os.environ["YOLO_CONFIG_DIR"] = config_dir


@lru_cache(maxsize=1)
def load_sku110k_planogram_model():
    if not os.path.exists(SKU110K_PLANOGRAM_MODEL_PATH):
        raise FileNotFoundError(
            f"SKU110K model not found: {SKU110K_PLANOGRAM_MODEL_PATH}"
        )

    ensure_sku110k_ultralytics_config_dir()
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is not installed") from exc

    model = YOLO(SKU110K_PLANOGRAM_MODEL_PATH)
    print(
        "[SKU110K_PLANOGRAM] loaded model "
        f"{SKU110K_PLANOGRAM_DISPLAY_MODEL_PATH}"
    )
    return model


def detect_sku110k_planogram_products(
    image: np.ndarray,
    confidence_threshold: float = SKU110K_PLANOGRAM_CONFIDENCE_THRESHOLD,
) -> List[Dict]:
    model = load_sku110k_planogram_model()
    results = model.predict(
        source=image,
        conf=confidence_threshold,
        device="cpu",
        verbose=False,
        save=False,
    )

    if not results:
        print("[SKU110K_PLANOGRAM] detections count=0")
        return []

    boxes = getattr(results[0], "boxes", None)
    if boxes is None:
        print("[SKU110K_PLANOGRAM] detections count=0")
        return []

    image_h, image_w = image.shape[:2]
    detections = []

    for box in boxes:
        confidence = float(box.conf[0].item())
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        clipped_x1 = int(max(0, min(round(x1), image_w - 1)))
        clipped_y1 = int(max(0, min(round(y1), image_h - 1)))
        clipped_x2 = int(max(0, min(round(x2), image_w)))
        clipped_y2 = int(max(0, min(round(y2), image_h)))

        if clipped_x2 <= clipped_x1 or clipped_y2 <= clipped_y1:
            continue

        detections.append(
            {
                "class_name": "product",
                "confidence": confidence,
                "x1": clipped_x1,
                "y1": clipped_y1,
                "x2": clipped_x2,
                "y2": clipped_y2,
            }
        )

    print(f"[SKU110K_PLANOGRAM] detections count={len(detections)}")
    return detections


def expected_slot_type(slot: Dict) -> str:
    slot_type = str(slot.get("type", "")).strip().lower()
    if slot_type in {"product", "promo"}:
        return slot_type

    return slot_kind(slot)


def slot_box_xyxy(image: np.ndarray, slot: Dict) -> Tuple[int, int, int, int]:
    image_h, image_w = image.shape[:2]

    x1 = int(float(slot["x"]) * image_w)
    y1 = int(float(slot["y"]) * image_h)
    x2 = int((float(slot["x"]) + float(slot["w"])) * image_w)
    y2 = int((float(slot["y"]) + float(slot["h"])) * image_h)

    x1 = max(0, min(x1, image_w - 1))
    y1 = max(0, min(y1, image_h - 1))
    x2 = max(0, min(x2, image_w))
    y2 = max(0, min(y2, image_h))

    if x2 <= x1 or y2 <= y1:
        raise ValueError("Invalid slot coordinates")

    return x1, y1, x2, y2


def sku110k_detection_matches_slot(
    slot_box: Tuple[int, int, int, int],
    detection: Dict,
) -> bool:
    if detection.get("class_name") != "product":
        return False

    coverage = slot_detection_coverage(slot_box, detection)
    overlap = box_iou(slot_box, detection_box(detection))
    return (
        detection_center_inside_slot(detection, slot_box)
        or coverage >= SKU110K_SLOT_COVERAGE_THRESHOLD
        or overlap >= SKU110K_SLOT_IOU_THRESHOLD
    )


def evaluate_slots_with_sku110k_planogram(
    aligned_img: np.ndarray,
    slots: List[Dict],
    detections: List[Dict],
) -> Tuple[List[Dict], List[Dict]]:
    missing_items = []
    slot_results = []

    for slot in slots:
        slot_id = slot.get("slot_id")
        expected_count, min_count, required_count = slot_count_requirements(slot)

        try:
            slot_box = slot_box_xyxy(aligned_img, slot)
        except (KeyError, TypeError, ValueError):
            print(
                f"[SKU110K_PLANOGRAM] slot={slot_id} "
                f"count=0/{required_count} status=MISSING reason=invalid slot"
            )
            missing_items.append(
                {
                    "slot_id": slot_id,
                    "product_name": slot_name(slot),
                    "score": 0.0,
                    "status": "MISSING",
                    "expected_count": expected_count,
                    "detected_count": 0,
                    "required_count": required_count,
                    "reason": "invalid slot coordinates",
                }
            )
            slot_results.append(
                {
                    "slot": slot,
                    "slot_id": slot_id,
                    "product_name": slot_name(slot),
                    "score": 0.0,
                    "status": "MISSING",
                    "label": "MISSING",
                    "expected_count": expected_count,
                    "min_count": min_count,
                    "required_count": required_count,
                    "detected_count": 0,
                    "reason": "invalid slot coordinates",
                }
            )
            continue

        matches = [
            detection
            for detection in detections
            if sku110k_detection_matches_slot(slot_box, detection)
        ]
        matched_count = len(matches)
        passed = matched_count >= required_count
        status = "PASS" if passed else "MISSING"
        score = max((detection_confidence(item) for item in matches), default=0.0)
        print(
            f"[SKU110K_PLANOGRAM] slot={slot_id} "
            f"count={matched_count}/{required_count} status={status}"
        )

        if not passed:
            missing_items.append(
                {
                    "slot_id": slot_id,
                    "product_name": slot_name(slot),
                    "score": 0.0,
                    "status": "MISSING",
                    "expected_count": expected_count,
                    "detected_count": matched_count,
                    "required_count": required_count,
                    "reason": "insufficient SKU110K product detections",
                }
            )

        slot_results.append(
            {
                "slot": slot,
                "slot_id": slot_id,
                "product_name": slot_name(slot),
                "score": round(float(score), 4),
                "status": status,
                "label": status,
                "expected_count": expected_count,
                "min_count": min_count,
                "required_count": required_count,
                "detected_count": matched_count,
                "reason": None if passed else "insufficient SKU110K product detections",
            }
        )

    return missing_items, slot_results


def sku110k_planogram_summary(
    product_slots: List[Dict],
    promo_slots: List[Dict],
    slot_results: List[Dict],
) -> Dict:
    product_total = len(product_slots)
    product_missing_count = sum(
        1 for item in slot_results if item.get("status") != "PASS"
    )
    product_pass_rate = pass_rate(product_total, product_missing_count)
    promo_total = len(promo_slots)

    return {
        "product_total": product_total,
        "product_missing_count": product_missing_count,
        "product_pass_rate": product_pass_rate,
        "promo_total": promo_total,
        "promo_missing_count": 0,
        "promo_pass_rate": 1.0,
        "overall_compliance_score": product_pass_rate,
    }


def draw_sku110k_planogram_label(
    image: np.ndarray,
    text: str,
    x: int,
    y: int,
    color: Tuple[int, int, int],
) -> None:
    text = truncate_label(text)
    if not text:
        return

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.36
    thickness = 1
    padding = 3
    image_h, image_w = image.shape[:2]
    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    label_w = min(text_w + padding * 2, image_w)
    label_h = text_h + baseline + padding * 2
    label_left = max(0, min(x, image_w - label_w))
    label_top = y - label_h if y >= label_h else y
    label_top = max(0, min(label_top, image_h - label_h))

    cv2.rectangle(
        image,
        (label_left, label_top),
        (label_left + label_w, label_top + label_h),
        color,
        -1,
    )
    cv2.putText(
        image,
        text,
        (label_left + padding, label_top + text_h + padding),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def draw_sku110k_planogram_annotation(
    image: np.ndarray,
    detections: List[Dict],
    slot_results: List[Dict],
) -> np.ndarray:
    annotated = image.copy()

    for detection in detections:
        try:
            x1, y1, x2, y2 = detection_box(detection)
        except (KeyError, TypeError, ValueError):
            continue
        cv2.rectangle(annotated, (x1, y1), (x2, y2), (180, 130, 60), 1)

    for result in slot_results:
        slot = result.get("slot", {})
        try:
            x1, y1, x2, y2 = slot_box_xyxy(annotated, slot)
        except (KeyError, TypeError, ValueError):
            continue

        color = BOX_COLORS["PASS"] if result.get("status") == "PASS" else BOX_COLORS["MISSING"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 4)
        detected_count = int(result.get("detected_count", 0) or 0)
        required_count = int(result.get("required_count", 1) or 1)
        slot_id = result.get("slot_id") or slot.get("slot_id") or ""
        if result.get("status") == "PASS":
            label = f"{slot_id} {detected_count}/{required_count}"
        else:
            label = f"{slot_id} MISS {detected_count}/{required_count}"
        draw_sku110k_planogram_label(annotated, label, x1, y1, color)

    return annotated


def evaluate_slots_with_yolo_detections(
    aligned_img: np.ndarray,
    ref_img: Optional[np.ndarray],
    slots: List[Dict],
    detections: List[Dict],
) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    missing_items = []
    slot_results = []
    accepted_detections = []

    for slot in slots:
        slot_type = expected_slot_type(slot)
        slot_id = slot.get("slot_id")
        expected_count, min_count, required_count = slot_count_requirements(slot)
        appearance_check = USE_SLOT_APPEARANCE_CHECK and slot_requires_appearance_check(
            slot,
            expected_count,
            min_count,
        )
        appearance_similarity = None
        appearance_threshold = slot_appearance_threshold(slot_type)
        normal_presence_pass = False
        print(f"[HYBRID] Slot {slot_id} appearance_check={appearance_check}")

        try:
            slot_box = slot_box_xyxy(aligned_img, slot)
        except (KeyError, TypeError, ValueError):
            appearance_similarity = 0.0 if appearance_check else None
            print(f"[HYBRID] Slot {slot_id} normal_presence_pass={normal_presence_pass}")
            sim_display = (
                "n/a" if appearance_similarity is None else f"{appearance_similarity:.2f}"
            )
            print(
                f"[HYBRID] Slot {slot_id} count=0/{required_count} "
                f"sim={sim_display} passed=False reason=invalid slot coordinates"
            )
            slot_results.append(
                {
                    "slot": slot,
                    "slot_id": slot_id,
                    "product_name": slot_name(slot),
                    "score": 0.0,
                    "status": "WARNING",
                    "label": "WARNING",
                    "expected_count": expected_count,
                    "min_count": min_count,
                    "required_count": required_count,
                    "detected_count": 0,
                    "appearance_similarity": appearance_similarity,
                    "reason": "invalid slot coordinates",
                }
            )
            continue

        matches, best_confidence, best_coverage, best_inside_ratio = matching_hybrid_detections(
            slot_box,
            slot_type,
            detections,
        )
        detected_count = len(matches)
        normal_presence_pass = detected_count > 0
        print(f"[HYBRID] Slot {slot_id} normal_presence_pass={normal_presence_pass}")

        if appearance_check:
            reference_crop = crop_box(ref_img, slot_box)
            uploaded_crop = crop_box(aligned_img, slot_box)
            appearance_similarity = compute_crop_similarity(reference_crop, uploaded_crop)

        effective_detected_count = detected_count
        appearance_passed = True
        if appearance_check:
            appearance_passed = appearance_similarity >= appearance_threshold
            grouped_count_passed = (
                required_count > 1
                and detected_count > 0
                and detected_count < required_count
                and appearance_similarity is not None
                and appearance_similarity
                >= max(appearance_threshold, COUNT_SENSITIVE_GROUP_MIN_SIMILARITY)
            )
            if grouped_count_passed:
                effective_detected_count = required_count

        count_passed = effective_detected_count >= required_count
        if appearance_check:
            passed = count_passed and appearance_passed

            if not count_passed and not appearance_passed:
                reason = "insufficient detections; appearance mismatch / possible background product"
                log_reason = "insufficient detections; appearance mismatch"
            elif not count_passed:
                reason = "insufficient detections"
                log_reason = reason
            elif not appearance_passed:
                reason = "appearance mismatch / possible background product"
                log_reason = "appearance mismatch"
            else:
                reason = None
                log_reason = "ok"
        else:
            passed = normal_presence_pass
            if passed:
                reason = None
                log_reason = "ok"
            else:
                reason = "no valid matching YOLO detection"
                log_reason = reason

        sim_display = "n/a" if appearance_similarity is None else f"{appearance_similarity:.2f}"
        print(
            f"[HYBRID] Slot {slot_id} count={effective_detected_count}/{required_count} "
            f"sim={sim_display} passed={passed} reason={log_reason}"
        )

        if not passed:
            status = "PROMO_MISSING" if slot_type == "promo" else "MISSING"
            label = "PROMO MISSING" if status == "PROMO_MISSING" else "MISSING"
            score = 0.0
            missing_items.append(
                {
                    "slot_id": slot_id,
                    "product_name": slot_name(slot),
                    "score": score,
                    "status": status,
                    "expected_count": expected_count,
                    "detected_count": effective_detected_count,
                    "required_count": required_count,
                    "appearance_similarity": appearance_similarity,
                    "reason": reason,
                }
            )
        else:
            score = round(best_confidence, 4)
            status = "PASS"
            label = "PASS"

        if appearance_passed and matches:
            accepted_detections.extend(matches)

        slot_results.append(
            {
                "slot": slot,
                "slot_id": slot_id,
                "product_name": slot_name(slot),
                "score": score,
                "status": status,
                "label": label,
                "expected_count": expected_count,
                "min_count": min_count,
                "required_count": required_count,
                "detected_count": detected_count,
                "appearance_similarity": appearance_similarity,
                "appearance_threshold": appearance_threshold if appearance_check else None,
                "reason": reason,
            }
        )

    return missing_items, slot_results, unique_detections(accepted_detections)


def draw_hybrid_annotation(
    image: np.ndarray,
    detections: List[Dict],
    slots: List[Dict],
    slot_results: List[Dict],
) -> np.ndarray:
    annotated = draw_yolo_detection_boxes(image, detections)

    for index, slot in enumerate(slots):
        result = slot_results[index] if index < len(slot_results) else {}
        if result.get("status") == "PASS":
            continue

        try:
            x1, y1, x2, y2 = slot_box_xyxy(annotated, slot)
        except (KeyError, TypeError, ValueError):
            continue

        code = short_slot_code(result.get("slot_id") or slot.get("slot_id"))
        detected_count = result.get("detected_count")
        required_count = result.get("required_count")
        appearance_similarity = result.get("appearance_similarity")
        if detected_count is not None and required_count is not None:
            count_text = f" {detected_count}/{required_count}"
        else:
            count_text = ""
        if appearance_similarity is not None:
            sim_text = f" sim={float(appearance_similarity):.2f}"
        else:
            sim_text = ""
        label = f"MISS {code}{count_text}{sim_text}" if code else f"MISS{count_text}{sim_text}"
        x = x1
        y = y1
        w = x2 - x1
        h = y2 - y1
        color = BOX_COLORS["MISSING"]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 4)
        draw_label(annotated, label, x, y, w, h, color)

    return annotated


def alignment_failure_response(
    image: np.ndarray,
    model_score: float,
    analysis_mode: str,
) -> Dict:
    annotated = draw_banner(image, "NEED RETAKE", BOX_COLORS["UNKNOWN_MODEL"])
    annotated_image_name = save_annotated_image(annotated)
    return {
        "detected_model": "UNKNOWN",
        "model_score": model_score,
        "result": "NEED_RETAKE",
        "missing_count": 0,
        "missing_items": [],
        "annotated_image_name": annotated_image_name,
        "reason": ALIGNMENT_FAILURE_REASON,
        "analysis_mode": analysis_mode,
        **compliance_summary([], []),
    }


def analyze_hybrid(
    uploaded_img: np.ndarray,
    model_result: Dict,
    detected_model: str,
    model_score: float,
) -> Optional[Dict]:
    print("[HYBRID] Running hybrid shelf audit")

    aligned_img = model_result.get("aligned_image")
    if detected_model not in HYBRID_MODEL_IDS or aligned_img is None:
        print("[HYBRID] Alignment failed")
        print("[HYBRID] result=NEED_RETAKE")
        return alignment_failure_response(uploaded_img, model_score, "hybrid")

    print(f"[HYBRID] Detected model: {detected_model}")
    print("[HYBRID] Alignment success")

    planogram = load_planogram(detected_model)
    slots = planogram.get("slots", []) or []
    ref_img = model_result.get("reference_image")
    aligned_debug_image_name = save_aligned_debug_image(aligned_img, detected_model)

    roi = target_shelf_roi(aligned_img, slots)
    slot_boxes = valid_slot_boxes(aligned_img, slots)
    print(f"[HYBRID] ROI: {roi[0]},{roi[1]},{roi[2]},{roi[3]}")
    yolo_input = mask_image_to_roi(aligned_img, roi)

    try:
        from yolo_detector import detect_objects

        detections = detect_objects(
            yolo_input,
            confidence_threshold=min(YOLO_PRODUCT_MIN_CONF, YOLO_PROMO_MIN_CONF),
        )
    except Exception as exc:
        print(f"[YOLO] Fallback to similarity check: {exc}")
        return None

    raw_product_count, raw_promo_count, raw_total_count = count_yolo_detections(detections)
    print(
        f"[HYBRID] Raw detections: total={raw_total_count} "
        f"product={raw_product_count} promo={raw_promo_count}"
    )

    useful_detections = filter_hybrid_detections(
        detections,
        roi=roi,
        slot_boxes=slot_boxes,
    )
    product_count, promo_count, total_count = count_yolo_detections(useful_detections)
    dropped_detection_count = max(0, raw_total_count - total_count)
    print(
        f"[HYBRID] ROI-filtered detections: total={total_count} "
        f"product={product_count} promo={promo_count}"
    )
    print(f"[HYBRID] Dropped background detections: {dropped_detection_count}")

    if not slots:
        missing_items = []
        slot_results = []
        accepted_detections = []
    else:
        missing_items, slot_results, accepted_detections = evaluate_slots_with_yolo_detections(
            aligned_img,
            ref_img,
            slots,
            useful_detections,
        )

    rejected_detection_count = max(0, len(useful_detections) - len(accepted_detections))
    print(f"[HYBRID] Accepted detections: {len(accepted_detections)}")
    print(f"[HYBRID] Rejected detections: {rejected_detection_count}")

    summary = compliance_summary(slots, slot_results)
    result = classify_result(summary)
    print(f"[HYBRID] product_pass_rate={summary['product_pass_rate']}")
    print(f"[HYBRID] promo_pass_rate={summary['promo_pass_rate']}")
    print(f"[HYBRID] Final result={result}")

    annotated = draw_hybrid_annotation(
        aligned_img,
        accepted_detections,
        slots,
        slot_results,
    )
    annotated_image_name = save_annotated_image(annotated)

    return {
        "detected_model": detected_model,
        "model_score": model_score,
        "result": result,
        "missing_count": len(missing_items),
        "missing_items": missing_items,
        "annotated_image_name": annotated_image_name,
        "aligned_debug_image_name": aligned_debug_image_name,
        "analysis_mode": "hybrid",
        **summary,
    }


def analyze_sku110k_planogram(
    uploaded_img: np.ndarray,
    model_result: Dict,
    detected_model: str,
    model_score: float,
) -> Dict:
    print("[SKU110K_PLANOGRAM] Running SKU110K planogram shelf audit")

    aligned_img = model_result.get("aligned_image")
    if detected_model not in HYBRID_MODEL_IDS or aligned_img is None:
        print("[SKU110K_PLANOGRAM] Alignment failed")
        print("[SKU110K_PLANOGRAM] final result=NEED_RETAKE")
        return alignment_failure_response(
            uploaded_img,
            model_score,
            "sku110k_planogram",
        )

    print(f"[SKU110K_PLANOGRAM] Detected model: {detected_model}")
    planogram = load_planogram(detected_model)
    slots = planogram.get("slots", []) or []
    product_slots = [slot for slot in slots if expected_slot_type(slot) == "product"]
    promo_slots = [slot for slot in slots if expected_slot_type(slot) == "promo"]
    aligned_debug_image_name = save_aligned_debug_image(aligned_img, detected_model)

    if not product_slots:
        print("[SKU110K_PLANOGRAM] slot pass/missing summary passed=0 missing=0 total=0")
        print("[SKU110K_PLANOGRAM] final result=PASS")
        annotated = draw_banner(
            aligned_img,
            "NO PRODUCT SLOTS CONFIGURED",
            BOX_COLORS["WARNING"],
        )
        annotated_image_name = save_annotated_image(annotated)
        summary = sku110k_planogram_summary(product_slots, promo_slots, [])
        print(
            "[SKU110K_PLANOGRAM] metrics "
            f"analysis_mode=sku110k_planogram "
            f"product_total={summary['product_total']} "
            f"product_missing_count={summary['product_missing_count']} "
            f"product_pass_rate={summary['product_pass_rate']} "
            "final_result=PASS"
        )
        return {
            "detected_model": detected_model,
            "model_score": model_score,
            "result": "PASS",
            "missing_count": 0,
            "missing_items": [],
            "annotated_image_name": annotated_image_name,
            "aligned_debug_image_name": aligned_debug_image_name,
            "analysis_mode": "sku110k_planogram",
            **summary,
        }

    detections = detect_sku110k_planogram_products(
        aligned_img,
        confidence_threshold=SKU110K_PLANOGRAM_CONFIDENCE_THRESHOLD,
    )
    missing_items, slot_results = evaluate_slots_with_sku110k_planogram(
        aligned_img,
        product_slots,
        detections,
    )
    summary = sku110k_planogram_summary(product_slots, promo_slots, slot_results)
    result = "FAIL" if summary["product_missing_count"] > 0 else "PASS"
    print(
        "[SKU110K_PLANOGRAM] slot pass/missing summary "
        f"passed={summary['product_total'] - summary['product_missing_count']} "
        f"missing={summary['product_missing_count']} total={summary['product_total']}"
    )
    print(
        "[SKU110K_PLANOGRAM] metrics "
        f"analysis_mode=sku110k_planogram "
        f"product_total={summary['product_total']} "
        f"product_missing_count={summary['product_missing_count']} "
        f"product_pass_rate={summary['product_pass_rate']} "
        f"final_result={result}"
    )
    print(f"[SKU110K_PLANOGRAM] final result={result}")

    annotated = draw_sku110k_planogram_annotation(
        aligned_img,
        detections,
        slot_results,
    )
    annotated_image_name = save_annotated_image(annotated)

    return {
        "detected_model": detected_model,
        "model_score": model_score,
        "result": result,
        "missing_count": len(missing_items),
        "missing_items": missing_items,
        "annotated_image_name": annotated_image_name,
        "aligned_debug_image_name": aligned_debug_image_name,
        "analysis_mode": "sku110k_planogram",
        **summary,
    }


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


def analyze_slot_similarity(
    uploaded_img: np.ndarray,
    model_result: Dict,
    detected_model: str,
    model_score: float,
    analysis_mode: str = "slot_similarity",
) -> Dict:
    if model_result.get("result") == "NEED_RETAKE":
        response = alignment_failure_response(uploaded_img, model_score, analysis_mode)
        return response

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
            "analysis_mode": analysis_mode,
            **compliance_summary([], []),
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
            "analysis_mode": analysis_mode,
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
        "analysis_mode": analysis_mode,
        **summary,
    }


def analyze_image(image_path: str) -> Dict:
    uploaded_img = read_image(image_path)
    if uploaded_img is None:
        raise ValueError(f"Could not read image: {image_path}")

    mode = selected_analysis_mode()
    model_ids = HYBRID_MODEL_IDS if mode in {"hybrid", "sku110k_planogram"} else None
    model_result = detect_shelf_model(uploaded_img, model_ids=model_ids)
    detected_model = model_result["detected_model"]
    model_score = float(model_result["model_score"])

    if mode == "sku110k_planogram":
        return analyze_sku110k_planogram(
            uploaded_img,
            model_result,
            detected_model,
            model_score,
        )

    if mode == "hybrid":
        hybrid_response = analyze_hybrid(
            uploaded_img,
            model_result,
            detected_model,
            model_score,
        )
        if hybrid_response is not None:
            return hybrid_response

        return analyze_slot_similarity(
            uploaded_img,
            model_result,
            detected_model,
            model_score,
        )

    if mode == "yolo_only":
        yolo_only_response = analyze_yolo_only(
            uploaded_img,
            model_result,
            detected_model,
            model_score,
        )
        if yolo_only_response is not None:
            return yolo_only_response

        return analyze_slot_similarity(
            uploaded_img,
            model_result,
            detected_model,
            model_score,
        )

    return analyze_slot_similarity(
        uploaded_img,
        model_result,
        detected_model,
        model_score,
    )
