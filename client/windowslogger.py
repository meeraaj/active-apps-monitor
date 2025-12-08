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
from typing import Set


# --- Windows APIs via ctypes ---
user32 = ctypes.windll.user32  # type: ignore[attr-defined]
kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]

# Default set of noisy process names to ignore to reduce log noise. You can
# adjust this list or use `--whitelist` / `--gui-only` when running the script.
DEFAULT_IGNORE_NAMES: Set[str] = {
    "conhost.exe",
    "netsh.exe",
    "wslhost.exe",
    "wslrelay.exe",
    "vmmemwsl",
    "vmwp.exe",
    "git.exe",
    "git-remote-https.exe",
    "git-credential-manager.exe",
    "sh.exe",
}


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
    
    For browsers (Chrome, Edge, etc.), the window title often contains the page title
    and URL information, which helps track which websites are being visited.
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
                
                # For browser windows, the title often contains valuable info about the webpage
                # Format: "Page Title - Google Chrome" or "Page Title - Microsoft Edge"
                is_browser = name_s.lower() in {"chrome.exe", "msedge.exe", "brave.exe", "firefox.exe"}
                
                if is_browser and title_s != "?":
                    # Extract page title (remove " - Google Chrome" suffix etc.)
                    page_title = title_s
                    for browser_suffix in [" - Google Chrome", " - Microsoft Edge", " - Brave", " - Mozilla Firefox"]:
                        if page_title.endswith(browser_suffix):
                            page_title = page_title[:-len(browser_suffix)]
                            break
                    logger.info(f"active pid={pid_s} name={name_s} page={page_title} window_title={title_s} ts={ts}")
                else:
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


def _get_top_level_window_pids() -> set:
    """Return a set of PIDs that own visible top-level windows.

    Uses EnumWindows + GetWindowThreadProcessId + IsWindowVisible. This helps
    identify GUI applications versus short-lived console/helper processes.
    """
    pids = set()

    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, lParam):
        try:
            # Only consider visible windows with non-empty titles
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            # Skip windows with no title (often not user-facing)
            if length == 0:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                pids.add(pid.value)
        except Exception:
            # Don't let window API errors stop enumeration
            pass
        return True

    enum_cb = WNDENUMPROC(_callback)
    try:
        user32.EnumWindows(enum_cb, 0)
    except Exception:
        # EnumWindows can sometimes fail under restricted contexts; ignore
        pass

    return pids


def _is_main_browser_process(pid: int, name: str) -> bool:
    """Return True if this is a main browser process, False if it's a child/helper.

    Chrome/Edge/Brave use multi-process architecture. Child processes have
    --type=renderer, --type=gpu-process, etc. in their command line. The main
    browser process (the one the user launched) typically has no --type flag
    or has --type=browser (rare).

    For non-browser processes, always returns True (treat as main).
    """
    # Only apply this logic to known Chromium-based browsers
    if name.lower() not in {"chrome.exe", "msedge.exe", "brave.exe", "msedgewebview2.exe"}:
        return True  # not a browser we recognize, treat as main

    try:
        p = psutil.Process(pid)
        cmdline = p.cmdline()
        # Check for --type= flags (child processes have these)
        for arg in cmdline:
            if arg.startswith("--type="):
                # --type=browser is the main process (rare but valid)
                if arg == "--type=browser":
                    return True
                # Any other --type means it's a child process
                return False
        # No --type flag found → this is the main browser process
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
        # Can't determine, assume it's main to avoid missing launches
        return True


def _get_window_title_for_pid(pid: int) -> str | None:
    """Try to find a window title for a given PID by enumerating all windows.
    
    This is useful for getting browser page titles when a process starts.
    Returns None if no window title found or if errors occur.
    """
    found_title = None
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd, lParam):
        nonlocal found_title
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            
            # Get PID for this window
            window_pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
            
            if window_pid.value == pid:
                # Get window title
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if buf.value:
                        found_title = buf.value
                        return False  # Stop enumeration, we found it
        except Exception:
            pass
        return True

    enum_cb = WNDENUMPROC(_callback)
    try:
        user32.EnumWindows(enum_cb, 0)
    except Exception:
        pass

    return found_title


def monitor_processes(
    interval: float,
    logger: logging.Logger,
    include_system: bool = False,
    snapshot_each_interval: bool = False,
    gui_only: bool = False,
    whitelist: set | None = None,
):
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
    prev_windowed = _get_top_level_window_pids() if gui_only else set()
    # Cache exe paths for PIDs we learn about so proc_end can include the exe even
    # if the process has already exited by the time we handle the end event.
    pid_exe_cache: dict[int, str] = {}
    # Combine default ignore list with any runtime logic. We keep the default
    # ignore set here and allow whitelist/gui_only to override logging behavior.
    ignore_names = {n.lower() for n in DEFAULT_IGNORE_NAMES}
    whitelist = {n.lower() for n in (whitelist or set())}
    try:
        while True:
            time.sleep(max(0.1, float(interval)))
            curr = _get_process_snapshot(include_system)
            curr_windowed = _get_top_level_window_pids() if gui_only else set()

            # Detect starts and stops
            started = curr.keys() - prev.keys()
            stopped = prev.keys() - curr.keys()

            for pid in sorted(started):
                name, ctime, user = curr.get(pid, (None, None, None))
                ctime_s = datetime.fromtimestamp(ctime).strftime("%Y-%m-%d %H:%M:%S") if ctime else "?"
                user_s = user or "?"
                name_s = name or "?"
                # Skip noisy helper processes by default to reduce log volume.
                if name_s.lower() in ignore_names and (not whitelist or name_s.lower() not in whitelist) and not gui_only:
                    # still cache a placeholder so that any later proc_end can clear state
                    pid_exe_cache.pop(pid, None)
                    continue

                # For Chrome/Edge/Brave, skip child processes (only log main browser process)
                if not _is_main_browser_process(pid, name_s):
                    pid_exe_cache.pop(pid, None)
                    continue

                # Attempt to resolve the executable path now and cache it. This may
                # fail with AccessDenied or NoSuchProcess; handle gracefully. We
                # avoid doing this for ignored names above.
                exe_s = "?"
                try:
                    p = psutil.Process(pid)
                    exe_val = p.exe()
                    if exe_val:
                        exe_s = exe_val
                except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                    exe_s = "?"
                pid_exe_cache[pid] = exe_s

                # If gui_only is enabled, only log if this PID currently owns a
                # top-level window or its name is explicitly whitelisted.
                if gui_only:
                    if pid not in curr_windowed and name_s.lower() not in whitelist:
                        continue

                # For browsers, try to get the window title (often contains page info)
                is_browser = name_s.lower() in {"chrome.exe", "msedge.exe", "brave.exe", "firefox.exe"}
                if is_browser:
                    # Give the browser a moment to create its window
                    time.sleep(0.5)
                    window_title = _get_window_title_for_pid(pid)
                    if window_title:
                        # Extract page title (remove browser suffix)
                        page_title = window_title
                        for browser_suffix in [" - Google Chrome", " - Microsoft Edge", " - Brave", " - Mozilla Firefox"]:
                            if page_title.endswith(browser_suffix):
                                page_title = page_title[:-len(browser_suffix)]
                                break
                        logger.info(f"proc_start pid={pid} name={name_s} exe={exe_s} user={user_s} started_at={ctime_s} page={page_title} window_title={window_title}")
                    else:
                        logger.info(f"proc_start pid={pid} name={name_s} exe={exe_s} user={user_s} started_at={ctime_s}")
                else:
                    logger.info(f"proc_start pid={pid} name={name_s} exe={exe_s} user={user_s} started_at={ctime_s}")

            for pid in sorted(stopped):
                name, ctime, user = prev.get(pid, (None, None, None))
                user_s = user or "?"
                name_s = name or "?"
                # For proc_end, rely on the previous windowed set: if this PID had
                # a top-level window previously, treat it as a GUI app close. Also
                # honor whitelist entries regardless.
                if gui_only:
                    if pid not in prev_windowed and name_s.lower() not in whitelist:
                        # ensure we clean cached state
                        pid_exe_cache.pop(pid, None)
                        continue

                # If the name is in the ignore list and we aren't whitelisting it,
                # skip logging (but clear any cached state).
                if name_s.lower() in ignore_names and (not whitelist or name_s.lower() not in whitelist) and not gui_only:
                    pid_exe_cache.pop(pid, None)
                    continue

                # For Chrome/Edge/Brave, skip child processes (only log main browser process)
                if not _is_main_browser_process(pid, name_s):
                    pid_exe_cache.pop(pid, None)
                    continue

                # Prefer cached exe (from proc_start); if missing, try to query it
                # now (may fail if process already exited).
                exe_s = pid_exe_cache.pop(pid, None)
                if not exe_s:
                    try:
                        p = psutil.Process(pid)
                        exe_val = p.exe()
                        exe_s = exe_val if exe_val else "?"
                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                        exe_s = "?"

                logger.info(f"proc_end pid={pid} name={name_s} exe={exe_s} user={user_s}")

            if snapshot_each_interval:
                # Log a compact snapshot header and then individual lines. If
                # gui_only is set, filter snapshot entries to GUI/whitelisted procs.
                display_items = curr.items()
                if gui_only:
                    display_items = ((pid, info) for pid, info in curr.items() if pid in curr_windowed or (info[0] or "").lower() in whitelist)
                logger.info(f"proc_snapshot count={len(curr)}")
                for pid, (name, ctime, user) in display_items:
                    name_s = name or "?"
                    user_s = user or "?"
                    logger.info(f"proc pid={pid} name={name_s} user={user_s}")
            prev = curr
            prev_windowed = curr_windowed
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
    parser.add_argument("--gui-only", action="store_true", help="Only log processes that own top-level visible windows (or are whitelisted)")
    parser.add_argument("--whitelist", type=str, default="", help="Comma-separated process names to always include (e.g., chrome.exe,Code.exe)")
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

    # Build whitelist set from comma-separated CLI argument
    whitelist_set = {s.strip().lower() for s in args.whitelist.split(",") if s.strip()} if getattr(args, "whitelist", None) is not None else set()

    if args.mode == "active":
        monitor_active_app(args.interval, logger, heartbeat_seconds=heartbeat)
    elif args.mode == "process":
        monitor_processes(
            args.interval,
            logger,
            include_system=args.include_system,
            snapshot_each_interval=bool(args.proc_snapshot),
            gui_only=args.gui_only,
            whitelist=whitelist_set,
        )
    elif args.mode == "both":
        # Run processes in a background thread and active monitor in main thread
        t = threading.Thread(
            target=monitor_processes,
            args=(args.interval, logger),
            kwargs={
                "include_system": args.include_system,
                "snapshot_each_interval": bool(args.proc_snapshot),
                "gui_only": args.gui_only,
                "whitelist": whitelist_set,
            },
            daemon=True,
        )
        t.start()
        monitor_active_app(args.interval, logger, heartbeat_seconds=heartbeat)


if __name__ == "__main__":
    main()
