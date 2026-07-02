#!/usr/bin/env python3
"""Compare the current shelf detector with the experimental SKU110K detector."""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
REFERENCE_DIR = BACKEND_DIR / "reference"
DEBUG_DIR = BACKEND_DIR / "debug" / "sku110k"
PLANOGRAM_PATH = BACKEND_DIR / "planograms" / "model_a.json"
REFERENCE_CANDIDATES = ("model_a.jpg",)
DEFAULT_CURRENT_OUTPUT = DEBUG_DIR / "current_detector_result.jpg"
DEFAULT_SKU110K_OUTPUT = DEBUG_DIR / "sku110k_detector_result.jpg"


@dataclass
class DetectorRun:
    name: str
    detections: list[dict]
    elapsed_ms: float
    error: Exception | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run current and SKU110K detectors on the MODEL_A reference shelf image."
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=None,
        help="Optional shelf image path. Defaults to backend/reference/model_a.jpg.",
    )
    parser.add_argument("--confidence", type=float, default=0.10)
    parser.add_argument("--planogram", type=Path, default=PLANOGRAM_PATH)
    parser.add_argument("--current-output", type=Path, default=DEFAULT_CURRENT_OUTPUT)
    parser.add_argument("--sku110k-output", type=Path, default=DEFAULT_SKU110K_OUTPUT)
    return parser.parse_args()


def find_reference_image() -> Path:
    for filename in REFERENCE_CANDIDATES:
        candidate = REFERENCE_DIR / filename
        if candidate.exists():
            return candidate

    lower_names = {filename.lower() for filename in REFERENCE_CANDIDATES}
    for candidate in REFERENCE_DIR.iterdir():
        if candidate.name.lower() in lower_names:
            return candidate

    expected = ", ".join(str(REFERENCE_DIR / name) for name in REFERENCE_CANDIDATES)
    raise FileNotFoundError(f"Reference image not found. Expected one of: {expected}")


def load_image(path: Path):
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Could not read image: {path}")
    return image


def import_detectors() -> tuple[Callable, Callable]:
    sys.path.insert(0, str(BACKEND_DIR))
    from sku110k_detector import detect_objects as detect_sku110k_objects
    from yolo_detector import detect_objects as detect_current_objects

    return detect_current_objects, detect_sku110k_objects


def run_detector(
    name: str,
    detect_fn: Callable,
    image,
    confidence_threshold: float,
) -> DetectorRun:
    start = time.perf_counter()
    try:
        detections = detect_fn(image, confidence_threshold=confidence_threshold)
    except Exception as exc:
        return DetectorRun(name=name, detections=[], elapsed_ms=0.0, error=exc)

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return DetectorRun(name=name, detections=detections, elapsed_ms=elapsed_ms)


def count_class(detections: list[dict], class_name: str) -> int:
    return sum(1 for item in detections if item.get("class_name") == class_name)


def confidence_stats(detections: list[dict]) -> str:
    confidences = [
        float(item.get("confidence", 0.0))
        for item in detections
        if item.get("confidence") is not None
    ]
    if not confidences:
        return "count=0"

    total = sum(confidences)
    return (
        f"count={len(confidences)} "
        f"min={min(confidences):.3f} "
        f"mean={total / len(confidences):.3f} "
        f"max={max(confidences):.3f}"
    )


def draw_detections(image, detections: list[dict], title: str):
    annotated = image.copy()
    height, width = annotated.shape[:2]
    thickness = max(1, round(min(height, width) / 300))
    font_scale = max(0.45, min(height, width) / 1100)

    cv2.putText(
        annotated,
        title,
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (255, 255, 255),
        thickness + 2,
        cv2.LINE_AA,
    )
    cv2.putText(
        annotated,
        title,
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        font_scale,
        (20, 20, 20),
        thickness,
        cv2.LINE_AA,
    )

    for detection in detections:
        class_name = str(detection.get("class_name", "unknown"))
        confidence = float(detection.get("confidence", 0.0))
        x1 = int(detection["x1"])
        y1 = int(detection["y1"])
        x2 = int(detection["x2"])
        y2 = int(detection["y2"])
        color = (0, 190, 0) if class_name == "product" else (0, 140, 255)
        label = f"{class_name} {confidence:.2f}"

        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, thickness)
        label_y = max(16, y1 - 6)
        cv2.putText(
            annotated,
            label,
            (x1, label_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )

    return annotated


def save_debug_image(path: Path, image, detections: list[dict], title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    annotated = draw_detections(image, detections, title)
    if not cv2.imwrite(str(path), annotated):
        raise OSError(f"Could not write debug image: {path}")


def is_promo_slot(slot: dict) -> bool:
    text = " ".join(
        str(slot.get(key, "")) for key in ["slot_id", "type", "label", "name"]
    ).lower()
    return "promo" in text or "tag" in text


def slot_required_count(slot: dict) -> int:
    for key in ("min_count", "expected_count"):
        value = slot.get(key)
        if value is None:
            continue
        try:
            return max(1, int(value))
        except (TypeError, ValueError):
            continue

    return 1


def slot_box(image, slot: dict) -> tuple[int, int, int, int]:
    height, width = image.shape[:2]
    x1 = int(float(slot["x"]) * width)
    y1 = int(float(slot["y"]) * height)
    x2 = int((float(slot["x"]) + float(slot["w"])) * width)
    y2 = int((float(slot["y"]) + float(slot["h"])) * height)
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(0, min(x2, width))
    y2 = max(0, min(y2, height))
    return x1, y1, x2, y2


def detection_center(detection: dict) -> tuple[float, float]:
    return (
        (float(detection["x1"]) + float(detection["x2"])) / 2.0,
        (float(detection["y1"]) + float(detection["y2"])) / 2.0,
    )


def detection_in_slot(detection: dict, box: tuple[int, int, int, int]) -> bool:
    x, y = detection_center(detection)
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


def slot_coverage_report(image, planogram_path: Path, detections: list[dict]) -> str:
    if not planogram_path.exists():
        return f"planogram not found: {planogram_path}"

    with planogram_path.open("r", encoding="utf-8-sig") as handle:
        planogram = json.load(handle)

    product_slots = [slot for slot in planogram.get("slots", []) if not is_promo_slot(slot)]
    expected_slots = [
        slot
        for slot in product_slots
        if slot.get("expected_count") is not None or slot.get("min_count") is not None
    ]
    product_detections = [
        item for item in detections if item.get("class_name") == "product"
    ]

    covered = 0
    expected_met = 0
    for slot in product_slots:
        box = slot_box(image, slot)
        detected_count = sum(1 for item in product_detections if detection_in_slot(item, box))
        if detected_count > 0:
            covered += 1
        if slot in expected_slots and detected_count >= slot_required_count(slot):
            expected_met += 1

    return (
        f"product_slots_covered={covered}/{len(product_slots)} "
        f"expected_count_slots_met={expected_met}/{len(expected_slots)}"
    )


def print_detector_report(run: DetectorRun, image, planogram_path: Path) -> None:
    print(f"{run.name} detector:")
    if run.error is not None:
        print(f"  error: {run.error}")
        return

    print(f"  product count: {count_class(run.detections, 'product')}")
    print(f"  promo count: {count_class(run.detections, 'promo')}")
    print(f"  inference time ms: {run.elapsed_ms:.1f}")
    print(f"  confidence stats: {confidence_stats(run.detections)}")
    print(f"  slot coverage: {slot_coverage_report(image, planogram_path, run.detections)}")


def main() -> int:
    args = parse_args()
    image_path = args.image or find_reference_image()
    image = load_image(image_path)
    detect_current_objects, detect_sku110k_objects = import_detectors()

    current_run = run_detector(
        "current",
        detect_current_objects,
        image,
        confidence_threshold=args.confidence,
    )
    sku110k_run = run_detector(
        "SKU110K",
        detect_sku110k_objects,
        image,
        confidence_threshold=args.confidence,
    )

    print(f"image: {image_path}")
    print(f"confidence threshold: {args.confidence}")
    print_detector_report(current_run, image, args.planogram)
    print_detector_report(sku110k_run, image, args.planogram)

    if current_run.error is None:
        save_debug_image(
            args.current_output,
            image,
            current_run.detections,
            "Current detector",
        )
        print(f"current debug image: {args.current_output}")

    if sku110k_run.error is None:
        save_debug_image(
            args.sku110k_output,
            image,
            sku110k_run.detections,
            "SKU110K detector",
        )
        print(f"SKU110K debug image: {args.sku110k_output}")

    return 1 if current_run.error or sku110k_run.error else 0


if __name__ == "__main__":
    raise SystemExit(main())
