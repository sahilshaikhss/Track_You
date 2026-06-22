from flask import Flask, render_template, request
from supabase import create_client, Client as SupabaseClient
from twilio.rest import Client as TwilioClient

import hashlib
import time
import re
import os
import requests
import tempfile
import base64
from watcher import start_watcher
from model.face_effnet_cbir import EffNetCBIR
from mtcnn import MTCNN
import cv2


import threading
import time

import model.face_effnet_cbir

print(
    "MODEL FILE:",
    model.face_effnet_cbir.__file__
)

print(
    "HAS ADD METHOD:",
    hasattr(EffNetCBIR, "add_new_image")
)
detector = MTCNN()
# ================= APP =================
app = Flask(__name__)
app.secret_key = "change_this_secret"

# ================= SUPABASE =================
#@@@SUPABASE_URL = "https://kxmkdnrmnckkrzicesrj.supabase.co"

# USE SERVICE ROLE KEY HERE
#@@@@@SUPABASE_KEY = "sb_publishable_6BJt0uNBhuTAZK3V04paOQ_fGbfKMaU"

supabase: SupabaseClient = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ================= TWILIO =================
#SSSSTWILIO_SID = "AC5d23e6db2fd9d27a21df02ca77a84498###"
#@DDDTWILIO_AUTH = "64570b5062c46ec8f8beb73cd9a9c7de###"

TWILIO_PHONE = "+14784009309"

twilio_client = TwilioClient(
    TWILIO_SID,
    TWILIO_AUTH
)

# ================= EFFNETCBIR =================
cbir_model = EffNetCBIR()

# ================= DATASET =================
ORIGINAL_DATASET_PATH = "dataset"
FACES_DATASET_PATH = "faces_dataset"

os.makedirs(ORIGINAL_DATASET_PATH, exist_ok=True)
os.makedirs(FACES_DATASET_PATH, exist_ok=True)
# ================= UTIL =================
def normalize_phone(phone):

    if not phone:
        return None

    phone = re.sub(r"\D", "", phone)

    return phone[-10:]


def format_e164(phone):

    return "+91" + phone


# ================= SYNC DATASET =================
def sync_faces_dataset():

    print("Syncing dataset...")

    images = supabase.table("person_images") \
        .select("*") \
        .execute()

    if not images.data:
        return

    for img in images.data:

        img_url = img["image_path"]

        phone = img["guardian_phone"]

        filename = img_url.split("/")[-1]

        local_filename = f"{phone}_{filename}"

        local_path = os.path.join(
        ORIGINAL_DATASET_PATH,
          local_filename
                )

        # skip existing
        if os.path.exists(local_path):
            continue

        try:

            response = requests.get(
                img_url,
                timeout=10
            )

            if response.status_code == 200:

                with open(local_path, "wb") as f:
                    f.write(response.content)

                print(f"Downloaded: {local_filename}")

        except Exception as e:

            print("Download failed:", e)


# ================= HOME =================
@app.route('/')
def home():

    return render_template("register.html")


# ================= REGISTER =================
@app.route('/register', methods=['POST'])
def register():

    name = request.form.get('guardian_name')

    phone = normalize_phone(
        request.form.get('guardian_phone')
    )

    address = request.form.get('address')

    members = request.form.get('members')

    if not name or not phone:

        return "Missing data", 400

    # ================= CHECK DUPLICATE =================
    existing = supabase.table("registered_persons") \
        .select("*") \
        .eq("guardian_phone", phone) \
        .execute()

    if existing.data:

        return render_template(
            "register.html",
            popup_message="Phone already registered"
        )

    # ================= UNIQUE CODE =================
    unique_code = hashlib.sha1(
        f"{name}{phone}{time.time()}".encode()
    ).hexdigest()[:10]

    # ================= INSERT USER =================
    supabase.table("registered_persons").insert({

        "guardian_name": name,
        "guardian_phone": phone,
        "address": address,
        "members": members,
        "unique_code": unique_code

    }).execute()

    # ================= DELETE OLD IMAGES =================
    supabase.table("person_images") \
        .delete() \
        .eq("guardian_phone", phone) \
        .execute()

    # ================= IMAGE UPLOAD =================
    files = request.files.getlist(
        "individual_photos"
    )

    count = 1

    if files:

        for f in files:

            if f and f.filename != "":

                file_ext = f.filename \
                    .rsplit(".", 1)[-1] \
                    .lower()

                file_path = f"{phone}/{count}.{file_ext}"

                file_bytes = f.read()
                local_path = os.path.join(
                ORIGINAL_DATASET_PATH,
                f"{phone}_{count}.{file_ext}"
                )

                with open(local_path, "wb") as img_file:
                  img_file.write(file_bytes)

                # upload to supabase
                supabase.storage \
                    .from_("faces") \
                    .upload(

                        file_path,

                        file_bytes,

                        file_options={
                            "content-type": f.mimetype,
                            "upsert": "true"
                        }
                    )

                # public url
                public_url = supabase.storage \
                    .from_("faces") \
                    .get_public_url(file_path)

                # save DB
                supabase.table("person_images").insert({

                    "guardian_phone": phone,
                    "image_path": public_url,
                    "embedding": None

                }).execute()

                count += 1

    # ================= AUTO SYNC =================
    #sync_faces_dataset()

   ## cbir_model.build_image_database(
    #    DATASET_PATH
   # )

    return render_template(
        "success.html",
        guardian_name=name,
        registration_id=unique_code
    )


def crop_query_face(query_path):

    os.makedirs("query_faces", exist_ok=True)

    img = cv2.imread(query_path)

    if img is None:
        return query_path

    rgb = cv2.cvtColor(
        img,
        cv2.COLOR_BGR2RGB
    )

    faces = detector.detect_faces(rgb)

    if len(faces) == 0:
        return query_path

    face = max(
        faces,
        key=lambda f: f["box"][2] * f["box"][3]
    )

    x, y, w, h = face["box"]

    x = max(0, x)
    y = max(0, y)

    margin = 30

    x1 = max(0, x - margin)
    y1 = max(0, y - margin)

    x2 = min(rgb.shape[1], x + w + margin)
    y2 = min(rgb.shape[0], y + h + margin)

    face_crop = rgb[y1:y2, x1:x2]

    crop_path = os.path.join(
        "query_faces",
        os.path.basename(query_path)
    )

    cv2.imwrite(
        crop_path,
        cv2.cvtColor(
            face_crop,
            cv2.COLOR_RGB2BGR
        )
    )

    return crop_path


# ================= DELETE =================
@app.route('/delete', methods=['GET', 'POST'])
def delete():

    if request.method == 'POST':

        phone = request.form.get(
            'guardian_phone'
        )

        if not phone:

            return render_template(
                "delete.html",
                message="Phone required"
            )

        phone = normalize_phone(phone)

        try:

            result = supabase.table(
                "registered_persons"
            ).delete() \
             .eq("guardian_phone", phone) \
             .execute()

            # remove local images
            for file in os.listdir(DATASET_PATH):

                if file.startswith(phone + "_"):

                    os.remove(
                        os.path.join(
                            DATASET_PATH,
                            file
                        )
                    )

            # rebuild DB
            cbir_model.build_image_database(
                DATASET_PATH
            )

            if result.data:

                return render_template(
                    "delete.html",
                    message="Deleted successfully"
                )

            else:

                return render_template(
                    "delete.html",
                    message="No record found"
                )

        except Exception as e:

            return render_template(
                "delete.html",
                message=str(e)
            )

    return render_template("delete.html")


# ================= DIRECT MESSAGE =================
@app.route('/direct_message', methods=['GET', 'POST'])
def direct_message():

    visitor_info = None

    msg_status = None

    if request.method == 'POST':

        phone = request.form.get(
            'guardian_phone'
        )

        message = request.form.get(
            'message'
        )

        action = request.form.get(
            'action'
        )

        phone = normalize_phone(phone)

        if action == "search":

            result = supabase.table(
                "registered_persons"
            ).select("*") \
             .eq("guardian_phone", phone) \
             .execute()

            if result.data:

                v = result.data[0]

                visitor_info = {

                    "name": v.get("guardian_name"),
                    "phone": v.get("guardian_phone"),
                    "address": v.get("address"),
                    "members": v.get("members")
                }

            else:

                msg_status = "No record found"

        elif action == "send":

            try:

                twilio_client.messages.create(

                    body=message,

                    from_=TWILIO_PHONE,

                    to=format_e164(phone)

                )

                msg_status = "Message sent"

            except Exception as e:

                msg_status = str(e)

    return render_template(
        "direct_message.html",
        visitor_info=visitor_info,
        msg_status=msg_status
    )


# ================= QUERY PAGE =================
@app.route('/query_upload')
def query_upload():

    return render_template(
        "query_upload.html"
    )


@app.route('/process_query', methods=['POST'])
def process_query():

    try:

        query_file = request.files.get("query_image")

        if not query_file:

            return render_template(
                "query_results.html",
                error="No image uploaded"
            )

        file_ext = query_file.filename.rsplit(".", 1)[-1].lower()

        filename = f"{int(time.time())}.{file_ext}"

        query_bytes = query_file.read()

        # ================= SAVE ORIGINAL QUERY LOCALLY =================
        os.makedirs("query_original", exist_ok=True)

        local_query_path = os.path.join(
            "query_original",
            filename
        )

        with open(local_query_path, "wb") as f:
            f.write(query_bytes)

        # ================= CROP QUERY FACE =================
        cropped_query = crop_query_face(
        local_query_path
                    )

# ================= SEARCH USING CROPPED FACE =================
        similar_paths, scores = cbir_model.query_image(
        cropped_query
        )

        # ================= SAVE QUERY TO SUPABASE =================
        supabase.storage \
            .from_("query-images") \
            .upload(
                filename,
                query_bytes,
                file_options={
                    "content-type": query_file.mimetype,
                    "upsert": "true"
                }
            )

        query_public_url = supabase.storage \
            .from_("query-images") \
            .get_public_url(filename)

        query_insert = supabase.table(
            "query_images"
        ).insert({
            "image_path": query_public_url
        }).execute()

        query_id = query_insert.data[0]["id"]

        # ================= BUILD RESULTS =================
        matches = []

        for path, score in zip(
            similar_paths,
            scores
        ):

            filename_db = os.path.basename(path)

            guardian_phone = filename_db.split("_")[0]

            visitor = supabase.table(
                "registered_persons"
            ).select("*") \
             .eq(
                "guardian_phone",
                guardian_phone
             ) \
             .execute()

            if not visitor.data:
                continue

            visitor = visitor.data[0]

            image_name = filename_db.split(
                "_",
                1
            )[1]

            # ORIGINAL IMAGE URL
            image_url = supabase.storage \
                .from_("faces") \
                .get_public_url(
                    f"{guardian_phone}/{image_name}"
                )

            matches.append({

                "visitor": visitor,

                "score": f"{score:.2f}%",

                "url": image_url,

                "query_id": query_id,

                "guardian_phone": guardian_phone
            })

        return render_template(
            "query_results.html",
            matches=matches,
            query_image_url=query_public_url
        )

    except Exception as e:

        return render_template(
            "query_results.html",
            error=str(e)
        )
# ================= SEND ALERT =================
@app.route('/send_alert')
def send_alert():

    image_url = request.args.get(
        "image_url"
    )

    query_id = request.args.get(
        "query_id"
    )

    guardian_phone = request.args.get(
        "guardian_phone"
    )

    score = request.args.get(
        "score"
    )

    query_data = supabase.table(
        "query_images"
    ).select("*") \
     .eq("id", query_id) \
     .execute()

    if not query_data.data:

        return "Invalid query"

    query_image_url = query_data.data[0]["image_path"]

    process = supabase.table(
        "query_process"
    ).insert({

        "guardian_phone": guardian_phone,

        "matched_image_url": image_url,

        "query_image_url": query_image_url,

        "query_image_id": query_id,

        "similarity_score": score,

        "status": "Still Processing"

    }).execute()

    process_id = process.data[0]["id"]

    found_link = (
        f"http://127.0.0.1:5000/"
        f"reunification/{process_id}/found"
    )

    not_found_link = (
        f"http://127.0.0.1:5000/"
        f"reunification/{process_id}/not_found"
    )

    success = None
    error = None

    try:

        twilio_client.messages.create(

            body=(
                f"Possible Match Found\n\n"
                f"FOUND:\n{found_link}\n\n"
                f"NOT FOUND:\n{not_found_link}"
            ),

            from_=TWILIO_PHONE,

            to=format_e164(guardian_phone)
        )

        success = "Alert sent"

    except Exception as e:

        error = str(e)

    # ================= GET GUARDIAN INFO =================
    guardian = supabase.table(
        "registered_persons"
    ).select("*") \
     .eq("guardian_phone", guardian_phone) \
     .execute()

    print("PHONE:", guardian_phone)
    print("GUARDIAN DATA:", guardian.data)

    guardian_name = "Not available"

    if guardian.data:

        guardian_name = guardian.data[0].get(
            "guardian_name",
            "Not available"
        )

    return render_template(

        "alert_sent.html",

        success=success,

        error=error,

        guardian_name=guardian_name,

        guardian_phone=guardian_phone,

        found_link=found_link,

        not_found_link=not_found_link
    )
# ================= REUNIFICATION =================
@app.route('/reunification/<int:process_id>/<status>')
def reunification_update(
    process_id,
    status
):

    if status == "found":

        new_status = (
            "Reunification Done"
        )

    else:

        new_status = (
            "Person Not Found"
        )

    supabase.table(
        "query_process"
    ).update({

        "status": new_status

    }).eq(
        "id",
        process_id
    ).execute()

    return render_template(
        "reunification_response.html",
        status=new_status
    )


# ================= LIVE PROCESSING =================
@app.route('/processing')
def processing():

    result = supabase.table(
        "query_process"
    ).select("*") \
     .order(
        "created_at",
        desc=True
     ) \
     .execute()

    return render_template(
        "processing.html",
        processes=result.data
    )


def auto_crop_faces():

    detector = MTCNN()

    valid_ext = (
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp"
    )

    print("👀 Face crop watcher started")


    while True:

        try:

            for filename in os.listdir(
                ORIGINAL_DATASET_PATH
            ):

                if not filename.lower().endswith(valid_ext):
                    continue


                input_path = os.path.join(
                    ORIGINAL_DATASET_PATH,
                    filename
                )


                output_path = os.path.join(
                    FACES_DATASET_PATH,
                    filename
                )


                # already cropped
                if os.path.exists(output_path):
                    continue



                img = cv2.imread(
                    input_path
                )


                if img is None:
                    continue



                rgb = cv2.cvtColor(
                    img,
                    cv2.COLOR_BGR2RGB
                )


                faces = detector.detect_faces(
                    rgb
                )


                if len(faces) == 0:

                    print(
                        "No face:",
                        filename
                    )

                    continue



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
                    x-margin
                )

                y1 = max(
                    0,
                    y-margin
                )


                x2 = min(
                    rgb.shape[1],
                    x+w+margin
                )


                y2 = min(
                    rgb.shape[0],
                    y+h+margin
                )


                crop = rgb[
                    y1:y2,
                    x1:x2
                ]


                cv2.imwrite(
                    output_path,
                    cv2.cvtColor(
                        crop,
                        cv2.COLOR_RGB2BGR
                    )
                )


                print(
                    "✅ Cropped:",
                    filename
                )


            # scan every 5 seconds
            time.sleep(5)


        except Exception as e:

            print(
                "Crop watcher error:",
                e
            )

            time.sleep(5)
def auto_sync():

    # wait after app start
    time.sleep(30)


    while True:

        try:

            print("🔄 Syncing dataset...")

            sync_faces_dataset()

            print("✅ Dataset synced")


        except Exception as e:

            print(
                f"❌ Sync failed: {e}"
            )


        time.sleep(60)


def update_model_with_new_face(face_path):

    try:

        print(
            "🧠 Updating model with:",
            face_path
        )


        cbir_model.add_new_image(
            face_path
        )


        print(
            "✅ New face added to search database"
        )


    except Exception as e:

        print(
            "❌ Incremental update failed:",
            e
        )
# ================= RUN =================

if __name__ == "__main__":

    print("\n==============================")
    print("🚀 Starting Lost Person System")
    print("==============================\n")


    # Build model once from existing faces_dataset

    try:

        print(
            "🧠 Loading face database..."
        )

        cbir_model.build_image_database(
            FACES_DATASET_PATH
        )

        print(
            "✅ Face database loaded"
        )


    except Exception as e:

        print(
            "❌ Model loading error:",
            e
        )



    # Supabase sync watcher

    threading.Thread(
        target=auto_sync,
        daemon=True
    ).start()



    # New image crop watcher

    threading.Thread(
        target=start_watcher,
        args=(
            ORIGINAL_DATASET_PATH,
            FACES_DATASET_PATH,
            update_model_with_new_face
        ),
        daemon=True
    ).start()



    print(
        "🔄 Supabase sync watcher running"
    )

    print(
        "🙂 MTCNN crop watcher running"
    )


    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True,
        use_reloader=False
    )