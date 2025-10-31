import argparse
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Match lines like:
# 2025-10-29 19:33:07 | INFO | active pid=5576 name=Code.exe title=... ts=2025-10-29 19:33:07
ACTIVE_LINE = re.compile(r"\| INFO \| active .*?ts=(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")


def hour_key(ts: datetime) -> str:
    return ts.strftime("%Y-%m-%d %H:00:00")


def group_lines_by_hour(logfile: Path):
    groups: dict[str, list[str]] = defaultdict(list)
    with logfile.open("r", encoding="utf-8", errors="ignore") as f:
        for raw in f:
            if "| INFO | active " not in raw:
                continue
            m = ACTIVE_LINE.search(raw)
            if not m:
                continue
            ts = datetime.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S")
            groups[hour_key(ts)].append(raw.rstrip("\n"))
    return groups


def write_hourly_log(groups, out_log: Path):
    with out_log.open("w", encoding="utf-8") as lf:
        hours = sorted(groups.keys())
        for idx, hour in enumerate(hours):
            lf.write(f"===== {hour} =====\n")
            for line in groups[hour]:
                lf.write(line + "\n")
            if idx < len(hours) - 1:
                lf.write("---------- hour boundary ----------\n")


def _parse_hour(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:00:00")


def _now_hour() -> datetime:
    n = datetime.now()
    return n.replace(minute=0, second=0, microsecond=0)


def _load_state(state_path: Path) -> datetime | None:
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        s = data.get("last_hour")
        if s:
            return _parse_hour(s)
    except Exception:
        return None
    return None


def _save_state(state_path: Path, hour_dt: datetime):
    payload = {"last_hour": hour_dt.strftime("%Y-%m-%d %H:00:00")}
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def append_new_hours(groups, out_log: Path, state_path: Path):
    hours = sorted(groups.keys())
    if not hours:
        return 0
    last_hour_dt = _load_state(state_path)
    current_hour = _now_hour()

    # Decide which hours to append: strictly after last_hour_dt and strictly before current_hour
    to_write: list[str] = []
    for h in hours:
        h_dt = _parse_hour(h)
        if (last_hour_dt is None or h_dt > last_hour_dt) and h_dt < current_hour:
            to_write.append(h)

    if not to_write:
        return 0

    # If file already has content, add a boundary before appending the next block
    need_leading_boundary = out_log.exists() and out_log.stat().st_size > 0

    with out_log.open("a", encoding="utf-8") as lf:
        first = True
        for idx, hour in enumerate(to_write):
            if need_leading_boundary and first:
                lf.write("---------- hour boundary ----------\n")
            first = False
            lf.write(f"===== {hour} =====\n")
            for line in groups[hour]:
                lf.write(line + "\n")
            if idx < len(to_write) - 1:
                lf.write("---------- hour boundary ----------\n")

    # Update state to the last written hour
    _save_state(state_path, _parse_hour(to_write[-1]))
    return len(to_write)


def main():
    ap = argparse.ArgumentParser(description="Simple hourly timestamp-based logger: groups original active lines by hour")
    ap.add_argument("--logfile", default="app-usage.log", help="Input log file (from windowslogger.py)")
    ap.add_argument("--out-log", dest="out_log", default="usage-hourly.log", help="Output hourly grouped log")
    ap.add_argument("--append", action="store_true", help="Append only new completed hours using a simple state file")
    ap.add_argument("--state", default=".simple_hourly_state.json", help="Path to the state file for append mode")
    ap.add_argument("--quiet", action="store_true", help="Suppress console output")
    args = ap.parse_args()

    groups = group_lines_by_hour(Path(args.logfile))
    out_path = Path(args.out_log)
    if args.append:
        wrote = append_new_hours(groups, out_path, Path(args.state))
        if not args.quiet:
            print(f"Appended {wrote} hour(s) to {args.out_log}")
    else:
        write_hourly_log(groups, out_path)
        if not args.quiet:
            print(f"Wrote hourly log to {args.out_log}")


if __name__ == "__main__":
    main()
