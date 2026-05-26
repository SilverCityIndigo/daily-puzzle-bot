# Daily Flow — Railway deploy checklist

The bot advances through `puzzles/p01.png`, `p02.png`, … using a **tracker file**. If that file is not on a **persistent volume**, every redeploy resets progress and you will see early puzzles (e.g. `p03`) posted again.

## One-time Railway setup

1. **Volume** — Open the **worker** service (not the command search) → **Settings** → scroll to **Volumes**. You may already have `worker-volume` on the project canvas. If not, click **Add Volume** and pick a mount path (e.g. `/data`).
2. **Variables** — With a volume attached, Railway sets `RAILWAY_VOLUME_MOUNT_PATH` automatically. The bot stores the tracker at `{that path}/tracker.json`. You only need `TRACKER_FILE` if you want a custom path.
3. **Redeploy** after the volume exists, then run `python bot.py set-tracker-file p12.png` (or whatever was last posted) once in Railway Shell.

## After a bad or duplicate post

```bash
# See what the bot thinks is next (run in Railway shell or: railway run python bot.py status)
python bot.py status

# Point tracker at the last puzzle that was actually sent (example: p11 was last, so next is p12)
python bot.py set-tracker-file p11.png

# Optional: post today's puzzle immediately
python bot.py post-now
```

`delete` removes a Discord message only; it does **not** move the tracker.

`replace <message_id>` deletes the message, **rewinds** the tracker one step, then posts that slot again (no double-skip).

## Verify before relying on the schedule

```bash
python bot.py status
```

Confirm:

- `Tracker file` is `/data/tracker.json` (not `/app/tracker.json`)
- `Next post would be` is the puzzle you expect
