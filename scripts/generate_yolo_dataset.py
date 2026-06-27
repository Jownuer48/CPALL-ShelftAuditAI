#!/usr/bin/env python3
"""Generate a YOLO dataset from shelf reference images and planogram slots."""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
REFERENCE_DIR = BACKEND_DIR / "reference"
PLANOGRAM_DIR = BACKEND_DIR / "planograms"
DATASET_DIR = REPO_ROOT / "datasets" / "shelf_audit"
IMAGE_SIZE = (800, 600)  # width, height, matching backend analyzer size
CLASS_NAMES = ["product", "promo"]
MIN_BOX_SIZE_PX = 3.0


@dataclass(frozen=True)
class ModelSource:
    model_id: str
    reference_name: str
    planogram_name: str


SOURCES = [
    ModelSource("MODEL_A", "model_a.jpg", "model_a.json"),
    ModelSource("MODEL_B", "model_b.jpg", "model_b.json"),
]


@dataclass(frozen=True)
class YoloBox:
    class_id: int
    x_center: float
    y_center: float
    width: float
    height: float

    def line(self) -> str:
        return (
            f"{self.class_id} "
            f"{self.x_center:.6f} {self.y_center:.6f} "
            f"{self.width:.6f} {self.height:.6f}"
        )


@dataclass
class PreparedSource:
    source: ModelSource
    image: np.ndarray
    boxes: list[YoloBox]


def find_file_case_insensitive(directory: Path, filename: str) -> Path:
    exact = directory / filename
    if exact.exists():
        return exact

    target = filename.lower()
    for candidate in directory.iterdir():
        if candidate.name.lower() == target:
            return candidate

    raise FileNotFoundError(f"Could not find {filename} in {directory}")


def read_reference(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Could not read reference image: {path}")

    return cv2.resize(image, IMAGE_SIZE, interpolation=cv2.INTER_AREA)


def read_planogram(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def slot_class_id(slot: dict) -> int:
    slot_text = " ".join(
        str(slot.get(key, "")) for key in ["type", "slot_id", "label", "name"]
    ).lower()
    return 1 if "promo" in slot_text or "tag" in slot_text else 0


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def slot_to_yolo_box(slot: dict) -> YoloBox | None:
    try:
        x = float(slot["x"])
        y = float(slot["y"])
        w = float(slot["w"])
        h = float(slot["h"])
    except (KeyError, TypeError, ValueError):
        return None

    x1 = clamp(x)
    y1 = clamp(y)
    x2 = clamp(x + w)
    y2 = clamp(y + h)

    if x2 <= x1 or y2 <= y1:
        return None

    width = x2 - x1
    height = y2 - y1
    x_center = x1 + width / 2.0
    y_center = y1 + height / 2.0

    return YoloBox(slot_class_id(slot), x_center, y_center, width, height)


def load_source(source: ModelSource) -> PreparedSource:
    reference_path = find_file_case_insensitive(REFERENCE_DIR, source.reference_name)
    planogram_path = PLANOGRAM_DIR / source.planogram_name
    image = read_reference(reference_path)
    planogram = read_planogram(planogram_path)
    boxes = [box for slot in planogram.get("slots", []) if (box := slot_to_yolo_box(slot))]

    if not boxes:
        raise ValueError(f"No valid boxes found in {planogram_path}")

    return PreparedSource(source, image, boxes)


def yolo_to_pixel_corners(box: YoloBox, width: int, height: int) -> np.ndarray:
    box_w = box.width * width
    box_h = box.height * height
    center_x = box.x_center * width
    center_y = box.y_center * height
    x1 = center_x - box_w / 2.0
    y1 = center_y - box_h / 2.0
    x2 = center_x + box_w / 2.0
    y2 = center_y + box_h / 2.0

    return np.array(
        [[[x1, y1]], [[x2, y1]], [[x2, y2]], [[x1, y2]]],
        dtype=np.float32,
    )


def transform_box(box: YoloBox, matrix: np.ndarray, width: int, height: int) -> YoloBox | None:
    corners = yolo_to_pixel_corners(box, width, height)
    transformed = cv2.perspectiveTransform(corners, matrix).reshape(-1, 2)

    x1 = float(np.clip(np.min(transformed[:, 0]), 0, width - 1))
    y1 = float(np.clip(np.min(transformed[:, 1]), 0, height - 1))
    x2 = float(np.clip(np.max(transformed[:, 0]), 0, width - 1))
    y2 = float(np.clip(np.max(transformed[:, 1]), 0, height - 1))

    box_w = x2 - x1
    box_h = y2 - y1
    if box_w < MIN_BOX_SIZE_PX or box_h < MIN_BOX_SIZE_PX:
        return None

    return YoloBox(
        class_id=box.class_id,
        x_center=clamp((x1 + box_w / 2.0) / width),
        y_center=clamp((y1 + box_h / 2.0) / height),
        width=clamp(box_w / width),
        height=clamp(box_h / height),
    )


def build_geometric_transform(rng: np.random.Generator, width: int, height: int) -> np.ndarray:
    angle = float(rng.uniform(-4.0, 4.0))
    scale = float(rng.uniform(0.97, 1.03))
    shift_x = float(rng.uniform(-0.018, 0.018) * width)
    shift_y = float(rng.uniform(-0.018, 0.018) * height)

    affine = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, scale)
    affine[0, 2] += shift_x
    affine[1, 2] += shift_y
    affine_3x3 = np.vstack([affine, [0.0, 0.0, 1.0]]).astype(np.float32)

    max_x = width * 0.025
    max_y = height * 0.025
    src = np.float32(
        [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]
    )
    jitter = np.float32(
        [
            [rng.uniform(0, max_x), rng.uniform(0, max_y)],
            [rng.uniform(-max_x, 0), rng.uniform(0, max_y)],
            [rng.uniform(-max_x, 0), rng.uniform(-max_y, 0)],
            [rng.uniform(0, max_x), rng.uniform(-max_y, 0)],
        ]
    )
    perspective = cv2.getPerspectiveTransform(src, src + jitter)

    return perspective @ affine_3x3


def apply_photometric_augmentations(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    alpha = float(rng.uniform(0.82, 1.20))
    beta = float(rng.uniform(-20, 20))
    augmented = cv2.convertScaleAbs(image, alpha=alpha, beta=beta)

    if rng.random() < 0.45:
        kernel_size = int(rng.choice([3, 5]))
        augmented = cv2.GaussianBlur(augmented, (kernel_size, kernel_size), 0)

    return augmented


def augment_sample(
    image: np.ndarray,
    boxes: Iterable[YoloBox],
    rng: np.random.Generator,
) -> tuple[np.ndarray, list[YoloBox]]:
    height, width = image.shape[:2]
    matrix = build_geometric_transform(rng, width, height)
    warped = cv2.warpPerspective(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_REFLECT_101,
    )
    augmented_boxes = [
        transformed
        for box in boxes
        if (transformed := transform_box(box, matrix, width, height)) is not None
    ]

    return apply_photometric_augmentations(warped, rng), augmented_boxes


def write_label_file(path: Path, boxes: Iterable[YoloBox]) -> None:
    path.write_text("\n".join(box.line() for box in boxes) + "\n", encoding="utf-8")


def ensure_dataset_dirs(dataset_dir: Path) -> dict[str, Path]:
    paths = {
        "train_images": dataset_dir / "images" / "train",
        "val_images": dataset_dir / "images" / "val",
        "train_labels": dataset_dir / "labels" / "train",
        "val_labels": dataset_dir / "labels" / "val",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def clean_generated_files(paths: dict[str, Path]) -> None:
    for path in paths.values():
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True, exist_ok=True)


def write_data_yaml(dataset_dir: Path) -> None:
    yaml_text = (
        "path: .\n"
        "train: images/train\n"
        "val: images/val\n"
        "nc: 2\n"
        "names: [\"product\", \"promo\"]\n"
    )
    (dataset_dir / "data.yaml").write_text(yaml_text, encoding="utf-8")


def generate_split(
    prepared_sources: list[PreparedSource],
    split: str,
    count: int,
    image_dir: Path,
    label_dir: Path,
    rng: np.random.Generator,
) -> int:
    written = 0
    attempts = 0
    max_attempts = count * 8

    while written < count and attempts < max_attempts:
        source = prepared_sources[written % len(prepared_sources)]
        attempts += 1
        image, boxes = augment_sample(source.image, source.boxes, rng)
        if not boxes:
            continue

        stem = f"{source.source.model_id.lower()}_{split}_{written:04d}"
        image_path = image_dir / f"{stem}.jpg"
        label_path = label_dir / f"{stem}.txt"

        cv2.imwrite(str(image_path), image, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        write_label_file(label_path, boxes)
        written += 1

    if written < count:
        raise RuntimeError(f"Generated only {written}/{count} images for {split}")

    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate YOLO shelf audit data from reference images and planograms."
    )
    parser.add_argument("--train-count", type=int, default=300)
    parser.add_argument("--val-count", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260627)
    parser.add_argument("--dataset-dir", type=Path, default=DATASET_DIR)
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove existing generated images and labels before writing new samples.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.train_count < 1 or args.val_count < 1:
        raise ValueError("train-count and val-count must both be positive")

    prepared_sources = [load_source(source) for source in SOURCES]
    paths = ensure_dataset_dirs(args.dataset_dir)
    if args.clean:
        clean_generated_files(paths)

    rng = np.random.default_rng(args.seed)
    train_written = generate_split(
        prepared_sources,
        "train",
        args.train_count,
        paths["train_images"],
        paths["train_labels"],
        rng,
    )
    val_written = generate_split(
        prepared_sources,
        "val",
        args.val_count,
        paths["val_images"],
        paths["val_labels"],
        rng,
    )
    write_data_yaml(args.dataset_dir)

    print(f"Generated {train_written} train images and {val_written} val images")
    print(f"Dataset: {args.dataset_dir}")
    print(f"Classes: {CLASS_NAMES}")


if __name__ == "__main__":
    main()
