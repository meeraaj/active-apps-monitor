import os
import sys
import time
import json
import threading
import logging
import google.generativeai as genai
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

# Try relative import first, then absolute
try:
    from .shared_utils import get_container_client, download_and_parse_log, parse_log_to_df
except ImportError:
    try:
        from shared_utils import get_container_client, download_and_parse_log, parse_log_to_df
    except ImportError:
        # Fallback for when running from root without package structure
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        from shared_utils import get_container_client, download_and_parse_log, parse_log_to_df

load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

class GeminiService:
    def __init__(self, reports_dir="reports", user_id_to_monitor=None):
        self.reports_dir = reports_dir
        self.user_id = user_id_to_monitor
        self.running = False
        self.thread = None
        
        if GEMINI_API_KEY:
            genai.configure(api_key=GEMINI_API_KEY)
        else:
            print("Warning: GEMINI_API_KEY not found. AI predictions will be disabled.", file=sys.stderr)

    def start(self):
        if self.running:
            return

        self.running = True
        self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.thread.start()
        print(f"GeminiService started. Monitoring logs for user: {self.user_id if self.user_id else 'ALL'}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)

    def monitor_loop(self):
        if not os.path.exists(self.reports_dir):
            os.makedirs(self.reports_dir)
            
        print(f"GeminiService: Monitoring Azure logs...")
        
        while self.running:
            try:
                container = get_container_client()
                
                # List blobs
                blobs = []
                prefix = f"{self.user_id}/" if self.user_id else None
                
                # Note: listing all blobs can be slow. 
                # In a real production app, we'd use Event Grid or similar.
                # For this utility, we'll list and check the recent ones.
                blob_iter = container.list_blobs(name_starts_with=prefix)
                
                # We can't easily slice an iterator without consuming it.
                # Let's consume it but limit the count if it's huge? 
                # Or just convert to list (might be memory heavy if millions).
                # Assuming reasonable number of logs for this project.
                blobs = list(blob_iter)
                
                # Check last 20 blobs (most recent usually at the end if named by timestamp/lexicographically)
                recent_blobs = blobs[-20:] if blobs else []
                
                for blob in recent_blobs:
                    if not self.running: break
                    
                    # Create a safe filename for the report
                    safe_name = blob.name.replace('/', '_').replace('\\', '_').replace('.zip', '.json')
                    report_path = os.path.join(self.reports_dir, safe_name)
                    
                    if not os.path.exists(report_path):
                        print(f"GeminiService: New log found: {blob.name}")
                        print("GeminiService: Generating AI Report...")
                        
                        report_content = self.generate_ai_productivity_report(blob.name)
                        
                        with open(report_path, 'w', encoding='utf-8') as f:
                            f.write(report_content)
                            
                        print(f"GeminiService: Saved report to: {report_path}")
                
                # Sleep
                for _ in range(60):
                    if not self.running: break
                    time.sleep(1)
                    
            except Exception as e:
                print(f"Error in GeminiService monitor loop: {e}")
                time.sleep(60)

    def generate_ai_productivity_report(self, blob_name: str, is_local: bool = False, user_id: str = None) -> str:
        """
        Uses Gemini AI to generate a productivity report and predictions based on the log data.
        """
        if not GEMINI_API_KEY:
            return "Error: GEMINI_API_KEY is not set in the environment."

        try:
            # 1. Get Log Content & Parse
            if is_local:
                # Assuming read_local_log is available or we implement it here.
                # But this method is mostly for Azure blobs in the service context.
                # We'll skip local support in the service for now or import it.
                from .shared_utils import read_local_log
                log_content = read_local_log(blob_name)
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
            
            # Clean up response
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
