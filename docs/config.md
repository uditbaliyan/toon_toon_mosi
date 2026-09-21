# Configuration & CLI Reference

This document provides a comprehensive reference for the command-line interface arguments, global system settings in `src/config.py`, and dynamic settings overrides.

---

## 💻 Command-Line Interface (CLI)

The orchestrator `main.py` is invoked via a CLI with 9 arguments:

| Option | Type | Required | Default | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `--script` | String | **Yes** | — | Path to the annotated transcript file (.txt) containing `<emotion>` tags. |
| `--audio` | String | **Yes** | — | Path to the voiceover WAV file (.wav). |
| `--output` | String | **Yes** | — | Path to output the final video file (.mp4). |
| `--character` | String | No | `"cary"` | Target character subdirectory name under `assets/characters/`. |
| `--use_blender`| String | No | `"true"` | Toggle `MouthBlender` coarticulation (`"true"` or `"false"`). |
| `--bg_video` | String | No | `None` | Path to overlay background video (reserved). |
| `--bg_music` | String | No | `None` | Path to background music track (.wav). |
| `--music_volume`| Float | No | `0.044` | Volume multiplier for background music track (0.0 to 1.0). |

---

## ⚙️ Global Configuration Settings (`src/config.py`)

Global constants are consolidated inside [config.py](file:///c:/Users/HP/Desktop/Github/toon_toon/toon_toon_mosi/src/config.py) and serve as default values:

```python
# Canvas Defaults
FRAME_RATE = 30                 # Pipeline rendering and output framerate
CANVAS_WIDTH = 1280             # Canvas composition area width
CANVAS_HEIGHT = 720             # Canvas composition area height

# Jiggle Transition Decay Oscillation
POSE_CHANGE_MIN_SECONDS = 2     # Minimum delay between random pose shifts
POSE_CHANGE_MAX_SECONDS = 6     # Maximum delay between random pose shifts
JIGGLE_FADER = 0.06             # Decay factor for pose-shifting jiggles
JIGGLE_MULTIPLIER = 0.6         # Frequency multiplier for jiggle oscillation
```

---

## 📈 Logging & Diagnostics

ToonToon captures pipeline logs inside `logs/toontoon_pipeline.log`. The logging level is configured in `main.py`:

```python
logger.setLevel(logging.DEBUG)  # Capture debug, info, warning, and error logs
```

### Logging Outputs

*   **`DEBUG` Level**: Captures matrix values, script tokens, and individual frame details (logged every 300 frames to prevent log bloat).
*   **`INFO` Level**: Captures milestone completions (e.g. parsed character manifests, completed Gentle alignment, active compositing).
*   **`WARNING` Level**: Captures non-fatal warnings (e.g. fallback candidate pose matches, missing manifest).
*   **`ERROR` Level**: Captures pipeline errors (e.g. Gentle API timeout, bad file paths).

---

## 🏁 Tuning for Performance

If rendering on low-spec hardware or compiling long animations, you can optimize execution speed by tuning configurations in `src/config.py`:

> [!TIP]
> 1. **Lower Output Resolution**: Set `CANVAS_WIDTH = 1280` and `CANVAS_HEIGHT = 720` in `src/config.py` (saves up to 50% rendering time).
> 2. **Lower Framerate**: Set `FRAME_RATE = 24` instead of `30` (reduces frame rendering loop iterations by 20%).
> 3. **Change FFmpeg Preset**: Modify `compositor.py` to use `-preset faster` or `-preset veryfast` (improves encoding speed, although the video file size may be larger).
