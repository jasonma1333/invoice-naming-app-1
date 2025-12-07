from flask import Flask, request, send_file, jsonify
import os
import tempfile
from werkzeug.utils import secure_filename
import re

try:
    import fitz
except ImportError:
    fitz = None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

class HSBCRenamer:
    def __init__(self):
        self.pattern = re.compile(r"(\d{10,})\s*/\s*([A-Z]{3})\s*-?\s*([A-Z0-9]+)")
    
    def extract_info(self, pdf_path):
        if not fitz:
            return None
        try:
            doc = fitz.open(pdf_path)
            text = "".join([doc.load_page(i).get_text() for i in range(min(3, len(doc)))])
            doc.close()
            match = self.pattern.search(text)
            return {'outlet_num': match.group(1), 'bene_abbr': match.group(2), 'outlet_code': match.group(3)} if match else None
        except:
            return None
    
    def generate_filename(self, info, period_code):
        from datetime import datetime
        year = datetime.now().strftime("%y")
        period = period_code.upper().replace('P', '')
        return f"{year}_P{period}_{info['bene_abbr']}_{info['outlet_code']}_{info['outlet_num']}.pdf"

@app.route("/")
def index():
    return """<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>HSBC 重命名工具</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{font-family:-apple-system,sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:20px}.container{max-width:900px;margin:0 auto;background:white;border-radius:20px;padding:40px;box-shadow:0 20px 60px rgba(0,0,0,0.2)}h1{text-align:center;color:#333;margin-bottom:10px;font-size:2.5em}.subtitle{text-align:center;color:#666;margin-bottom:40px}.settings{background:#f8f9fa;border-radius:15px;padding:25px;margin-bottom:30px}.label{display:block;margin-bottom:8px;font-weight:500;color:#555}.input{width:100%;padding:12px 15px;border:2px solid #e0e0e0;border-radius:10px;font-size:1em}.input:focus{outline:none;border-color:#667eea}.upload{border:3px dashed #ddd;border-radius:15px;padding:60px 20px;text-align:center;margin:30px 0;cursor:pointer}.icon{font-size:4em;margin-bottom:20px}.btn{padding:15px 30px;border:none;border-radius:12px;font-size:1em;font-weight:600;cursor:pointer;background:linear-gradient(45deg,#667eea,#764ba2);color:white}.btn:hover{transform:translateY(-2px);box-shadow:0 10px 25px rgba(102,126,234,0.4)}.alert{padding:15px 20px;border-radius:10px;margin:20px 0;font-weight:500}.error{background:#f8d7da;color:#721c24}.success{background:#d4edda;color:#155724}</style>
</head>
<body><div class="container"><h1>📄 HSBC Payment Advice 重命名工具</h1><p class="subtitle">自動提取 PDF 資訊並重新命名</p><div class="settings"><label class="label">期間代碼</label><input type="text" id="code" class="input" placeholder="P1, P8, P9" value="P8"></div><div class="upload" onclick="document.getElementById('file').click()"><div class="icon">☁️</div><div>點擊上傳 PDF</div></div><input type="file" id="file" style="display:none" accept=".pdf" onchange="upload(event)"><div id="alert"></div></div>
<script>function show(msg,type){document.getElementById('alert').innerHTML='<div class="alert '+type+'">'+msg+'</div>'}
async function upload(e){const f=e.target.files[0];if(!f)return;const code=document.getElementById('code').value.trim();if(!code){show('請輸入期間代碼','error');return}const data=new FormData();data.append('file',f);data.append('period_code',code);try{const r=await fetch('/upload',{method:'POST',body:data});if(!r.ok)throw new Error('處理失敗');const blob=await r.blob();const url=window.URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;const cd=r.headers.get('Content-Disposition');a.download=cd?cd.split('filename=')[1].replace(/"/g,''):'renamed.pdf';document.body.appendChild(a);a.click();window.URL.revokeObjectURL(url);show('✅ 檔案已下載','success')}catch(err){show('❌ '+err.message,'error')}}</script>
</body></html>"""

@app.route("/health")
def health():
    return jsonify({"status":"ok"})

@app.route("/upload",methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error":"缺少檔案"}),400
    f=request.files["file"]
    if not f.filename or not f.filename.endswith('.pdf'):
        return jsonify({"error":"無效 PDF"}),400
    code=request.form.get("period_code","P1").upper()
    if not code.startswith('P'):
        code=f"P{code}"
    with tempfile.NamedTemporaryFile(delete=False,suffix=".pdf") as tmp:
        f.save(tmp.name)
        path=tmp.name
    try:
        r=HSBCRenamer()
        info=r.extract_info(path)
        if not info:
            os.unlink(path)
            return jsonify({"error":"無法解析"}),400
        name=secure_filename(r.generate_filename(info,code))
        return send_file(path,as_attachment=True,download_name=name,mimetype="application/pdf")
    except Exception as e:
        if os.path.exists(path):
            os.unlink(path)
        return jsonify({"error":str(e)}),500
