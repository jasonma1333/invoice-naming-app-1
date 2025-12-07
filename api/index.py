from flask import Flask, request, send_file, jsonify
import os
import tempfile
import zipfile
from werkzeug.utils import secure_filename
import re

try:
    import fitz
except ImportError:
    fitz = None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4.5 * 1024 * 1024  # Vercel 限制 4.5MB

class HSBCRenamer:
    def __init__(self):
        self.pattern = re.compile(r"(\d{10,})\s*/\s*([A-Z]{3})\s*-?\s*([A-Z0-9]+)")
    
    def extract_info(self, pdf_path):
        if not fitz: return None
        try:
            doc = fitz.open(pdf_path)
            text = "".join([doc.load_page(i).get_text() for i in range(min(3, len(doc)))])
            doc.close()
            match = self.pattern.search(text)
            if match:
                return {'outlet_num': match.group(1), 'bene_abbr': match.group(2), 'outlet_code': match.group(3)}
            return None
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
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSBC 批量重命名工具</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; display: flex; justify-content: center; align-items: center; }
        .container { width: 100%; max-width: 600px; background: white; border-radius: 20px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.2); }
        h1 { text-align: center; color: #333; margin-bottom: 10px; font-size: 1.8em; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 0.9em; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #555; }
        input[type="text"] { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 1em; }
        .upload-box { border: 2px dashed #ddd; border-radius: 15px; padding: 40px 20px; text-align: center; cursor: pointer; transition: all 0.3s; background: #f8f9fa; }
        .upload-box:hover { border-color: #667eea; background: #f0f4ff; }
        .btn { width: 100%; padding: 15px; border: none; border-radius: 12px; font-size: 1em; font-weight: 600; cursor: pointer; background: linear-gradient(45deg, #667eea, #764ba2); color: white; margin-top: 20px; }
        .btn:disabled { opacity: 0.7; cursor: not-allowed; }
        #status { margin-top: 20px; padding: 15px; border-radius: 10px; display: none; font-size: 0.9em; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .file-list { margin-top: 15px; max-height: 150px; overflow-y: auto; font-size: 0.85em; color: #666; text-align: left; border-top: 1px solid #eee; padding-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 HSBC 批量重命名</h1>
        <p class="subtitle">支援多檔上傳 (Vercel 限制總大小 4.5MB)</p>
        
        <div class="form-group">
            <label>期間代碼 (Period Code)</label>
            <input type="text" id="code" value="P8" placeholder="例如: P1, P8">
        </div>
        
        <div class="upload-box" onclick="document.getElementById('file').click()">
            <div style="font-size: 3em; margin-bottom: 10px;">📂</div>
            <div id="uploadText">點擊選擇 PDF 檔案 (可多選)</div>
            <div style="font-size: 0.8em; color: #999; margin-top: 5px;">支援 Ctrl/Cmd+點擊 或 拖曳多個檔案</div>
        </div>
        <!-- multiple 屬性允許選擇多個檔案 -->
        <input type="file" id="file" accept=".pdf" multiple style="display:none" onchange="updateFileList(this)">
        
        <div id="fileList" class="file-list"></div>
        
        <button class="btn" onclick="upload()" id="btn">開始處理</button>
        <div id="status"></div>
    </div>

    <script>
        function updateFileList(input) {
            const list = document.getElementById('fileList');
            const text = document.getElementById('uploadText');
            list.innerHTML = '';
            
            if(input.files && input.files.length > 0) {
                let totalSize = 0;
                text.innerText = `已選擇 ${input.files.length} 個檔案`;
                
                for(let i=0; i<input.files.length; i++) {
                    const file = input.files[i];
                    totalSize += file.size;
                    const div = document.createElement('div');
                    div.innerText = `• ${file.name} (${(file.size/1024).toFixed(1)}KB)`;
                    list.appendChild(div);
                }
                
                if(totalSize > 4.5 * 1024 * 1024) {
                    showStatus('⚠️ 警告: 總檔案大小超過 4.5MB，上傳可能會失敗', 'error');
                } else {
                    document.getElementById('status').style.display = 'none';
                }
            } else {
                text.innerText = "點擊選擇 PDF 檔案 (可多選)";
            }
        }

        async function upload() {
            const fileInput = document.getElementById('file');
            if(!fileInput.files || fileInput.files.length === 0) {
                showStatus('請先選擇檔案', 'error');
                return;
            }
            
            const btn = document.getElementById('btn');
            const originalText = btn.innerText;
            btn.disabled = true;
            btn.innerText = '處理中...';
            
            const formData = new FormData();
            for(let i=0; i<fileInput.files.length; i++) {
                formData.append('file', fileInput.files[i]);
            }
            formData.append('period_code', document.getElementById('code').value);
            
            try {
                const res = await fetch('/upload', {method: 'POST', body: formData});
                if(res.ok) {
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    const contentDisposition = res.headers.get('Content-Disposition');
                    let filename = 'renamed_files.zip';
                    if (contentDisposition) {
                        const match = contentDisposition.match(/filename="?([^"]+)"?/);
                        if (match && match[1]) filename = match[1];
                    }
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    showStatus('✅ 成功！已下載: ' + filename, 'success');
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
    files = request.files.getlist("file")
    if not files or len(files) == 0:
        return jsonify({"error": "未找到檔案"}), 400
    
    # 檢查總大小
    total_size = 0
    for f in files:
        f.seek(0, os.SEEK_END)
        total_size += f.tell()
        f.seek(0)
    
    if total_size > 4.5 * 1024 * 1024:
        return jsonify({"error": f"總檔案大小 ({total_size/1024/1024:.1f}MB) 超過 Vercel 限制 (4.5MB)"}), 400

    period_code = request.form.get("period_code", "P1")
    if not period_code.startswith('P'): period_code = f"P{period_code}"
    
    renamer = HSBCRenamer()
    
    # 如果只有一個檔案，直接返回 PDF
    if len(files) == 1:
        f = files[0]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            f.save(tmp.name)
            path = tmp.name
        
        try:
            info = renamer.extract_info(path)
            if not info:
                os.unlink(path)
                return jsonify({"error": "無法解析 PDF"}), 400
            
            new_name = renamer.generate_filename(info, period_code)
            return send_file(path, as_attachment=True, download_name=secure_filename(new_name), mimetype="application/pdf")
        except Exception as e:
            if os.path.exists(path): os.unlink(path)
            return jsonify({"error": str(e)}), 500

    # 多個檔案，打包成 ZIP
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "renamed_files.zip")
            processed_count = 0
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for f in files:
                    if not f.filename: continue
                    
                    # 保存原始檔案
                    temp_path = os.path.join(temp_dir, secure_filename(f.filename))
                    f.save(temp_path)
                    
                    # 處理
                    info = renamer.extract_info(temp_path)
                    if info:
                        new_name = renamer.generate_filename(info, period_code)
                        zipf.write(temp_path, secure_filename(new_name))
                        processed_count += 1
                    else:
                        # 如果解析失敗，使用原名加上前綴
                        zipf.write(temp_path, f"ERROR_{secure_filename(f.filename)}")
            
            if processed_count == 0:
                return jsonify({"error": "沒有檔案被成功解析"}), 400
                
            return send_file(zip_path, as_attachment=True, download_name=f"renamed_{period_code}.zip", mimetype="application/zip")
            
    except Exception as e:
        return jsonify({"error": f"批次處理失敗: {str(efrom flask import Flask, request, send_file, jsonify
import os
import tempfile
import zipfile
from werkzeug.utils import secure_filename
import re

try:
    import fitz
except ImportError:
    fitz = None

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4.5 * 1024 * 1024  # Vercel 限制 4.5MB

class HSBCRenamer:
    def __init__(self):
        self.pattern = re.compile(r"(\d{10,})\s*/\s*([A-Z]{3})\s*-?\s*([A-Z0-9]+)")
    
    def extract_info(self, pdf_path):
        if not fitz: return None
        try:
            doc = fitz.open(pdf_path)
            text = "".join([doc.load_page(i).get_text() for i in range(min(3, len(doc)))])
            doc.close()
            match = self.pattern.search(text)
            if match:
                return {'outlet_num': match.group(1), 'bene_abbr': match.group(2), 'outlet_code': match.group(3)}
            return None
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
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSBC 批量重命名工具</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; padding: 20px; display: flex; justify-content: center; align-items: center; }
        .container { width: 100%; max-width: 600px; background: white; border-radius: 20px; padding: 40px; box-shadow: 0 20px 60px rgba(0,0,0,0.2); }
        h1 { text-align: center; color: #333; margin-bottom: 10px; font-size: 1.8em; }
        .subtitle { text-align: center; color: #666; margin-bottom: 30px; font-size: 0.9em; }
        .form-group { margin-bottom: 20px; }
        label { display: block; margin-bottom: 8px; font-weight: 600; color: #555; }
        input[type="text"] { width: 100%; padding: 12px; border: 2px solid #e0e0e0; border-radius: 10px; font-size: 1em; }
        .upload-box { border: 2px dashed #ddd; border-radius: 15px; padding: 40px 20px; text-align: center; cursor: pointer; transition: all 0.3s; background: #f8f9fa; }
        .upload-box:hover { border-color: #667eea; background: #f0f4ff; }
        .btn { width: 100%; padding: 15px; border: none; border-radius: 12px; font-size: 1em; font-weight: 600; cursor: pointer; background: linear-gradient(45deg, #667eea, #764ba2); color: white; margin-top: 20px; }
        .btn:disabled { opacity: 0.7; cursor: not-allowed; }
        #status { margin-top: 20px; padding: 15px; border-radius: 10px; display: none; font-size: 0.9em; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .file-list { margin-top: 15px; max-height: 150px; overflow-y: auto; font-size: 0.85em; color: #666; text-align: left; border-top: 1px solid #eee; padding-top: 10px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>📄 HSBC 批量重命名</h1>
        <p class="subtitle">支援多檔上傳 (Vercel 限制總大小 4.5MB)</p>
        
        <div class="form-group">
            <label>期間代碼 (Period Code)</label>
            <input type="text" id="code" value="P8" placeholder="例如: P1, P8">
        </div>
        
        <div class="upload-box" onclick="document.getElementById('file').click()">
            <div style="font-size: 3em; margin-bottom: 10px;">📂</div>
            <div id="uploadText">點擊選擇 PDF 檔案 (可多選)</div>
            <div style="font-size: 0.8em; color: #999; margin-top: 5px;">支援 Ctrl/Cmd+點擊 或 拖曳多個檔案</div>
        </div>
        <!-- multiple 屬性允許選擇多個檔案 -->
        <input type="file" id="file" accept=".pdf" multiple style="display:none" onchange="updateFileList(this)">
        
        <div id="fileList" class="file-list"></div>
        
        <button class="btn" onclick="upload()" id="btn">開始處理</button>
        <div id="status"></div>
    </div>

    <script>
        function updateFileList(input) {
            const list = document.getElementById('fileList');
            const text = document.getElementById('uploadText');
            list.innerHTML = '';
            
            if(input.files && input.files.length > 0) {
                let totalSize = 0;
                text.innerText = `已選擇 ${input.files.length} 個檔案`;
                
                for(let i=0; i<input.files.length; i++) {
                    const file = input.files[i];
                    totalSize += file.size;
                    const div = document.createElement('div');
                    div.innerText = `• ${file.name} (${(file.size/1024).toFixed(1)}KB)`;
                    list.appendChild(div);
                }
                
                if(totalSize > 4.5 * 1024 * 1024) {
                    showStatus('⚠️ 警告: 總檔案大小超過 4.5MB，上傳可能會失敗', 'error');
                } else {
                    document.getElementById('status').style.display = 'none';
                }
            } else {
                text.innerText = "點擊選擇 PDF 檔案 (可多選)";
            }
        }

        async function upload() {
            const fileInput = document.getElementById('file');
            if(!fileInput.files || fileInput.files.length === 0) {
                showStatus('請先選擇檔案', 'error');
                return;
            }
            
            const btn = document.getElementById('btn');
            const originalText = btn.innerText;
            btn.disabled = true;
            btn.innerText = '處理中...';
            
            const formData = new FormData();
            for(let i=0; i<fileInput.files.length; i++) {
                formData.append('file', fileInput.files[i]);
            }
            formData.append('period_code', document.getElementById('code').value);
            
            try {
                const res = await fetch('/upload', {method: 'POST', body: formData});
                if(res.ok) {
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    const contentDisposition = res.headers.get('Content-Disposition');
                    let filename = 'renamed_files.zip';
                    if (contentDisposition) {
                        const match = contentDisposition.match(/filename="?([^"]+)"?/);
                        if (match && match[1]) filename = match[1];
                    }
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(url);
                    showStatus('✅ 成功！已下載: ' + filename, 'success');
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
    files = request.files.getlist("file")
    if not files or len(files) == 0:
        return jsonify({"error": "未找到檔案"}), 400
    
    # 檢查總大小
    total_size = 0
    for f in files:
        f.seek(0, os.SEEK_END)
        total_size += f.tell()
        f.seek(0)
    
    if total_size > 4.5 * 1024 * 1024:
        return jsonify({"error": f"總檔案大小 ({total_size/1024/1024:.1f}MB) 超過 Vercel 限制 (4.5MB)"}), 400

    period_code = request.form.get("period_code", "P1")
    if not period_code.startswith('P'): period_code = f"P{period_code}"
    
    renamer = HSBCRenamer()
    
    # 如果只有一個檔案，直接返回 PDF
    if len(files) == 1:
        f = files[0]
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            f.save(tmp.name)
            path = tmp.name
        
        try:
            info = renamer.extract_info(path)
            if not info:
                os.unlink(path)
                return jsonify({"error": "無法解析 PDF"}), 400
            
            new_name = renamer.generate_filename(info, period_code)
            return send_file(path, as_attachment=True, download_name=secure_filename(new_name), mimetype="application/pdf")
        except Exception as e:
            if os.path.exists(path): os.unlink(path)
            return jsonify({"error": str(e)}), 500

    # 多個檔案，打包成 ZIP
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "renamed_files.zip")
            processed_count = 0
            
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for f in files:
                    if not f.filename: continue
                    
                    # 保存原始檔案
                    temp_path = os.path.join(temp_dir, secure_filename(f.filename))
                    f.save(temp_path)
                    
                    # 處理
                    info = renamer.extract_info(temp_path)
                    if info:
                        new_name = renamer.generate_filename(info, period_code)
                        zipf.write(temp_path, secure_filename(new_name))
                        processed_count += 1
                    else:
                        # 如果解析失敗，使用原名加上前綴
                        zipf.write(temp_path, f"ERROR_{secure_filename(f.filename)}")
            
            if processed_count == 0:
                return jsonify({"error": "沒有檔案被成功解析"}), 400
                
            return send_file(zip_path, as_attachment=True, download_name=f"renamed_{period_code}.zip", mimetype="application/zip")
            
    except Exception as e:
        return jsonify({"error": f"批次處理失敗: {str(e
