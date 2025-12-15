import os
import sys
import zipfile
import shutil
import sqlite3
import jwt
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, render_template, jsonify
from flask_cors import CORS
from azure.storage.blob import BlobServiceClient
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from gemini_service import GeminiService

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
# Load connection string from environment variable for security
CONNECT_STR = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME', 'appmonitor')
SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_here') # Change this in production!
DOWNLOAD_FOLDER = "server_downloads"
EXTRACT_FOLDER = "server_extracted_logs"
DB_NAME = "monitor.db"

# Ensure directories exist
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)
os.makedirs(EXTRACT_FOLDER, exist_ok=True)

def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("PRAGMA foreign_keys = ON;")
        
        # Create users table
        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'user'
            )
        ''')
        
        # Migration: Add role column if it doesn't exist (for existing DBs)
        try:
            c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
        except sqlite3.OperationalError:
            # Column already exists
            pass

        # Ensure default admin exists
        c.execute("SELECT id FROM users WHERE role = 'admin'")
        if not c.fetchone():
            admin_password = generate_password_hash("admin123")
            try:
                c.execute("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)", 
                          ("System Admin", "admin@monitor.com", admin_password, "admin"))
                print("Default admin account created: admin@monitor.com / admin123")
            except sqlite3.IntegrityError:
                pass # Email might exist as user, manual intervention needed or ignore

        c.execute('''
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                log_file_url TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        conn.commit()

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            current_user_id = data['user_id']
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        
        return f(current_user_id, *args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith("Bearer "):
                token = auth_header.split(" ")[1]
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            if data.get('role') != 'admin':
                 return jsonify({'message': 'Admin privilege required!'}), 403
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        
        return f(*args, **kwargs)
    return decorated

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
    Clears the folder first to avoid mixing logs.
    """
    try:
        # Clear existing files
        if os.path.exists(EXTRACT_FOLDER):
            shutil.rmtree(EXTRACT_FOLDER)
        os.makedirs(EXTRACT_FOLDER, exist_ok=True)

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

@app.route('/users', methods=['GET'])
def get_users():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users")
        users = [{"id": row[0], "name": row[1], "email": row[2]} for row in c.fetchall()]
        return jsonify(users)

@app.route('/users', methods=['POST'])
def create_user():
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        data = request.get_json()
        
        if not data or not data.get('email') or not data.get('password') or not data.get('name'):
             return jsonify({"error": "Missing name, email or password"}), 400

        hashed_password = generate_password_hash(data['password'])
        role = data.get('role', 'user') # Default to user, but allow setting if needed (or restrict this)

        try:
            c.execute("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)", 
                      (data['name'], data['email'], hashed_password, role))
            conn.commit()
            return jsonify({"id": c.lastrowid, "message": "User created"}), 201
        except sqlite3.IntegrityError:
            return jsonify({"error": "User with this email already exists"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 400

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Missing email or password"}), 400

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, password, role FROM users WHERE email = ?", (data['email'],))
        user = c.fetchone()

        if user and check_password_hash(user[2], data['password']):
            token = jwt.encode({
                'user_id': user[0],
                'role': user[3],
                'exp': datetime.utcnow() + timedelta(hours=24)
            }, SECRET_KEY, algorithm="HS256")
            
            return jsonify({'token': token, 'user_id': user[0], 'name': user[1], 'role': user[3]})
        
        return jsonify({"error": "Invalid credentials"}), 401

@app.route('/logs', methods=['GET'])
@token_required
def get_logs(current_user_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM logs WHERE user_id = ?", (current_user_id,))
        logs = [{"id": row[0], "user_id": row[1], "log_file_url": row[2], "timestamp": row[3]} for row in c.fetchall()]
        return jsonify(logs)

@app.route('/logs', methods=['POST'])
@token_required
def create_log(current_user_id):
    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        data = request.get_json()
        try:
            timestamp = data.get('timestamp', datetime.now().isoformat())
            # Use current_user_id from the token, not from the request body
            c.execute("INSERT INTO logs (user_id, log_file_url, timestamp) VALUES (?, ?, ?)", 
                      (current_user_id, data['log_file_url'], timestamp))
            conn.commit()
            return jsonify({"id": c.lastrowid, "message": "Log entry created"}), 201
        except sqlite3.IntegrityError:
            return jsonify({"error": "Constraint violation"}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 400

@app.route('/get_user_id', methods=['POST'])
def get_user_id():
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({"error": "Username is required"}), 400

    with sqlite3.connect(DB_NAME) as conn:
        c = conn.cursor()
        # Try to find by name
        c.execute("SELECT id FROM users WHERE name = ?", (username,))
        row = c.fetchone()
        
        if row:
            return jsonify({"user_id": row[0]})
        else:
            # Try to find by email just in case they entered email
            c.execute("SELECT id FROM users WHERE email = ?", (username,))
            row = c.fetchone()
            if row:
                return jsonify({"user_id": row[0]})
                
            return jsonify({"error": "User not found"}), 404

@app.route('/admin/reports', methods=['GET'])
@admin_required
def get_admin_reports():
    """
    API Endpoint for Admin Dashboard to get parsed logs.
    """
    logs = parse_logs_from_disk()
    return jsonify(logs)

@app.route('/', methods=['GET'])
def health_check():
    return "Backend is running!"

if __name__ == '__main__':
    init_db()
    
    # Start Gemini Service
    # Monitor all users (user_id=None) and save reports to 'reports' folder
    gemini_service = GeminiService(reports_dir="reports", user_id_to_monitor=None)
    gemini_service.start()

    # Start Simple Monitor (Client) on the server machine
    try:
        # Add root directory to path to import simple_monitor
        sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from simple_monitor import SimpleMonitor
        
        # Use a default user for the server monitor (e.g., ID 1 which is usually admin)
        # Or create a specific "server_monitor" user if needed.
        # For now, we'll use ID "1" (Admin)
        print("Starting SimpleMonitor for Server (User ID: 1)...")
        monitor = SimpleMonitor(user_id="1", test_mode=False)
        monitor.start()
    except Exception as e:
        print(f"Failed to start SimpleMonitor: {e}")
    
    app.run(debug=True, port=5001)