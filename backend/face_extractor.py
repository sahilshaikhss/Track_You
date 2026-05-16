# face_extractor.py
import os
import cv2
from mtcnn import MTCNN

def extract_faces(image_path, output_dir):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    image = cv2.imread(image_path)
    if image is None:
        print(f"Error reading image {image_path}")
        return []

    detector = MTCNN()
    faces = detector.detect_faces(image)

    if not faces:
        print(f"No faces detected in {image_path}")
        return []

    saved_paths = []
    for i, face_data in enumerate(faces):
        x, y, w, h = face_data['box']
        face_crop = image[y:y+h, x:x+w]
        output_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(image_path))[0]}_face_{i+1}.jpg")
        cv2.imwrite(output_path, face_crop)
        saved_paths.append(output_path)
        print(f"Saved face to {output_path}")

    return saved_paths
