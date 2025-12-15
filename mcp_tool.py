import sys
import os
import pandas as pd
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

# Ensure we can import from server package
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from server.shared_utils import get_container_client, download_and_parse_log, parse_log_to_df
from server.gemini_service import GeminiService

load_dotenv()

# Initialize MCP Server
mcp = FastMCP("ProductivityMonitor")

@mcp.tool()
def list_user_logs(user_id: str, limit: int = 20) -> str:
    """
    Lists the most recent log files for a specific user in Azure Blob Storage.
    """
    try:
        container = get_container_client()
        blobs = []
        for b in container.list_blobs(name_starts_with=f"{user_id}/"):
            blobs.append(b.name)
        
        if not blobs:
            return f"No logs found for user: {user_id}"
        
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

@mcp.tool()
def generate_ai_productivity_report(blob_name: str, user_id: str = None) -> str:
    """
    Uses Gemini AI to generate a productivity report and predictions based on the log data.
    """
    service = GeminiService() # Instantiate to use the method
    return service.generate_ai_productivity_report(blob_name, user_id=user_id)

if __name__ == "__main__":
    mcp.run()
