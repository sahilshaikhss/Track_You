import os
import time
import cv2

from mtcnn import MTCNN


detector = MTCNN()


def crop_face(
    input_path,
    output_path
):

    img = cv2.imread(
        input_path
    )

    if img is None:
        return False


    rgb = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2RGB
    )


    faces = detector.detect_faces(
        rgb
    )


    if len(faces) == 0:

        print(
            "No face found:",
            input_path
        )

        return False


    face = max(
        faces,
        key=lambda f:
        f["box"][2] *
        f["box"][3]
    )


    x, y, w, h = face["box"]


    margin = 30


    x1 = max(
        0,
        x - margin
    )

    y1 = max(
        0,
        y - margin
    )


    x2 = min(
        rgb.shape[1],
        x + w + margin
    )

    y2 = min(
        rgb.shape[0],
        y + h + margin
    )


    crop = rgb[
        y1:y2,
        x1:x2
    ]


    # make sure faces_dataset exists
    os.makedirs(
        os.path.dirname(output_path),
        exist_ok=True
    )


    cv2.imwrite(
        output_path,
        cv2.cvtColor(
            crop,
            cv2.COLOR_RGB2BGR
        )
    )


    return True



def start_watcher(
    dataset_path,
    faces_path,
    model_callback=None
):

    print(
        "👀 Face crop watcher started"
    )


    while True:

        try:

            files = os.listdir(
                dataset_path
            )


            for file in files:


                # supported images
                if not file.lower().endswith(
                    (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".bmp"
                    )
                ):
                    continue



                input_path = os.path.join(
                    dataset_path,
                    file
                )


                output_path = os.path.join(
                    faces_path,
                    file
                )



                # already cropped
                if os.path.exists(output_path):
                    continue



                success = crop_face(
                    input_path,
                    output_path
                )


                if success:

                    print(
                    "✅ Cropped and saved:",
                       file
                        )


                  # Add new face into EfficientNet model

                    if model_callback:

                        model_callback(
                        output_path
                         )
 

            # check every 5 seconds
            time.sleep(5)



        except Exception as e:

            print(
                "Watcher error:",
                e
            )

            time.sleep(5)