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
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from hsbc_payment_renamer import HSBCPaymentAdviceRenamer

app = Flask(__name__, template_folder='../templates')
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
def upload():
    """處理單個檔案上傳和重命名"""
    if "file" not in request.files:
        return jsonify({"error": "缺少檔案欄位 file"}), 400
    
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "未選擇檔案"}), 400
    
    if not allowed_file(f.filename):
        return jsonify({"error": "僅支援 PDF"}), 400

    # 獲取期間代碼，格式如 P1, P2, P8
    period_code = request.form.get("period_code", "P1").upper()
    if not period_code.startswith('P'):
        period_code = f"P{period_code}"

    # 儲存臨時檔案
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        f.save(tmp.name)
        temp_path = tmp.name

    try:
        # 使用 HSBC renamer 處理
        renamer = HSBCPaymentAdviceRenamer()
        info = renamer.extract_pdf_info(temp_path)
        
        if info:
            new_name = renamer.generate_new_filename(info, period_code)
        else:
            # 如果無法提取資訊，返回錯誤
            os.unlink(temp_path)
            return jsonify({"error": "無法解析 PDF 內容，請確認這是 HSBC Payment Advice"}), 400

        if not new_name:
            new_name = "unknown.pdf"
        if not new_name.endswith(".pdf"):
            new_name += ".pdf"
        
        safe = secure_filename(new_name)
        
        return send_file(
            temp_path, 
            as_attachment=True, 
            download_name=safe, 
            mimetype="application/pdf"
        )
    except Exception as e:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        return jsonify({"error": f"處理檔案時發生錯誤: {str(e)}"}), 500

@app.route("/batch_upload", methods=["POST"])
def batch_upload():
    """處理批量上傳"""
    files = request.files.getlist('files')
    
    if not files or all(f.filename == '' for f in files):
        return jsonify({"error": "沒有選擇檔案"}), 400
    
    period_code = request.form.get("period_code", "P1").upper()
    if not period_code.startswith('P'):
        period_code = f"P{period_code}"
    
    # 創建臨時 ZIP 檔案
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
        zip_path = temp_zip.name
    
    processed_files = []
    errors = []
    
    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in files:
                if file.filename == '' or not allowed_file(file.filename):
                    continue
                
                try:
                    # 處理單個檔案
                    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
                        file.save(temp_file.name)
                        temp_path = temp_file.name
                    
                    renamer = HSBCPaymentAdviceRenamer()
                    info = renamer.extract_pdf_info(temp_path)
                    
                    if info:
                        new_name = renamer.generate_new_filename(info, period_code)
                        if not new_name.endswith('.pdf'):
                            new_name += '.pdf'
                        safe_filename = secure_filename(new_name)
                        
                        # 將檔案加入 ZIP
                        zipf.write(temp_path, safe_filename)
                        processed_files.append(safe_filename)
                    else:
                        errors.append(f'{file.filename}: 無法解析內容')
                    
                    # 清理臨時檔案
                    os.unlink(temp_path)
                    
                except Exception as e:
                    errors.append(f'{file.filename}: {str(e)}')
                    if 'temp_path' in locals() and os.path.exists(temp_path):
                        os.unlink(temp_path)
        
        if not processed_files:
            os.unlink(zip_path)
            return jsonify({'error': '沒有成功處理任何檔案', 'errors': errors}), 400
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name='renamed_pdfs.zip',
            mimetype='application/zip'
        )
        
    except Exception as e:
        if os.path.exists(zip_path):
            os.unlink(zip_path)
        return jsonify({'error': f'批量處理時發生錯誤: {str(e)}'}), 500

# Vercel serverless function handler
app = app
