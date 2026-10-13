# Recording a video

Some problems only show up over time: the bot clicks the wrong cow, walks back and forth,
or gets stuck after an hour. A recording shows you what happened, and its frames show
Claude. (Claude can look at pictures but not videos, so the panel turns the part you care
about into one picture of 9 frames: `frames.png`.)

## You don't have to be recording: the black box

While the bot runs it keeps the last 80 seconds of screens in memory (one every 2
seconds). When something goes wrong (an error, or the HP guard running away), it saves them
in `data/incidents/<time>/`:

- `frames.png`: 9 frames up to the moment it went wrong, each with the time, the mouse
  (a cross) and the activity;
- `last.png`: the screen at that moment, full size;
- `log.txt`: why, and the end of the log.

**Send to PC** includes the newest one (`error-frames.png`, `error-last.png`,
`error-log.txt`), and when a run stops on an error Discord gets the picture with the
message. So after a problem: Send to PC, and tell me roughly when.

## Record

In the panel, the **Record** card:

1. Pick what to keep:
   - **keep everything (up to 60 min)**: for watching a problem happen.
   - **keep the last 5 (or 15) minutes**: leave it on during a long run you're not
     watching. When something goes wrong, the minutes before it are there.
2. Tick **whole screen** only if you need more than the game (e.g. a RuneLite popup or the
   panel itself). Without it, it records the game; Calibrate first.
3. Click **Record**. It runs next to whatever the bot is doing; start the bot as usual.
4. Click **Stop recording** when you've seen enough. It also stops by itself after
   60 minutes.

Under the picture each frame shows the **time**, the **mouse position** and the bot's
**latest log line**. The VM doesn't draw the mouse, so a white cross marks it.

## Send it

1. Watch the video if you like: on the PC it's in the shared folder after step 3. Or find
   the time where it went wrong in the panel's Output or the log.
2. In the Record card, type the times into **from** and **to**, e.g. `20:41:00` and
   `20:41:30` (the times under the picture). Leave them empty for the last 30 seconds.
3. Click **Send recording to PC**. The shared folder gets a new folder (`skillbot` → the
   newest) with everything **Send to PC** sends, plus:
   - `frames.png`: 9 frames evenly spread between your two times, each labelled with its
     time
   - a folder with the video: one file per minute (`part-0000.mp4`, `part-0001.mp4`, ...;
     they play in the Windows Media Player or VLC)
4. Drag `frames.png` into the chat, with the time and what you saw. If 9 frames are too
   far apart, send a shorter stretch (10 seconds gives a frame every second).

`frames.png` also shows up under **Images** in the panel.

## From a terminal

```sh
python -m skillbot record               # the game, until Ctrl+C (60 min at most)
python -m skillbot record --keep 5      # only the last 5 minutes
python -m skillbot record --screen      # the whole screen
python -m skillbot frames --from 20:41:00 --to 20:41:30   # frames.png from the newest
```

Recordings live in `data/recordings/`; the panel keeps the newest 5. They show your
account name, like screenshots, so they never go into git.
