# ========================= IMPORTS =========================
import os
import time
import hashlib
import tempfile
import base64
import re

from flask import Flask, render_template, request, Response
from flask_sqlalchemy import SQLAlchemy
from twilio.rest import Client

from model.face_facenet_cbir import FaceNetCBIR
from PIL import Image
import numpy as np

# ========================= APP =========================
app = Flask(__name__)
app.secret_key = "change_this_secret"

# ========================= DB =========================
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://root:Sahil%40.com1@localhost:3306/Kaizen"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ========================= TWILIO =========================
TWILIO_SID = "ACf49660fa2ae66e3237418d06d2c10783"
TWILIO_AUTH = "de775601733e03a3bb8bfb7f38f3a2da"
TWILIO_PHONE = "+14195737481"
twilio_client = Client(TWILIO_SID, TWILIO_AUTH)

TWILIO_VERIFIED_NUMBER = "8830001371"

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


class QueryImage(db.Model):
    __tablename__ = "query_images"

    id = db.Column(db.Integer, primary_key=True)
    image_data = db.Column(db.LargeBinary)
    mime_type = db.Column(db.String(50))


class QueryProcess(db.Model):
    __tablename__ = "query_process"

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.Integer)
    image_id = db.Column(db.Integer)
    query_image_id = db.Column(db.Integer)
    status = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

# ========================= INIT =========================
with app.app_context():
    db.create_all()

# ========================= MODEL =========================
cbir_model = FaceNetCBIR()

# ========================= CACHE =========================
known_embeddings = []
known_visitors = []
known_image_ids = []

def load_cache():
    global known_embeddings, known_visitors, known_image_ids

    print("Loading face cache...")

    images = ImageModel.query.all()
    temp_dir = tempfile.mkdtemp()

    for i, img in enumerate(images):
        path = os.path.join(temp_dir, f"{i}.jpg")

        with open(path, "wb") as f:
            f.write(img.image_data)

        emb = cbir_model.extract_features(path)   # ✅ FIXED HERE

        if emb is not None:
            known_embeddings.append(emb)
            known_visitors.append(img.visitor)
            known_image_ids.append(img.id)

    print("Cache loaded:", len(known_embeddings))

with app.app_context():
    load_cache()

# ========================= HOME =========================
@app.route('/')
def search_page():
    return render_template("search.html")

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
            img = ImageModel(
                visitor_id=visitor.id,
                image_data=f.read(),
                mime_type=f.mimetype,
                image_type="individual"
            )
            db.session.add(img)

        db.session.commit()

        return render_template(
            "success.html",
            guardian_name=name,
            registration_id=unique_code
        )

    return render_template("register.html")

# ========================= QUERY =========================
@app.route('/process_query', methods=['POST'])
def process_query():

    query_file = request.files.get("query_image")
    query_bytes = query_file.read()

    query_img = QueryImage(image_data=query_bytes, mime_type=query_file.mimetype)
    db.session.add(query_img)
    db.session.commit()

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
    temp.write(query_bytes)
    temp.close()

    query_emb = cbir_model.extract_features(temp.name)   # ✅ FIXED

    best_score = 0
    best_index = -1

    for i, emb in enumerate(known_embeddings):

        score = np.dot(query_emb, emb) / (
            np.linalg.norm(query_emb) * np.linalg.norm(emb)
        )

        if score > best_score:
            best_score = score
            best_index = i

    status = "NOT FOUND"
    visitor = None
    image_id = None

    if best_score > 0.6 and best_index != -1:
        status = "FOUND"
        visitor = known_visitors[best_index]
        image_id = known_image_ids[best_index]

    process = QueryProcess(
        visitor_id=visitor.id if visitor else None,
        image_id=image_id,
        query_image_id=query_img.id,
        status=status
    )

    db.session.add(process)
    db.session.commit()

    return render_template(
        "query_results.html",
        matches=[{
            "visitor": visitor,
            "score": f"{best_score*100:.2f}",
            "image_id": image_id,
            "query_id": query_img.id
        }] if status == "FOUND" else [],
        message=status,
        query_image_url="data:image/jpeg;base64," + base64.b64encode(query_bytes).decode()
    )

# ========================= DELETE =========================
@app.route('/delete', methods=['GET','POST'])
def delete_visitor():

    msg = None

    if request.method == 'POST':
        phone = request.form['guardian_phone']
        v = Visitor.query.filter_by(guardian_phone=phone).first()

        if v:
            db.session.delete(v)
            db.session.commit()
            msg = "Deleted successfully"
        else:
            msg = "Not found"

    return render_template("delete.html", message=msg)

# ========================= DIRECT MESSAGE =========================
@app.route('/direct_message', methods=['GET', 'POST'])
def direct_message():

    visitor_info = None
    msg_status = None

    if request.method == 'POST':

        guardian_phone = request.form.get('guardian_phone')
        action = request.form.get('action')
        message = request.form.get('message')

        phone = normalize_phone(guardian_phone)

        visitor = Visitor.query.filter_by(guardian_phone=phone).first()

        if action == 'search':

            if visitor:
                visitor_info = {
                    "name": visitor.guardian_name,
                    "phone": visitor.guardian_phone,
                    "address": visitor.address,
                    "members": visitor.members
                }
                msg_status = "Guardian found."
            else:
                msg_status = "No registered guardian found (can still send SMS)."

        elif action == 'send':

            try:
                twilio_client.messages.create(
                    body=message,
                    from_=TWILIO_PHONE,
                    to=f"+91{phone}"
                )

                msg_status = f"Message sent to {phone}"

            except Exception as e:
                msg_status = f"Failed to send: {str(e)}"

    return render_template(
        "direct_message.html",
        visitor_info=visitor_info,
        msg_status=msg_status
    )

# ========================= ALERT =========================
@app.route('/send_alert/<int:image_id>/<int:query_id>')
def send_alert(image_id, query_id):

    img = db.session.get(ImageModel, image_id)
    query_img = db.session.get(QueryImage, query_id)

    if not img or not query_img:
        return "Invalid data"

    visitor = img.visitor

    guardian_phone = normalize_phone(visitor.guardian_phone)

    found_link = f"http://127.0.0.1:5000/reunification/{query_id}/found"
    not_found_link = f"http://127.0.0.1:5000/reunification/{query_id}/not_found"

    process = QueryProcess(
        visitor_id=visitor.id,
        image_id=img.id,
        query_image_id=query_id,
        status="Still Processing"
    )

    db.session.add(process)
    db.session.commit()

    try:
        twilio_client.messages.create(
            body=f"FOUND: {found_link}\nNOT FOUND: {not_found_link}",
            from_=TWILIO_PHONE,
            to=f"+91{guardian_phone}"
        )
        success = "Sent"
    except Exception as e:
        success = str(e)

    return success

# ========================= PROCESSING =========================
@app.route('/processing')
def processing():

    processes = QueryProcess.query.order_by(QueryProcess.created_at.desc()).all()

    return render_template("processing.html", processes=processes)

# ========================= REUNIFICATION =========================
@app.route('/reunification/<int:process_id>/<status>')
def reunification_update(process_id, status):

    process = db.session.get(QueryProcess, process_id)

    if not process:
        return "Invalid Process"

    if status == "found":
        process.status = "Reunification Done"
    else:
        process.status = "Person Not Found"

    db.session.commit()

    return render_template("reunification_response.html", status=process.status)

# ========================= RUN =========================
if __name__ == "__main__":
    app.run(debug=True)