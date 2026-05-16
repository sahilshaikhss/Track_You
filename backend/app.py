from flask import Flask, render_template, request
from supabase import create_client, Client as SupabaseClient
from twilio.rest import Client as TwilioClient
import hashlib
import time
import base64
import re



app = Flask(__name__)
app.secret_key = "change_this_secret"

SUPABASE_URL = "https://kxmkdnrmnckkrzicesrj.supabase.co"
SUPABASE_KEY = "sb_publishable_6BJt0uNBhuTAZK3V04paOQ_fGbfKMaU"


supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= TWILIO =================
TWILIO_SID = "AC5d23e6db2fd9d27a21df02ca77a84498"
TWILIO_AUTH = "ee2fb1328b8559bc365b9cf1ebf70457"
TWILIO_PHONE = "+14784009309"

twilio_client = TwilioClient(TWILIO_SID, TWILIO_AUTH)


# ================= UTIL =================
def normalize_phone(phone):
    if not phone:
        return None
    phone = re.sub(r"\D", "", phone)
    return phone[-10:]


def format_e164(phone):
    # India format
    return "+91" + phone




@app.route('/')
def home():
    return render_template("register.html")


@app.route('/register', methods=['POST'])
def register():

    try:
        name = request.form.get('guardian_name')
        phone = request.form.get('guardian_phone')
        address = request.form.get('address')
        members = request.form.get('members')

        if not name or not phone:
            return "Missing fields", 400

        phone_norm = normalize_phone(phone)

        # duplicate check
        existing = supabase.table("registered_persons") \
            .select("*") \
            .eq("guardian_phone", phone_norm) \
            .execute()

        if existing.data:
            return render_template("register.html", popup_message="Phone already registered")

        unique_code = hashlib.sha1(
            f"{name}{phone}{time.time()}".encode()
        ).hexdigest()[:10]

        # ================= SAVE MAIN PERSON =================
        supabase.table("registered_persons").insert({
            "guardian_name": name,
            "guardian_phone": phone_norm,
            "address": address,
            "members": members,
            "group_photo_url": None,  # optional for now
        }).execute()

        # ================= SAVE IMAGES =================
        files = request.files.getlist("individual_photos") or []

        for f in files:
            img_bytes = f.read()
            if not img_bytes:
                continue

            image_base64 = base64.b64encode(img_bytes).decode()

            supabase.table("person_images").insert({
                "guardian_phone": phone_norm,
                "image_url": image_base64   # (temporary base64 storage)
            }).execute()

        return render_template(
            "success.html",
            guardian_name=name,
            registration_id=unique_code
        )

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return "Internal Server Error", 500


# ================= DELETE PAGE =================
@app.route('/delete', methods=['GET', 'POST'])
def delete():

    if request.method == 'POST':

        phone = request.form.get('guardian_phone')

        if not phone:
            return render_template("delete.html", message="Phone is required")

        phone = normalize_phone(phone)

        try:
            # 🔥 DELETE FROM SUPABASE
            result = supabase.table("registered_persons") \
                .delete() \
                .eq("guardian_phone", phone) \
                .execute()

            # check if anything deleted
            if result.data:
                return render_template("delete.html", message="Record deleted successfully")
            else:
                return render_template("delete.html", message="No record found for this phone")

        except Exception as e:
            return render_template("delete.html", message=f"Error: {str(e)}")

    return render_template("delete.html")

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
            msg_status = "Invalid phone number"
            return render_template("direct_message.html", msg_status=msg_status)

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
                msg_status = "Message cannot be empty"
                return render_template("direct_message.html", msg_status=msg_status)

            try:
                to_number = "+91" + phone  # India format

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
if __name__ == "__main__":
    app.run(debug=True)