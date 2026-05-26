# Daily Flow — Railway deploy checklist

The bot advances through `puzzles/p01.png`, `p02.png`, … using a **tracker file**. If that file is not on a **persistent volume**, every redeploy resets progress and you will see early puzzles (e.g. `p03`) posted again.

## One-time Railway setup

1. **Volume** — Open the **worker** service → **Settings** → **Volumes**. Mount path should be `/data` (`worker-volume`).
2. **Redeploy** after the volume exists.
3. **Sync tracker once** via `railway ssh` (not `railway run` — that runs on your PC):

```bash
railway ssh
python scripts/tracker.py set p12.png
python scripts/tracker.py status
exit
```

Use `scripts/tracker.py` in SSH because `python bot.py` needs the Discord package, which is not on the default `python` in the container shell.

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
