import os
import json
import base64
import random
from flask import Flask, jsonify, request
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_gspread_client():
    if "GCP_CREDS_B64" in os.environ:
        creds_json = base64.b64decode(os.environ["GCP_CREDS_B64"]).decode("utf-8")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)

@app.route("/random_profile", methods=["POST"])
def get_random_profile():
    try:
        data = request.get_json(silent=True) or {}
        telegram_id = str(data.get("telegram_id", ""))
        tab_name = str(data.get("tab_name", ""))  # e.g., 'Kogi_Female', 'Lagos_Male'

        if not telegram_id or not tab_name:
            return jsonify({"status": "error", "message": "Missing parameters"}), 400

        gc = get_gspread_client()
        workbook = gc.open("Valenust Users")
        
        try:
            sheet = workbook.worksheet(tab_name)
        except Exception:
            return jsonify({"status": "error", "message": f"Tab '{tab_name}' not found"}), 404

        # Fetch all rows from the requested tab
        all_records = sheet.get_all_records()

        valid_candidates = []
        for profile in all_records:
            # Skip the user's own profile
            if str(profile.get("Telegram_Id", "")) == telegram_id:
                continue
            
            valid_candidates.append(profile)

        # If tab is empty or only has the user's own profile
        if not valid_candidates:
            return jsonify({"status": "empty", "message": "No candidates available"}), 200

        # Pick ONE random candidate row
        selected = random.choice(valid_candidates)

        return jsonify({
            "status": "success",
            "candidate": {
                "telegram_id": selected.get("Telegram_Id"),
                "name": selected.get("User_name"),
                "age": selected.get("User_age"),
                "bio": selected.get("Bio"),
                "photo_url": selected.get("Photo_URL"),
                "location": selected.get("Location")
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
        
