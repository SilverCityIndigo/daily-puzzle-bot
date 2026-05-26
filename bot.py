import asyncio
import discord
import os
import json
import re
import sys
from discord.ext import tasks
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pytz

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
_channel_raw = os.getenv("CHANNEL_ID")
if not TOKEN or not TOKEN.strip():
    raise SystemExit("Set DISCORD_TOKEN in Railway Variables (or .env locally).")
if not _channel_raw or not _channel_raw.strip():
    raise SystemExit("Set CHANNEL_ID in Railway Variables (or .env locally).")
try:
    CHANNEL_ID = int(_channel_raw.strip())
except ValueError as e:
    raise SystemExit(f"CHANNEL_ID must be an integer (no quotes). Got: {_channel_raw!r}") from e
PUZZLES_DIR = "puzzles"
# Eastern Time (EST/EDT): same wall clock as Toronto; DST handled automatically.
POST_TIMEZONE = os.getenv("POST_TIMEZONE", "America/New_York")
# Daily post time when not in application-id test mode (see TEST_APPLICATION_ID).
POST_HOUR = int(os.getenv("POST_HOUR", "9"))
POST_MINUTE = int(os.getenv("POST_MINUTE", "0"))
# If TEST_APPLICATION_ID matches this bot's user id (same as Application ID in the portal),
# use TEST_POST_HOUR / TEST_POST_MINUTE instead. Omit on Railway so production stays on POST_HOUR.
TEST_APPLICATION_ID = os.getenv("TEST_APPLICATION_ID", "").strip()
TEST_POST_HOUR = int(os.getenv("TEST_POST_HOUR", "1"))
TEST_POST_MINUTE = int(os.getenv("TEST_POST_MINUTE", "0"))


def _default_tracker_file() -> str:
    explicit = os.getenv("TRACKER_FILE", "").strip()
    if explicit:
        return explicit
    # Railway containers wipe the app filesystem on redeploy; persist on a mounted volume.
    if os.getenv("RAILWAY_ENVIRONMENT"):
        return "/data/tracker.json"
    return "tracker.json"


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
        try:
            import fcntl  # Unix only (Railway/Linux)

            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        except ImportError:
            pass
        json.dump(data, f, indent=2)
        f.write("\n")


def _natural_sort_key(name: str):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def list_puzzle_files():
    """Sorted puzzle filenames (p01 before p10). Only files in puzzles/ on disk."""
    if not os.path.isdir(PUZZLES_DIR):
        return []
    return sorted(
        (
            f
            for f in os.listdir(PUZZLES_DIR)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        ),
        key=_natural_sort_key,
    )


def resolve_last_index(puzzles: list[str], tracker: dict) -> int:
    """
    Index of the last posted puzzle, or -1 if none.
    Prefer last_file so new puzzles can be added without index drift or redeploy resets.
    """
    last_file = tracker.get("last_file")
    last_index = tracker.get("last_index", -1)

    if last_file and last_file in puzzles:
        idx = puzzles.index(last_file)
        if last_index != idx:
            print(
                f"Tracker: using last_file {last_file} (index {idx}); "
                f"stored last_index was {last_index}"
            )
        return idx

    if 0 <= last_index < len(puzzles):
        if last_file:
            print(
                f"Warning: last_file {last_file!r} missing from puzzle list; "
                f"using last_index {last_index} ({puzzles[last_index]})"
            )
        return last_index

    if last_file or last_index != -1:
        print(
            f"Warning: tracker stale (last_file={last_file!r}, last_index={last_index}); "
            "starting from the first puzzle"
        )
    return -1


def peek_next_filename() -> str | None:
    puzzles = list_puzzle_files()
    if not puzzles:
        return None
    next_index = resolve_last_index(puzzles, get_tracker()) + 1
    if next_index >= len(puzzles):
        return None
    return puzzles[next_index]


def select_next_puzzle():
    """
    Choose the next puzzle without updating the tracker.
    Returns (path, filename, next_index) or None.
    """
    puzzles = list_puzzle_files()
    if not puzzles:
        return None
    tracker = get_tracker()
    last_index = resolve_last_index(puzzles, tracker)
    next_index = last_index + 1

    if next_index >= len(puzzles):
        last_name = puzzles[last_index] if last_index >= 0 else "(none)"
        print(
            f"No new puzzle to post: last posted was {last_name}. "
            f"Add the next image after {puzzles[-1]} to puzzles/ and redeploy. "
            "Tracker unchanged; will retry on the next scheduled run."
        )
        return None

    filename = puzzles[next_index]
    path = os.path.join(PUZZLES_DIR, filename)
    print(f"Next puzzle {next_index + 1}/{len(puzzles)}: {filename}")
    return path, filename, next_index


def commit_posted_puzzle(filename: str, next_index: int):
    save_tracker({"last_index": next_index, "last_file": filename})


def rewind_tracker_one():
    """Undo the last tracker advance (e.g. before re-posting after a mistaken daily)."""
    puzzles = list_puzzle_files()
    if not puzzles:
        return
    tracker = get_tracker()
    last_index = resolve_last_index(puzzles, tracker)
    if last_index <= 0:
        if os.path.exists(TRACKER_FILE):
            os.remove(TRACKER_FILE)
        print("Tracker cleared (no puzzles posted yet).")
        return
    prev = last_index - 1
    save_tracker({"last_index": prev, "last_file": puzzles[prev]})
    print(f"Tracker rewound to {puzzles[prev]} (index {prev})")


def daily_message_text():
    date_str = datetime.now(pytz.timezone(POST_TIMEZONE)).strftime("%m/%d/%y")
    return f"♟️ **Daily Puzzle ({date_str})**\nGood luck!"


intents = discord.Intents.default()
client = discord.Client(intents=intents)


async def send_next_puzzle(channel):
    selection = select_next_puzzle()
    if selection is None:
        return None
    path, filename, next_index = selection
    await channel.send(daily_message_text(), file=discord.File(path))
    commit_posted_puzzle(filename, next_index)
    print(f"Posted: {path}")
    return path


@tasks.loop(hours=24)
async def post_puzzle():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("Channel not found")
        return
    result = await send_next_puzzle(channel)
    if result is None:
        print("Skipped daily post (no puzzles or sequence exhausted).")


@post_puzzle.before_loop
async def before_puzzle():
    await client.wait_until_ready()
    tid = TEST_APPLICATION_ID
    if tid and client.user and str(client.user.id) == tid:
        hour, minute = TEST_POST_HOUR, TEST_POST_MINUTE
        print(
            f"Test schedule: next post at {hour:02d}:{minute:02d} "
            f"({POST_TIMEZONE}) — TEST_APPLICATION_ID matches this bot"
        )
    else:
        hour, minute = POST_HOUR, POST_MINUTE
        print(f"Production schedule: next post at {hour:02d}:{minute:02d} ({POST_TIMEZONE})")
    tz = pytz.timezone(POST_TIMEZONE)
    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    wait_seconds = (target - now).total_seconds()
    print(f"First puzzle posts in {wait_seconds/3600:.1f} hours")
    await asyncio.sleep(wait_seconds)


async def post_next_puzzle_once():
    """Post the next puzzle in sequence once (same tracker step as the daily job)."""
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        raise SystemExit(f"Channel {CHANNEL_ID} not found. Is the bot in this server?")
    tracker = get_tracker()
    print(
        f"Tracker before post: last_index={tracker.get('last_index', -1)}, "
        f"last_file={tracker.get('last_file', '(none)')}"
    )
    path = await send_next_puzzle(channel)
    if path is None:
        raise SystemExit("No puzzles found in puzzles/ or sequence exhausted.")
    after = get_tracker()
    print(
        f"Tracker after post: last_index={after.get('last_index')}, "
        f"last_file={after.get('last_file')}"
    )


async def delete_bot_message(message_id: int):
    """Delete a message this bot sent. Does not change tracker or post a new puzzle."""
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        raise SystemExit(f"Channel {CHANNEL_ID} not found.")
    msg = await channel.fetch_message(message_id)
    if msg.author.id != client.user.id:
        raise SystemExit("That message was not sent by this bot — delete it manually in Discord.")
    await msg.delete()
    print(f"Deleted message {message_id}")


async def replace_post(message_id: int):
    """
    Delete a mistaken daily post and re-send the puzzle for that slot.
    Rewinds the tracker by one step first so we do not skip ahead in the sequence.
    """
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        raise SystemExit(f"Channel {CHANNEL_ID} not found. Is the bot in this server?")
    tracker = get_tracker()
    print(
        f"Tracker before replace: last_index={tracker.get('last_index', -1)}, "
        f"last_file={tracker.get('last_file', '(none)')}"
    )
    msg = await channel.fetch_message(message_id)
    if msg.author.id != client.user.id:
        raise SystemExit(
            "That message was not sent by this bot. Delete it manually in Discord, "
            "then run replace only if you still need to post the next puzzle."
        )
    await msg.delete()
    print(f"Deleted message {message_id}")
    rewind_tracker_one()
    path = await send_next_puzzle(channel)
    if path is None:
        raise SystemExit("No puzzles found in puzzles/")
    after = get_tracker()
    print(
        f"Tracker after replace: last_index={after.get('last_index')}, "
        f"last_file={after.get('last_file')}"
    )
    print("Tomorrow's automatic post will continue from the next file after this one.")


async def run_one_shot_cli(action):
    @client.event
    async def on_ready():
        try:
            await action()
        finally:
            await client.close()

    async with client:
        await client.start(TOKEN)


def cmd_set_tracker(index: int, filename: str):
    puzzles = list_puzzle_files()
    if not puzzles:
        raise SystemExit("No puzzles in puzzles/")
    if index < -1 or index >= len(puzzles):
        raise SystemExit(f"index must be -1 .. {len(puzzles) - 1}; have {len(puzzles)} file(s)")
    if filename not in puzzles:
        raise SystemExit(f"{filename!r} not in puzzle list: {puzzles}")
    if puzzles[index] != filename:
        raise SystemExit(f"At index {index} expected {puzzles[index]!r}, got {filename!r}")
    save_tracker({"last_index": index, "last_file": filename})
    print(f"Tracker set: last_index={index}, last_file={filename}")
    if index + 1 < len(puzzles):
        print(f"Next post will be: {puzzles[index + 1]}")
    else:
        print("Next post will wait until more puzzle images are added.")


def cmd_set_tracker_file(filename: str):
    puzzles = list_puzzle_files()
    if not puzzles:
        raise SystemExit("No puzzles in puzzles/")
    if filename not in puzzles:
        raise SystemExit(f"{filename!r} not in puzzle list: {puzzles}")
    cmd_set_tracker(puzzles.index(filename), filename)


def warn_tracker_persistence():
    if not os.getenv("RAILWAY_ENVIRONMENT"):
        return
    if TRACKER_FILE == "tracker.json" or not TRACKER_FILE.startswith("/data"):
        print(
            "Warning: tracker is not on a Railway volume path — "
            "progress resets on redeploy. Mount a volume at /data "
            "(TRACKER_FILE defaults to /data/tracker.json on Railway)."
        )
    elif not os.path.isdir(os.path.dirname(TRACKER_FILE)):
        print(
            f"Warning: tracker directory {os.path.dirname(TRACKER_FILE)!r} does not exist. "
            "Mount a Railway volume at /data before the next deploy."
        )


def run_scheduled_bot():
    @client.event
    async def on_ready():
        print(f"Daily Flow is online as {client.user}")
        puzzles = list_puzzle_files()
        if puzzles:
            print(f"Loaded {len(puzzles)} puzzle(s): {', '.join(puzzles)}")
            tracker = get_tracker()
            last = tracker.get("last_file")
            if last:
                print(f"Last posted: {last} (index {tracker.get('last_index', -1)})")
            nxt = peek_next_filename()
            if nxt:
                print(f"Next scheduled post: {nxt}")
            else:
                print("Next scheduled post: (waiting for more puzzles in puzzles/)")
        else:
            print("Warning: no puzzle images in puzzles/ — posts will be skipped")
        warn_tracker_persistence()
        print(f"Tracker path: {os.path.abspath(TRACKER_FILE)}")
        post_puzzle.start()

    client.run(TOKEN)


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "post-now":
        asyncio.run(run_one_shot_cli(post_next_puzzle_once))
    elif len(sys.argv) >= 3 and sys.argv[1] == "delete":
        message_id = int(sys.argv[2])
        asyncio.run(run_one_shot_cli(lambda: delete_bot_message(message_id)))
    elif len(sys.argv) >= 3 and sys.argv[1] == "replace":
        message_id = int(sys.argv[2])
        asyncio.run(run_one_shot_cli(lambda: replace_post(message_id)))
    elif len(sys.argv) >= 4 and sys.argv[1] == "set-tracker":
        cmd_set_tracker(int(sys.argv[2]), sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "set-tracker-file":
        cmd_set_tracker_file(sys.argv[2])
    elif len(sys.argv) >= 2 and sys.argv[1] == "status":
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
        warn_tracker_persistence()
    else:
        run_scheduled_bot()
