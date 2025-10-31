# Active Apps Monitor (Windows)

A tiny Windows utility that logs which application is currently active (in the foreground), with timestamps and window titles — and can also log all processes as they start/stop.

## What it does

- Detects the foreground window using native Windows APIs (no extra packages beyond `psutil`).
- Logs PID, process name, window title, and timestamp whenever the active app changes.
- Optional heartbeat to re-log the current app at a fixed cadence.
- Process mode: logs process start/stop events; optional full snapshot per interval.
- Rotating file logs by default to keep size under control.
- Can also print a one-time list of running processes (original behavior).

## Install

Requires Python 3.8+ on Windows.

```powershell
# From the repo root
python -m pip install --upgrade pip ; `
python -m pip install -r requirements.txt
```

If `python` isn’t on your PATH, try the launcher:

```powershell
py -m pip install -r requirements.txt
```

## Run

Log the currently active app whenever it changes (writes `app-usage.log` in the current folder):

```powershell
python .\windowslogger.py
```

Useful options:

- `--interval <seconds>`: Polling interval (default: 2.0)
- `--logfile <path>`: Log file path (default: `app-usage.log`)
- `--stdout`: Also print logs to the console
- `--heartbeat <seconds>`: Re-log current app even if unchanged (set 0 to disable; default: 300)
- `--mode <active|process|both>`: What to monitor (default: `active`)
- `--proc-snapshot`: In `process` mode, also log a full snapshot each interval
- `--include-system`: In `process` mode, include system processes
- `--list-once`: Print all running processes once and exit
- `--no-rotate`: Disable rotating logs (writes to a single file)

Examples:

```powershell
# Log to a custom folder and also mirror to console
python .\windowslogger.py --logfile .\logs\app-usage.log --stdout

# Faster polling with no heartbeat
python .\windowslogger.py --interval 1.0 --heartbeat 0

# Original behavior: list processes and exit
python .\windowslogger.py --list-once

# Monitor process start/stop events
python .\windowslogger.py --mode process --stdout

# Monitor both active app and process events
python .\windowslogger.py --mode both --stdout

# Log a full snapshot of all processes every interval (careful: large logs)
python .\windowslogger.py --mode process --proc-snapshot --interval 5 --stdout

## Run in background and at logon

We include helper scripts under `scripts/`:

- `scripts\start-windowslogger.ps1` — starts the logger hidden in the background and writes to a log file (defaults to `%LOCALAPPDATA%\ActiveAppsMonitor\app-usage.log`).
- `scripts\register-startup-task.ps1` — registers a Task Scheduler task to run the logger at user logon.

Start hidden now (defaults to active app mode):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-windowslogger.ps1
```

Start both active and process monitoring, logging to your AppData folder:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start-windowslogger.ps1 -Mode both
```

Register to run at logon (uses Task Scheduler):

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\register-startup-task.ps1 -Mode both
```

To tail the log:

```powershell
Get-Content "$env:LOCALAPPDATA\ActiveAppsMonitor\app-usage.log" -Tail 50 -Wait
```
```

## Log format

Each line contains a timestamp and details. Examples:

```
# Active app
2025-10-29 11:35:10 | INFO | active pid=1234 name=chrome.exe title=Stack Overflow - How to ... ts=2025-10-29 11:35:10

# Process events
2025-10-29 11:36:02 | INFO | proc_start pid=43210 name=code.exe user=MEERA started_at=2025-10-29 11:36:01
2025-10-29 11:45:55 | INFO | proc_end pid=43210 name=code.exe user=MEERA

# Optional snapshot header + entries (when --proc-snapshot is used)
2025-10-29 11:40:00 | INFO | proc_snapshot count=142
2025-10-29 11:40:00 | INFO | proc pid=5576 name=Code.exe user=MEERA
...
```

Fields:
- `pid`: Process ID
- `name`: Process executable name
- `title`: Foreground window title
- `ts`: Redundant ISO-like timestamp included in the message body for easier downstream parsing

## Run at startup (Task Scheduler)

1. Open Task Scheduler and create a new task.
2. Triggers: At log on (or at startup).
3. Actions: Start a program
   - Program/script: `python`
   - Add arguments: `"C:\\path\\to\\windowslogger.py" --logfile "C:\\path\\to\\logs\\app-usage.log"`
   - Start in: `C:\\path\\to` (the folder containing the script)
4. Check "Run whether user is logged on or not" and "Run with highest privileges" if desired.

## Troubleshooting

- If you see access errors for some processes, that’s normal for protected system apps. The logger will skip them.
- Ensure you’re running on Windows; this tool uses Windows-specific APIs.
- If `psutil` is missing, install dependencies via `pip install -r requirements.txt`.

## License

MIT
