
import os
import cv2
import numpy as np
from mtcnn import MTCNN

# Original dataset
INPUT_FOLDER = "dataset"

# Face cropped dataset
OUTPUT_FOLDER = "faces_dataset"

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

detector = MTCNN()

valid_ext = (
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp"
)

count = 0

for filename in os.listdir(INPUT_FOLDER):

    if not filename.lower().endswith(valid_ext):
        continue

    save_path = os.path.join(
    OUTPUT_FOLDER,
    filename
    )

    if os.path.exists(save_path):
      continue 

    img_path = os.path.join(
        INPUT_FOLDER,
        filename
    )

    img = cv2.imread(img_path)

    if img is None:
        continue

    rgb = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2RGB
    )

    faces = detector.detect_faces(rgb)

    if len(faces) == 0:

        print(
            f"No face found: {filename}"
        )

        continue

    # Largest face
    face = max(
        faces,
        key=lambda f: f["box"][2] * f["box"][3]
    )

    x, y, w, h = face["box"]

    x = max(0, x)
    y = max(0, y)

    # Extra margin around face
    margin = 30

    x1 = max(0, x - margin)
    y1 = max(0, y - margin)

    x2 = min(
        rgb.shape[1],
        x + w + margin
    )

    y2 = min(
        rgb.shape[0],
        y + h + margin
    )

    face_crop = rgb[
        y1:y2,
        x1:x2
    ]

    save_path = os.path.join(
        OUTPUT_FOLDER,
        filename
    )

    cv2.imwrite(
        save_path,
        cv2.cvtColor(
            face_crop,
            cv2.COLOR_RGB2BGR
        )
    )

    count += 1

    print(
        f"Saved: {filename}"
    )

print(
    f"\nDone. Cropped {count} images."
)