"""
Tracker CLI — no Discord dependency. Use in Railway SSH when `python bot.py` fails.

  python scripts/tracker.py status
  python scripts/tracker.py set p12.png
"""
import json
import os
import re
import sys

PUZZLES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "puzzles")


def _default_tracker_file() -> str:
    explicit = os.getenv("TRACKER_FILE", "").strip()
    if explicit:
        return explicit
    mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if mount:
        return os.path.join(mount, "tracker.json")
    if os.getenv("RAILWAY_ENVIRONMENT"):
        return "/data/tracker.json"
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tracker.json")


TRACKER_FILE = _default_tracker_file()


def get_tracker():
    if not os.path.exists(TRACKER_FILE):
        return {"last_index": -1}
    with open(TRACKER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_tracker(data):
    parent = os.path.dirname(os.path.abspath(TRACKER_FILE))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def _natural_sort_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def list_puzzle_files():
    if not os.path.isdir(PUZZLES_DIR):
        return []
    return sorted(
        (f for f in os.listdir(PUZZLES_DIR) if f.lower().endswith((".png", ".jpg", ".jpeg"))),
        key=_natural_sort_key,
    )


def resolve_last_index(puzzles: list[str], tracker: dict) -> int:
    last_file = tracker.get("last_file")
    last_index = tracker.get("last_index", -1)
    if last_file and last_file in puzzles:
        return puzzles.index(last_file)
    if 0 <= last_index < len(puzzles):
        return last_index
    return -1


def peek_next_filename():
    puzzles = list_puzzle_files()
    if not puzzles:
        return None
    nxt = resolve_last_index(puzzles, get_tracker()) + 1
    return puzzles[nxt] if nxt < len(puzzles) else None


def cmd_set(filename: str):
    puzzles = list_puzzle_files()
    if not puzzles:
        raise SystemExit("No puzzles in puzzles/")
    if filename not in puzzles:
        raise SystemExit(f"{filename!r} not in puzzle list: {puzzles}")
    idx = puzzles.index(filename)
    save_tracker({"last_index": idx, "last_file": filename})
    print(f"Tracker set: last_index={idx}, last_file={filename}")
    if idx + 1 < len(puzzles):
        print(f"Next post will be: {puzzles[idx + 1]}")
    else:
        print("Next post will wait until more puzzle images are added.")


def cmd_status():
    puzzles = list_puzzle_files()
    tracker = get_tracker()
    print(f"Tracker file: {os.path.abspath(TRACKER_FILE)}")
    print(f"Puzzles on disk ({len(puzzles)}): {', '.join(puzzles) if puzzles else '(none)'}")
    print(
        f"Last posted: {tracker.get('last_file', '(none)')} "
        f"(index {tracker.get('last_index', -1)})"
    )
    nxt = peek_next_filename()
    print(f"Next post would be: {nxt or '(none — add more puzzles)'}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__.strip())
        raise SystemExit(0)
    if sys.argv[1] == "status":
        cmd_status()
    elif sys.argv[1] == "set" and len(sys.argv) >= 3:
        cmd_set(sys.argv[2])
    else:
        print("Usage: python scripts/tracker.py status | set <filename>")
        raise SystemExit(1)
