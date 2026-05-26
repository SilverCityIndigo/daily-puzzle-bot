# Daily Flow — Railway deploy checklist

The bot advances through `puzzles/p01.png`, `p02.png`, … using a **tracker file**. If that file is not on a **persistent volume**, every redeploy resets progress and you will see early puzzles (e.g. `p03`) posted again.

## One-time Railway setup

1. **Volume** — In the Railway project, add a volume mounted at `/data`.
2. **Variables** — You do not need `TRACKER_FILE` if the volume is mounted at `/data`; the bot defaults to `/data/tracker.json` when `RAILWAY_ENVIRONMENT` is set. To override, set `TRACKER_FILE=/data/tracker.json`.
3. **Redeploy** after the volume exists so the bot can create the tracker on disk.

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
