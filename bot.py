import asyncio
import discord
import os
import json
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
# On Railway, mount a volume and set e.g. TRACKER_FILE=/data/tracker.json so the puzzle index survives redeploys.
TRACKER_FILE = os.getenv("TRACKER_FILE", "tracker.json")

def get_tracker():
    if not os.path.exists(TRACKER_FILE):
        return {"last_index": -1}
    with open(TRACKER_FILE, "r") as f:
        return json.load(f)

def save_tracker(data):
    with open(TRACKER_FILE, "w") as f:
        json.dump(data, f)

def get_next_puzzle():
    puzzles = sorted([
        f for f in os.listdir(PUZZLES_DIR)
        if f.lower().endswith((".png", ".jpg", ".jpeg"))
    ])
    if not puzzles:
        return None
    tracker = get_tracker()
    next_index = tracker["last_index"] + 1
    if next_index >= len(puzzles):
        next_index = 0
    save_tracker({"last_index": next_index})
    return os.path.join(PUZZLES_DIR, puzzles[next_index])

intents = discord.Intents.default()
client = discord.Client(intents=intents)

@tasks.loop(hours=24)
async def post_puzzle():
    channel = client.get_channel(CHANNEL_ID)
    if channel is None:
        print("Channel not found")
        return
    puzzle_path = get_next_puzzle()
    if puzzle_path is None:
        print("No puzzles found in /puzzles folder")
        return
    date_str = datetime.now(pytz.timezone(POST_TIMEZONE)).strftime("%m/%d/%y")
    message = f"♟️ **Daily Puzzle ({date_str})**\nWhite to move — can you find the best continuation?"
    await channel.send(message, file=discord.File(puzzle_path))
    print(f"Posted: {puzzle_path}")

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

@client.event
async def on_ready():
    print(f"Daily Flow is online as {client.user}")
    post_puzzle.start()

client.run(TOKEN)