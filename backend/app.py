# ========================= IMPORTS =========================
import os
import time
import hashlib
import tempfile
import base64
import re

from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from twilio.rest import Client
from supabase import create_client, Client as SupabaseClient

from model.face_facenet_cbir import FaceNetCBIR

# ========================= APP =========================
app = Flask(__name__)
app.secret_key = "change_this_secret"

# ========================= MYSQL =========================
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://root:Sahil%40.com1@localhost:3306/Kaizen"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ========================= SUPABASE =========================
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "YOUR_SUPABASE_KEY"

supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

# ========================= TWILIO =========================
TWILIO_SID = "ACxxxxxxxxxxxxxxxx"
TWILIO_AUTH = "xxxxxxxxxxxxxxxx"
TWILIO_PHONE = "+14195737481"
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

# ========================= UTIL =========================
def normalize_phone(phone):
    if not phone:
        return None
    phone = re.sub(r"\D", "", phone)
    return phone[-10:]

# ========================= MODELS (MYSQL) =========================
class Visitor(db.Model):
    __tablename__ = "visitors"

    id = db.Column(db.Integer, primary_key=True)
    unique_code = db.Column(db.String(20))
    guardian_name = db.Column(db.String(100))
    guardian_phone = db.Column(db.String(20), unique=True)
    address = db.Column(db.String(255))
    members = db.Column(db.Text)


class ImageModel(db.Model):
    __tablename__ = "images"

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer, db.ForeignKey("visitors.id"))
    image_data = db.Column(db.LargeBinary)
    mime_type = db.Column(db.String(50))
    image_type = db.Column(db.String(20))

    visitor = db.relationship("Visitor")


# ========================= INIT DB =========================
with app.app_context():
    db.create_all()

# ========================= FACE MODEL =========================
cbir_model = FaceNetCBIR()

# ========================= CACHE =========================
known_embeddings = []
known_visitors = []
known_image_ids = []

# ========================= REGISTER =========================
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['guardian_name']
        phone = request.form['guardian_phone']
        address = request.form.get('address')
        members = request.form.get('members')

        existing = Visitor.query.filter_by(guardian_phone=phone).first()
        if existing:
            return render_template("register.html", popup_message="Phone already registered")

        unique_code = hashlib.sha1(f"{name}{phone}{time.time()}".encode()).hexdigest()[:10]

        # ================= MYSQL INSERT =================
        visitor = Visitor(
            guardian_name=name,
            guardian_phone=phone,
            address=address,
            members=members,
            unique_code=unique_code
        )

        db.session.add(visitor)
        db.session.commit()

        files = request.files.getlist("individual_photos")

        for f in files:
            img_bytes = f.read()

            img = ImageModel(
                visitor_id=visitor.id,
                image_data=img_bytes,
                mime_type=f.mimetype,
                image_type="individual"
            )
            db.session.add(img)

        db.session.commit()

        # ================= SUPABASE INSERT =================
        try:
            supabase.table("visitors").insert({
                "guardian_name": name,
                "guardian_phone": phone,
                "address": address,
                "members": members,
                "unique_code": unique_code
            }).execute()

            # upload images (base64 for simplicity)
            for f in files:
                img_bytes = f.read()
                supabase.table("images").insert({
                    "visitor_phone": phone,
                    "image_base64": base64.b64encode(img_bytes).decode(),
                    "mime_type": f.mimetype,
                    "image_type": "individual"
                }).execute()

        except Exception as e:
            print("Supabase error:", e)

        # ================= SUCCESS PAGE =================
        return render_template(
            "success.html",
            guardian_name=name,
            registration_id=unique_code
        )

    return render_template("register.html")


# ========================= RUN =========================
if __name__ == "__main__":
    app.run(debug=True)