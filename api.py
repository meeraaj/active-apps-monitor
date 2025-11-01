"""
REST API for Active Apps Monitor
Provides endpoints to query app usage, control monitoring, and get health metrics
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import os
import threading
import psutil
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import json

# Import monitoring functions from windowslogger
from windowslogger import (
    get_active_window_info,
    monitor_active_app,
    monitor_processes,
    configure_logger,
    _get_top_level_window_pids
)

app = Flask(__name__)
CORS(app)  # Enable CORS for web clients

# Global state
monitor_thread: Optional[threading.Thread] = None
monitor_active = False
monitor_config = {
    'mode': 'process',
    'interval': 2,
    'gui_only': True,
    'include_system': False
}

LOG_FILE = 'app-usage.log'


# ==================== Helper Functions ====================

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """Parse a log line into a structured dict."""
    try:
        # Format: "2025-10-31 22:37:42 | INFO | proc_start pid=11088 name=chrome.exe exe=C:\Program Files\..."
        parts = line.split(' | ')
        if len(parts) < 3:
            return None
        
        timestamp_str = parts[0].strip()
        level = parts[1].strip()
        message = parts[2].strip()
        
        # Parse timestamp
        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        
        # Parse event type and fields
        tokens = message.split()
        if not tokens:
            return None
        
        event_type = tokens[0]
        fields = {}
        
        for token in tokens[1:]:
            if '=' in token:
                key, value = token.split('=', 1)
                fields[key] = value
        
        return {
            'timestamp': timestamp.isoformat(),
            'level': level,
            'event_type': event_type,
            'fields': fields
        }
    except Exception:
        return None


def read_logs(limit: int = 100, event_filter: Optional[str] = None,
              app_filter: Optional[str] = None,
              since: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Read and parse log entries with optional filters."""
    if not os.path.exists(LOG_FILE):
        return []
    
    logs = []
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # Process from newest to oldest
            for line in reversed(lines):
                if not line.strip():
                    continue
                
                parsed = parse_log_line(line)
                if not parsed:
                    continue
                
                # Apply filters
                if event_filter and parsed['event_type'] != event_filter:
                    continue
                
                if app_filter and app_filter.lower() not in parsed['fields'].get('name', '').lower():
                    continue
                
                if since:
                    log_time = datetime.fromisoformat(parsed['timestamp'])
                    if log_time < since:
                        continue
                
                logs.append(parsed)
                
                if len(logs) >= limit:
                    break
        
        return list(reversed(logs))  # Return in chronological order
    
    except Exception as e:
        return []


def get_running_apps() -> List[Dict[str, Any]]:
    """Get list of currently running GUI applications."""
    gui_pids = _get_top_level_window_pids()
    apps = []
    
    for proc in psutil.process_iter(['pid', 'name', 'exe', 'username', 'create_time', 'cpu_percent', 'memory_info']):
        try:
            if proc.info['pid'] not in gui_pids:
                continue
            
            apps.append({
                'pid': proc.info['pid'],
                'name': proc.info['name'],
                'exe': proc.info['exe'] or '',
                'user': proc.info['username'] or '',
                'started_at': datetime.fromtimestamp(proc.info['create_time']).isoformat(),
                'cpu_percent': proc.info['cpu_percent'] or 0,
                'memory_mb': round(proc.info['memory_info'].rss / 1024 / 1024, 2) if proc.info['memory_info'] else 0
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    
    return sorted(apps, key=lambda x: x['started_at'], reverse=True)


def get_system_health() -> Dict[str, Any]:
    """Get system health metrics."""
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    return {
        'cpu': {
            'percent': cpu_percent,
            'count': psutil.cpu_count()
        },
        'memory': {
            'total_gb': round(memory.total / 1024 / 1024 / 1024, 2),
            'used_gb': round(memory.used / 1024 / 1024 / 1024, 2),
            'percent': memory.percent
        },
        'disk': {
            'total_gb': round(disk.total / 1024 / 1024 / 1024, 2),
            'used_gb': round(disk.used / 1024 / 1024 / 1024, 2),
            'percent': disk.percent
        },
        'timestamp': datetime.now().isoformat()
    }


def calculate_app_stats(logs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Calculate usage statistics per application."""
    app_sessions = {}  # app_name -> list of (start_time, end_time, duration)
    active_sessions = {}  # pid -> (app_name, start_time)
    
    for log in logs:
        event = log['event_type']
        fields = log['fields']
        
        if event == 'proc_start':
            pid = fields.get('pid')
            name = fields.get('name')
            started_at = fields.get('started_at', log['timestamp'])
            
            if pid and name:
                active_sessions[pid] = (name, started_at)
        
        elif event == 'proc_end':
            pid = fields.get('pid')
            name = fields.get('name')
            end_time = log['timestamp']
            
            if pid and pid in active_sessions:
                app_name, start_time = active_sessions[pid]
                
                # Calculate duration
                try:
                    start_dt = datetime.fromisoformat(start_time)
                    end_dt = datetime.fromisoformat(end_time)
                    duration_sec = (end_dt - start_dt).total_seconds()
                    
                    if app_name not in app_sessions:
                        app_sessions[app_name] = []
                    
                    app_sessions[app_name].append({
                        'start': start_time,
                        'end': end_time,
                        'duration_sec': duration_sec
                    })
                except Exception:
                    pass
                
                del active_sessions[pid]
    
    # Aggregate stats per app
    stats = []
    for app_name, sessions in app_sessions.items():
        total_duration = sum(s['duration_sec'] for s in sessions)
        avg_duration = total_duration / len(sessions) if sessions else 0
        
        stats.append({
            'app_name': app_name,
            'launch_count': len(sessions),
            'total_duration_sec': round(total_duration, 2),
            'total_duration_minutes': round(total_duration / 60, 2),
            'avg_duration_sec': round(avg_duration, 2),
            'sessions': sessions
        })
    
    return sorted(stats, key=lambda x: x['total_duration_sec'], reverse=True)


# ==================== API Endpoints ====================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'monitor_active': monitor_active
    })


@app.route('/api/system/health', methods=['GET'])
def system_health():
    """Get system health metrics (CPU, memory, disk)."""
    try:
        health = get_system_health()
        return jsonify({
            'success': True,
            'data': health
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/apps/running', methods=['GET'])
def running_apps():
    """Get currently running GUI applications."""
    try:
        apps = get_running_apps()
        return jsonify({
            'success': True,
            'count': len(apps),
            'data': apps
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/apps/active', methods=['GET'])
def active_app():
    """Get currently active (foreground) application."""
    try:
        pid, name, title = get_active_window_info()
        
        if not pid:
            return jsonify({
                'success': True,
                'data': None
            })
        
        # Get additional process info
        try:
            proc = psutil.Process(pid)
            exe = proc.exe()
            user = proc.username()
            cpu = proc.cpu_percent(interval=0.1)
            mem_mb = round(proc.memory_info().rss / 1024 / 1024, 2)
        except Exception:
            exe = ''
            user = ''
            cpu = 0
            mem_mb = 0
        
        return jsonify({
            'success': True,
            'data': {
                'pid': pid,
                'name': name,
                'title': title,
                'exe': exe,
                'user': user,
                'cpu_percent': cpu,
                'memory_mb': mem_mb
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Get app usage logs with optional filters."""
    try:
        # Query parameters
        limit = int(request.args.get('limit', 100))
        event_filter = request.args.get('event_type')  # proc_start, proc_end, active_window
        app_filter = request.args.get('app')  # filter by app name
        hours = request.args.get('hours')  # last N hours
        
        # Calculate since timestamp
        since = None
        if hours:
            since = datetime.now() - timedelta(hours=int(hours))
        
        logs = read_logs(limit=limit, event_filter=event_filter, 
                        app_filter=app_filter, since=since)
        
        return jsonify({
            'success': True,
            'count': len(logs),
            'data': logs
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats/apps', methods=['GET'])
def app_stats():
    """Get usage statistics per application."""
    try:
        hours = int(request.args.get('hours', 24))
        since = datetime.now() - timedelta(hours=hours)
        
        logs = read_logs(limit=10000, since=since)
        stats = calculate_app_stats(logs)
        
        return jsonify({
            'success': True,
            'period_hours': hours,
            'count': len(stats),
            'data': stats
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/stats/summary', methods=['GET'])
def usage_summary():
    """Get summary statistics for a time period."""
    try:
        hours = int(request.args.get('hours', 24))
        since = datetime.now() - timedelta(hours=hours)
        
        logs = read_logs(limit=10000, since=since)
        
        # Count events
        starts = sum(1 for log in logs if log['event_type'] == 'proc_start')
        ends = sum(1 for log in logs if log['event_type'] == 'proc_end')
        
        # Unique apps
        unique_apps = set()
        for log in logs:
            if log['event_type'] in ['proc_start', 'proc_end']:
                name = log['fields'].get('name')
                if name:
                    unique_apps.add(name)
        
        return jsonify({
            'success': True,
            'period_hours': hours,
            'data': {
                'total_events': len(logs),
                'app_launches': starts,
                'app_closes': ends,
                'unique_apps': len(unique_apps),
                'app_names': sorted(list(unique_apps))
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/monitor/status', methods=['GET'])
def monitor_status():
    """Get current monitor status and configuration."""
    return jsonify({
        'success': True,
        'data': {
            'active': monitor_active,
            'config': monitor_config
        }
    })


@app.route('/api/monitor/start', methods=['POST'])
def start_monitor():
    """Start the monitoring process."""
    global monitor_thread, monitor_active
    
    if monitor_active:
        return jsonify({
            'success': False,
            'error': 'Monitor is already running'
        }), 400
    
    try:
        # Get configuration from request body
        data = request.get_json() or {}
        mode = data.get('mode', 'process')
        interval = data.get('interval', 2)
        gui_only = data.get('gui_only', True)
        include_system = data.get('include_system', False)
        
        # Update config
        monitor_config.update({
            'mode': mode,
            'interval': interval,
            'gui_only': gui_only,
            'include_system': include_system
        })
        
        # Setup logger
        logger = configure_logger(LOG_FILE)
        
        # Start monitoring in background thread
        monitor_active = True
        
        def run_monitor():
            if mode in ['active', 'both']:
                active_thread = threading.Thread(
                    target=monitor_active_app,
                    args=(interval, logger)
                )
                active_thread.daemon = True
                active_thread.start()
            
            if mode in ['process', 'both']:
                monitor_processes(
                    interval=interval,
                    logger=logger,
                    include_system=include_system,
                    snapshot_each_interval=False,
                    gui_only=gui_only,
                    whitelist=set()
                )
        
        monitor_thread = threading.Thread(target=run_monitor)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        return jsonify({
            'success': True,
            'message': 'Monitor started successfully',
            'config': monitor_config
        })
    
    except Exception as e:
        monitor_active = False
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/monitor/stop', methods=['POST'])
def stop_monitor():
    """Stop the monitoring process."""
    global monitor_active
    
    if not monitor_active:
        return jsonify({
            'success': False,
            'error': 'Monitor is not running'
        }), 400
    
    monitor_active = False
    
    return jsonify({
        'success': True,
        'message': 'Monitor stopped successfully'
    })


@app.route('/api/monitor/config', methods=['PUT'])
def update_config():
    """Update monitor configuration (requires restart if running)."""
    try:
        data = request.get_json()
        
        if 'mode' in data:
            monitor_config['mode'] = data['mode']
        if 'interval' in data:
            monitor_config['interval'] = int(data['interval'])
        if 'gui_only' in data:
            monitor_config['gui_only'] = bool(data['gui_only'])
        if 'include_system' in data:
            monitor_config['include_system'] = bool(data['include_system'])
        
        return jsonify({
            'success': True,
            'message': 'Configuration updated (restart monitor to apply changes)',
            'config': monitor_config
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ==================== Main ====================

if __name__ == '__main__':
    print("Active Apps Monitor REST API")
    print("=" * 50)
    print("Starting API server on http://localhost:5000")
    print("\nAvailable endpoints:")
    print("  GET  /api/health              - Health check")
    print("  GET  /api/system/health       - System metrics (CPU, memory, disk)")
    print("  GET  /api/apps/running        - Currently running GUI apps")
    print("  GET  /api/apps/active         - Currently active (foreground) app")
    print("  GET  /api/logs                - App usage logs (with filters)")
    print("  GET  /api/stats/apps          - Per-app usage statistics")
    print("  GET  /api/stats/summary       - Summary statistics")
    print("  GET  /api/monitor/status      - Monitor status and config")
    print("  POST /api/monitor/start       - Start monitoring")
    print("  POST /api/monitor/stop        - Stop monitoring")
    print("  PUT  /api/monitor/config      - Update configuration")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
