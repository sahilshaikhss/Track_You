# ========================= IMPORTS =========================
from flask import Flask, render_template, request
from supabase import create_client, Client
import re
import hashlib
import time

# ========================= APP =========================
app = Flask(__name__)
app.secret_key = "change_this_secret"

# ========================= SUPABASE =========================
SUPABASE_URL = "https://kxmkdnrmnckkrzicesrj.supabase.co"
SUPABASE_KEY = "sb_publishable_6BJt0uNBhuTAZK3V04paOQ_fGbfKMaU"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ========================= UTIL =========================
def normalize_phone(phone):
    phone = re.sub(r"\D", "", phone)
    return phone[-10:]

def generate_code(name, phone):
    return hashlib.sha1(f"{name}{phone}{time.time()}".encode()).hexdigest()[:10]

# ========================= HOME =========================
@app.route('/')
def home():
    return render_template("register.html")

# ========================= REGISTER =========================
@app.route('/register', methods=['POST'])
def register():

    name = request.form.get("guardian_name")
    phone = normalize_phone(request.form.get("guardian_phone"))
    address = request.form.get("address")
    members = request.form.get("members")

    unique_code = generate_code(name, phone)

    # ================= CHECK DUPLICATE =================
    existing = supabase.table("visitors") \
        .select("*") \
        .eq("guardian_phone", phone) \
        .execute()

    if existing.data:
        return render_template("register.html", popup_message="Phone already registered")

    # ================= INSERT VISITOR =================
    supabase.table("visitors").insert({
        "guardian_name": name,
        "guardian_phone": phone,
        "address": address,
        "members": members,
        "unique_code": unique_code
    }).execute()

    # ================= UPLOAD IMAGES =================
    files = request.files.getlist("individual_photos")

    for i, f in enumerate(files):
        file_bytes = f.read()

        file_path = f"{phone}/{unique_code}_{i}.jpg"

        # upload to storage
        supabase.storage.from_("visitor-images").upload(
            file_path,
            file_bytes,
            {"content-type": f.mimetype}
        )

        # get public URL
        image_url = supabase.storage.from_("visitor-images").get_public_url(file_path)

        # save image metadata
        supabase.table("images").insert({
            "visitor_phone": phone,
            "image_url": image_url,
            "image_type": "individual"
        }).execute()

    # ================= SUCCESS =================
    return render_template(
        "success.html",
        guardian_name=name,
        registration_id=unique_code
    )

# ========================= RUN =========================
if __name__ == "__main__":
    app.run(debug=True)