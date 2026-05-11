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
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))
PUZZLES_DIR = "puzzles"
# Eastern Time (EST/EDT): same wall clock as Toronto; DST handled automatically.
POST_TIMEZONE = os.getenv("POST_TIMEZONE", "America/New_York")
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
    # Wait until next 9:00 AM in POST_TIMEZONE (default US Eastern).
    tz = pytz.timezone(POST_TIMEZONE)
    now = datetime.now(tz)
    target = now.replace(hour=9, minute=0, second=0, microsecond=0)
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