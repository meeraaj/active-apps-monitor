import logging
import logging.handlers
import os
import zipfile
import time
import sys
from windowslogger import monitor_processes

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

def upload_to_azure(file_path):
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
            if upload_to_azure(file_path):
                try:
                    os.remove(file_path)
                    print(f"Deleted local file: {filename}")
                except OSError as e:
                    print(f"Error deleting {filename}: {e}")

class HourlyZipHandler(logging.handlers.TimedRotatingFileHandler):
    """
    Log handler that rotates the log file every hour and zips the old file.
    """
    def __init__(self, filename):
        # Rotate every 1 hour ('h'). 
        # interval=1 means 1 unit of 'h'.
        super().__init__(filename, when='h', interval=1, encoding='utf-8')
        self.namer = self._zip_namer
        self.rotator = self._zip_rotator

    def _zip_namer(self, default_name):
        return default_name

    def _zip_rotator(self, source, dest):
        base = os.path.basename(source)
        zip_name = f"{source}.zip"
        try:
            with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(source, base)
            
            # Remove the original text file after zipping
            if os.path.exists(source):
                os.remove(source)
                
            # Upload the zip file to Azure
            if upload_to_azure(zip_name):
                try:
                    os.remove(zip_name)
                except OSError:
                    pass
            
        except Exception as e:
            print(f"Error processing log file: {e}")

def main():
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

    handler = HourlyZipHandler(log_file)
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
    
    print("=" * 50)
    print("Simple App Monitor")
    print("=" * 50)
    print(f"Monitoring started.")
    print(f"Logs are written to: {log_file}")
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
        # gui_only=False ensures we catch all processes, but we filter noise in the logger
        monitor_processes(
            interval=2.0,
            logger=logger,
            include_system=False,
            snapshot_each_interval=False,
            gui_only=False
        )
    except KeyboardInterrupt:
        print("\nStopping monitor...")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    main()
