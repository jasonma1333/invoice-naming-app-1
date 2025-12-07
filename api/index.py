from flask import Flask, request, send_file, jsonify
import os
import tempfile
import zipfile
from werkzeug.utils import secure_filename
import re

# 嘗試導入 PyMuPDF
try:
    import fitz
except ImportError:
    fitz = None

app = Flask(__name__)
# Vercel Serverless 限制請求大小約 4.5MB
app.config['MAX_CONTENT_LENGTH'] = 4.5 * 1024 * 1024

class HSBCRenamer:
    def __init__(self):
        # 匹配 HSBC Payment Advice 的關鍵資訊
        self.pattern = re.compile(r"(\d{10,})\s*/\s*([A-Z]{3})\s*-?\s*([A-Z0-9]+)")
    
    def extract_info(self, pdf_path):
        if not fitz:
            return None
        try:
            doc = fitz.open(pdf_path)
            text = ""
            # 只讀取前 3 頁以提高效能
            for page_num in range(min(3, len(doc))):
                text += doc.load_page(page_num).get_text()
            doc.close()
            
            match = self.pattern.search(text)
            if match:
                return {
                    'outlet_num': match.group(1),
                    'bene_abbr': match.group(2),
                    'outlet_code': match.group(3)
                }
            return None
        except Exception:
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
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSBC Payment Advice 重命名工具</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; display: flex; justify-content: center; align-items: center; }
        .container { width: 100%; max-width: 600px; background: white; border-radius: 20px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.2); }
        h1 { text-align: center; color: #333; margin-bottom: 10px; font-size: 1.8em; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 0.9em; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #555; }
        input[type="text"] { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 1em; transition: border-color 0.3s; }
        input[type="text"]:focus { outline: none; border-color: #667eea; }
        .upload-box { border: 2px dashed #ddd; border-radius: 15px; padding: 40px 20px; text-align: center; cursor: pointer; transition: all 0.3s; background: #f8f9fa; }
        .upload-box:hover { border-color: #667eea; background: #f0f4ff; }
        .btn { width: 100%; padding: 15px; border: none; border-radius: 12px; font-size: 1em; font-weight: 600; cursor: pointer; background: linear-gradient(45deg, #667eea, #764ba2); color: white; margin-top: 20px; transition: transform 0.2s; }
        .btn:hover { transform: translateY(-2px); }
        .btn:disabled { opacity: 0.7; cursor: not-allowed; transform: none; }
        #status { margin-top: 20px; padding: 15px; border-radius: 10px; display: none; font-size: 0.9em; line-height: 1.5; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .loading { display: inline-block; width: 20px; height: 20px; border: 3px solid rgba(255,255,255,.3); border-radius: 50%; border-top-color: white; animation: spin 1s ease-in-out infinite; margin-right: 10px; vertical-align: middle; }
        @keyframes spin { to { transform: rotate(360deg); } }
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 HSBC 重命名工具</h1>
        <p class="subtitle">自動提取 PDF 資訊並重新命名 (Vercel 版)</p>
        
        <div class="form-group">
            <label>期間代碼 (Period Code)</label>
            <input type="text" id="code" value="P8" placeholder="例如: P1, P8">
        </div>
        
        <div class="upload-box" onclick="document.getElementById('file').click()">
            <div style="font-size: 3em; margin-bottom: 10px;">☁️</div>
            <div id="fileName">點擊選擇 PDF 檔案</div>
        </div>
        <input type="file" id="file" accept=".pdf" style="display:none" onchange="updateFileName(this)">
        
        <button class="btn" onclick="upload()" id="btn">開始處理</button>
        
        <div id="status"></div>
    </div>

    <script>
        function updateFileName(input) {
            if(input.files && input.files[0]) {
                document.getElementById('fileName').innerText = "已選擇: " + input.files[0].name;
                document.getElementById('status').style.display = 'none';
            }
        }

        async function upload() {
            const fileInput = document.getElementById('file');
            const file = fileInput.files[0];
            if(!file) {
                showStatus('請先選擇檔案', 'error');
                return;
            }
            
            const btn = document.getElementById('btn');
            const originalText = btn.innerText;
            btn.disabled = true;
            btn.innerHTML = '<span class="loading"></span>處理中...';
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('period_code', document.getElementById('code').value);
            
            try {
                const res = await fetch('/upload', {method: 'POST', body: formData});
                if(res.ok) {
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    const contentDisposition = res.headers.get('Content-Disposition');
                    let filename = 'renamed.pdf';
                    if (contentDisposition) {
                        const match = contentDisposition.match(/filename="?([^"]+)"?/);
                        if (match && match[1]) filename = match[1];
                    }
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    showStatus('✅ 成功！檔案已下載: ' + filename, 'success');
                } else {
                    const err = await res.json();
                    showStatus('❌ 錯誤: ' + (err.error || '未知錯誤'), 'error');
                }
            } catch(e) {
                showStatus('❌ 網絡錯誤: ' + e.message, 'error');
            } finally {
                btn.disabled = false;
                btn.innerText = originalText;
            }
        }

        function showStatus(msg, type) {
            const el = document.getElementById('status');
            el.style.display = 'block';
            el.className = type;
            el.innerText = msg;
        }
    </script>
</body>
</html>"""

@app.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "未找到檔案"}), 400
    
    f = request.files["file"]
    if f.filename == "":
        return jsonify({"error": "未選擇檔案"}), 400
    
    # 檢查檔案大小 (Vercel 限制)
    f.seek(0, os.SEEK_END)
    size = f.tell()
    f.seek(0)
    if size > 4.5 * 1024 * 1024:
        return jsonify({"error": "檔案過大 (超過 4.5MB)，Vercel 免費版限制上傳大小"}), 400

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        f.save(tmp.name)
        path = tmp.name

    try:
        renamer = HSBCRenamer()
        info = renamer.extract_info(path)
        
        if not info:
            os.unlink(path)
            return jsonify({"error": "無法解析 PDF 內容，請確認這是 HSBC Payment Advice"}), 400

        period_code = request.form.get("period_code", "P1")
        if not period_code.startswith('P'): period_code = f"P{period_code}"
        
        new_name = renamer.generate_filename(info, period_code)
        safe = secure_filename(new_name)
        
        return send_file(
            path, 
            as_attachment=True, 
            download_name=safe, 
            mimetype="application/pdf"
        )
    except Exception as e:
        if os.path.exists(path):
            os.unlink(path)
        return jsonify({"error": f"處理失敗: {str(e)}"}), 500
