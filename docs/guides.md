# Character Onboarding & Asset Mapping Guide

This guide explains how to onboard custom characters, structure asset folders, define parameters in `character_manifest.json`, and map mouth anchors using the coordinates matrix.

---

## 📂 Character Directory Structure

Each character directory lives under `assets/characters/` and must adhere strictly to the layout below:

```
assets/characters/{character_name}/
├── character_manifest.json         # Complete metadata, mapping, and coords
├── mouthCoordinates.csv            # Bounding box coords (fallback)
├── poses/                          # 90 pose files (poses/emotion_name/pose*.png)
│   ├── explain/
│   │   ├── pose0001.png            # pose0001 (explain, pose0, open)
│   │   ├── pose0002.png            # pose0002 (explain, pose0, half-closed)
│   │   ├── pose0003.png            # pose0003 (explain, pose0, fully-closed)
│   │   └── ... (15 files)
│   ├── happy/                      # Poses 16-30
│   ├── sad/                        # Poses 31-45
│   ├── angry/                      # Poses 46-60
│   ├── confused/                   # Poses 61-75
│   └── rq/                         # Poses 76-90
└── mouths/                         # 22 mouth sprites (mouths/sentiment/mouth*.png)
    ├── happy/
    │   ├── mouth0001.png           # slot 0 (y / smile)
    │   ├── ...
    │   └── mouth0011.png           # slot 10 (u / tight rounded)
    └── sad/
        ├── mouth0012.png           # slot 0 (y / sad-narrow)
        └── ... (mouth0012 to mouth0022)
```

---

## 📝 The `character_manifest.json` Specification

The manifest file centralizes configuration overrides for individual characters, allowing custom canvas sizes, custom blinking structures, custom phonemes, and coordinates matrices.

```json
{
  "character_name": "cary",
  "meta": {
    "author": "Author Name",
    "description": "Short description of the character assets."
  },
  "dimensions": {
    "native_resolution": [640, 360],
    "target_resolution": [1920, 1080],
    "coordinate_scale_factor": 3.0
  },
  "emotions": {
    "explain":  { "id": 0, "is_positive": true },
    "happy":    { "id": 1, "is_positive": true },
    "sad":      { "id": 2, "is_positive": false },
    "angry":    { "id": 3, "is_positive": false },
    "confused": { "id": 4, "is_positive": false },
    "rq":       { "id": 5, "is_positive": true }
  },
  "phonemes": {
    "positive_offset": 1,
    "negative_offset": 12,
    "max_mouth_shapes": 11,
    "structural_dictionary": {
      "aa": "a", "ae": "a", "ah": "a", "sil": "m", "b": "m", "p": "m"
    }
  },
  "blinking": {
    "frame_modulus": 60,
    "states": {
      "open": { "id": 0, "trigger_frames": [] },
      "half": { "id": 1, "trigger_frames": [56, 59] },
      "closed": { "id": 2, "trigger_frames": [57, 58] }
    }
  },
  "mouth_coordinates_matrix": [
    [130.6, 167.1, 1.0, 1.0, 0.0],
    [166.7, 163.1, 1.0, 1.0, 0.0]
  ]
}
```

### Manifest Sections Explained

#### 1. `dimensions`
*   `native_resolution`: Bounding box of the original canvas (typically `[640, 360]`).
*   `target_resolution`: Resolution of the upscaled canvas (typically `[1920, 1080]`).
*   `coordinate_scale_factor`: Bounding scale factor ($\text{Target} / \text{Native}$).

#### 2. `emotions`
*   Lists all supported emotions.
*   `id`: Binds the emotion to a specific block index.
*   `is_positive`: Binds the emotion to the positive mouth directory (`mouths/happy/`) or the negative directory (`mouths/sad/`).

#### 3. `blinking`
*   `frame_modulus`: Timeline loop size (e.g. eyes blink every 60 frames).
*   `trigger_frames`: List of frames in the cycle where eyes are fully or half closed.

---

## 🎯 Bounding Box Coordinate Mapping

To paste a mouth sprite onto a body pose, the renderer must find the face anchor coordinates. Bounding coordinates are specified as a 5-element array in the `mouth_coordinates_matrix`:

$$\text{Row Vector} = [X, \; Y, \; S_x, \; S_y, \; R]$$

```
Anchor Point (X, Y)
       │
       ▼
 ┌───────────┐
 │   Mouth   │  (Width: W, Height: H)
 │  [Center] │  
 └───────────┘
```

Where:
*   **$X$**: Horizontal anchor offset in legacy pixels (0 to 640).
*   **$Y$**: Vertical anchor offset in legacy pixels (0 to 360).
*   **$S_x$**: Horizontal scale factor ($1.0$ = native width, $-1.0$ = horizontally flipped mouth).
*   **$S_y$**: Vertical scale factor.
*   **$R$**: Rotation angle in degrees (clockwise rotation).

> [!WARNING]
> Keep coordinate values within **legacy 640×360 space**. Do not write raw 1920×1080 values into the matrix, as the engine scales coordinates automatically using the `coordinate_scale_factor`!

---

## 🚀 How to Add a New Character (Step-by-Step)

### Step 1: Create the Directory Directory
Initialize folders inside `assets/characters/`:
```bash
mkdir -p assets/characters/new_char/poses
mkdir -p assets/characters/new_char/mouths
```

### Step 2: Render Body Sprites
Export **90 pose files** (Full HD, transparent background) following the index mapping:

$$\text{Pose Index} = (\text{Emotion ID} \times 5 + \text{Pose ID}) \times 3 + \text{Blink State} + 1$$

Group the pose files into emotion subfolders under `poses/`.

### Step 3: Render Mouth Sprites
Export **22 mouth files** matching the slots layout (slots 0–10 positive, slots 11–21 negative) and place them in the happy and sad directories under `mouths/`.

### Step 4: Record Coordinates
Measure the mouth anchor points in legacy space (640×360). List them in order (Emotion 0 Pose 0 $\rightarrow$ Emotion 5 Pose 4 = 30 lines total) and add them to the `mouth_coordinates_matrix` inside `character_manifest.json`.

---

## 🔍 Troubleshooting Onboarding Issues

### 1. "Mouth floating in the wrong place"
*   **Cause**: The coordinates were measured on the Full HD canvas rather than the legacy 640×360 canvas.
*   **Fix**: Divide your Full HD X and Y coordinates by $3.0$ before adding them to `character_manifest.json`.

### 2. "Eyes blinking at random intervals"
*   **Cause**: The blinking moduli do not match.
*   **Fix**: Update the `blinking` trigger arrays in your manifest to specify the exact frame indexes for open, half, and closed eyes.
