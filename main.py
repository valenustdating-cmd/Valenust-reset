import os
import json
from flask import Flask, request, jsonify
import gspread

app = Flask(__name__)

gc = gspread.service_account(filename="credentials.json")
sheet = gc.open("Valenust Users")

@app.route('/reset', methods=['POST'])
def reset_user():
    data = request.get_json() or {}
    telegram_id = str(data.get('telegram_id', ''))
    
    if not telegram_id:
        return jsonify({"error": "No telegram_id provided"}), 400

    for worksheet in sheet.worksheets():
        try:
            cell_list = worksheet.findall(telegram_id)
            for cell in cell_list:
                current_val = cell.value or ""
                new_val = current_val.replace(telegram_id, "").replace(",,", ",").strip(",")
                worksheet.update_cell(cell.row, cell.col, new_val)
        except Exception:
            continue
            
    return jsonify({"status": "success", "message": "Feed reset successful"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
