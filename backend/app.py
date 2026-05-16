from flask import Flask, render_template, request
from supabase import create_client, Client as SupabaseClient
from twilio.rest import Client as TwilioClient

import hashlib
import time
import re
import os
from werkzeug.utils import secure_filename

# ================= APP =================
app = Flask(__name__)
app.secret_key = "change_this_secret"

# ================= SUPABASE =================
SUPABASE_URL = "https://kxmkdnrmnckkrzicesrj.supabase.co"
SUPABASE_KEY = "sb_publishable_6BJt0uNBhuTAZK3V04paOQ_fGbfKMaU"

supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= TWILIO =================
TWILIO_SID = "AC5d23e6db2fd9d27a21df02ca77a84498"
TWILIO_AUTH = "ee2fb1328b8559bc365b9cf1ebf70457"
TWILIO_PHONE = "+14784009309"

twilio_client = TwilioClient(TWILIO_SID, TWILIO_AUTH)

# ================= DATASET STORAGE =================
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


# ================= HOME =================
@app.route('/')
def home():
    return render_template("register.html")


@app.route('/register', methods=['POST'])
def register():

    name = request.form.get('guardian_name')
    phone = normalize_phone(request.form.get('guardian_phone'))
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
            popup_message="This phone number is already registered!"
        )

    # ================= UNIQUE CODE (FIXED) =================
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

    # ================= IMAGE STORAGE =================
    files = request.files.getlist("individual_photos")

    person_folder = os.path.join(DATASET_PATH, phone)
    os.makedirs(person_folder, exist_ok=True)

    # clear old local images
    for f in os.listdir(person_folder):
        os.remove(os.path.join(person_folder, f))

    # clear old DB images
    supabase.table("person_images") \
        .delete() \
        .eq("guardian_phone", phone) \
        .execute()

    count = 1

    if files and files[0].filename != "":

        for f in files:

            if not f or f.filename == "":
                continue

            filepath = os.path.join(person_folder, f"{count}.jpg")

            # save locally
            f.save(filepath)

            # save in supabase
            supabase.table("person_images").insert({
                "guardian_phone": phone,
                "image_path": filepath,
                "embedding": None
            }).execute()

            count += 1

    return render_template(
        "success.html",
        guardian_name=name,
        registration_id=unique_code
    )
# ================= DELETE =================
@app.route('/delete', methods=['GET', 'POST'])
def delete():
    if request.method == 'POST':

        phone = request.form.get('guardian_phone')

        if not phone:
            return render_template("delete.html", message="Phone is required")

        phone = normalize_phone(phone)

        try:
            result = supabase.table("registered_persons") \
                .delete() \
                .eq("guardian_phone", phone) \
                .execute()

            # delete dataset folder also
            folder = os.path.join(DATASET_PATH, phone)
            if os.path.exists(folder):
                for file in os.listdir(folder):
                    os.remove(os.path.join(folder, file))
                os.rmdir(folder)

            if result.data:
                return render_template("delete.html", message="Record deleted successfully")
            else:
                return render_template("delete.html", message="No record found")

        except Exception as e:
            return render_template("delete.html", message=f"Error: {str(e)}")

    return render_template("delete.html")


# ================= DIRECT MESSAGE =================
@app.route('/direct_message', methods=['GET', 'POST'])
def direct_message():

    visitor_info = None
    msg_status = None

    if request.method == 'POST':

        phone = request.form.get('guardian_phone')
        message = request.form.get('message')
        action = request.form.get('action')

        phone = normalize_phone(phone)

        if not phone:
            return render_template("direct_message.html", msg_status="Invalid phone number")

        # ================= SEARCH =================
        if action == "search":

            try:
                result = supabase.table("registered_persons") \
                    .select("*") \
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

            except Exception as e:
                msg_status = f"Search error: {str(e)}"

        # ================= SEND SMS =================
        elif action == "send":

            if not message:
                return render_template("direct_message.html", msg_status="Message cannot be empty")

            try:
                to_number = format_e164(phone)

                twilio_client.messages.create(
                    body=message,
                    from_=TWILIO_PHONE,
                    to=to_number
                )

                msg_status = "Message sent successfully ✔"

            except Exception as e:
                msg_status = f"Twilio Error: {str(e)}"

    return render_template(
        "direct_message.html",
        visitor_info=visitor_info,
        msg_status=msg_status
    )


# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)
    