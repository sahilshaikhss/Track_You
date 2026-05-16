import os
import numpy as np
from tensorflow.keras import layers, models, applications
from tensorflow.keras.preprocessing import image
from tensorflow.keras.applications.efficientnet import preprocess_input
from sklearn.neighbors import NearestNeighbors
from PIL import ImageFile, Image

ImageFile.LOAD_TRUNCATED_IMAGES = True

class EffNetCBIR:
    def __init__(self, input_shape=(224,224,3), dataset_folder=None, weights='imagenet'):
        self.input_shape = input_shape
        self.dataset_folder = dataset_folder
        # Ensure input has 3 channels for pretrained weights
        if self.input_shape[2] != 3 and weights == 'imagenet':
            print("⚠ Input shape must have 3 channels for ImageNet weights. Overriding to 3 channels.")
            self.input_shape = (self.input_shape[0], self.input_shape[1], 3)

        self.feature_extractor = self._build_feature_extractor(weights=weights)
        self.knn = NearestNeighbors(n_neighbors=5, metric='cosine')
        self.image_paths = np.array([])
        self.features = np.array([])

    def _build_feature_extractor(self, weights='imagenet'):
        """
        Build EfficientNetB0 feature extractor with proper RGB input.
        """
        base_model = applications.EfficientNetB0(
            include_top=False,
            weights=None,  # 'imagenet' or None
            input_shape=self.input_shape,
            pooling='avg'
        )
        base_model.trainable = False

        inputs = layers.Input(shape=self.input_shape)
        x = base_model(inputs, training=False)
        x = layers.Dense(512, activation='relu')(x)
        x = layers.BatchNormalization()(x)
        x = layers.Dropout(0.3)(x)
        features = layers.Dense(256, activation='relu', name='feature_vector')(x)

        return models.Model(inputs=inputs, outputs=features)

    def preprocess_image(self, img_path):
        # Always convert image to RGB to match model input
        img = Image.open(img_path).convert("RGB")
        img = img.resize(self.input_shape[:2])
        arr = image.img_to_array(img)
        arr = preprocess_input(arr)
        return np.expand_dims(arr, axis=0)

    def extract_features(self, img_path):
        try:
            arr = self.preprocess_image(img_path)
            feats = self.feature_extractor.predict(arr, verbose=0)
            return feats.flatten()
        except Exception as e:
            print(f"❌ Failed to extract features from {img_path}: {e}")
            return None

    def build_image_database(self, image_folder=None):
        if image_folder is None:
            image_folder = self.dataset_folder
        if image_folder is None:
            raise ValueError("No image folder provided.")

        valid_ext = ('.jpg','.jpeg','.png','.bmp','.tiff')
        paths, feats = [], []

        for root, _, files in os.walk(image_folder):
            for f in files:
                if f.lower().endswith(valid_ext):
                    p = os.path.join(root, f)
                    fv = self.extract_features(p)
                    if fv is not None:
                        paths.append(p)
                        feats.append(fv)

        if len(feats) == 0:
            self.image_paths = np.array([])
            self.features = np.array([])
            raise RuntimeError("No valid images found in database.")

        self.image_paths = np.array(paths)
        self.features = np.vstack(feats)
        self.knn.fit(self.features)
        print(f"✅ CBIR DB built with {len(self.image_paths)} images.")

    def query_image(self, query_img_path, num_results=5):
        if self.features is None or len(self.features) == 0:
            raise RuntimeError("Database empty. Run build_image_database() first.")

        qf = self.extract_features(query_img_path)
        if qf is None:
            raise ValueError("Could not extract features from query image.")

        k = min(num_results, len(self.image_paths))
        distances, indices = self.knn.kneighbors(qf.reshape(1,-1), n_neighbors=k)
        similar = self.image_paths[indices[0]]
        distances = distances[0]
        return similar, distances
