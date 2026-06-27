from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from scrap_gmaps import scrape_gmaps
from dashboard import validate_excel
import pandas as pd
import os
import re
from werkzeug.utils import secure_filename
import warnings
import sys
sys.stdout.reconfigure(line_buffering=True)

warnings.simplefilter("ignore")
app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

# =========================
# PATH CONFIG
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  
PROJECT_ROOT = os.path.dirname(BASE_DIR)                

OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

def safe_filename(text):
    return re.sub(r"[^\w\s-]", "", text).strip().lower().replace(" ", "_")

@app.route("/style.css")
def style():
    return send_from_directory(PROJECT_ROOT, "style.css")

@app.route("/images/<path:filename>")
def images(filename):
    return send_from_directory(os.path.join(PROJECT_ROOT, "images"), filename)

@app.route("/")
def homepage():
    return send_from_directory(PROJECT_ROOT, "homepage.html")

@app.route("/dashboard")
def dashboard_page():
    return send_from_directory(PROJECT_ROOT, "dashboard.html")

@app.route("/koleksidata")
def koleksi_page():
    return send_from_directory(PROJECT_ROOT, "koleksidata.html")

@app.route("/upload-dashboard", methods=["POST"])
def upload_dashboard():
    try:
        if "file" not in request.files:
            return jsonify({"status":"error","message":"File tidak ditemukan"}), 400

        file = request.files["file"]
        title = request.form.get("title","").strip()

        if not title:
            return jsonify({"status":"error","message":"Judul dashboard wajib diisi"}), 400

        if not file.filename.lower().endswith((".xlsx",".xls")):
            return jsonify({"status":"error","message":"File harus .xlsx/.xls"}), 400

        filename = secure_filename(file.filename)
        temp_path = os.path.join(OUTPUT_DIR, filename)
        file.save(temp_path)

        try:
            df = pd.read_excel(temp_path, engine="openpyxl", dtype=str)
            df.columns = [c.strip() for c in df.columns]
            csv_filename = safe_filename(filename.rsplit(".",1)[0])+".csv"
            csv_path = os.path.join(OUTPUT_DIR, csv_filename)
            df.to_csv(csv_path, index=False)
            validation = validate_excel(csv_path)
        except Exception as e:
            validation = {
                "status":"error",
                "message": f"Gagal baca Excel: {str(e)}",
                "columns": [],
                "total_rows": 0
            }

        return jsonify({
            "status":"ok",
            "dashboard_title": title,
            "filename": filename,
            "csv_filename": csv_filename,
            "validation": validation
        }), 200

    except Exception as e:
        return jsonify({"status":"error","message":str(e)}),500

@app.route("/scrape", methods=["POST"])
def scrape():
    try:
        data = request.get_json(force=True)
        query = data.get("query")

        if not query:
            return jsonify([])

        rows = scrape_gmaps(query)

        if not rows:
            return jsonify([])

        return jsonify(rows)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/export-excel", methods=["POST"])
def export_excel():
    try:
        data = request.get_json(force=True)
        rows = data.get("rows")
        query = data.get("query")

        if not rows:
            return jsonify({"error": "data kosong"}), 400

        df = pd.DataFrame(rows)

        df = df[[
            "nama",
            "alamat",
            "wilayah",
            "no_telp",
            "aktivitas",
            "link_maps"
        ]]

        safe_name = safe_filename(query) if query else ""
        if not safe_name:
            safe_name = "hasil_scrape"

        filename = safe_name + ".xlsx"
        filepath = os.path.join(OUTPUT_DIR, filename)

        df.to_excel(filepath, index=False, engine="openpyxl")

        return send_file(
            filepath,
            as_attachment=True,
            download_name=filename
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=False)
