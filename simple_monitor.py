import logging
import logging.handlers
import os
import zipfile
import time
import sys
from windowslogger import monitor_processes

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
            if os.path.exists(source):
                os.remove(source)
        except Exception as e:
            print(f"Error zipping log file: {e}")

def main():
    log_file = os.path.join(LOG_DIR, 'monitor.log')
    
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
