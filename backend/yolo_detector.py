import os
from functools import lru_cache
from typing import Dict, List

import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
YOLO_MODEL_PATH = os.path.join(BASE_DIR, "yolo_models", "shelf_yolo.pt")
DISPLAY_MODEL_PATH = "backend/yolo_models/shelf_yolo.pt"
CLASS_NAMES = {
    0: "product",
    1: "promo",
}


@lru_cache(maxsize=1)
def load_model():
    if not os.path.exists(YOLO_MODEL_PATH):
        raise FileNotFoundError(f"YOLO model not found: {YOLO_MODEL_PATH}")

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise RuntimeError("ultralytics is not installed") from exc

    model = YOLO(YOLO_MODEL_PATH)
    print(f"[YOLO] Loaded model: {DISPLAY_MODEL_PATH}")
    return model


def detect_objects(
    image: np.ndarray,
    confidence_threshold: float = 0.10,
) -> List[Dict]:
    model = load_model()
    results = model.predict(
        source=image,
        conf=confidence_threshold,
        verbose=False,
        save=False,
    )

    if not results:
        return []

    result = results[0]
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return []

    detections = []
    image_h, image_w = image.shape[:2]

    for box in boxes:
        class_id = int(box.cls[0].item())
        class_name = CLASS_NAMES.get(class_id)
        if class_name is None:
            continue

        confidence = float(box.conf[0].item())
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        clipped_x1 = int(max(0, min(round(x1), image_w - 1)))
        clipped_y1 = int(max(0, min(round(y1), image_h - 1)))
        clipped_x2 = int(max(0, min(round(x2), image_w - 1)))
        clipped_y2 = int(max(0, min(round(y2), image_h - 1)))

        if clipped_x2 <= clipped_x1 or clipped_y2 <= clipped_y1:
            continue

        detections.append(
            {
                "class_name": class_name,
                "confidence": confidence,
                "x1": clipped_x1,
                "y1": clipped_y1,
                "x2": clipped_x2,
                "y2": clipped_y2,
            }
        )

    product_count = sum(1 for item in detections if item["class_name"] == "product")
    promo_count = sum(1 for item in detections if item["class_name"] == "promo")
    print(
        f"[YOLO] Detections: {len(detections)} total, "
        f"product={product_count}, promo={promo_count}"
    )

    return detections
