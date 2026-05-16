# ========================= IMPORTS =========================
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
from supabase import create_client, Client as SupabaseClient
from twilio.rest import Client

import re
import hashlib
import time
import base64

# ========================= APP =========================
app = Flask(__name__)
app.secret_key = "change_this_secret"

# ========================= MYSQL CONFIG =========================
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


# ========================= MODELS =========================
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


# ========================= HOME =========================
@app.route('/')
def home():
    return render_template("search.html")


# ========================= REGISTER =========================
@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['guardian_name']
        phone = request.form['guardian_phone']
        address = request.form.get('address')
        members = request.form.get('members')

        # check duplicate
        existing = Visitor.query.filter_by(guardian_phone=phone).first()
        if existing:
            return render_template("register.html", popup_message="Phone already registered")

        # unique code
        unique_code = hashlib.sha1(
            f"{name}{phone}{time.time()}".encode()
        ).hexdigest()[:10]

        # ================= MYSQL SAVE =================
        visitor = Visitor(
            guardian_name=name,
            guardian_phone=phone,
            address=address,
            members=members,
            unique_code=unique_code
        )

        db.session.add(visitor)
        db.session.commit()

        # ================= FILE HANDLING =================
        files = request.files.getlist("individual_photos")

        image_payloads = []

        for f in files:
            img_bytes = f.read()

            # save in MySQL
            db.session.add(ImageModel(
                visitor_id=visitor.id,
                image_data=img_bytes,
                mime_type=f.mimetype,
                image_type="individual"
            ))

            # prepare for Supabase
            image_payloads.append({
                "visitor_phone": phone,
                "image_base64": base64.b64encode(img_bytes).decode(),
                "mime_type": f.mimetype,
                "image_type": "individual"
            })

        db.session.commit()

        # ================= SUPABASE SYNC =================
        try:
            supabase.table("visitors").insert({
                "guardian_name": name,
                "guardian_phone": phone,
                "address": address,
                "members": members,
                "unique_code": unique_code
            }).execute()

            if image_payloads:
                supabase.table("images").insert(image_payloads).execute()

        except Exception as e:
            print("Supabase error:", e)

        # ================= SUCCESS =================
        return render_template(
            "success.html",
            guardian_name=name,
            registration_id=unique_code
        )

    return render_template("register.html")


# ========================= RUN =========================
if __name__ == "__main__":
    app.run(debug=True)