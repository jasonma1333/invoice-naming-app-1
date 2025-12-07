from flask import Flask, request, send_file, jsonify, render_template
import os
import sys
import tempfile
import zipfile
from werkzeug.utils import secure_filename

# 修復導入路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

try:
    from hsbc_payment_renamer import HSBCPaymentAdviceRenamer
except ImportError:
    # 如果導入失敗,定義一個簡單版本
    import re
    import fitz
    
    class HSBCPaymentAdviceRenamer:
        def __init__(self):
            self.pattern = re.compile(r"(\d{10,})\s*/\s*([A-Z]{3})\s*-?\s*([A-Z0-9]+)")
        
        def extract_pdf_info(self, pdf_path):
            try:
                doc = fitz.open(pdf_path)
                text = ""
                for page_num in range(min(3, len(doc))):
                    text += doc.load_page(page_num).get_text()
                doc.close()
                
                match = self.pattern.search(text)
                if match:
                    outlet_num = match.group(1)
                    bene_abbr = match.group(2)
                    outlet_code = match.group(3)
                    return {
                        'outlet_num': outlet_num,
                        'bene_abbr': bene_abbr,
                        'outlet_code': outlet_code
                    }
                return None
            except Exception:
                return None
        
        def generate_new_filename(self, info, period_code):
            from datetime import datetime
            year = datetime.now().strftime("%y")
            period = period_code.upper().replace('P', '')
            return f"{year}_P{period}_{info['bene_abbr']}_{info['outlet_code']}_{info['outlet_num']}.pdf"

app = Flask(__name__, 
            template_folder=os.path.join(parent_dir, 'templates'))
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

ALLOWED_EXTENSIONS = {"pdf"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/health")
def health():
    return jsonify({"status": "ok", "message": "Service is running"})

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "缺少檔案欄位 file"}), 400
    
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "未選擇檔案"}), 400
    
    if not allowed_file(f.filename):
        return jsonify({"error": "僅支援 PDF"}), 400

    period_code = request.form.get("period_code", "P1").upper()
    if not period_code.startswith('P'):
        period_code = f"P{period_code}"

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        f.save(tmp.name)
        temp_path = tmp.name

    try:
        renamer = HSBCPaymentAdviceRenamer()
        info = renamer.extract_pdf_info(temp_path)
        
        if info:
            new_name = renamer.generate_new_filename(info, period_code)
        else:
            os.unlink(temp_path)
            return jsonify({"error": "無法解析 PDF 內容"}), 400

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
        return jsonify({"error": f"處理失敗: {str(e)}"}), 500

@app.route("/batch_upload", methods=["POST"])
def batch_upload():
    files = request.files.getlist('files')
    
    if not files or all(f.filename == '' for f in files):
        return jsonify({"error": "沒有選擇檔案"}), 400
    
    period_code = request.form.get("period_code", "P1").upper()
    if not period_code.startswith('P'):
        period_code = f"P{period_code}"
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
        zip_path = temp_zip.name
    
    processed_files = []
    
    try:
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in files:
                if file.filename == '' or not allowed_file(file.filename):
                    continue
                
                try:
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
                        
                        zipf.write(temp_path, safe_filename)
                        processed_files.append(safe_filename)
                    
                    os.unlink(temp_path)
                except Exception:
                    if 'temp_path' in locals() and os.path.exists(temp_path):
                        os.unlink(temp_path)
        
        if not processed_files:
            os.unlink(zip_path)
            return jsonify({'error': '沒有成功處理任何檔案'}), 400
        
        return send_file(
            zip_path,
            as_attachment=True,
            download_name='renamed_pdfs.zip',
            mimetype='application/zip'
        )
        
    except Exception as e:
        if os.path.exists(zip_path):
            os.unlink(zip_path)
        return jsonify({'error': f'批量處理失敗: {str(e)}'}), 500
