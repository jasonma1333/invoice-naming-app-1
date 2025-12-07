from flask import Flask, request, send_file, jsonify
import os
import tempfile
import zipfile
from werkzeug.utils import secure_filename
import re
import traceback

# 安全導入 PyMuPDF
fitz = None
startup_error = None
try:
    import fitz
except Exception as e:
    # 捕捉所有錯誤 (包括 OSError, ImportError 等)
    startup_error = f"{type(e).__name__}: {str(e)}"

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4.5 * 1024 * 1024

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
    # 如果啟動時有錯誤，顯示警告
    warning_html = ""
    if startup_error:
        warning_html = f"""
        <div style="background:#f8d7da;color:#721c24;padding:15px;margin-bottom:20px;border-radius:8px;border:1px solid #f5c6cb;">
            <strong>⚠️ 系統警告:</strong> PDF 處理庫加載失敗。<br>
            錯誤詳情: <code>{startup_error}</code><br>
            <small>請檢查 requirements.txt 是否包含 PyMuPDF</small>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSBC 批量重命名工具</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/FileSaver.js/2.0.5/FileSaver.min.js"></script>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f0f2f5; padding: 20px; display: flex; justify-content: center; }}
        .container {{ width: 100%; max-width: 600px; background: white; border-radius: 15px; padding: 30px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); }}
        h1 {{ text-align: center; color: #1a1a1a; margin-bottom: 20px; }}
        .control-group {{ margin-bottom: 20px; }}
        label {{ font-weight: bold; display: block; margin-bottom: 5px; }}
        input[type="text"] {{ width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 8px; box-sizing: border-box; }}
        .btn-group {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 20px; }}
        .btn {{ padding: 15px; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; transition: 0.2s; color: white; text-align: center; }}
        .btn-folder {{ background: #007bff; }}
        .btn-zip {{ background: #28a745; }}
        .btn:hover {{ opacity: 0.9; transform: scale(0.98); }}
        .progress-area {{ margin-top: 20px; display: none; }}
        .progress-bar {{ width: 100%; height: 10px; background: #eee; border-radius: 5px; overflow: hidden; }}
        .progress-fill {{ height: 100%; background: #007bff; width: 0%; transition: width 0.3s; }}
        .log {{ margin-top: 10px; font-size: 0.85em; color: #666; max-height: 150px; overflow-y: auto; border: 1px solid #eee; padding: 10px; border-radius: 5px; }}
        .hidden-input {{ display: none; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 HSBC 批量重命名</h1>
        {warning_html}
        
        <div class="control-group">
            <label>期間代碼 (Period Code)</label>
            <input type="text" id="code" value="P8" placeholder="例如: P8">
        </div>

        <div class="btn-group">
            <button class="btn btn-folder" onclick="document.getElementById('folderInput').click()">
                📂 選擇資料夾 / 多檔<br><small>(推薦! 無大小限制)</small>
            </button>
            <button class="btn btn-zip" onclick="document.getElementById('zipInput').click()">
                📦 上傳 ZIP 檔<br><small>(限 4.5MB 以下)</small>
            </button>
        </div>

        <input type="file" id="folderInput" class="hidden-input" webkitdirectory multiple accept=".pdf" onchange="handleFolder(this)">
        <input type="file" id="zipInput" class="hidden-input" accept=".zip" onchange="handleZip(this)">

        <div id="progressArea" class="progress-area">
            <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                <span id="statusText">準備中...</span>
                <span id="percentText">0%</span>
            </div>
            <div class="progress-bar"><div id="progressFill" class="progress-fill"></div></div>
            <div id="log" class="log"></div>
        </div>
    </div>

    <script>
        const logDiv = document.getElementById('log');
        const progressArea = document.getElementById('progressArea');
        const progressFill = document.getElementById('progressFill');
        
        function log(msg, color='black') {{
            logDiv.innerHTML += `<div style="color:${{color}}">${{msg}}</div>`;
            logDiv.scrollTop = logDiv.scrollHeight;
        }}

        function resetUI() {{
            progressArea.style.display = 'block';
            logDiv.innerHTML = '';
            progressFill.style.width = '0%';
            document.getElementById('percentText').innerText = '0%';
        }}

        async function handleFolder(input) {{
            if (!input.files.length) return;
            resetUI();
            
            const files = Array.from(input.files).filter(f => f.name.toLowerCase().endsWith('.pdf'));
            if (files.length === 0) {{
                log("❌ 沒有找到 PDF 檔案", "red");
                return;
            }}

            log(`📦 準備處理 ${{files.length}} 個檔案...`);
            const zip = new JSZip();
            const periodCode = document.getElementById('code').value;
            let successCount = 0;

            for (let i = 0; i < files.length; i++) {{
                const file = files[i];
                document.getElementById('statusText').innerText = `正在處理 (${{i+1}}/${{files.length}}): ${{file.name}}`;
                
                try {{
                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('period_code', periodCode);

                    const res = await fetch('/process_one', {{ method: 'POST', body: formData }});
                    
                    if (res.ok) {{
                        const blob = await res.blob();
                        const disposition = res.headers.get('Content-Disposition');
                        let newName = file.name;
                        if (disposition && disposition.includes('filename=')) {{
                            newName = disposition.split('filename=')[1].replace(/"/g, '');
                        }}
                        
                        zip.file(newName, blob);
                        log(`✅ 成功: ${{file.name}} -> ${{newName}}`, "green");
                        successCount++;
                    }} else {{
                        log(`⚠️ 失敗: ${{file.name}} (無法解析)`, "orange");
                        zip.file(`ERROR_${{file.name}}`, file);
                    }}
                }} catch (e) {{
                    log(`❌ 錯誤: ${{file.name}} (${{e.message}})`, "red");
                }}

                const percent = Math.round(((i + 1) / files.length) * 100);
                progressFill.style.width = `${{percent}}%`;
                document.getElementById('percentText').innerText = `${{percent}}%`;
            }}

            if (successCount > 0) {{
                document.getElementById('statusText').innerText = "正在打包下載...";
                const content = await zip.generateAsync({{type:"blob"}});
                saveAs(content, `renamed_files_${{periodCode}}.zip`);
                log("🎉 全部完成！已自動下載 ZIP。", "blue");
            }} else {{
                document.getElementById('statusText').innerText = "處理完成，但沒有成功檔案";
            }}
        }}

        async function handleZip(input) {{
            const file = input.files[0];
            if (!file) return;
            
            if (file.size > 4.5 * 1024 * 1024) {{
                alert("❌ ZIP 檔案超過 4.5MB 限制！\\n請改用「選擇資料夾」按鈕，它支援無限大小。");
                input.value = '';
                return;
            }}

            resetUI();
            log("📤 正在上傳 ZIP 處理...", "blue");
            document.getElementById('statusText').innerText = "伺服器處理中...";
            progressFill.style.width = "50%";

            const formData = new FormData();
            formData.append('file', file);
            formData.append('period_code', document.getElementById('code').value);

            try {{
                const res = await fetch('/process_zip', {{ method: 'POST', body: formData }});
                if (res.ok) {{
                    const blob = await res.blob();
                    saveAs(blob, `renamed_zip_result.zip`);
                    progressFill.style.width = "100%";
                    document.getElementById('percentText').innerText = "100%";
                    log("✅ 伺服器處理完成，已下載。", "green");
                }} else {{
                    const err = await res.json();
                    log(`❌ 伺服器錯誤: ${{err.error}}`, "red");
                }}
            }} catch (e) {{
                log(`❌ 網絡錯誤: ${{e.message}}`, "red");
            }}
        }}
    </script>
</body>
</html>"""

@app.route("/process_one", methods=["POST"])
def process_one():
    if "file" not in request.files: return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        f.save(tmp.name)
        path = tmp.name

    try:
        renamer = HSBCRenamer()
        info = renamer.extract_info(path)
        if not info:
            os.unlink(path)
            return jsonify({"error": "Parse failed"}), 400
            
        period_code = request.form.get("period_code", "P1")
        if not period_code.startswith('P'): period_code = f"P{period_code}"
        
        new_name = renamer.generate_filename(info, period_code)
        return send_file(path, as_attachment=True, download_name=secure_filename(new_name), mimetype="application/pdf")
    except Exception as e:
        if os.path.exists(path): os.unlink(path)
        return jsonify({"error": str(e)}), 500

@app.route("/process_zip", methods=["POST"])
def process_zip():
    if "file" not in request.files: return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    
    period_code = request.form.get("period_code", "P1")
    if not period_code.startswith('P'): period_code = f"P{period_code}"
    
    renamer = HSBCRenamer()
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "upload.zip")
            f.save(zip_path)
            
            output_zip_path = os.path.join(temp_dir, "output.zip")
            
            with zipfile.ZipFile(zip_path, 'r') as z_in, zipfile.ZipFile(output_zip_path, 'w') as z_out:
                for item in z_in.infolist():
                    if item.filename.endswith('.pdf'):
                        z_in.extract(item, temp_dir)
                        pdf_path = os.path.join(temp_dir, item.filename)
                        
                        info = renamer.extract_info(pdf_path)
                        if info:
                            new_name = renamer.generate_filename(info, period_code)
                            z_out.write(pdf_path, secure_filename(new_name))
                        else:
                            z_out.write(pdf_path, f"ERROR_{os.path.basename(item.filename)}")
            
            return send_file(output_zip_path, as_attachment=True, download_name=f"renamed_{period_code}.zip", mimetype="application/zip")
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500
