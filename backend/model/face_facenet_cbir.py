# face_facenet_cbir.py
import os
import numpy as np
from sklearn.neighbors import NearestNeighbors
from keras_facenet import FaceNet
from PIL import Image

class FaceNetCBIR:
    def __init__(self, dataset_folder=None):
        self.dataset_folder = dataset_folder
        self.embedder = FaceNet()
        self.knn = NearestNeighbors(n_neighbors=5, metric='cosine')
        self.image_paths = []
        self.features = None

    def preprocess_image(self, img_path):
        img = Image.open(img_path).convert("RGB")
        return np.array(img)

    # ✅ MAIN FUNCTION (STANDARDIZED NAME)
    def extract_embedding(self, img_path):
        try:
            img_arr = self.preprocess_image(img_path)
            emb = self.embedder.embeddings([img_arr])[0]
            return emb
        except Exception as e:
            print(f"❌ Failed to extract embedding: {e}")
            return None

    # 🔁 Alias (extra safety)
    def extract_features(self, img_path):
        return self.extract_embedding(img_path)

    def build_image_database(self, image_folder=None):
        if image_folder is None:
            image_folder = self.dataset_folder

        if image_folder is None:
            raise ValueError("No image folder provided.")

        valid_ext = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff')
        paths, feats = [], []

        for root, _, files in os.walk(image_folder):
            for f in files:
                if f.lower().endswith(valid_ext):
                    p = os.path.join(root, f)
                    emb = self.extract_embedding(p)
                    if emb is not None:
                        paths.append(p)
                        feats.append(emb)

        if len(feats) == 0:
            self.image_paths = []
            self.features = None
            raise RuntimeError("No valid images found in database.")

        self.image_paths = paths
        self.features = np.vstack(feats)
        self.knn.fit(self.features)

        print(f"✅ CBIR DB built with {len(self.image_paths)} images.")

    def query_image(self, query_img_path, num_results=5):
        if self.features is None or len(self.features) == 0:
            raise RuntimeError("Database empty. Run build_image_database() first.")

        q_emb = self.extract_embedding(query_img_path)

        if q_emb is None:
            raise ValueError("Could not extract features from query image.")

        k = min(num_results, len(self.image_paths))
        distances, indices = self.knn.kneighbors([q_emb], n_neighbors=k)

        similar = [self.image_paths[i] for i in indices[0]]
        distances = distances[0]

        return similar, distances