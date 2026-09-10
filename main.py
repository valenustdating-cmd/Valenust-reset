import os
import json
import base64
import random
import time
import re
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

DATA_CACHE = {}
CACHE_TTL = 60

def get_gspread_client():
    if "GCP_CREDS_B64" in os.environ:
        creds_json = base64.b64decode(os.environ["GCP_CREDS_B64"]).decode("utf-8")
        creds_dict = json.loads(creds_json)
        creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file("credentials.json", scopes=SCOPES)
    return gspread.authorize(creds)

def get_cached_records(tab_name):
    now = time.time()
    
    if tab_name in DATA_CACHE:
        cache_entry = DATA_CACHE[tab_name]
        if now - cache_entry["timestamp"] < CACHE_TTL:
            return cache_entry["records"]

    gc = get_gspread_client()
    workbook = gc.open("Valenust Users")
    sheet = workbook.worksheet(tab_name)
    all_records = sheet.get_all_records()

    DATA_CACHE[tab_name] = {
        "timestamp": now,
        "records": all_records
    }
    
    return all_records

def invalidate_cache(tab_name):
    """Clears the cache when a payment updates Google Sheets so changes show immediately."""
    if tab_name in DATA_CACHE:
        del DATA_CACHE[tab_name]

def clean_phone(phone_str):
    """Formats phone numbers for WhatsApp wa.me links."""
    digits = re.sub(r"\D", "", str(phone_str or ""))
    if digits.startswith("0") and len(digits) == 11:
        digits = "234" + digits[1:]
    return digits


@app.route("/webhook/payment", methods=["POST"])
def process_payment():
    try:
        data = request.get_json(silent=True) or {}
        
        # 1. Grab telegram_id from every possible SendPulse location
        raw_id = (
            data.get("telegram_id") or 
            data.get("contact", {}).get("telegram_id") or 
            data.get("contact", {}).get("variables", {}).get("telegram_id") or ""
        )
        telegram_id = str(raw_id).strip()

        # Catch empty or unparsed SendPulse variables immediately
        if not telegram_id or "{{" in telegram_id or "}}" in telegram_id:
            return jsonify({
                "status": "error", 
                "message": f"SendPulse sent an invalid Telegram ID: '{telegram_id}'. Ensure 'telegram_id' contact variable is set."
            }), 400

        try:
            days = int(data.get("days", 30))
        except (ValueError, TypeError):
            days = 30

        gc = get_gspread_client()
        workbook = gc.open("Valenust Users")

        # 2. Compute exact expiry date string
        new_expiry = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d")
        
        # 3. Direct fast-path search on Main_Male and Main_Female
        user_found = False
        sheets_to_search = ["Main_Male", "Main_Female"]

        for tab_name in sheets_to_search:
            sheet = workbook.worksheet(tab_name)
            
            # Fetch entire Column A in a single, ultra-fast API call
            col_a_ids = [str(x).strip() for x in sheet.col_values(1)]
            
            if telegram_id in col_a_ids:
                # Get exact row index instantly (1-based index)
                target_row = col_a_ids.index(telegram_id) + 1
                
                # Column M is Column 13 (VIP_Expiry)
                vip_col_idx = 13
                
                # Update cell directly without searching the full sheet
                sheet.update_cell(target_row, vip_col_idx, new_expiry)
                
                # Clear local server cache immediately
                invalidate_cache(tab_name)
                user_found = True
                break

        if not user_found:
            return jsonify({
                "status": "error", 
                "message": f"Telegram ID {telegram_id} was not found in Main_Male or Main_Female"
            }), 404

        return jsonify({
            "status": "success",
            "message": f"VIP updated instantly for Telegram ID {telegram_id}",
            "vip_expiry": new_expiry
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Server Error: {str(e)}"}), 500


@app.route("/random_profile", methods=["POST"])
def get_random_profile():
    try:
        data = request.get_json(silent=True) or {}
        telegram_id = str(data.get("telegram_id", "")).strip()
        tab_name = str(data.get("tab_name", "")).strip()
        user_location = str(data.get("location", "")).strip()

        if not telegram_id or not tab_name:
            return jsonify({"status": "error", "message": "Missing required parameters"}), 400

        try:
            all_records = get_cached_records(tab_name)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Sheet fetch error: {str(e)}"}), 500

        valid_candidates = []
        for p in all_records:
            clean_record = {str(k).strip(): v for k, v in p.items()}
            p_id = str(clean_record.get("Telegram_Id", "")).strip()
            p_photo = str(clean_record.get("Photo_URL", "")).strip()
            
            if p_id and p_photo and p_id != telegram_id:
                valid_candidates.append(clean_record)

        if not valid_candidates:
            return jsonify({"status": "empty", "message": "No candidates available on the app yet"}), 200

        same_state_candidates = []
        if user_location:
            same_state_candidates = [
                p for p in valid_candidates 
                if str(p.get("Location", "")).strip().lower() == user_location.lower()
            ]

        final_pool = same_state_candidates if same_state_candidates else valid_candidates
        selected = random.choice(final_pool)

        return jsonify({
            "status": "success",
            "candidate": {
                "telegram_id": str(selected.get("Telegram_Id", "")),
                "name": str(selected.get("User_name", "Anonymous")),
                "age": str(selected.get("User_age", "")),
                "bio": str(selected.get("Bio", "No bio provided.")),
                "photo_url": str(selected.get("Photo_URL", "")),
                "location": str(selected.get("Location", "")),
                "phone": clean_phone(selected.get("Phone_Contact", selected.get("Phone_number", "")))
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/check_vip", methods=["POST"])
def check_vip():
    try:
        data = request.get_json(silent=True) or {}
        telegram_id = str(data.get("telegram_id", "")).strip()
        tab_name = str(data.get("tab_name", "")).strip()

        if not telegram_id or not tab_name:
            return jsonify({
                "is_vip": "false", 
                "is_ref_valid": "false", 
                "status": "EXPIRED", 
                "reason": "Missing parameters"
            }), 200

        all_records = get_cached_records(tab_name)
        user = next((p for p in all_records if str(p.get("Telegram_Id", "")).strip() == telegram_id), None)

        if not user:
            return jsonify({
                "is_vip": "false", 
                "is_ref_valid": "false", 
                "status": "EXPIRED", 
                "reason": "User not found"
            }), 200

        today = datetime.now().date()

        vip_expiry_str = str(user.get("VIP_Expiry", "")).strip()
        is_vip = "false"
        if vip_expiry_str:
            try:
                vip_date = datetime.strptime(vip_expiry_str, "%Y-%m-%d").date()
                if vip_date >= today:
                    is_vip = "true"
            except ValueError:
                pass

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


@app.route("/get_liker", methods=["POST"])
def get_liker():
    try:
        data = request.get_json(silent=True) or {}
        telegram_id = str(data.get("telegram_id", "")).strip()

        if not telegram_id:
            return jsonify({"status": "error", "message": "Missing required parameters"}), 400

        try:
            all_records = get_cached_records("Likes")
        except Exception as e:
            return jsonify({"status": "error", "message": f"Sheet fetch error: {str(e)}"}), 500

        valid_candidates = []
        for p in all_records:
            clean_record = {str(k).strip(): v for k, v in p.items()}
            liked_cand = str(clean_record.get("Liked_candidate", clean_record.get("Liked_candidate_id", ""))).strip()
            liker_photo = str(clean_record.get("Liker_Photo", "")).strip()
            
            if liked_cand == telegram_id and liker_photo:
                valid_candidates.append(clean_record)

        if not valid_candidates:
            return jsonify({"status": "empty", "message": "No likes found"}), 200

        selected = random.choice(valid_candidates)

        return jsonify({
            "status": "success",
            "candidate": {
                "telegram_id": str(selected.get("Liker_id", "")),
                "name": str(selected.get("Liker_username", "Anonymous")),
                "age": str(selected.get("Liker_age", "")),
                "bio": str(selected.get("Liker_Bio", "No bio provided.")),
                "photo_url": str(selected.get("Liker_Photo", "")),
                "location": str(selected.get("Liker_location", "")),
                "phone": clean_phone(selected.get("liker_phone", selected.get("Liker_phone", "")))
            }
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
