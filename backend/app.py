from flask import Flask, render_template, request
from supabase import create_client, Client
import hashlib
import time
import base64
import re

# ================= APP =================
app = Flask(__name__)
app.secret_key = "change_this_secret"

# ================= SUPABASE =================
SUPABASE_URL = "https://kxmkdnrmnckkrzicesrj.supabase.co"
SUPABASE_KEY = "sb_publishable_6BJt0uNBhuTAZK3V04paOQ_fGbfKMaU"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= UTIL =================
def normalize_phone(phone):
    if not phone:
        return None
    phone = re.sub(r"\D", "", phone)
    return phone[-10:]


# ================= HOME =================
@app.route('/')
def home():
    return render_template("register.html")


# ================= REGISTER =================
@app.route('/register', methods=['POST'])
def register():

    try:
        name = request.form.get('guardian_name')
        phone = request.form.get('guardian_phone')
        address = request.form.get('address')
        members = request.form.get('members')

        # validation
        if not name or not phone:
            return "Missing required fields", 400

        phone_norm = normalize_phone(phone)

        # unique code
        unique_code = hashlib.sha1(
            f"{name}{phone}{time.time()}".encode()
        ).hexdigest()[:10]

        # ================= SAVE VISITOR =================
        supabase.table("visitors").insert({
            "guardian_name": name,
            "guardian_phone": phone_norm,
            "address": address,
            "members": members,
            "unique_code": unique_code
        }).execute()

        # ================= SAVE IMAGES =================
        files = request.files.getlist("individual_photos")

        image_rows = []

        for f in files:
            if not f:
                continue

            img_bytes = f.read()
            if not img_bytes:
                continue

            image_rows.append({
                "guardian_phone": phone_norm,
                "image_base64": base64.b64encode(img_bytes).decode(),
                "mime_type": f.mimetype
            })

        if image_rows:
            supabase.table("images").insert(image_rows).execute()

        # ================= SUCCESS =================
        return render_template(
            "success.html",
            guardian_name=name,
            registration_id=unique_code
        )

    except Exception as e:
        print("ERROR:", str(e))
        return f"Server Error: {str(e)}", 500


# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)