import os
import sys
import io
import time
import zipfile
import logging
import json
import pandas as pd
import google.generativeai as genai
from datetime import datetime
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from azure.storage.blob import BlobServiceClient

# Load environment variables
load_dotenv()

# Configuration
AZURE_CONNECTION_STRING = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
AZURE_CONTAINER_NAME = os.getenv('AZURE_CONTAINER_NAME', 'app-monitor-logs')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    print("Warning: GEMINI_API_KEY not found. AI predictions will be disabled.", file=sys.stderr)

# Initialize MCP Server
mcp = FastMCP("ProductivityMonitor")

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


@mcp.tool()
def list_user_logs(user_id: str, limit: int = 20) -> str:
    """
    Lists the most recent log files for a specific user in Azure Blob Storage.
    """
    try:
        container = get_container_client()
        # Note: Listing all blobs can be slow if there are thousands.
        # We list them to find the most recent ones (last in alphabetical order).
        blobs = []
        for b in container.list_blobs(name_starts_with=f"{user_id}/"):
            blobs.append(b.name)
        
        if not blobs:
            return f"No logs found for user: {user_id}"
        
        # Get the last 'limit' blobs
        recent_blobs = blobs[-limit:]
        
        return f"Found {len(blobs)} logs for {user_id} (showing last {len(recent_blobs)}):\n" + "\n".join(recent_blobs)
    except Exception as e:
        return f"Error listing logs: {str(e)}"

@mcp.tool()
def analyze_productivity(blob_name: str) -> str:
    """
    Downloads a specific zipped log file, parses the activity, and returns a productivity summary.
    """
    try:
        log_content = download_and_parse_log(blob_name)
        df = parse_log_to_df(log_content)

        if df.empty:
            return "No process events found in the log."
        
        # Basic Analysis
        start_time = df['timestamp'].min()
        end_time = df['timestamp'].max()
        duration = end_time - start_time
        app_counts = df[df['event'] == 'start']['name'].value_counts().to_dict()
        browser_pages = df[df['page'] != ""]['page'].unique()
        urls = df[df['url'] != ""]['url'].unique()
        
        summary = f"""
Productivity Analysis for {blob_name}
-------------------------------------
Session Start: {start_time}
Session End:   {end_time}
Total Duration: {duration}

Top Applications Launched:
{pd.Series(app_counts).to_markdown()}

Browser Pages Visited:
{', '.join(browser_pages) if len(browser_pages) > 0 else "None detected"}

URLs Visited:
{', '.join(urls) if len(urls) > 0 else "None detected"}

Raw Event Count: {len(df)}
"""
        return summary

    except Exception as e:
        return f"Error analyzing blob: {str(e)}"

def analyze_local_productivity(file_path: str) -> str:
    """
    Reads a local log file, parses the activity, and returns a productivity summary.
    """
    try:
        log_content = read_local_log(file_path)
        df = parse_log_to_df(log_content)

        if df.empty:
            return "No process events found in the log."
        
        # Basic Analysis
        start_time = df['timestamp'].min()
        end_time = df['timestamp'].max()
        duration = end_time - start_time
        app_counts = df[df['event'] == 'start']['name'].value_counts().to_dict()
        browser_pages = df[df['page'] != ""]['page'].unique()
        urls = df[df['url'] != ""]['url'].unique()
        
        summary = f"""
Productivity Analysis for {file_path}
-------------------------------------
Session Start: {start_time}
Session End:   {end_time}
Total Duration: {duration}

Top Applications Launched:
{pd.Series(app_counts).to_markdown()}

Browser Pages Visited:
{', '.join(browser_pages) if len(browser_pages) > 0 else "None detected"}

URLs Visited:
{', '.join(urls) if len(urls) > 0 else "None detected"}

Raw Event Count: {len(df)}
"""
        return summary

    except Exception as e:
        return f"Error analyzing local file: {str(e)}"

@mcp.tool()
def generate_ai_productivity_report(blob_name: str, is_local: bool = False, user_id: str = None) -> str:
    """
    Uses Gemini AI to generate a productivity report and predictions based on the log data.
    Also saves raw data and analysis to the database.
    """
    if not GEMINI_API_KEY:
        return "Error: GEMINI_API_KEY is not set in the environment."

    try:
        # 1. Get Log Content & Parse
        if is_local:
            log_content = read_local_log(blob_name)
            # Try to infer user_id from filename if not provided
            if not user_id:
                user_id = "local_user"
        else:
            log_content = download_and_parse_log(blob_name)
            # Try to infer user_id from blob path "userid/..."
            if not user_id and "/" in blob_name:
                user_id = blob_name.split("/")[0]
        
        if not user_id:
            user_id = "unknown"

        df = parse_log_to_df(log_content)
        
        if df.empty:
            return "No data found."

        # 3. Generate Analysis Summary for Gemini
        # Basic Analysis
        start_time = df['timestamp'].min()
        end_time = df['timestamp'].max()
        duration = end_time - start_time
        app_counts = df[df['event'] == 'active']['name'].value_counts().to_dict()
        browser_pages = df[df['page'] != ""]['page'].unique()
        urls = df[df['url'] != ""]['url'].unique()
        
        basic_analysis = f"""
Productivity Analysis for {blob_name}
-------------------------------------
Session Start: {start_time}
Session End:   {end_time}
Total Duration: {duration}

Top Applications Launched:
{pd.Series(app_counts).to_markdown()}

Browser Pages Visited:
{', '.join(browser_pages) if len(browser_pages) > 0 else "None detected"}

URLs Visited:
{', '.join(urls) if len(urls) > 0 else "None detected"}

Raw Event Count: {len(df)}
"""
        
        if "Error" in basic_analysis:
            return basic_analysis

        # Construct prompt for Gemini
        prompt = f"""
        You are a security and productivity expert. Analyze the following computer usage log summary.
        
        DATA:
        {basic_analysis}
        
        TASK:
        Analyze the overall session and provide a summary.
        Return a valid JSON object with the following structure:
        {{
            "is_productive": <boolean, true if the session was mostly productive>,
            "is_dangerous": <boolean, true if any dangerous activity was detected>,
            "productivity_reason": "<summary explaining the classification>",
            "apps": [
                {{
                    "name": "<app name or window title>",
                    "category": "<category>",
                    "is_productive": <boolean>,
                    "is_dangerous": <boolean>,
                    "productivity_reason": "<reason>"
                }}
            ]
        }}
        
        CRITICAL:
        - Flag apps as "dangerous" if they are known malware, suspicious tools, or unauthorized remote access tools.
        - Flag apps as "productive" based on a typical professional workflow (coding, writing, research).
        - Strictly return ONLY the JSON object. Do not include markdown formatting like ```json or any other text.
        """
        
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        
        # Clean up response if it contains markdown code blocks
        text = response.text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
            
        # Inject user_id and timestamps
        try:
            data = json.loads(text.strip())
            data['user_id'] = user_id
            data['start_time'] = start_time.strftime("%Y-%m-%d %H:%M:%S")
            data['end_time'] = end_time.strftime("%Y-%m-%d %H:%M:%S")
            text = json.dumps(data, indent=2)
        except json.JSONDecodeError:
            pass
            
        return text.strip()
        
    except Exception as e:
        return f"Error generating AI report: {str(e)}"

if __name__ == "__main__":
    # Check if running in test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("=== Productivity MCP Test Mode ===")
        user_id = input("Enter User ID to test: ").strip()
        if not user_id:
            print("User ID required.")
            sys.exit(1)
            
        print(f"\n1. Listing logs for {user_id}...")
        logs_output = list_user_logs(user_id)
        print(logs_output)
        
        if "Found" in logs_output:
            # Extract first filename from output or ask user
            # Output format: "Found X logs for user:\nfilename1\nfilename2"
            lines = logs_output.split('\n')
            if len(lines) > 1:
                first_log = lines[1].strip()
                print(f"\n2. Analyzing first log: {first_log}...")
                
                print("\n--- Basic Analysis ---")
                print(analyze_productivity(first_log))
                
                print("\n--- AI Report (Gemini) ---")
                print(generate_ai_productivity_report(first_log))
        else:
            print("No logs found to analyze.")

    elif len(sys.argv) > 1 and sys.argv[1] == "--generate-all":
        print("=== Batch Generate Reports ===")
        
        force = "--force" in sys.argv
        
        user_id = input("Enter User ID: ").strip()
        if not user_id:
            print("User ID required.")
            sys.exit(1)
            
        reports_dir = "reports"
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
            
        print(f"Fetching all logs for user '{user_id}'...")
        try:
            container = get_container_client()
            blobs = list(container.list_blobs(name_starts_with=f"{user_id}/"))
            
            if not blobs:
                print("No logs found.")
            else:
                print(f"Found {len(blobs)} logs. Processing...")
                for i, blob in enumerate(blobs):
                    safe_name = blob.name.replace('/', '_').replace('\\', '_').replace('.zip', '.json')
                    report_path = os.path.join(reports_dir, safe_name)
                    
                    if os.path.exists(report_path) and not force:
                        print(f"[{i+1}/{len(blobs)}] Skipping existing: {safe_name} (Use --force to overwrite)")
                        continue
                        
                    print(f"[{i+1}/{len(blobs)}] Generating report for: {blob.name}")
                    try:
                        # Pass user_id explicitly to ensure DB updates work correctly
                        report_content = generate_ai_productivity_report(blob.name, user_id=user_id)
                        if "Error" in report_content and not report_content.strip().startswith("{"):
                             print(f"  Failed: {report_content}")
                        else:
                            with open(report_path, 'w', encoding='utf-8') as f:
                                f.write(report_content)
                            print(f"  Saved to {report_path}")
                    except Exception as e:
                        print(f"  Error processing {blob.name}: {e}")
                        
        except Exception as e:
            print(f"Error: {e}")

    elif len(sys.argv) > 1 and sys.argv[1] == "--local":
        if len(sys.argv) < 3:
            print("Usage: python productivity_mcp.py --local <path_to_log_file>")
            sys.exit(1)
            
        log_file = sys.argv[2]
        if not os.path.exists(log_file):
            print(f"Error: File not found: {log_file}")
            sys.exit(1)
            
        print(f"Analyzing local file: {log_file}")
        report = generate_ai_productivity_report(log_file, is_local=True)
        print("\n--- AI Report ---")
        print(report)
        
        # Save to reports dir
        reports_dir = "reports"
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
            
        report_name = os.path.basename(log_file) + ".json"
        report_path = os.path.join(reports_dir, report_name)
        
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"\nSaved report to: {report_path}")

    elif len(sys.argv) > 1 and sys.argv[1] == "--auto":
        print("=== Productivity MCP Auto-Report Mode ===")
        user_id = input("Enter User ID to monitor: ").strip()
        if not user_id:
            print("User ID required.")
            sys.exit(1)
            
        reports_dir = "reports"
        if not os.path.exists(reports_dir):
            os.makedirs(reports_dir)
            
        print(f"Monitoring Azure logs for user '{user_id}'...")
        print(f"Reports will be saved to '{reports_dir}/'")
        print("Press Ctrl+C to stop.")
        
        while True:
            try:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking for new logs...")
                container = get_container_client()
                # List all blobs for the user
                # Optimization: This can be slow if there are many blobs.
                # We iterate and keep the last 100 to check against.
                blobs = []
                for b in container.list_blobs(name_starts_with=f"{user_id}/"):
                    blobs.append(b)
                
                # Only look at the last 20 blobs to save time on checking existence
                recent_blobs = blobs[-20:] if blobs else []
                
                if not recent_blobs:
                    print(f"  No logs found yet. Waiting...")
                else:
                    for blob in recent_blobs:
                        # Create a safe filename for the report
                        safe_name = blob.name.replace('/', '_').replace('\\', '_').replace('.zip', '.json')
                        report_path = os.path.join(reports_dir, safe_name)
                        
                        # Check if report already exists
                        if not os.path.exists(report_path):
                            print(f"  New log found: {blob.name}")
                            print("  Generating AI Report...")
                            
                            report_content = generate_ai_productivity_report(blob.name)
                            
                            # Save report
                            with open(report_path, 'w', encoding='utf-8') as f:
                                f.write(report_content)
                                
                            print(f"  Saved report to: {report_path}")
                        else:
                            # Report already exists, skip
                            pass
                            
                # Wait before next poll
                time.sleep(60)
                
            except KeyboardInterrupt:
                print("\nStopping auto-monitor.")
                break
            except Exception as e:
                print(f"Error in auto-monitor loop: {e}")
                time.sleep(60)

    else:
        # Standard MCP Server mode (waits for client connection)
        mcp.run()
