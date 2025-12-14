import logging
import logging.handlers
import os
import zipfile
import time
import sys
import re
import threading
import random
import csv
import requests
from datetime import datetime, timedelta, timezone
from windowslogger import monitor_processes, monitor_active_app

# Global User ID
USER_ID = None
SERVER_URL = "http://localhost:5000"

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    print("Warning: 'python-dotenv' not found. .env file will not be loaded.")

# Try to import Azure Blob Storage library
try:
    from azure.storage.blob import BlobServiceClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    print("Warning: 'azure-storage-blob' not found. Azure upload will be disabled.")

# Try to import browser_history
try:
    from browser_history import get_history
    BROWSER_HISTORY_AVAILABLE = True
except ImportError:
    BROWSER_HISTORY_AVAILABLE = False
    print("Warning: 'browser-history' not found. Browser history tracking will be disabled.")

# Azure Configuration
AZURE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME', 'app-monitor-logs')

# Ensure logs directory exists
LOG_DIR = 'logs'
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# List of process names to ignore (system noise)
NOISY_APPS = {
    "svchost.exe", "backgroundTaskHost.exe", "RuntimeBroker.exe", "updater.exe",
    "conhost.exe", "SearchFilterHost.exe", "SearchProtocolHost.exe", "sppsvc.exe",
    "MoUsoCoreWorker.exe", "FsIso.exe", "SpatialAudioLicenseSrv.exe", "WUDFHost.exe",
    "wslhost.exe", "wslrelay.exe", "vmmemwsl", "vmwp.exe", "git.exe",
    "git-remote-https.exe", "git-credential-manager.exe", "sh.exe", "taskhostw.exe",
    "TextInputHost.exe", "ApplicationFrameHost.exe", "smartscreen.exe", "ctfmon.exe",
    "csrss.exe", "winlogon.exe", "services.exe", "lsass.exe", "smss.exe",
    "fontdrvhost.exe", "dwm.exe", "Memory Compression", "Registry", "System",
    "System Idle Process", "msedgewebview2.exe"
}

class NoiseFilter(logging.Filter):
    """
    Filter out log records for noisy system processes.
    """
    def filter(self, record):
        msg = record.getMessage()
        # Check if any noisy app name is in the message
        for app in NOISY_APPS:
            if f"name={app}" in msg or f"name={app.lower()}" in msg:
                return False
        return True

def upload_to_azure(file_path, blob_name=None):
    """
    Uploads a file to Azure Blob Storage. Returns True if successful, False otherwise.
    """
    if not AZURE_AVAILABLE:
        return False
    
    if not AZURE_CONNECTION_STRING:
        print("Error: AZURE_STORAGE_CONNECTION_STRING environment variable not set. Skipping upload.")
        return False

    try:
        blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
        container_client = blob_service_client.get_container_client(AZURE_CONTAINER_NAME)
        
        # Create container if it doesn't exist
        if not container_client.exists():
            container_client.create_container()

        if not blob_name:
            blob_name = os.path.basename(file_path)
            
        blob_client = container_client.get_blob_client(blob_name)

        print(f"Uploading {blob_name} to Azure Blob Storage...")
        with open(file_path, "rb") as data:
            blob_client.upload_blob(data, overwrite=True)
        print(f"Successfully uploaded {blob_name}.")
        return True
        
    except Exception as e:
        print(f"Failed to upload to Azure: {e}")
        return False

def fetch_recent_browser_history(output_file, duration_minutes=60):
    """
    Fetches browser history for the last 'duration_minutes' and writes it to a CSV file.
    Returns True if history was written, False otherwise.
    """
    if not BROWSER_HISTORY_AVAILABLE:
        return False

    try:
        print(f"Fetching browser history for the last {duration_minutes} minutes...")
        # get_history() fetches history from all installed browsers
        outputs = get_history()
        histories = outputs.histories
        
        # Calculate cutoff time (UTC, as browser_history usually returns aware datetimes)
        # We use timezone.utc to ensure we have an aware datetime for comparison
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=duration_minutes)
        
        recent_history = []
        for entry in histories:
            # entry is usually (datetime, url) or (datetime, url, title)
            if len(entry) >= 2:
                dt = entry[0]
                url = entry[1]
            else:
                continue
                
            # Ensure dt is comparable (aware vs naive)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            
            if dt > cutoff_time:
                recent_history.append((dt, url))
        
        if not recent_history:
            print("No recent browser history found.")
            return False
            
        # Sort by time
        recent_history.sort(key=lambda x: x[0])
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "URL"])
            for dt, url in recent_history:
                writer.writerow([dt.isoformat(), url])
                
        print(f"Saved {len(recent_history)} browser history entries to {output_file}")
        return True
        
    except Exception as e:
        print(f"Error fetching browser history: {e}")
        return False

def get_blob_name_with_timestamp(filename):
    """
    Generates a blob name with format: userid/start_time_to_end_time.zip
    Assumes filename contains a timestamp like YYYY-MM-DD_HH-MM-SS or YYYY-MM-DD_HH
    """
    try:
        # Try to find timestamp pattern using regex
        # Match YYYY-MM-DD_HH-MM-SS (custom) or YYYY-MM-DD_HH (default)
        match = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})', filename)
        if not match:
            match = re.search(r'(\d{4}-\d{2}-\d{2}_\d{2})', filename)
        
        if match:
            start_str = match.group(1)
            
            # Try parsing with seconds
            try:
                start_dt = datetime.strptime(start_str, "%Y-%m-%d_%H-%M-%S")
            except ValueError:
                # Try parsing without minutes/seconds (default hourly)
                try:
                    start_dt = datetime.strptime(start_str, "%Y-%m-%d_%H")
                except ValueError:
                    # Should not happen if regex matched, but safe fallback
                    raise ValueError("Date parse failed")
            
            end_dt = start_dt + timedelta(hours=1)
            
            # Format output consistently
            start_fmt = start_dt.strftime("%Y-%m-%d_%H-%M-%S")
            end_fmt = end_dt.strftime("%Y-%m-%d_%H-%M-%S")
            
            if USER_ID:
                return f"{USER_ID}/{start_fmt}_to_{end_fmt}.zip"
            else:
                return f"unknown_user/{start_fmt}_to_{end_fmt}.zip"
                
    except Exception as e:
        print(f"Debug: Timestamp parsing failed for {filename}: {e}")
    
    # Fallback if parsing fails
    if USER_ID:
        return f"{USER_ID}/{os.path.basename(filename)}"
    return os.path.basename(filename)

def upload_existing_zips():
    """
    Scans the log directory for existing .zip files and uploads them.
    """
    if not os.path.exists(LOG_DIR):
        return

    print("Checking for existing zip files to upload...")
    for filename in os.listdir(LOG_DIR):
        if filename.endswith(".zip"):
            file_path = os.path.join(LOG_DIR, filename)
            blob_name = get_blob_name_with_timestamp(filename)
            
            if upload_to_azure(file_path, blob_name):
                try:
                    os.remove(file_path)
                    print(f"Deleted local file: {filename}")
                except OSError as e:
                    print(f"Error deleting {filename}: {e}")

class HourlyZipHandler(logging.handlers.TimedRotatingFileHandler):
    """
    Log handler that rotates the log file every hour and zips the old file.
    """
    def __init__(self, filename, when='h', interval=1):
        # Rotate every 1 hour ('h') by default, or custom for testing
        super().__init__(filename, when=when, interval=interval, encoding='utf-8')
        # Ensure deterministic suffix for parsing (YYYY-MM-DD_HH-MM-SS)
        self.suffix = "%Y-%m-%d_%H-%M-%S"
        self.namer = self._zip_namer
        self.rotator = self._zip_rotator
        
        # Calculate interval in minutes for browser history fetching
        self.history_interval_minutes = 60 # Default
        if when == 'h':
            self.history_interval_minutes = interval * 60
        elif when == 'm':
            self.history_interval_minutes = interval
        elif when == 'd':
            self.history_interval_minutes = interval * 1440

    def _zip_namer(self, default_name):
        return default_name

    def _zip_rotator(self, source, dest):
        base = os.path.basename(source)
        zip_name = f"{source}.zip"
        try:
            # Fetch browser history before zipping
            history_file = f"{source}_history.csv"
            history_added = fetch_recent_browser_history(history_file, self.history_interval_minutes)

            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Add the main log file
                zf.write(source, base)
                
                # Add the history file if it exists
                if history_added and os.path.exists(history_file):
                    zf.write(history_file, os.path.basename(history_file))

            # Remove the original text file after zipping
            if os.path.exists(source):
                os.remove(source)
            
            # Remove the history file
            if history_added and os.path.exists(history_file):
                os.remove(history_file)
                
            # Upload the zip file to Azure
            blob_name = get_blob_name_with_timestamp(os.path.basename(zip_name))
            if upload_to_azure(zip_name, blob_name):
                try:
                    os.remove(zip_name)
                except OSError:
                    pass
            
        except Exception as e:
            print(f"Error processing log file: {e}")

def heartbeat_loop(logger, interval=600):
    """
    Logs a heartbeat message every 'interval' seconds to ensure log rotation triggers
    even if the system is idle.
    """
    while True:
        time.sleep(interval)
        logger.info("Heartbeat: Monitor is active")

def run_test_generator(logger):
    """Generates fake logs to test rotation"""
    print("Generating dummy logs to trigger rotation...")
    apps = ["Notepad.exe", "Chrome.exe", "Spotify.exe", "Code.exe", "Slack.exe"]
    import json
    while True:
        app = random.choice(apps)
        pid = random.randint(1000, 9999)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Log active window event (JSON format)
        log_data = {
            "event_type": "active_window",
            "pid": pid,
            "name": app,
            "window_title": f"Fake Title for {app}",
            "timestamp": ts
        }
        if app == "Chrome.exe":
            log_data["page_title"] = f"Search for {random.randint(1, 100)}"
            
        logger.info(json.dumps(log_data))
        time.sleep(random.uniform(0.5, 2.0))

def get_user_id_from_server(username):
    """
    Fetches the User ID from the server based on the username.
    """
    try:
        print(f"Connecting to server at {SERVER_URL}...")
        response = requests.post(f"{SERVER_URL}/get_user_id", json={"username": username}, timeout=5)
        
        if response.status_code == 200:
            user_id = response.json().get("user_id")
            print(f"Successfully retrieved User ID: {user_id}")
            return str(user_id)
        elif response.status_code == 404:
            print(f"Error: User '{username}' not found on server.")
            return None
        else:
            print(f"Server returned error: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to server at {SERVER_URL}. Is it running?")
        return None
    except Exception as e:
        print(f"Error fetching User ID: {e}")
        return None

def main():
    global USER_ID
    
    # Check for test mode
    test_mode = "--test" in sys.argv
    
    print("=" * 50)
    print("Simple App Monitor")
    if test_mode:
        print("!!! TEST MODE ENABLED: Rotating every 1 MINUTE !!!")
    print("=" * 50)
    
    # Ask for Username instead of User ID
    while not USER_ID:
        username = input("Enter Username: ").strip()
        if not username:
            print("Username cannot be empty.")
            continue
            
        USER_ID = get_user_id_from_server(username)
        
        if not USER_ID:
            retry = input("Try again? (y/n): ").lower()
            if retry != 'y':
                print("Exiting...")
                sys.exit(1)

    log_file = os.path.join(LOG_DIR, 'monitor.log')
    
    # Upload any existing zip files from previous runs
    if AZURE_AVAILABLE and AZURE_CONNECTION_STRING:
        upload_existing_zips()
    
    # Setup logger
    logger = logging.getLogger("simple_monitor")
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers to avoid duplicates if re-run
    if logger.handlers:
        logger.handlers.clear()

    if test_mode:
        # Rotate every 1 minute for testing
        handler = HourlyZipHandler(log_file, when='m', interval=1)
    else:
        # Rotate every 1 hour normally
        handler = HourlyZipHandler(log_file, when='h', interval=1)
        
    # Ensure deterministic suffix for parsing
    handler.suffix = "%Y-%m-%d_%H-%M-%S"
    
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    
    # Add the noise filter
    handler.addFilter(NoiseFilter())
    
    logger.addHandler(handler)
    
    # Optional: Add console handler to see output in terminal (also filtered)
    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(NoiseFilter())
    logger.addHandler(console)
    
    # Start Heartbeat Thread (Daemon so it dies when main thread dies)
    # Logs every 10 minutes (600s) to force rotation checks
    # In test mode, heartbeat faster (10s)
    hb_interval = 10 if test_mode else 600
    t = threading.Thread(target=heartbeat_loop, args=(logger, hb_interval), daemon=True)
    t.start()
    
    print(f"Monitoring started for User: {USER_ID}")
    print(f"Logs are written to: {log_file}")
    if test_mode:
        print(f"Logs will be rotated and zipped every 1 MINUTE (Test Mode).")
    else:
        print(f"Logs will be rotated and zipped every hour.")
        
    if AZURE_AVAILABLE and AZURE_CONNECTION_STRING:
        print(f"Azure Upload: ENABLED (Container: {AZURE_CONTAINER_NAME})")
    else:
        print("Azure Upload: DISABLED (Missing library or connection string)")
    print("Tracking: Application Start/Stop")
    print("Filtering: System background processes are hidden.")
    print("Press Ctrl+C to stop.")
    print("=" * 50)

    try:
        if test_mode:
            run_test_generator(logger)
        else:
            # Use monitor_active_app to track the foreground window title (browser history/search terms)
            print("Tracking: Active Window Titles (Browser Tabs, Application Titles)")
            monitor_active_app(
                interval=1.0,
                logger=logger,
                heartbeat_seconds=60.0
            )
    except KeyboardInterrupt:
        print("\nStopping monitor...")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    main()
