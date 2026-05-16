from flask import Flask, render_template, request
from supabase import create_client
from dotenv import load_dotenv

import os
import time
import uuid

# load env
load_dotenv()

# flask app
app = Flask(__name__)

# supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY
)



# home page
@app.route('/')
def home():
    return render_template("register.html")

# register route
@app.route('/register', methods=['POST'])
def register():

    try:

        # form data
        guardian_name = request.form['guardian_name']
        guardian_phone = request.form['guardian_phone']
        address = request.form['address']
        members = request.form['members']

        # ---------------- CHECK DUPLICATE PHONE ----------------
        existing = supabase.table(
            "registered_persons"
        ).select("*").eq(
            "guardian_phone",
            guardian_phone
        ).execute()

        if existing.data:
            return render_template(
                "register.html",
                popup_message="Phone number already registered!"
            )

        # ---------------- UNIQUE REGISTRATION ID ----------------
        registration_id = "CC2026-" + str(uuid.uuid4())[:6].upper()

        # timestamp
        timestamp = int(time.time())

        # ---------------- GROUP PHOTO ----------------
        group_photo = request.files['group_photo']

        group_filename = f"group_{guardian_phone}_{timestamp}.jpg"

        supabase.storage.from_(
            "person-images"
        ).upload(
            group_filename,
            group_photo.read()
        )

        group_photo_url = supabase.storage.from_(
            "person-images"
        ).get_public_url(group_filename)

        # ---------------- INDIVIDUAL PHOTOS ----------------
        individual_urls = []

        individual_files = request.files.getlist(
            "individual_photos"
        )

        for index, photo in enumerate(individual_files):

            filename = f"{guardian_phone}_{index}_{timestamp}.jpg"

            supabase.storage.from_(
                "person-images"
            ).upload(
                filename,
                photo.read()
            )

            url = supabase.storage.from_(
                "person-images"
            ).get_public_url(filename)

            individual_urls.append(url)

        # ---------------- SAVE DATABASE ----------------
        data = {
            "guardian_name": guardian_name,
            "guardian_phone": guardian_phone,
            "address": address,
            "members": members,
            "individual_photo_urls": individual_urls,
            "group_photo_url": group_photo_url,
            "registration_id": registration_id
        }

        supabase.table(
            "registered_persons"
        ).insert(data).execute()

        # ---------------- SUCCESS PAGE ----------------
        return render_template(
            "success.html",
            guardian_name=guardian_name,
            registration_id=registration_id
        )

    except Exception as e:
        return f"Error: {str(e)}"
    

# ========================= DELETE VISITOR =========================
@app.route('/delete', methods=['GET', 'POST'])
def delete_visitor():

    message = None

    if request.method == 'POST':

        guardian_phone = request.form['guardian_phone']

        # ---------------- CHECK IF EXISTS ----------------
        existing = supabase.table(
            "registered_persons"
        ).select("*").eq(
            "guardian_phone",
            guardian_phone
        ).execute()

        if existing.data:

            # ---------------- DELETE RECORD ----------------
            supabase.table(
                "registered_persons"
            ).delete().eq(
                "guardian_phone",
                guardian_phone
            ).execute()

            message = (
                f"Visitor with phone "
                f"{guardian_phone} deleted successfully."
            )

        else:

            message = (
                f"No visitor found with "
                f"{guardian_phone}"
            )

    return render_template(
        "delete.html",
        message=message
    )
    



# run app
if __name__ == '__main__':
   app.run(host="0.0.0.0", port=5000)