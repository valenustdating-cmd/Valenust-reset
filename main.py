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
    if "GCP_CREDS_B64" in os.environ:
        creds_json = base64.b64decode(os.environ["GCP_CREDS_B64"]).decode("utf-8")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)

@app.route("/", methods=["GET"])
def home():
    return jsonify({"status": "online", "message": "Valenust Reset API is running!"}), 200

@app.route("/reset", methods=["POST", "GET"])
def reset_seen_by():
    try:
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
        workbook = gc.open("Valenust Users")
        found = False

        # Loop through ALL tabs in the spreadsheet
        for sheet in workbook.worksheets():
            try:
                cell = sheet.find(str(telegram_id))
                if cell:
                    # Clear Column E (seen_by) in this sheet
                    sheet.update_cell(cell.row, 5, "")
                    found = True
            except Exception:
                continue

        if found:
            return jsonify({
                "status": "success", 
                "message": f"Successfully cleared seen_by across all sheets for Telegram ID {telegram_id}"
            }), 200
        else:
            return jsonify({"status": "error", "message": f"Telegram ID {telegram_id} not found in any sheet"}), 404

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
                   
