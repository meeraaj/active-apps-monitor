import argparse
import logging
from logging.handlers import RotatingFileHandler
import os
import time
from datetime import datetime
import ctypes
from ctypes import wintypes
import threading
import psutil


# --- Windows APIs via ctypes ---
user32 = ctypes.windll.user32  # type: ignore[attr-defined]
kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]


def get_active_window_info():
    """
    Return a tuple (pid, process_name, window_title) for the current foreground window.

    If any value can't be retrieved, provide best-effort fallbacks and avoid raising.
    """
    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return (None, None, None)

        # Get PID from foreground window
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        pid_value = pid.value if pid.value != 0 else None

        # Get window title
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
        else:
            title = None

        # Resolve process name
        name = None
        if pid_value is not None:
            try:
                p = psutil.Process(pid_value)
                name = p.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                name = None

        return (pid_value, name, title)
    except Exception:
        # Never crash the logger because of window API glitches
        return (None, None, None)


def configure_logger(log_path: str, max_bytes: int = 1_000_000, backups: int = 5, also_stdout: bool = False) -> logging.Logger:
    """
    Configure a rotating file logger.

    - log_path: path to log file
    - max_bytes: rotate when exceeding this size
    - backups: number of backup files to keep
    - also_stdout: mirror logs to console
    """
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)

    logger = logging.getLogger("active_apps_monitor")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(log_path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    if also_stdout:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    return logger


def monitor_active_app(interval: float, logger: logging.Logger, heartbeat_seconds: float | None = 300.0):
    """
    Monitor changes to the foreground application and log when they change.

    - interval: polling interval in seconds
    - heartbeat_seconds: if set, re-log current app at this cadence even if unchanged
    """
    last = (None, None, None)
    last_heartbeat = time.monotonic()

    logger.info("monitor_active_start interval=%.2fs" % interval)
    try:
        while True:
            pid, name, title = get_active_window_info()
            current = (pid, name, title)

            now = time.monotonic()
            heartbeat_due = False
            if heartbeat_seconds is not None and (now - last_heartbeat) >= heartbeat_seconds:
                heartbeat_due = True
                last_heartbeat = now

            if current != last or heartbeat_due:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                pid_s = str(pid) if pid is not None else "?"
                name_s = name if name else "?"
                title_s = title if title else "?"
                logger.info(f"active pid={pid_s} name={name_s} title={title_s} ts={ts}")
                last = current

            time.sleep(max(0.1, float(interval)))
    except KeyboardInterrupt:
        logger.info("monitor_active_stop reason=keyboard_interrupt")
    except Exception as e:
        logger.exception("monitor_active_crash %s", e)


def _is_system_process(pid: int | None, name: str | None, username: str | None) -> bool:
    if pid in (0, 4):
        return True
    if username:
        uname = username.split("\\")[-1].upper()
        if uname in {"SYSTEM", "LOCAL SERVICE", "NETWORK SERVICE"}:
            return True
    if name in {"System", "System Idle Process"}:
        return True
    return False


def _get_process_snapshot(include_system: bool):
    """Return dict pid -> (name, create_time, username)."""
    snapshot = {}
    for p in psutil.process_iter(["pid", "name", "create_time", "username"]):
        try:
            pid = p.info.get("pid")
            name = p.info.get("name")
            ctime = p.info.get("create_time")
            user = p.info.get("username")
            if not include_system and _is_system_process(pid, name, user):
                continue
            if pid is not None:
                snapshot[pid] = (name, ctime, user)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return snapshot


def monitor_processes(interval: float, logger: logging.Logger, include_system: bool = False, snapshot_each_interval: bool = False):
    """
    Monitor process starts/stops. Optionally log full snapshot each interval.
    """
    logger.info(
        "monitor_process_start interval=%.2fs include_system=%s snapshot_each_interval=%s",
        interval,
        include_system,
        snapshot_each_interval,
    )
    prev = _get_process_snapshot(include_system)
    try:
        while True:
            time.sleep(max(0.1, float(interval)))
            curr = _get_process_snapshot(include_system)

            # Detect starts and stops
            started = curr.keys() - prev.keys()
            stopped = prev.keys() - curr.keys()

            for pid in sorted(started):
                name, ctime, user = curr.get(pid, (None, None, None))
                ctime_s = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S") if ctime else "?"
                user_s = user or "?"
                name_s = name or "?"
                logger.info(f"proc_start pid={pid} name={name_s} user={user_s} started_at={ctime_s}")

            for pid in sorted(stopped):
                name, ctime, user = prev.get(pid, (None, None, None))
                user_s = user or "?"
                name_s = name or "?"
                logger.info(f"proc_end pid={pid} name={name_s} user={user_s}")

            if snapshot_each_interval:
                # Log a compact snapshot header and then individual lines
                logger.info(f"proc_snapshot count={len(curr)}")
                for pid, (name, ctime, user) in curr.items():
                    name_s = name or "?"
                    user_s = user or "?"
                    logger.info(f"proc pid={pid} name={name_s} user={user_s}")

            prev = curr
    except KeyboardInterrupt:
        logger.info("monitor_process_stop reason=keyboard_interrupt")
    except Exception as e:
        logger.exception("monitor_process_crash %s", e)


def list_processes_once(print_func=print):
    """Replicate the original behavior: print all running processes once."""
    for process in psutil.process_iter(["pid", "name"]):
        try:
            print_func(f"PID: {process.info['pid']}, Name: {process.info['name']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue


def parse_args():
    parser = argparse.ArgumentParser(description="Active apps monitor for Windows")
    parser.add_argument("--interval", type=float, default=float(os.getenv("AAM_INTERVAL", 2.0)), help="Polling interval in seconds (default: 2.0)")
    parser.add_argument("--logfile", type=str, default=os.getenv("AAM_LOGFILE", "app-usage.log"), help="Path to log file (default: app-usage.log)")
    parser.add_argument("--stdout", action="store_true", help="Also log to console")
    parser.add_argument("--list-once", action="store_true", help="Print all running processes once and exit")
    parser.add_argument("--no-rotate", action="store_true", help="Disable file rotation (writes to a single file)")
    parser.add_argument("--heartbeat", type=float, default=float(os.getenv("AAM_HEARTBEAT", 300.0)), help="Heartbeat seconds to re-log even if unchanged; set 0 to disable")
    parser.add_argument("--mode", choices=["active", "process", "both"], default=os.getenv("AAM_MODE", "active"), help="What to monitor: foreground active app, process starts/stops, or both")
    parser.add_argument("--proc-snapshot", action="store_true", help="In process mode, also log full snapshot each interval")
    parser.add_argument("--include-system", action="store_true", help="Include system processes in process monitoring")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.list_once:
        list_processes_once()
        return

    if args.no_rotate:
        # Use a plain file handler if rotation disabled
        logger = logging.getLogger("active_apps_monitor")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        fh = logging.FileHandler(args.logfile, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        if args.stdout:
            sh = logging.StreamHandler()
            sh.setFormatter(fmt)
            logger.addHandler(sh)
    else:
        logger = configure_logger(args.logfile, also_stdout=args.stdout)

    heartbeat = None if args.heartbeat and args.heartbeat <= 0 else args.heartbeat

    if args.mode == "active":
        monitor_active_app(args.interval, logger, heartbeat_seconds=heartbeat)
    elif args.mode == "process":
        monitor_processes(args.interval, logger, include_system=args.include_system, snapshot_each_interval=bool(args.proc_snapshot))
    elif args.mode == "both":
        # Run processes in a background thread and active monitor in main thread
        t = threading.Thread(target=monitor_processes, args=(args.interval, logger), kwargs={"include_system": args.include_system, "snapshot_each_interval": bool(args.proc_snapshot)}, daemon=True)
        t.start()
        monitor_active_app(args.interval, logger, heartbeat_seconds=heartbeat)


if __name__ == "__main__":
    main()
