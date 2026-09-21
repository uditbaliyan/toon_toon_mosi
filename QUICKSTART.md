# ToonToon Quick Start Guide

Get ToonToon running in 5 minutes.

## Prerequisites

- Python 3.10+
- FFmpeg installed
- Docker (for Gentle API)
- ~2GB free RAM

## 1. Install & Setup (2 minutes)

```bash
# Install Python packages
pip install -r requirements.txt

# Start Gentle API container
docker run -d -p 8765:8765 lowerquality/gentle

# Verify Gentle is running
curl http://localhost:8765/status
# Expected: {"ok": true}
```

## 2. Prepare Your Assets (varies)

Create directory structure:

```bash
mkdir -p assets/characters/cary/poses
mkdir -p assets/characters/cary/mouths
```

Then place:
- `poses/pose0001.png` through `pose0090.png` (90 files)
- `mouths/mouth0001.png` through `mouth0022.png` (22 files)
- `mouthCoordinates.csv` (30 lines of coordinates)
- `character_manifest.json`

See `MOUTH_COORDINATES_EXAMPLE.csv` for coordinate format.

## 3. Create Script & Audio

### Write Script (`story.txt`)

```
<explain> Hello there!

<happy> I'm so glad to see you.

<sad> But I have some bad news.

<confused> Do you understand?

<angry> Why aren't you listening?!

<rq> Will everything be okay?
```

### Record Audio (`voice.wav`)

Record voiceover matching the script text (without emotion tags).

## 4. Run Pipeline

```bash
python main.py \
  --script story.txt \
  --audio voice.wav \
  --character cary \
  --output animation.mp4
```

Expected output:
```
[ToonToon] Validating inputs...
[ToonToon] Parsing annotated script...
[ToonToon] Aligning audio with Gentle API...
[ToonToon] Scheduling animation frames...
[ToonToon] Initializing renderer...
[ToonToon] Starting FFmpeg pipeline...
[ToonToon] Rendering and streaming frames...
[ToonToon] Rendered frame 30 / 180 (16.7%)
[ToonToon] Rendered frame 60 / 180 (33.3%)
...
[ToonToon] ✓ Success! Video saved: animation.mp4 (45.2 MB)
```

## 5. View Your Video

```bash
open animation.mp4          # macOS
xdg-open animation.mp4      # Linux
start animation.mp4         # Windows
```

## Common Options

### Add Background Music

```bash
python main.py \
  --script story.txt \
  --audio voice.wav \
  --character cary \
  --bg_music background.wav \
  --music_volume 0.08 \
  --output animation.mp4
```

### Use Different Character

```bash
python main.py \
  --script story.txt \
  --audio voice.wav \
  --character newchar \
  --output animation.mp4
```

### Adjust Quality (Faster)

Edit `src/config.py`:

```python
FRAME_RATE = 24  # Instead of 30 (saves 20% time)
CANVAS_WIDTH = 1280  # Instead of 1920 (saves 50% time)
CANVAS_HEIGHT = 720  # Instead of 1080
```

## Troubleshooting

### "Failed to connect to Gentle API"

```bash
# Start Gentle
docker run -d -p 8765:8765 lowerquality/gentle

# Check it's running
docker ps | grep gentle
```

### "FFmpeg not found"

```bash
# Install FFmpeg
brew install ffmpeg        # macOS
sudo apt-get install ffmpeg  # Ubuntu
choco install ffmpeg       # Windows
```

### "Character assets not found"

```bash
# Check directory structure
ls -la assets/characters/cary/poses/    # Should have 90 PNG files
ls -la assets/characters/cary/mouths/   # Should have 22 PNG files
cat assets/characters/cary/mouthCoordinates.csv  # Should have 30 lines
```

### "Mouth position looks wrong"

Check `mouthCoordinates.csv` values — they must be in **legacy 640×360 space**.  
The renderer automatically upscales by 3× to 1920×1080.

Recalibrate using `MOUTH_COORDINATES_EXAMPLE.csv` as reference.

## Full Documentation

- 📖 [README.md](README.md) — Project overview
- 🏗️ [docs/architecture.md](docs/architecture.md) — System design
- 🎨 [docs/guides.md](docs/guides.md) — Add new characters
- ⚙️ [docs/config.md](docs/config.md) — Configuration options
- 📚 [docs/reference.md](docs/reference.md) — API documentation

## Next Steps

1. **Explore Examples** — Check `docs/guides.md` for character onboarding
2. **Build Docs Locally**
   ```bash
   pip install mkdocs mkdocs-material mkdocstrings[python]
   mkdocs serve
   # Visit http://localhost:8000
   ```
3. **Customize** — Modify `src/config.py` for custom emotions, frame rates, etc.
4. **Contribute** — Fork the repo and submit pull requests!

---

**That's it! You now have a working animation pipeline.** 🎬
