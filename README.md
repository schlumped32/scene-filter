# Scene Filter

Finds nudity in a movie file you own and makes a filtered copy (cut, blur or black screen), or just a list of
timestamps. Everything runs on your own computer; nothing is uploaded.

## Download

Get the newest version from the **Releases** page (right-hand side of this page):

- **Mac:** `Scene_Filter_for_Mac.zip`
- **Windows:** `Scene_Filter_for_Windows.zip`

Each download has a "How to open" file inside. After the first install, Scene Filter **updates itself**: each time
it opens, it checks here for a newer version and installs it. If an update ever fails to start, it goes back to the
previous version on its own.

## How it works

1. A quick pass over the whole movie (NudeNet's small model, 2 frames a second, several in parallel) flags
   anything that might be nudity, deliberately loosely.
2. Each suspicious moment is double-checked closely: 6 frames a second with NudeNet's larger, more accurate model.
   Only this closer look decides what's flagged.
3. You review the flagged scenes (blurred previews), untick any you want left alone, and choose what to do.

The "Animated movie" switch raises the bar for cartoons, which fool the detector. No detector is perfect:
review the results before relying on them.

## Project layout

| Folder | What's in it |
|---|---|
| `app/` | The app itself. This is what updates. `VERSION` is its version number. |
| `launcher/run.py` | The starter: checks for updates, installs them, falls back if one fails. Changes rarely. |
| `mac/` | The Mac app wrapper and its launcher script. |
| `windows/` | The Windows launcher. |
| `tools/build.py` | Builds a release. See `RELEASING.md`. |

## Credits and licenses

Detection uses [NudeNet](https://github.com/notAI-tech/NudeNet), whose license is the GNU AGPL-3.0.
Video work uses [FFmpeg](https://ffmpeg.org) (via imageio-ffmpeg). The browser screen uses Gradio.
