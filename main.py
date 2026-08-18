import os
import json
import base64
from flask import Flask, jsonify, request
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_gspread_client():
    # Authenticate via Base64 environment variable if available, else local credentials file
    if "GCP_CREDS_B64" in os.environ:
        creds_json = base64.b64decode(os.environ["GCP_CREDS_B64"]).decode("utf-8")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)

@app.route("/", methods=["GET"])
def home():
    # Health check route for Render
    return jsonify({"status": "online", "message": "Valenust Reset API is running!"}), 200

@app.route("/reset", methods=["POST", "GET"])
def reset_seen_by():
    try:
        # Accepts telegram_id from SendPulse JSON body or URL query parameters
        data = request.get_json(silent=True) or {}
        telegram_id = (
            data.get("telegram_id") 
            or data.get("user_id") 
            or request.args.get("telegram_id") 
            or request.args.get("user_id")
        )

        if not telegram_id:
            return jsonify({"status": "error", "message": "Missing telegram_id parameter"}), 400

        gc = get_gspread_client()
        sheet = gc.open("Valenust Users").sheet1

        # Locate the user's row using their Telegram ID
        cell = sheet.find(str(telegram_id))

        if cell:
            # Clears Column E (seen_by) for this specific user
            sheet.update_cell(cell.row, 5, "")
            return jsonify({
                "status": "success", 
                "message": f"Successfully cleared seen_by for Telegram ID {telegram_id}"
            }), 200
        else:
            return jsonify({"status": "error", "message": f"Telegram ID {telegram_id} not found in sheet"}), 404

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
        
