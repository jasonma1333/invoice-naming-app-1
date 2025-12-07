"""
HSBC Payment Advice PDF 重命名 Web 應用 - Vercel Serverless Function
提供網頁介面上傳 PDF、輸入年份和期間代碼,並下載重新命名的檔案
"""

from flask import Flask, request, send_file, jsonify, render_template
import os
import sys
import tempfile
import zipfile
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF

# 添加父目錄到 Python 路徑以導入 hsbc_payment_renamer
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)
from hsbc_payment_renamer import HSBCPaymentAdviceRenamer

# Vercel 環境中的路徑配置
template_dir = os.path.join(BASE_DIR, 'templates')
app = Flask(__name__, template_folder=template_dir)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50MB max upload
ALLOWED_EXTENSIONS = {"pdf"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def detect_pdf_type(pdf_path: str) -> str:
    """檢測 PDF 類型"""
    try:
        doc = fitz.open(pdf_path)
        text = []
        for i in range(min(2, len(doc))):
            text.append(doc.load_page(i).get_text())
        doc.close()
        content = "\n".join(text).lower()
        if any(k in content for k in ["hsbc", "payment advice", "payroll advice"]):
            return "hsbc"
        if any(k in content for k in ["invoice", "發票"]):
            return "invoice"
        return "unknown"
    except Exception:
        return "unknown"

@app.route("/")
def index():
    """主頁 - 顯示上傳介面"""
    return render_template('index.html')

@app.route("/health")
def health():
    """健康檢查"""
    return jsonify({"status": "ok"})

@app.route("/upload", methods=["POST"])
def upload_file():
    """單檔上傳並重命名"""
    if "file" not in request.files:
        return jsonify({"error": "未找到檔案"}), 400
    
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "未選擇檔案"}), 400
    
    if not allowed_file(file.filename):
        return jsonify({"error": "僅支援 PDF 檔案"}), 400
    
    period_code = request.form.get("period_code", "").strip().upper()
    if not period_code:
        return jsonify({"error": "請提供期間代碼"}), 400
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = os.path.join(temp_dir, secure_filename(file.filename))
            file.save(original_path)
            
            pdf_type = detect_pdf_type(original_path)
            if pdf_type != "hsbc":
                return jsonify({"error": "此檔案不是 HSBC Payment Advice PDF"}), 400
            
            renamer = HSBCPaymentAdviceRenamer(period_code)
            new_filename = renamer.rename_single_file(original_path, temp_dir)
            
            if not new_filename:
                return jsonify({"error": "重命名失敗"}), 500
            
            new_path = os.path.join(temp_dir, new_filename)
            return send_file(
                new_path,
                as_attachment=True,
                download_name=new_filename,
                mimetype="application/pdf"
            )
    
    except Exception as e:
        return jsonify({"error": f"處理失敗: {str(e)}"}), 500

@app.route("/batch_upload", methods=["POST"])
def batch_upload():
    """批次上傳並重命名"""
    if "files[]" not in request.files:
        return jsonify({"error": "未找到檔案"}), 400
    
    files = request.files.getlist("files[]")
    if not files or all(f.filename == "" for f in files):
        return jsonify({"error": "未選擇檔案"}), 400
    
    period_code = request.form.get("period_code", "").strip().upper()
    if not period_code:
        return jsonify({"error": "請提供期間代碼"}), 400
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_dir = os.path.join(temp_dir, "input")
            output_dir = os.path.join(temp_dir, "output")
            os.makedirs(input_dir)
            os.makedirs(output_dir)
            
            for file in files:
                if file and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(input_dir, filename))
            
            renamer = HSBCPaymentAdviceRenamer(period_code)
            results = renamer.batch_rename(input_dir, output_dir)
            
            if results["success_count"] == 0:
                return jsonify({"error": "沒有檔案被成功重命名"}), 400
            
            zip_path = os.path.join(temp_dir, "renamed_files.zip")
            with zipfile.ZipFile(zip_path, "w") as zipf:
                for filename in os.listdir(output_dir):
                    file_path = os.path.join(output_dir, filename)
                    zipf.write(file_path, filename)
            
            return send_file(
                zip_path,
                as_attachment=True,
                download_name=f"renamed_files_{period_code}.zip",
                mimetype="application/zip"
            )
    
    except Exception as e:
        return jsonify({"error": f"批次處理失敗: {str(e)}"}), 500

# Vercel serverless function handler
def handler(request):
    with app.request_context(request.environ):
        return app.full_dispatch_request()

# For local testing
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
