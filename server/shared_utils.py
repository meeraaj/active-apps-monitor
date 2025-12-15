import os
import io
import sys
import json
import zipfile
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from azure.storage.blob import BlobServiceClient

# Load environment variables
load_dotenv()

# Configuration
AZURE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME', 'app-monitor-logs')

def get_container_client():
    if not AZURE_CONNECTION_STRING:
        raise ValueError("AZURE_STORAGE_CONNECTION_STRING is not set")
    service = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    return service.get_container_client(AZURE_CONTAINER_NAME)

def download_and_parse_log(blob_name: str) -> str:
    """Helper to download and parse log content from Azure Blob."""
    container = get_container_client()
    blob_client = container.get_blob_client(blob_name)
    
    # Download blob into memory
    download_stream = blob_client.download_blob()
    zip_data = io.BytesIO(download_stream.readall())
    
    log_content = ""
    
    # Extract the zip
    with zipfile.ZipFile(zip_data) as z:
        file_list = z.namelist()
        target_file = next((f for f in file_list if f.endswith('.log')), file_list[0] if file_list else None)
        
        if not target_file:
            raise ValueError("No log file found inside the zip.")
            
        with z.open(target_file) as f:
            log_content = f.read().decode('utf-8', errors='ignore')
            
    return log_content

def read_local_log(file_path: str) -> str:
    """Helper to read a local log file."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def parse_log_to_df(log_content: str) -> pd.DataFrame:
    """Helper to parse raw log text into a DataFrame."""
    data = []
    lines = log_content.splitlines()
    
    for line in lines:
        try:
            # Fast split on first two pipes
            parts = line.split(" | ", 2)
            if len(parts) < 3:
                continue
                
            timestamp_str = parts[0]
            message = parts[2]
            
            # Fast timestamp parsing (assuming fixed format YYYY-MM-DD HH:MM:SS)
            try:
                # timestamp_str is "2025-12-13 10:00:00"
                ts = datetime(
                    int(timestamp_str[0:4]),
                    int(timestamp_str[5:7]),
                    int(timestamp_str[8:10]),
                    int(timestamp_str[11:13]),
                    int(timestamp_str[14:16]),
                    int(timestamp_str[17:19])
                )
            except (ValueError, IndexError):
                continue
            
            # Try parsing as JSON first (new format)
            # Optimization: Check if it looks like JSON before trying to parse
            if message.strip().startswith('{'):
                try:
                    json_data = json.loads(message)
                    # Handle active_window event
                    if json_data.get("event_type") == "active_window":
                        data.append({
                            "timestamp": ts,
                            "event": "active",
                            "pid": json_data.get("pid"),
                            "name": json_data.get("name"),
                            "exe": json_data.get("exe", ""),
                            "page": json_data.get("page_title", ""),
                            "window_title": json_data.get("window_title", ""),
                            "url": json_data.get("url", "")
                        })
                        continue
                except json.JSONDecodeError:
                    pass
            
            # Fallback to old format parsing
            if "proc_start" in line or "proc_end" in line:
                attr_dict = {}
                for part in message.split(" "):
                    if "=" in part:
                        k, v = part.split("=", 1)
                        attr_dict[k] = v
                
                event_type = "start" if "proc_start" in line else "end"
                
                data.append({
                    "timestamp": ts,
                    "event": event_type,
                    "pid": attr_dict.get("pid"),
                    "name": attr_dict.get("name"),
                    "exe": attr_dict.get("exe"),
                    "page": attr_dict.get("page", ""),
                    "window_title": attr_dict.get("window_title", ""),
                    "url": ""
                })
        except Exception:
            continue
                
    if not data:
        return pd.DataFrame()
        
    return pd.DataFrame(data)
