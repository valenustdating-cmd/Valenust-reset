import os
import json
import base64
import random
import time
from datetime import datetime
from flask import Flask, jsonify, request
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

# Simple in-memory cache store: { tab_name: {"timestamp": float, "records": list} }
DATA_CACHE = {}
CACHE_TTL = 60  # Cache duration in seconds (1 minute)

def get_gspread_client():
    if "GCP_CREDS_B64" in os.environ:
        creds_json = base64.b64decode(os.environ["GCP_CREDS_B64"]).decode("utf-8")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)

def get_cached_records(tab_name):
    """Fetches records from cache if valid, otherwise refreshes from Google Sheets."""
    now = time.time()
    
    # Check if we have valid, fresh data in cache
    if tab_name in DATA_CACHE:
        cache_entry = DATA_CACHE[tab_name]
        if now - cache_entry["timestamp"] < CACHE_TTL:
            return cache_entry["records"]

    # Fetch fresh data from Google Sheets
    gc = get_gspread_client()
    workbook = gc.open("Valenust Users")
    sheet = workbook.worksheet(tab_name)
    all_records = sheet.get_all_records()

    # Update cache
    DATA_CACHE[tab_name] = {
        "timestamp": now,
        "records": all_records
    }
    
    return all_records

@app.route("/random_profile", methods=["POST"])
def get_random_profile():
    try:
        data = request.get_json(silent=True) or {}
        telegram_id = str(data.get("telegram_id", "")).strip()
        tab_name = str(data.get("tab_name", "")).strip()       # e.g., 'Main_Male' or 'Main_Female'
        user_location = str(data.get("location", "")).strip()  # Passed from {{location}}

        if not telegram_id or not tab_name:
            return jsonify({"status": "error", "message": "Missing required parameters"}), 400

        try:
            all_records = get_cached_records(tab_name)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Sheet fetch error: {str(e)}"}), 500

        # 1. Exclude the user's own profile
        other_candidates = [
            p for p in all_records 
            if str(p.get("Telegram_Id", "")).strip() != telegram_id
        ]

        if not other_candidates:
            return jsonify({"status": "empty", "message": "No candidates available on the app yet"}), 200

        # 2. Try finding candidates in the user's state first
        same_state_candidates = []
        if user_location:
            same_state_candidates = [
                p for p in other_candidates 
                if str(p.get("Location", "")).strip().lower() == user_location.lower()
            ]

        # 3. Fall back to nationwide candidates if state is empty
        final_pool = same_state_candidates if same_state_candidates else other_candidates

        # 4. Pick one random candidate
        selected = random.choice(final_pool)

        return jsonify({
            "status": "success",
            "candidate": {
                "telegram_id": str(selected.get("Telegram_Id", "")),
                "name": str(selected.get("User_name", "Anonymous")),
                "age": str(selected.get("User_age", "")),
                "bio": str(selected.get("Bio", "No bio provided.")),
                "photo_url": str(selected.get("Photo_URL", "")),
                "location": str(selected.get("Location", ""))
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/check_vip", methods=["POST"])
def check_vip():
    try:
        data = request.get_json(silent=True) or {}
        telegram_id = str(data.get("telegram_id", "")).strip()
        tab_name = str(data.get("tab_name", "")).strip()  # 'Main_Male' or 'Main_Female'

        if not telegram_id or not tab_name:
            return jsonify({
                "is_vip": "false", 
                "is_ref_valid": "false", 
                "status": "EXPIRED", 
                "reason": "Missing parameters"
            }), 200

        # Uses the fast in-memory cached records
        all_records = get_cached_records(tab_name)

        # Find user record by Telegram_Id
        user = next((p for p in all_records if str(p.get("Telegram_Id", "")).strip() == telegram_id), None)

        if not user:
            return jsonify({
                "is_vip": "false", 
                "is_ref_valid": "false", 
                "status": "EXPIRED", 
                "reason": "User not found"
            }), 200

        today = datetime.now().date()

        # 1. Check VIP Expiry (Column M - header 'VIP_Expiry')
        vip_expiry_str = str(user.get("VIP_Expiry", "")).strip()
        is_vip = "false"
        if vip_expiry_str:
            try:
                vip_date = datetime.strptime(vip_expiry_str, "%Y-%m-%d").date()
                if vip_date >= today:
                    is_vip = "true"
            except ValueError:
                pass

        # 2. Check Referral Expiry (Column L - header 'Ref_Expiry')
        ref_expiry_str = str(user.get("Ref_Expiry", "")).strip()
        is_ref_valid = "false"
        if ref_expiry_str:
            try:
                ref_date = datetime.strptime(ref_expiry_str, "%Y-%m-%d").date()
                if ref_date >= today:
                    is_ref_valid = "true"
            except ValueError:
                pass

        return jsonify({
            "is_vip": is_vip,
            "is_ref_valid": is_ref_valid,
            "vip_expiry": vip_expiry_str,
            "ref_expiry": ref_expiry_str
        }), 200

    except Exception as e:
        return jsonify({
            "is_vip": "false", 
            "is_ref_valid": "false", 
            "status": "ERROR", 
            "message": str(e)
        }), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
