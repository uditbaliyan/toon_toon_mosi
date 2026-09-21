# Architecture & Deep Design Analysis

This document provides a comprehensive technical breakdown of the algorithmic pipelines, data flow decisions, and performance optimizations within the ToonToon engine.

---

## 📅 The Animation Scheduler (`src/scheduler.py`)

The `AnimationScheduler` translates raw phonetic timestamps and parsed script metadata into three parallel, synchronous time-series vectors (`phonemes[]`, `poses[]`, and `emotions[]`), all aligned to the output video's frame rate (default: 30 FPS).

```
Timeline:  0.0s    0.2s    0.4s    0.6s    0.8s    1.0s    1.2s    1.4s
Word:      [   Hello   ]           [   Brave   ]   [   Knight  ]
Phonemes:  [h][eh][l][ow]           [b][r][ey][v]   [n][ay][t]
Frames:    000102030405060708091011121314151617181920212223242526272829
```

### 1. Frame Onset & Anticipation Offset

To align mouth shapes slightly ahead of audio phonemes (which compensates for human visual latency and matches original hand-drawn animation techniques), the scheduler applies an **anticipation lead offset of 2 frames** to every single phonetic onset:

$$\text{Frame Index} = \max(0, \lfloor \text{Timestamp} \times \text{FPS} \rfloor - 2)$$

> [!IMPORTANT]
> This offset is applied globally to prevent lip-sync lag, ensuring mouth shapes open right before the corresponding audio reaches the speaker.

### 2. Vowel Arc Animation & Coarticulation Curves

ToonToon implements **Cary's Vowel Arc Algorithm**, which translates sustained open vowels into a natural bell curve of mouth shapes rather than hard, static shapes.

```
Vowel "aa" Arc (Duration: 6 frames)
Mouth Slot:
  5 |          /\
  4 |         /  \
  3 |        /    \
  2 |       /      \
  1 |      /        \
  0 |_____/__________\____
Frame:  1   2   3   4   5   6
```

#### The 'a' Arc (Open Vowels: aa, ae, ah, ao, eh, ih)
*   Computes an expansion path using context-based opening limits:
    *   `start_force` (True if the preceding consonant is narrow/lips-open like `t` or `y`).
    *   `end_force` (True if the succeeding consonant leaves the jaw slightly open).
*   Translates internal intensity levels to mouth shapes using identity mapping (slots 0, 2, 4, 5).
*   **The U-Adjacency Modifier:** If the preceding phoneme is `u` (rounded), the first frame's mouth index is incremented by `+1` (slot 0 $\rightarrow$ slot 1 = `y + u tinge`). If the succeeding phoneme is `u`, the last frame is incremented by `+1` (slot 2 $\rightarrow$ slot 3 = `mid-open + u tinge`). This produces natural coarticulation glides.

#### The 'u' Arc (Rounded Vowels: er, uw, uh, r, w)
*   Rounded vowels execute a distinct lip-puckering timeline.
*   For durations $> 2$ frames, the mouth starts in the O-ring shape (slot 9), holds the tight rounded sustain shape (slot 10), and returns to the O-ring shape (slot 9) on release:
    ```python
    slots = [9] + [10] * (duration - 2) + [9]
    ```

### 3. Timeline Sequence Optimization

*   **Punctuation-Based Pose Shifts:** Single line breaks (`\n`) or paragraph boundaries (`\n\n`) denote conversational pauses. The scheduler detects punctuation boundaries (`,`, `;`, `.`, `!`, `?`) and schedules a pose change, ensuring the character moves dynamically.
*   **Line-Break Closing:** When a character finishes speaking a paragraph (flagged by an annotated line break), the scheduler inserts an explicit closed mouth state (`slot 8 = m`) to prevent the character's mouth from remaining open during silence.

---

## 👄 The MouthBlender Post-Processor (`src/mouth_blender.py`)

The `MouthBlender` sits between the scheduler (which outputs flat, discrete integers) and the renderer. It converts the timeline into `BlendState` records containing two mouth sprites (`slot_a`, `slot_b`) and a scalar `weight` to perform real-time sub-sprite interpolation.

```
Discrete:    [ slot 8 (closed) ] ───► [    slot 4 (peak-open)     ]
Blended:     [slot 8] ─► [8->4, w=0.25] ─► [8->4, w=0.75] ─► [slot 4]
```

### 1. The Easing Curve Suite

Every mouth transition is spread over **4 frames** by default. Rather than a linear transition, the blend weight is passed through a specific mathematical curve chosen based on the transition category:

| Transition Category | Target Easing Curve | Formula | Visual Response |
| :--- | :--- | :--- | :--- |
| **Opening Jaw** (Resting $\rightarrow$ Vowel) | **Ease-Out** | $W(t) = 1.0 - (1.0 - t)^2$ | Rapidly drops open, then slowly settles. |
| **Closing Jaw** (Vowel $\rightarrow$ Resting) | **Ease-In** | $W(t) = t^2$ | Starts slowly, then snaps shut on contact. |
| **Glides** (Vowel $\rightarrow$ Vowel) | **Ease-InOut** | $W(t) = 3t^2 - 2t^3$ | Smooth S-curve transition. |
| **Plosives** (m, b, p) | **Snap Cut** | $W(t) = 0$ if $t < 0.5$ else $1.0$ | Hard cut halfway through the window. |

### 2. Vowel Anticipation

One frame prior to the onset of a wide-open vowel (slots 4, 5, 9, 10), the `MouthBlender` inserts a pre-blend weight of **0.15** toward the target shape:

$$\text{BlendWeight}_{\text{onset}-1} = 0.15$$

This mirrors human speech anatomy, where the lips begin to part and shape the mouth box slightly before vocalization begins.

### 3. Hold Micro-Variation (Anti-Freeze Oscillation)

Sustained holds of a single mouth shape (e.g. during long vowels) exceeding **7 frames** are given a subtle drift every **4 frames** to prevent a static, "frozen" look. The blender alternates the drift direction to create a gentle oscillation:

$$\text{Slot}_{\text{drift}} = \text{Slot}_{\text{base}} \pm 1, \quad \text{BlendWeight} = 0.12$$

---

## 🎨 The Frame Renderer (`src/renderer.py`)

The `FrameRenderer` composites in-memory layers using NumPy operations. By loading configurations dynamically from `character_manifest.json`, the renderer eliminates global bottlenecks.

```
┌──────────────────────────────────────┐
│        Canvas (1920 x 1080)          │
│  ┌──────────────────────────┐        │
│  │     Body Sprite Area     │        │
│  │   ┌──────────────────┐   │        │
│  │   │   Blended Mouth  │   │        │
│  │   │  [slot_a] [slot_b]───┼────────┼── Alpha Composited
│  │   └──────────────────┘   │        │
│  └──────────────────────────┘        │
└──────────────────────────────────────┘
```

### 1. Dynamic Resolution Fallback Chain

When looking for pose images, the renderer searches candidate folders following a fallback hierarchy to prevent rendering failure:

```
Requested: (Emotion, Pose, Blink) 
   │
   ├──► Miss? Try fallback: (explain, Pose, Blink)
   │       │
   │       └──► Miss? Try fallback: (Emotion, Pose, open)
   │               │
   │               └──► Miss? Try fallback: (explain, 0, open) -> [Fail-Safe Base]
```

### 2. Sub-Sprite Alpha Compositing

If the active `BlendState` is not pure (weight $> 0.0$), the renderer loads both `slot_a` and `slot_b` mouth sprites, matches their dimensions, and alpha-blends their pixel channels in memory:

```python
img_blended = (1.0 - weight) * img_a.astype(np.float32) + weight * img_b.astype(np.float32)
```

### 3. Horizontal Pose Flipping

When a script transition flags a paragraph break (character flip), the composite engine flips the assembled character body horizontally before copying it to the background canvas. The coordinates are calculated relative to the canvas bounding boxes:

```python
body = cv2.flip(body, 1)  # Horizontal axis flip
```
