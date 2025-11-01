# Active Apps Monitor REST API

A RESTful API for monitoring Windows application usage, system health, and providing productivity insights.

## Quick Start

### Installation

```powershell
# Install dependencies
& 'C:\msys64\ucrt64\bin\python.exe' -m pip install -r requirements.txt
```

### Run the API Server

```powershell
# Start the API server
& 'C:\msys64\ucrt64\bin\python.exe' .\api.py
```

The API will start on `http://localhost:5000`

## API Endpoints

### Health & Status

#### `GET /api/health`
Health check endpoint.

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-11-01T10:30:00",
  "monitor_active": false
}
```

---

### System Monitoring

#### `GET /api/system/health`
Get system health metrics (CPU, memory, disk usage).

**Response:**
```json
{
  "success": true,
  "data": {
    "cpu": {
      "percent": 45.2,
      "count": 8
    },
    "memory": {
      "total_gb": 16.0,
      "used_gb": 8.5,
      "percent": 53.1
    },
    "disk": {
      "total_gb": 500.0,
      "used_gb": 250.0,
      "percent": 50.0
    },
    "timestamp": "2025-11-01T10:30:00"
  }
}
```

---

### Application Monitoring

#### `GET /api/apps/running`
Get list of currently running GUI applications.

**Response:**
```json
{
  "success": true,
  "count": 5,
  "data": [
    {
      "pid": 12345,
      "name": "chrome.exe",
      "exe": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
      "user": "MRUDU\\mrudh",
      "started_at": "2025-11-01T10:00:00",
      "cpu_percent": 5.2,
      "memory_mb": 450.5
    }
  ]
}
```

#### `GET /api/apps/active`
Get currently active (foreground) application.

**Response:**
```json
{
  "success": true,
  "data": {
    "pid": 12345,
    "name": "chrome.exe",
    "title": "GitHub - Google Chrome",
    "exe": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "user": "MRUDU\\mrudh",
    "cpu_percent": 5.2,
    "memory_mb": 450.5
  }
}
```

---

### Log Queries

#### `GET /api/logs`
Get app usage logs with optional filters.

**Query Parameters:**
- `limit` (int, default: 100) - Maximum number of logs to return
- `event_type` (string) - Filter by event type: `proc_start`, `proc_end`, `active_window`
- `app` (string) - Filter by app name (case-insensitive substring match)
- `hours` (int) - Get logs from last N hours

**Examples:**
```
GET /api/logs?limit=50
GET /api/logs?event_type=proc_start
GET /api/logs?app=chrome&hours=24
GET /api/logs?event_type=proc_end&limit=20
```

**Response:**
```json
{
  "success": true,
  "count": 10,
  "data": [
    {
      "timestamp": "2025-11-01T10:00:00",
      "level": "INFO",
      "event_type": "proc_start",
      "fields": {
        "pid": "12345",
        "name": "chrome.exe",
        "exe": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "user": "MRUDU\\mrudh",
        "started_at": "2025-11-01T10:00:00"
      }
    }
  ]
}
```

---

### Statistics & Analytics

#### `GET /api/stats/apps`
Get usage statistics per application.

**Query Parameters:**
- `hours` (int, default: 24) - Time period for statistics

**Example:**
```
GET /api/stats/apps?hours=24
```

**Response:**
```json
{
  "success": true,
  "period_hours": 24,
  "count": 5,
  "data": [
    {
      "app_name": "chrome.exe",
      "launch_count": 3,
      "total_duration_sec": 7200.5,
      "total_duration_minutes": 120.01,
      "avg_duration_sec": 2400.17,
      "sessions": [
        {
          "start": "2025-11-01T08:00:00",
          "end": "2025-11-01T09:00:00",
          "duration_sec": 3600.0
        }
      ]
    }
  ]
}
```

#### `GET /api/stats/summary`
Get summary statistics for a time period.

**Query Parameters:**
- `hours` (int, default: 24) - Time period for statistics

**Response:**
```json
{
  "success": true,
  "period_hours": 24,
  "data": {
    "total_events": 150,
    "app_launches": 75,
    "app_closes": 75,
    "unique_apps": 12,
    "app_names": ["chrome.exe", "code.exe", "notepad.exe", ...]
  }
}
```

---

### Monitor Control

#### `GET /api/monitor/status`
Get current monitor status and configuration.

**Response:**
```json
{
  "success": true,
  "data": {
    "active": false,
    "config": {
      "mode": "process",
      "interval": 2,
      "gui_only": true,
      "include_system": false
    }
  }
}
```

#### `POST /api/monitor/start`
Start the monitoring process.

**Request Body:**
```json
{
  "mode": "process",
  "interval": 2,
  "gui_only": true,
  "include_system": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Monitor started successfully",
  "config": {
    "mode": "process",
    "interval": 2,
    "gui_only": true,
    "include_system": false
  }
}
```

#### `POST /api/monitor/stop`
Stop the monitoring process.

**Response:**
```json
{
  "success": true,
  "message": "Monitor stopped successfully"
}
```

#### `PUT /api/monitor/config`
Update monitor configuration (requires restart if running).

**Request Body:**
```json
{
  "mode": "both",
  "interval": 5,
  "gui_only": false,
  "include_system": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "Configuration updated (restart monitor to apply changes)",
  "config": {
    "mode": "both",
    "interval": 5,
    "gui_only": false,
    "include_system": true
  }
}
```

---

## Usage Examples

### Using cURL (PowerShell)

```powershell
# Get system health
curl http://localhost:5000/api/system/health

# Get running apps
curl http://localhost:5000/api/apps/running

# Get logs from last 12 hours
curl "http://localhost:5000/api/logs?hours=12&limit=50"

# Start monitoring
curl -X POST http://localhost:5000/api/monitor/start `
  -H "Content-Type: application/json" `
  -d '{"mode":"process","interval":2,"gui_only":true}'

# Stop monitoring
curl -X POST http://localhost:5000/api/monitor/stop
```

### Using Python Requests

```python
import requests

BASE_URL = "http://localhost:5000/api"

# Get system health
response = requests.get(f"{BASE_URL}/system/health")
print(response.json())

# Get app statistics
response = requests.get(f"{BASE_URL}/stats/apps?hours=24")
print(response.json())

# Start monitoring
config = {
    "mode": "process",
    "interval": 2,
    "gui_only": True,
    "include_system": False
}
response = requests.post(f"{BASE_URL}/monitor/start", json=config)
print(response.json())
```

### Using JavaScript (Fetch)

```javascript
const BASE_URL = 'http://localhost:5000/api';

// Get running apps
fetch(`${BASE_URL}/apps/running`)
  .then(res => res.json())
  .then(data => console.log(data));

// Get logs
fetch(`${BASE_URL}/logs?hours=24&event_type=proc_start`)
  .then(res => res.json())
  .then(data => console.log(data));

// Start monitoring
fetch(`${BASE_URL}/monitor/start`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    mode: 'process',
    interval: 2,
    gui_only: true
  })
})
  .then(res => res.json())
  .then(data => console.log(data));
```

---

## Configuration Options

### Monitor Modes

- `active` - Track foreground window changes
- `process` - Track process start/stop events
- `both` - Track both window changes and process events

### Parameters

- `interval` - Polling interval in seconds (default: 2)
- `gui_only` - Only track GUI applications with visible windows (default: true)
- `include_system` - Include system processes in monitoring (default: false)

---

## Error Handling

All endpoints return errors in this format:

```json
{
  "success": false,
  "error": "Error message here"
}
```

HTTP status codes:
- `200` - Success
- `400` - Bad request (invalid parameters)
- `500` - Internal server error

---

## Development

### Running in Development Mode

The API runs in debug mode by default when started directly:

```powershell
& 'C:\msys64\ucrt64\bin\python.exe' .\api.py
```

### Production Deployment

For production, use a WSGI server like Gunicorn or Waitress:

```powershell
# Install waitress
& 'C:\msys64\ucrt64\bin\python.exe' -m pip install waitress

# Run with waitress
& 'C:\msys64\ucrt64\bin\python.exe' -c "from waitress import serve; from api import app; serve(app, host='0.0.0.0', port=5000)"
```

---

## Security Notes

⚠️ **Important**: This API is designed for local use. If exposing to a network:

1. Add authentication (API keys, JWT tokens)
2. Use HTTPS (TLS/SSL)
3. Implement rate limiting
4. Validate and sanitize all inputs
5. Run behind a reverse proxy (nginx, Apache)

---

## Troubleshooting

### Port Already in Use

```powershell
# Find process using port 5000
netstat -ano | findstr :5000

# Kill the process (replace PID)
taskkill /PID <PID> /F
```

### Module Not Found Errors

```powershell
# Reinstall dependencies
& 'C:\msys64\ucrt64\bin\python.exe' -m pip install -r requirements.txt
```

### CORS Issues

The API has CORS enabled by default. If you still face issues, check:
- Browser console for specific CORS errors
- Ensure `flask-cors` is installed
- Check if any firewall/proxy is blocking requests

---

## Next Steps

Consider adding:
- [ ] Authentication (JWT, API keys)
- [ ] WebSocket support for real-time updates
- [ ] Database storage (SQLite, PostgreSQL)
- [ ] Productivity scoring/alerting
- [ ] Web dashboard UI
- [ ] Export functionality (CSV, JSON, PDF reports)
- [ ] Scheduled reports/notifications
