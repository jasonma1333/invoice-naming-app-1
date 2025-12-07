from flask import Flask, request, jsonify, render_template_string
import io
import re
import os
import sys

app = Flask(__name__)

# HTML Template with Client-Side Batching Logic
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>HSBC Payment Advice Renamer (Batch)</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/FileSaver.js/2.0.5/FileSaver.min.js"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }
        .container { background: #f9f9f9; padding: 2rem; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #333; margin-bottom: 1.5rem; }
        .upload-area { border: 2px dashed #ccc; padding: 2rem; text-align: center; background: white; border-radius: 4px; margin-bottom: 1rem; }
        .form-group { margin-bottom: 1rem; text-align: left; }
        label { display: block; margin-bottom: 0.5rem; font-weight: bold; }
        input[type="text"] { width: 100%; padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; }
        button { background: #0070f3; color: white; border: none; padding: 0.75rem 1.5rem; border-radius: 4px; cursor: pointer; font-size: 1rem; }
        button:disabled { background: #ccc; cursor: not-allowed; }
        #status { margin-top: 1rem; padding: 1rem; border-radius: 4px; display: none; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
        #log { margin-top: 1rem; font-family: monospace; font-size: 0.9rem; white-space: pre-wrap; background: #eee; padding: 1rem; max-height: 300px; overflow-y: auto; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1>HSBC Payment Advice Renamer</h1>
        
        <div class="form-group">
            <label for="periodCode">Period Code (e.g., P5):</label>
            <input type="text" id="periodCode" value="P1" placeholder="Enter Period Code">
        </div>

        <div class="upload-area">
            <p>Select a folder containing PDF files:</p>
            <input type="file" id="fileInput" webkitdirectory directory multiple accept=".pdf">
            <br><br>
            <button id="processBtn" onclick="processFiles()">Process & Download ZIP</button>
        </div>

        <div id="status"></div>
        <div id="log"></div>
        
        <div style="margin-top: 20px; font-size: 0.8em; color: #666;">
            <a href="/debug" target="_blank">System Debug Info</a>
        </div>
    </div>

    <script>
        function log(msg) {
            const logDiv = document.getElementById('log');
            logDiv.style.display = 'block';
            logDiv.innerText += msg + '\\n';
            console.log(msg);
        }

        async function processFiles() {
            const fileInput = document.getElementById('fileInput');
            const periodCode = document.getElementById('periodCode').value || 'P1';
            const statusDiv = document.getElementById('status');
            const btn = document.getElementById('processBtn');

            if (fileInput.files.length === 0) {
                alert("Please select a folder first.");
                return;
            }

            btn.disabled = true;
            statusDiv.style.display = 'block';
            statusDiv.className = '';
            statusDiv.innerText = 'Processing ' + fileInput.files.length + ' files...';
            document.getElementById('log').innerText = ''; // Clear log

            const zip = new JSZip();
            let processedCount = 0;
            let errorCount = 0;

            try {
                for (let i = 0; i < fileInput.files.length; i++) {
                    const file = fileInput.files[i];
                    
                    // Skip non-PDFs
                    if (!file.name.toLowerCase().endsWith('.pdf')) {
                        continue;
                    }

                    log(`Processing [${i+1}/${fileInput.files.length}]: ${file.name}...`);

                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('period_code', periodCode);

                    try {
                        const response = await fetch('/process_one', {
                            method: 'POST',
                            body: formData
                        });

                        if (!response.ok) {
                            const errText = await response.text();
                            throw new Error(`Server error: ${response.status} - ${errText}`);
                        }

                        const data = await response.json();
                        if (data.error) {
                            throw new Error(data.error);
                        }

                        // Add renamed file to zip
                        zip.file(data.new_name, file);
                        log(`  -> Renamed to: ${data.new_name}`);
                        processedCount++;

                    } catch (err) {
                        log(`  -> ERROR: ${err.message}`);
                        errorCount++;
                        zip.file("UNPROCESSED_" + file.name, file);
                    }
                }

                if (processedCount === 0 && errorCount > 0) {
                    throw new Error("All files failed to process. Check the log for details.");
                }

                statusDiv.innerText = 'Generating ZIP file...';
                const content = await zip.generateAsync({type: "blob"});
                saveAs(content, `renamed_invoices_${periodCode}.zip`);

                statusDiv.className = 'success';
                statusDiv.innerText = `Done! Processed: ${processedCount}, Errors: ${errorCount}. ZIP downloaded.`;

            } catch (e) {
                statusDiv.className = 'error';
                statusDiv.innerText = 'Error: ' + e.message;
                alert("An error occurred: " + e.message);
            } finally {
                btn.disabled = false;
            }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/debug')
def debug():
    try:
        import pypdf
        pypdf_version = pypdf.__version__
    except ImportError:
        pypdf_version = "Not Installed"
    except Exception as e:
        pypdf_version = f"Error: {str(e)}"
        
    return jsonify({
        "python_version": sys.version,
        "pypdf_version": pypdf_version,
        "cwd": os.getcwd(),
        "files": os.listdir('.')
    })

@app.route('/process_one', methods=['POST'])
def process_one():
    try:
        # Lazy import to prevent startup crash
        try:
            from pypdf import PdfReader
        except ImportError:
            return jsonify({"error": "Server Configuration Error: pypdf library not found. Please check requirements.txt"}), 500

        if 'file' not in request.files:
            return jsonify({"error": "No file part"}), 400
        
        file = request.files['file']
        period_code = request.form.get('period_code', 'P1')
        
        if file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        # Read PDF using pypdf
        try:
            # Create a copy of the stream for pypdf
            file_stream = io.BytesIO(file.read())
            reader = PdfReader(file_stream)
            
            if len(reader.pages) == 0:
                return jsonify({"error": "Empty PDF"}), 400
                
            text = reader.pages[0].extract_text()
            
        except Exception as e:
            return jsonify({"error": f"Failed to read PDF: {str(e)}"}), 500

        # Extraction Logic (Regex)
        extracted_info = {}
        
        # 1. Extract Year
        # Look for "Advice sending date" followed by date
        date_match = re.search(r"Advice sending date.*?(\d{1,2}\s+\w{3}\s+(\d{4}))", text, re.DOTALL | re.IGNORECASE)
        if date_match:
            year_short = date_match.group(2)[-2:]
            extracted_info['year'] = year_short
        else:
            # Fallback: Try to find just a date pattern if the label is missing/garbled
            # 20 Jun 2025
            fallback_date = re.search(r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{4})", text, re.IGNORECASE)
            if fallback_date:
                extracted_info['year'] = fallback_date.group(1)[-2:]
            else:
                return jsonify({"error": "Could not find date in PDF"}), 400

        # 2. Extract Outlet Info
        # Pattern: 1208008138/ APC-IT801
        outlet_match = re.search(r"(\d{10,})\s*/\s*([A-Z]{3})\s*-?\s*([A-Z0-9]+)", text)
        if outlet_match:
            extracted_info['outlet_num'] = outlet_match.group(1)
            extracted_info['bene_abbr'] = outlet_match.group(2)
            extracted_info['outlet_code'] = outlet_match.group(3)
        else:
            return jsonify({"error": "Could not find Outlet/Bene info pattern"}), 400

        # Generate New Filename
        new_filename = (
            f"{extracted_info['year']}_"
            f"{period_code}_"
            f"{extracted_info['bene_abbr']}_"
            f"{extracted_info['outlet_code']}_"
            f"{extracted_info['outlet_num']}.pdf"
        )

        return jsonify({"new_name": new_filename})

    except Exception as e:
        return jsonify({"error": f"Server Error: {str(e)}"}), 500

# For local testing
if __name__ == '__main__':
    app.run(debug=True, port=3000)
