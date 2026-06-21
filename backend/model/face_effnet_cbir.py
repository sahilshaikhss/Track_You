import os
import numpy as np
import tensorflow as tf
from mtcnn import MTCNN
from tensorflow.keras import layers, models, applications
from tensorflow.keras.preprocessing import image
from tensorflow.keras.applications.efficientnet import preprocess_input

from sklearn.neighbors import NearestNeighbors

from PIL import ImageFile, Image

ImageFile.LOAD_TRUNCATED_IMAGES = True


class EffNetCBIR:

    def __init__(
        self,
       input_shape=(300,300,3),
        dataset_folder="faces_dataset"
    ):

        self.input_shape = input_shape
        self.dataset_folder = dataset_folder
        
        self.detector = MTCNN()
        self.feature_extractor = self._build_feature_extractor()

        self.knn = NearestNeighbors(
            n_neighbors=5,
            metric="cosine",
            algorithm="brute"
        )

        self.image_paths = np.array([])
        self.features = np.array([])

    def _build_feature_extractor(self):

        base_model = applications.EfficientNetB3(
            include_top=False,
            weights="imagenet",
            input_shape=self.input_shape,
            pooling="avg"
        )

        base_model.trainable = False

        inputs = layers.Input(shape=self.input_shape)

        features = base_model(
            inputs,
            training=False
        )

        features = layers.Lambda(
            lambda x: tf.math.l2_normalize(
                x,
                axis=1
            ),
            name="feature_vector"
        )(features)

        return models.Model(
            inputs=inputs,
            outputs=features
        )

    def preprocess_image(self, img_path):

        img = Image.open(img_path).convert("RGB")

        img = img.resize(
           (
            self.input_shape[1],
            self.input_shape[0]
           ),
           Image.Resampling.LANCZOS
        )

        arr = image.img_to_array(img)

        arr = preprocess_input(arr)

        return np.expand_dims(
        arr,
        axis=0
      )

    def extract_features(self, img_path):

        try:

            arr = self.preprocess_image(
                img_path
            )

            features = self.feature_extractor.predict(
                arr,
                verbose=0
            )

            return features.flatten()

        except Exception as e:

            print(
                f"❌ Failed on {img_path}: {e}"
            )

            return None

    def build_image_database(
        self,
        image_folder=None
    ):

        if image_folder is None:
            image_folder = self.dataset_folder

        print(
            f"📁 Using dataset folder: {image_folder}"
        )

        valid_ext = (
            ".jpg",
            ".jpeg",
            ".png",
            ".bmp",
            ".tiff"
        )

        paths = []
        feats = []

        print("🔄 Building image database...")

        for root, _, files in os.walk(
            image_folder
        ):

            for file in files:

                if file.lower().endswith(
                    valid_ext
                ):

                    path = os.path.join(
                        root,
                        file
                    )

                    feature_vector = self.extract_features(
                        path
                    )

                    if feature_vector is not None:

                        paths.append(path)
                        feats.append(
                            feature_vector
                        )

        if len(feats) == 0:

            raise RuntimeError(
                "No valid images found."
            )

        self.image_paths = np.array(
            paths
        )

        self.features = np.vstack(
            feats
        )

        print(
            f"Feature matrix shape: {self.features.shape}"
        )

        self.knn.fit(
            self.features
        )

        print(
            f"✅ Database built with {len(self.image_paths)} images."
        )

    def query_image(
        self,
        query_img_path,
        num_results=5
    ):

        if len(self.features) == 0:

            raise RuntimeError(
                "Database empty."
            )

        query_features = self.extract_features(
            query_img_path
        )

        if query_features is None:

            raise ValueError(
                "Query image failed."
            )

        k = min(
            num_results,
            len(self.image_paths)
        )

        distances, indices = self.knn.kneighbors(
            query_features.reshape(
                1,
                -1
            ),
            n_neighbors=k
        )

        similar_images = self.image_paths[
            indices[0]
        ]

        similarity_scores = np.round(
    100 / (1 + np.abs(distances[0])),
    2
)

        return (
            similar_images,
            similarity_scores
        )