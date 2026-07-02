import json
import os
import cv2

MODEL = "a"

json_path = f"backend/planograms/model_{MODEL}.json"

possible_images = [
    f"backend/reference/model_{MODEL}.jpg",
    f"backend/reference/model_{MODEL}.png",
    f"backend/reference/model_{MODEL}.jpeg",
]

image_path = next((p for p in possible_images if os.path.exists(p)), None)

if image_path is None:
    raise FileNotFoundError(f"Reference image not found for model_{MODEL}")

img = cv2.imread(image_path)

if img is None:
    raise RuntimeError(f"Cannot read image: {image_path}")

with open(json_path, "r", encoding="utf-8-sig") as f:
    data = json.load(f)

h, w = img.shape[:2]

for slot in data["slots"]:
    x1 = int(slot["x"] * w)
    y1 = int(slot["y"] * h)
    x2 = int((slot["x"] + slot["w"]) * w)
    y2 = int((slot["y"] + slot["h"]) * h)

    slot_type = slot.get("type", "product")
    slot_id = slot.get("slot_id", "?")

    color = (0, 255, 0) if slot_type == "product" else (0, 165, 255)

    cv2.rectangle(img, (x1, y1), (x2, y2), color, 3)

    label = slot_id
    cv2.rectangle(img, (x1, max(0, y1 - 28)), (x1 + 180, y1), color, -1)
    cv2.putText(
        img,
        label,
        (x1 + 4, max(20, y1 - 7)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 0, 0),
        2,
    )

os.makedirs("backend/debug", exist_ok=True)
out_path = f"backend/debug/model_{MODEL}_slots_debug.jpg"
cv2.imwrite(out_path, img)

print(f"saved: {out_path}")
