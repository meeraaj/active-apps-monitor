# Simple App Monitor

This is a simplified monitor that tracks application start and stop events.

## Features
- Monitors process start and stop events.
- Logs to `logs/monitor.log`.
- Rotates the log file every hour.
- Zips the previous hour's log file automatically.
- Does NOT record active tab switches (focus changes).

## How to Run

1. Open a terminal.
2. Run the script:
   ```bash
   python simple_monitor.py
   ```
3. To stop, press `Ctrl+C`.

## Configuration
The script is configured to:
- Check for changes every 2.0 seconds.
- Log all processes (including background ones) to ensure no apps are missed.
- Ignore system processes (like System, Registry).

## Output
Logs are stored in the `logs` directory.
- Current log: `monitor.log`
- Archived logs: `monitor.log.YYYY-MM-DD_HH-MM-SS.zip`
