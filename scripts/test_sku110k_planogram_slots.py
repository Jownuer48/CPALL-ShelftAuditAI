#!/usr/bin/env python3
"""Run an experimental SKU110K product detector against MODEL_A planogram slots."""

from __future__ import annotations

import json
import os
import argparse
from pathlib import Path
from typing import Any

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
IMAGE_PATH = BACKEND_DIR / "reference" / "model_a.jpg"
PLANOGRAM_PATH = BACKEND_DIR / "planograms" / "model_a.json"
MODEL_PATH = BACKEND_DIR / "yolo_models" / "experiments" / "sku110k_product.pt"
DEBUG_DIR = BACKEND_DIR / "debug" / "sku110k"
OUTPUT_IMAGE_PATH = DEBUG_DIR / "sku110k_planogram_slots_model_a.jpg"
OUTPUT_JSON_PATH = DEBUG_DIR / "sku110k_planogram_slots_model_a.json"
SYNTHETIC_PREFIX = "synthetic_missing"
CONFIDENCE_THRESHOLD = 0.15
SLOT_COVERAGE_THRESHOLD = 0.25
IOU_THRESHOLD = 0.15


def ensure_ultralytics_config_dir() -> None:
    configured = os.environ.get("YOLO_CONFIG_DIR")
    candidate = Path(configured) if configured else DEBUG_DIR / "ultralytics_config"
    fallback = DEBUG_DIR / "ultralytics_config"

    try:
        candidate.mkdir(parents=True, exist_ok=True)
        probe = candidate / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        os.environ["YOLO_CONFIG_DIR"] = str(candidate)
    except OSError:
        fallback.mkdir(parents=True, exist_ok=True)
        os.environ["YOLO_CONFIG_DIR"] = str(fallback)


ensure_ultralytics_config_dir()
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit MODEL_A product slots with an experimental SKU110K detector."
    )
    parser.add_argument("--image", type=Path, default=IMAGE_PATH)
    parser.add_argument("--planogram", type=Path, default=PLANOGRAM_PATH)
    parser.add_argument("--model", type=Path, default=MODEL_PATH)
    parser.add_argument("--output-image", type=Path, default=None)
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--conf", type=float, default=CONFIDENCE_THRESHOLD)
    parser.add_argument(
        "--blank-slot",
        default=None,
        help="Create a synthetic missing-product image by blanking this slot_id first.",
    )
    return parser.parse_args()


def resolve_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def default_output_image(blank_slot: str | None) -> Path:
    if blank_slot:
        return DEBUG_DIR / f"sku110k_planogram_slots_model_a_missing_{safe_filename(blank_slot)}.jpg"
    return OUTPUT_IMAGE_PATH


def default_output_json(blank_slot: str | None) -> Path:
    if blank_slot:
        return DEBUG_DIR / f"sku110k_planogram_slots_model_a_missing_{safe_filename(blank_slot)}.json"
    return OUTPUT_JSON_PATH


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")


def load_image(path: Path):
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return image


def load_planogram(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def looks_normalized(values: list[float]) -> bool:
    return all(-0.01 <= value <= 1.5 for value in values)


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def safe_filename(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)


def scaled_box(values: list[float], image_w: int, image_h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = values
    if looks_normalized(values):
        x1 *= image_w
        x2 *= image_w
        y1 *= image_h
        y2 *= image_h

    left = clamp(round(min(x1, x2)), 0, image_w - 1)
    top = clamp(round(min(y1, y2)), 0, image_h - 1)
    right = clamp(round(max(x1, x2)), 0, image_w)
    bottom = clamp(round(max(y1, y2)), 0, image_h)
    if right <= left or bottom <= top:
        raise ValueError("Invalid slot box")
    return left, top, right, bottom


def slot_box(slot: dict[str, Any], image_w: int, image_h: int) -> tuple[int, int, int, int]:
    x = to_float(slot.get("x"))
    y = to_float(slot.get("y"))
    w = to_float(slot.get("w", slot.get("width")))
    h = to_float(slot.get("h", slot.get("height")))
    if None not in (x, y, w, h):
        return scaled_box([x, y, x + w, y + h], image_w, image_h)

    x1 = to_float(slot.get("x1", slot.get("left")))
    y1 = to_float(slot.get("y1", slot.get("top")))
    x2 = to_float(slot.get("x2", slot.get("right")))
    y2 = to_float(slot.get("y2", slot.get("bottom")))
    if None not in (x1, y1, x2, y2):
        return scaled_box([x1, y1, x2, y2], image_w, image_h)

    bbox = slot.get("bbox") or slot.get("box")
    if isinstance(bbox, list) and len(bbox) >= 4:
        values = [to_float(value) for value in bbox[:4]]
        if None not in values:
            bx, by, bw, bh = values
            return scaled_box([bx, by, bx + bw, by + bh], image_w, image_h)

    raise ValueError(f"Slot has no supported coordinates: {slot.get('slot_id')}")


def is_product_slot(slot: dict[str, Any]) -> bool:
    text = " ".join(
        str(slot.get(key, "")) for key in ["type", "category", "slot_id", "label", "name"]
    ).lower()
    if "promo" in text or "tag" in text:
        return False
    return "product" in text or slot.get("type") is None and slot.get("category") is None


def required_count(slot: dict[str, Any]) -> int:
    for key in ("min_count", "expected_count"):
        value = slot.get(key)
        if value is None:
            continue
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            continue
    return 1


def find_slot(planogram: dict[str, Any], slot_id: str) -> dict[str, Any]:
    for slot in planogram.get("slots", []):
        if str(slot.get("slot_id")) == slot_id:
            return slot
    raise ValueError(f"Slot not found in planogram: {slot_id}")


def nearby_neutral_fill(image, target_box: tuple[int, int, int, int]) -> tuple[int, int, int]:
    x1, y1, x2, y2 = target_box
    image_h, image_w = image.shape[:2]
    slot_w = x2 - x1
    slot_h = y2 - y1
    margin = max(16, round(min(slot_w, slot_h) * 0.35))

    sx1 = clamp(x1 - margin, 0, image_w - 1)
    sy1 = clamp(y1 - margin, 0, image_h - 1)
    sx2 = clamp(x2 + margin, 0, image_w)
    sy2 = clamp(y2 + margin, 0, image_h)
    sample = image[sy1:sy2, sx1:sx2]
    if sample.size == 0:
        sample = image

    mask = np.ones(sample.shape[:2], dtype=bool)
    local_x1 = max(0, x1 - sx1)
    local_y1 = max(0, y1 - sy1)
    local_x2 = min(mask.shape[1], x2 - sx1)
    local_y2 = min(mask.shape[0], y2 - sy1)
    mask[local_y1:local_y2, local_x1:local_x2] = False

    candidates = sample[mask]
    if candidates.size == 0:
        candidates = image.reshape(-1, 3)

    hsv = cv2.cvtColor(candidates.reshape(-1, 1, 3), cv2.COLOR_BGR2HSV).reshape(-1, 3)
    neutral = candidates[(hsv[:, 1] < 70) & (hsv[:, 2] > 35)]
    pixels = neutral if len(neutral) >= 100 else candidates
    color = np.median(pixels, axis=0)
    return tuple(int(channel) for channel in color.tolist())


def create_blank_slot_image(
    image,
    slot: dict[str, Any],
    output_dir: Path,
) -> tuple[Any, Path]:
    image_h, image_w = image.shape[:2]
    target_box = slot_box(slot, image_w, image_h)
    x1, y1, x2, y2 = target_box
    synthetic = image.copy()
    fill_color = nearby_neutral_fill(image, target_box)
    synthetic[y1:y2, x1:x2] = fill_color

    slot_id = safe_filename(str(slot.get("slot_id", "unknown_slot")))
    output_path = output_dir / f"{SYNTHETIC_PREFIX}_{slot_id}.jpg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), synthetic):
        raise OSError(f"Could not write synthetic missing image: {output_path}")
    return synthetic, output_path


def detect_products(image, model_path: Path, confidence_threshold: float) -> list[dict[str, Any]]:
    model = YOLO(str(model_path))
    results = model.predict(
        source=image,
        conf=confidence_threshold,
        device="cpu",
        verbose=False,
        save=False,
    )
    if not results:
        return []

    boxes = getattr(results[0], "boxes", None)
    if boxes is None:
        return []

    image_h, image_w = image.shape[:2]
    detections: list[dict[str, Any]] = []
    for box in boxes:
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        left = clamp(round(x1), 0, image_w - 1)
        top = clamp(round(y1), 0, image_h - 1)
        right = clamp(round(x2), 0, image_w)
        bottom = clamp(round(y2), 0, image_h)
        if right <= left or bottom <= top:
            continue
        detections.append(
            {
                "class_name": "product",
                "confidence": float(box.conf[0].item()),
                "x1": left,
                "y1": top,
                "x2": right,
                "y2": bottom,
            }
        )
    return detections


def intersection_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    width = max(0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0, min(ay2, by2) - max(ay1, by1))
    return width * height


def box_area(box: tuple[int, int, int, int]) -> int:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    inter = intersection_area(a, b)
    union = box_area(a) + box_area(b) - inter
    return 0.0 if union <= 0 else inter / union


def center_inside(detection_box: tuple[int, int, int, int], target_box: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = detection_box
    sx1, sy1, sx2, sy2 = target_box
    center_x = (x1 + x2) / 2.0
    center_y = (y1 + y2) / 2.0
    return sx1 <= center_x <= sx2 and sy1 <= center_y <= sy2


def matches_slot(detection: dict[str, Any], target_box: tuple[int, int, int, int]) -> bool:
    detection_box = (
        int(detection["x1"]),
        int(detection["y1"]),
        int(detection["x2"]),
        int(detection["y2"]),
    )
    slot_area = box_area(target_box)
    coverage = 0.0 if slot_area <= 0 else intersection_area(detection_box, target_box) / slot_area
    return (
        center_inside(detection_box, target_box)
        or coverage >= SLOT_COVERAGE_THRESHOLD
        or iou(detection_box, target_box) >= IOU_THRESHOLD
    )


def evaluate_slots(
    slots: list[dict[str, Any]],
    detections: list[dict[str, Any]],
    image_w: int,
    image_h: int,
) -> list[dict[str, Any]]:
    results = []
    for slot in slots:
        target_box = slot_box(slot, image_w, image_h)
        required = required_count(slot)
        matched = sum(1 for detection in detections if matches_slot(detection, target_box))
        status = "PASS" if matched >= required else "MISSING"
        results.append(
            {
                "slot_id": str(slot.get("slot_id", "UNKNOWN_SLOT")),
                "status": status,
                "required_count": required,
                "matched_count": matched,
                "box": target_box,
            }
        )
    return results


def draw_label(image, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.52
    thickness = 1
    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)
    label_y = max(text_h + baseline + 4, y)
    cv2.rectangle(
        image,
        (x, label_y - text_h - baseline - 6),
        (x + text_w + 8, label_y + baseline),
        color,
        -1,
    )
    cv2.putText(
        image,
        text,
        (x + 4, label_y - 4),
        font,
        font_scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def draw_output(image, detections: list[dict[str, Any]], slot_results: list[dict[str, Any]]):
    output = image.copy()

    for detection in detections:
        x1 = int(detection["x1"])
        y1 = int(detection["y1"])
        x2 = int(detection["x2"])
        y2 = int(detection["y2"])
        cv2.rectangle(output, (x1, y1), (x2, y2), (180, 130, 60), 1)

    for result in slot_results:
        x1, y1, x2, y2 = result["box"]
        status = result["status"]
        color = (0, 180, 0) if status == "PASS" else (0, 0, 255)
        cv2.rectangle(output, (x1, y1), (x2, y2), color, 4)
        if status == "PASS":
            label = f"{result['slot_id']} {result['matched_count']}/{result['required_count']}"
        else:
            label = (
                f"{result['slot_id']} MISS "
                f"{result['matched_count']}/{result['required_count']}"
            )
        draw_label(output, label, x1, y1, color)

    return output


def main() -> int:
    args = parse_args()
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    image_path = resolve_path(args.image)
    planogram_path = resolve_path(args.planogram)
    model_path = resolve_path(args.model)
    output_image_path = resolve_path(args.output_image) if args.output_image else default_output_image(args.blank_slot)
    output_json_path = resolve_path(args.output_json) if args.output_json else default_output_json(args.blank_slot)

    for path in [image_path, planogram_path, model_path]:
        require_file(path)

    image = load_image(image_path)
    planogram = load_planogram(planogram_path)
    audited_image_path = image_path
    if args.blank_slot:
        blank_slot = find_slot(planogram, args.blank_slot)
        image, audited_image_path = create_blank_slot_image(image, blank_slot, DEBUG_DIR)

    image_h, image_w = image.shape[:2]
    product_slots = [slot for slot in planogram.get("slots", []) if is_product_slot(slot)]
    detections = detect_products(image, model_path, args.conf)
    slot_results = evaluate_slots(product_slots, detections, image_w, image_h)

    passed_slots = sum(1 for item in slot_results if item["status"] == "PASS")
    total_slots = len(slot_results)
    missing_slots = total_slots - passed_slots
    pass_rate = 0.0 if total_slots == 0 else round(passed_slots / total_slots, 4)
    missing_slot_ids = [item["slot_id"] for item in slot_results if item["status"] == "MISSING"]

    annotated = draw_output(image, detections, slot_results)
    output_image_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_image_path), annotated):
        raise OSError(f"Could not write output image: {output_image_path}")

    report = {
        "image": str(audited_image_path),
        "planogram": str(planogram_path),
        "model": str(model_path),
        "total_slots": total_slots,
        "passed_slots": passed_slots,
        "missing_slots": missing_slots,
        "pass_rate": pass_rate,
        "slots": [
            {
                "slot_id": item["slot_id"],
                "status": item["status"],
                "required_count": item["required_count"],
                "matched_count": item["matched_count"],
            }
            for item in slot_results
        ],
    }
    output_json_path.parent.mkdir(parents=True, exist_ok=True)
    output_json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"total slots: {total_slots}")
    print(f"passed: {passed_slots}")
    print(f"missing: {missing_slots}")
    print(f"pass rate: {pass_rate:.4f}")
    print(f"missing slot IDs: {', '.join(missing_slot_ids) if missing_slot_ids else 'none'}")
    print(f"output image: {output_image_path}")
    print(f"output json: {output_json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
