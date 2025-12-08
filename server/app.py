import os
import zipfile
from flask import Flask, request, render_template, jsonify
from azure.storage.blob import BlobServiceClient
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# --- CONFIGURATION ---
# Load connection string from environment variable for security
CONNECT_STR = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME', 'appmonitor')
DOWNLOAD_FOLDER = "server_downloads"
EXTRACT_FOLDER = "server_extracted_logs"

# Ensure directories exist
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(EXTRACT_FOLDER, exist_ok=True)

def get_file_from_azure(filename):
    """
    Downloads a file from Azure Blob Storage to the local DOWNLOAD_FOLDER.
    """
    try:
        if not CONNECT_STR:
            print("Error: AZURE_STORAGE_CONNECTION_STRING is not set in .env file.")
            return None

        blob_service_client = BlobServiceClient.from_connection_string(CONNECT_STR)
        blob_client = blob_service_client.get_blob_client(container=CONTAINER_NAME, blob=filename)
        
        # Security: Sanitize the filename to prevent path traversal attacks
        safe_filename = secure_filename(filename)
        local_zip_path = os.path.join(DOWNLOAD_FOLDER, safe_filename)
        
        print(f"Downloading {filename} to {local_zip_path}...")
        with open(local_zip_path, "wb") as download_file:
            download_file.write(blob_client.download_blob().readall())
            
        print(f"Downloaded {filename} successfully.")
        return local_zip_path
    except Exception as e:
        print(f"Azure Download Error: {e}")
        return None

def unzip_file(zip_path):
    """
    Unzips the given zip file into the EXTRACT_FOLDER.
    """
    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(EXTRACT_FOLDER)
        print(f"Extracted {zip_path} to {EXTRACT_FOLDER}")
        return True
    except Exception as e:
        print(f"Unzip Error: {e}")
        return False

def parse_logs_from_disk():
    """
    Reads all text/log files from the EXTRACT_FOLDER and parses them.
    Also looks into .zip files found in the folder.
    Returns a list of dictionaries: [{'content': '...', 'status': '...'}, ...]
    """
    processed_lines = []
    try:
        # Iterate over all files in the extract folder
        for root, dirs, files in os.walk(EXTRACT_FOLDER):
            for file_name in files:
                full_path = os.path.join(root, file_name)
                
                # Case 1: Text or Log files
                if file_name.endswith('.txt') or file_name.endswith('.log'):
                    try:
                        with open(full_path, 'r', encoding='utf-8', errors='ignore') as log_file:
                            for line in log_file:
                                line = line.strip()
                                if not line: continue
                                
                                # Simple logic to highlight errors
                                status = "Danger" if "ERROR" in line.upper() else "Normal"
                                processed_lines.append({"content": line, "status": status})
                    except Exception as e:
                        print(f"Error reading file {file_name}: {e}")

                # Case 2: Zip files (Nested or just present)
                elif file_name.endswith('.zip'):
                    try:
                        with zipfile.ZipFile(full_path, 'r') as zf:
                            for internal_filename in zf.namelist():
                                if internal_filename.endswith('.txt') or internal_filename.endswith('.log'):
                                    with zf.open(internal_filename) as internal_file:
                                        # zipfile.open returns bytes, need to decode
                                        for line_bytes in internal_file:
                                            line = line_bytes.decode('utf-8', errors='ignore').strip()
                                            if not line: continue
                                            status = "Danger" if "ERROR" in line.upper() else "Normal"
                                            processed_lines.append({"content": line, "status": status})
                    except Exception as e:
                        print(f"Error reading zip file {file_name}: {e}")
                        
        return processed_lines
    except Exception as e:
        print(f"Error walking log directory: {e}")
        return []

@app.route('/files', methods=['POST'])
def download_and_unzip():
    """
    Endpoint to trigger file download and extraction.
    Expects JSON: { "filename": "log_data.zip" }
    """
    data = request.get_json()
    filename = data.get('filename')
    
    if not filename:
        return jsonify({"error": "No filename provided"}), 400
    
    # Note: We do NOT sanitize 'filename' here because we need to preserve 
    # folder paths (e.g. "1/monitor.log.zip") for Azure.
    # The get_file_from_azure function handles local path security internally.
    
    # 1. Download from Azure
    zip_path = get_file_from_azure(filename)
    if not zip_path:
        return jsonify({"error": "Failed to download from Azure. Check server logs."}), 500
        
    # 2. Unzip to disk
    success = unzip_file(zip_path)
    if success:
        return jsonify({"message": "File downloaded and extracted successfully."}), 200
    else:
        return jsonify({"error": "Failed to extract zip file"}), 500

@app.route('/report', methods=['GET'])
def generate_report():
    """
    Endpoint to view the report.
    Reads parsed data from the extracted files on disk.
    """
    logs = parse_logs_from_disk()
    return render_template('report.html', logs=logs)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
