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

from model.face_facenet_cbir import FaceNetCBIR

# ================= APP =================
app = Flask(__name__)
app.secret_key = "change_this_secret"

# ================= SUPABASE =================
SUPABASE_URL = "https://kxmkdnrmnckkrzicesrj.supabase.co"

# USE SERVICE ROLE KEY HERE
SUPABASE_KEY = "sb_publishable_6BJt0uNBhuTAZK3V04paOQ_fGbfKMaU"

supabase: SupabaseClient = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)

# ================= TWILIO =================
#TWILIO_SID = "AC5d23e6db2fd9d27a21df02ca77a84498#"
#TWILIO_AUTH = "ee2fb1328b8559bc365b9cf1ebf70457#"

TWILIO_PHONE = "+14784009309"

twilio_client = TwilioClient(
    TWILIO_SID,
    TWILIO_AUTH
)

# ================= FACENET =================
cbir_model = FaceNetCBIR()

# ================= DATASET =================
DATASET_PATH = "dataset"

os.makedirs(DATASET_PATH, exist_ok=True)

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
            DATASET_PATH,
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
    sync_faces_dataset()

    cbir_model.build_image_database(
        DATASET_PATH
    )

    return render_template(
        "success.html",
        guardian_name=name,
        registration_id=unique_code
    )


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


# ================= PROCESS QUERY =================
@app.route('/process_query', methods=['POST'])
def process_query():

    try:

        query_file = request.files.get(
            "query_image"
        )

        if not query_file:

            return render_template(
                "query_results.html",
                error="No image uploaded"
            )

        # ================= SAVE QUERY IMAGE =================
        file_ext = query_file.filename \
            .rsplit(".", 1)[-1] \
            .lower()

        filename = f"{int(time.time())}.{file_ext}"

        query_bytes = query_file.read()

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

        # ================= TEMP QUERY =================
        temp_query = tempfile.NamedTemporaryFile(
            delete=False,
            suffix=".jpg"
        )

        temp_query.write(query_bytes)

        temp_query.close()

        # ================= SEARCH =================
        similar_paths, distances = (
            cbir_model.query_image(
                temp_query.name
            )
        )

        matches = []

        for path, dist in zip(
            similar_paths,
            distances
        ):

            filename = os.path.basename(path)

            guardian_phone = filename.split("_")[0]

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

            image_name = filename.split(
                "_",
                1
            )[1]

            image_url = supabase.storage \
                .from_("faces") \
                .get_public_url(
                    f"{guardian_phone}/{image_name}"
                )

            matches.append({

                "visitor": visitor,

                "score": f"{(1 - dist) * 100:.2f}%",

                "url": image_url,

                "query_id": query_id,

                "guardian_phone": guardian_phone
            })

        os.unlink(temp_query.name)

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

    query_image_url = query_data \
        .data[0]["image_path"]

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

    return render_template(

        "alert_sent.html",

        success=success,

        error=error,

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


# ================= RUN =================
if __name__ == "__main__":

    sync_faces_dataset()

    try:

        cbir_model.build_image_database(
            DATASET_PATH
        )

        print("Face database loaded")

    except Exception as e:

        print("Database build skipped:", e)

    app.run(debug=True)