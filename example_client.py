"""
Example client for Active Apps Monitor REST API
Demonstrates how to interact with the API programmatically
"""

import requests
import json
import time
from datetime import datetime

BASE_URL = "http://localhost:5000/api"


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def health_check():
    """Check if API is running."""
    print_section("Health Check")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        data = response.json()
        print(f"Status: {data['status']}")
        print(f"Monitor Active: {data['monitor_active']}")
        print(f"Timestamp: {data['timestamp']}")
        return True
    except requests.exceptions.ConnectionError:
        print("❌ Cannot connect to API. Is the server running?")
        print("   Start with: python api.py")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def get_system_health():
    """Get system health metrics."""
    print_section("System Health")
    try:
        response = requests.get(f"{BASE_URL}/system/health")
        data = response.json()
        
        if data['success']:
            health = data['data']
            print(f"CPU: {health['cpu']['percent']}% ({health['cpu']['count']} cores)")
            print(f"Memory: {health['memory']['used_gb']:.2f}GB / {health['memory']['total_gb']:.2f}GB ({health['memory']['percent']}%)")
            print(f"Disk: {health['disk']['used_gb']:.2f}GB / {health['disk']['total_gb']:.2f}GB ({health['disk']['percent']}%)")
        else:
            print(f"❌ Error: {data['error']}")
    except Exception as e:
        print(f"❌ Error: {e}")


def get_running_apps():
    """Get currently running GUI applications."""
    print_section("Running Applications")
    try:
        response = requests.get(f"{BASE_URL}/apps/running")
        data = response.json()
        
        if data['success']:
            apps = data['data']
            print(f"Found {data['count']} running GUI applications:\n")
            
            for app in apps[:10]:  # Show first 10
                print(f"  • {app['name']} (PID: {app['pid']})")
                print(f"    CPU: {app['cpu_percent']}% | Memory: {app['memory_mb']:.1f}MB")
                print(f"    Path: {app['exe'][:60]}..." if len(app['exe']) > 60 else f"    Path: {app['exe']}")
                print()
            
            if data['count'] > 10:
                print(f"  ... and {data['count'] - 10} more")
        else:
            print(f"❌ Error: {data['error']}")
    except Exception as e:
        print(f"❌ Error: {e}")


def get_active_app():
    """Get currently active (foreground) application."""
    print_section("Active Application")
    try:
        response = requests.get(f"{BASE_URL}/apps/active")
        data = response.json()
        
        if data['success']:
            if data['data']:
                app = data['data']
                print(f"Name: {app['name']}")
                print(f"Title: {app['title']}")
                print(f"PID: {app['pid']}")
                print(f"CPU: {app['cpu_percent']}%")
                print(f"Memory: {app['memory_mb']:.1f}MB")
                print(f"Path: {app['exe']}")
            else:
                print("No active window detected")
        else:
            print(f"❌ Error: {data['error']}")
    except Exception as e:
        print(f"❌ Error: {e}")


def get_logs(hours=1, limit=20):
    """Get recent app usage logs."""
    print_section(f"Recent Logs (Last {hours} hour(s))")
    try:
        response = requests.get(f"{BASE_URL}/logs", params={
            'hours': hours,
            'limit': limit
        })
        data = response.json()
        
        if data['success']:
            logs = data['data']
            print(f"Found {data['count']} log entries:\n")
            
            for log in logs[:10]:  # Show first 10
                timestamp = datetime.fromisoformat(log['timestamp']).strftime('%H:%M:%S')
                event = log['event_type']
                fields = log['fields']
                
                name = fields.get('name', 'N/A')
                pid = fields.get('pid', 'N/A')
                
                print(f"  [{timestamp}] {event:15s} {name:20s} (PID: {pid})")
            
            if data['count'] > 10:
                print(f"\n  ... and {data['count'] - 10} more entries")
        else:
            print(f"❌ Error: {data['error']}")
    except Exception as e:
        print(f"❌ Error: {e}")


def get_app_stats(hours=24):
    """Get usage statistics per application."""
    print_section(f"App Usage Statistics (Last {hours} hours)")
    try:
        response = requests.get(f"{BASE_URL}/stats/apps", params={'hours': hours})
        data = response.json()
        
        if data['success']:
            stats = data['data']
            print(f"Analyzed {data['count']} applications:\n")
            
            for i, app in enumerate(stats[:10], 1):  # Top 10
                print(f"{i}. {app['app_name']}")
                print(f"   Launches: {app['launch_count']}")
                print(f"   Total Time: {app['total_duration_minutes']:.1f} minutes")
                print(f"   Avg Session: {app['avg_duration_sec']:.0f} seconds")
                print()
            
            if data['count'] > 10:
                print(f"  ... and {data['count'] - 10} more apps")
        else:
            print(f"❌ Error: {data['error']}")
    except Exception as e:
        print(f"❌ Error: {e}")


def get_summary(hours=24):
    """Get usage summary."""
    print_section(f"Usage Summary (Last {hours} hours)")
    try:
        response = requests.get(f"{BASE_URL}/stats/summary", params={'hours': hours})
        data = response.json()
        
        if data['success']:
            summary = data['data']
            print(f"Total Events: {summary['total_events']}")
            print(f"App Launches: {summary['app_launches']}")
            print(f"App Closes: {summary['app_closes']}")
            print(f"Unique Apps: {summary['unique_apps']}")
            print(f"\nMost Used Apps:")
            for app in summary['app_names'][:10]:
                print(f"  • {app}")
        else:
            print(f"❌ Error: {data['error']}")
    except Exception as e:
        print(f"❌ Error: {e}")


def monitor_control_demo():
    """Demonstrate monitor control."""
    print_section("Monitor Control Demo")
    
    # Check status
    print("1. Checking monitor status...")
    response = requests.get(f"{BASE_URL}/monitor/status")
    data = response.json()
    print(f"   Monitor active: {data['data']['active']}")
    print(f"   Config: {json.dumps(data['data']['config'], indent=2)}")
    
    # Start monitoring
    print("\n2. Starting monitor...")
    config = {
        "mode": "process",
        "interval": 2,
        "gui_only": True,
        "include_system": False
    }
    response = requests.post(f"{BASE_URL}/monitor/start", json=config)
    data = response.json()
    
    if data['success']:
        print(f"   ✓ {data['message']}")
        print(f"   Monitoring for 5 seconds...")
        time.sleep(5)
    else:
        print(f"   ❌ {data['error']}")
        return
    
    # Stop monitoring
    print("\n3. Stopping monitor...")
    response = requests.post(f"{BASE_URL}/monitor/stop")
    data = response.json()
    
    if data['success']:
        print(f"   ✓ {data['message']}")
    else:
        print(f"   ❌ {data['error']}")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("  Active Apps Monitor - API Client Examples")
    print("=" * 60)
    
    # Check if API is available
    if not health_check():
        return
    
    # Run examples
    get_system_health()
    get_running_apps()
    get_active_app()
    get_logs(hours=1, limit=20)
    get_summary(hours=24)
    get_app_stats(hours=24)
    
    # Monitor control demo (optional - commented out by default)
    # Uncomment to test monitor control:
    # monitor_control_demo()
    
    print("\n" + "=" * 60)
    print("  Examples Complete!")
    print("=" * 60)
    print("\nFor more examples, see API_README.md")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✓ Interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
