"""
FrameRenderer v7 — blend-state aware compositor

Adds BlendState support on top of the v6 renderer.
The only changes from v6 are:

  1. render_frame() now accepts an optional `blend_state: BlendState` kwarg.
     If supplied it supersedes the plain `mouth_id` integer and composites
     two mouth sprites using mouth_blender.blend_mouth_images().

  2. _load_mouth_pair() loads and returns two BGRA arrays.

  3. _composite_mouth_blend() pastes the blended mouth onto the body.

Everything else (pose loading, fallback chain, body scaling,
canvas compositing, coordinate loading) is identical to v6.
"""

import cv2
import numpy as np
from pathlib import Path
from typing import Dict, Optional, Tuple

from .config import (
    CANVAS_WIDTH, CANVAS_HEIGHT, COORDINATE_UPSCALE_FACTOR,
    EMOTION_POSITIVITY, EMOTION_FOLDER, MOUTH_FOLDER,
    EMOTION_POSE_OFFSET,
    POSE_COUNT, BLINK_STATES, EMOTION_COUNT,
    POSITIVE_MOUTH_BASE, NEGATIVE_MOUTH_BASE, MOUTHS_PER_SENTIMENT,
)
from .mouth_blender import BlendState, blend_mouth_images


class FrameRenderer:
    """
    Renders animation frames by compositing cached asset layers.

    Mouth slot → file mapping (v6/v7, matching original asset order):
        slot  0 → mouth0001  y / narrow-smile
        slot  1 → mouth0002  y + u-tinge
        slot  2 → mouth0003  mid-open ramp
        slot  3 → mouth0004  mid-open + u-tinge
        slot  4 → mouth0005  peak-open
        slot  5 → mouth0006  peak-open alt
        slot  6 → mouth0007  t / teeth-tongue
        slot  7 → mouth0008  f / lip-teeth
        slot  8 → mouth0009  m / closed
        slot  9 → mouth0010  o / wide O-ring
        slot 10 → mouth0011  u / tight-round sustain
    """

    def __init__(self, character_assets_path: str):
        self.assets_path = Path(character_assets_path)
        self.poses_path  = self.assets_path / "poses"
        self.mouths_path = self.assets_path / "mouths"
        self.mouth_coords_file = self.assets_path / "mouthCoordinates.csv"
        self.manifest_file = self.assets_path / "character_manifest.json"

        self.pose_cache:  Dict[str, np.ndarray] = {}
        self.mouth_cache: Dict[str, np.ndarray] = {}

        # Default configuration fallback
        self.coordinate_scale_factor = COORDINATE_UPSCALE_FACTOR
        self.emotion_positivity = EMOTION_POSITIVITY
        self.emotion_folder = EMOTION_FOLDER

        # Attempt to load manifest data dynamically
        self.manifest_data = {}
        if self.manifest_file.exists():
            try:
                import json
                with open(self.manifest_file, "r") as f:
                    self.manifest_data = json.load(f)
            except Exception as e:
                print(f"Warning: Failed to load character manifest: {e}")

        # Override configurations from manifest if available
        if self.manifest_data:
            if "dimensions" in self.manifest_data:
                self.coordinate_scale_factor = self.manifest_data["dimensions"].get("coordinate_scale_factor", COORDINATE_UPSCALE_FACTOR)
            if "emotions" in self.manifest_data:
                emotions_dict = self.manifest_data["emotions"]
                new_folder = {}
                new_positivity = []
                for emo_name, emo_info in emotions_dict.items():
                    emo_id = emo_info.get("id")
                    if emo_id is not None:
                        new_folder[emo_id] = emo_name
                        while len(new_positivity) <= emo_id:
                            new_positivity.append(1)
                        new_positivity[emo_id] = 1 if emo_info.get("is_positive", True) else 0
                self.emotion_folder = new_folder
                self.emotion_positivity = new_positivity

        # Load coordinates (from manifest matrix or fallback csv)
        if self.manifest_data and "mouth_coordinates_matrix" in self.manifest_data:
            self.mouth_coordinates = np.array(self.manifest_data["mouth_coordinates_matrix"])
        else:
            self.mouth_coordinates = self._load_mouth_coordinates()

        self._available_pose_paths = self._scan_available_poses()

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def _pose_file_path(self, emotion_id: int, pose_id: int, blink_state: int) -> Path:
        emotion_name = self.emotion_folder[emotion_id]
        offset       = EMOTION_POSE_OFFSET[emotion_id]
        file_index   = offset + pose_id * BLINK_STATES + blink_state
        return self.poses_path / emotion_name / f"pose{file_index:04d}.png"

    def _mouth_file_path(self, mouth_shape_code: int, is_positive: bool) -> Path:
        if is_positive:
            subfolder  = MOUTH_FOLDER[1]
            file_index = POSITIVE_MOUTH_BASE + mouth_shape_code
        else:
            subfolder  = MOUTH_FOLDER[0]
            file_index = NEGATIVE_MOUTH_BASE + mouth_shape_code
        return self.mouths_path / subfolder / f"mouth{file_index:04d}.png"

    # ------------------------------------------------------------------
    # Asset scanning
    # ------------------------------------------------------------------

    def _scan_available_poses(self) -> set:
        available = set()
        if not self.poses_path.exists():
            return available
        for f in self.poses_path.rglob("pose*.png"):
            available.add(str(f.resolve()))
        return available

    # ------------------------------------------------------------------
    # Pose resolution with fallback
    # ------------------------------------------------------------------

    def _resolve_pose_path(
        self, emotion_id: int, pose_id: int, blink_state: int
    ) -> Optional[Path]:
        candidates = [
            (emotion_id, pose_id, blink_state),
            (0,          pose_id, blink_state),
            (emotion_id, pose_id, 0),
            (0,          0,       0),
        ]
        for eid, pid, blink in candidates:
            path = self._pose_file_path(eid, pid, blink)
            if str(path.resolve()) in self._available_pose_paths:
                return path
        return None

    # ------------------------------------------------------------------
    # Public render entrypoint  (v7: accepts BlendState)
    # ------------------------------------------------------------------

    def render_frame(
        self,
        background:   Optional[np.ndarray],
        emotion_id:   int,
        pose_id:      int,
        mouth_id:     int,            # fallback plain slot (used when blend_state is None)
        blink_state:  int,
        is_flipped:   bool,
        blend_state:  Optional[BlendState] = None,   # NEW in v7
    ) -> np.ndarray:
        """
        Render a single animation frame.

        If blend_state is provided it is used for the mouth composite.
        Otherwise mouth_id is used as a plain (no-blend) slot, exactly
        as in v6.

        Args:
            background:   1280×720×3 BGR canvas.  None → green screen.
            emotion_id:   Emotion index (0–5).
            pose_id:      Pose within emotion (0–4).
            mouth_id:     Plain slot number (0–10); only used when blend_state=None.
            blink_state:  0=open, 1=half, 2=closed.
            is_flipped:   Flip character horizontally.
            blend_state:  BlendState from MouthBlender (supersedes mouth_id).

        Returns:
            BGR24 numpy array (CANVAS_HEIGHT × CANVAS_WIDTH × 3).
        """
        if background is None:
            canvas = np.zeros((CANVAS_HEIGHT, CANVAS_WIDTH, 3), dtype=np.uint8)
            canvas[:, :] = [0, 255, 0]
        else:
            canvas = background.copy()

        is_positive = (
            bool(self.emotion_positivity[emotion_id])
            if emotion_id < len(self.emotion_positivity)
            else True
        )

        # ── Load pose ──────────────────────────────────────────────────────
        pose_path = self._resolve_pose_path(emotion_id, pose_id, blink_state)
        body = self._load_image(pose_path, self.pose_cache)
        if body is None:
            return canvas
        body = body.copy()

        # ── Load & blend mouth ─────────────────────────────────────────────
        if blend_state is not None:
            mouth = self._load_blended_mouth(blend_state, is_positive)
        else:
            mouth_path = self._mouth_file_path(mouth_id, is_positive)
            mouth = self._load_image(mouth_path, self.mouth_cache)

        if mouth is None:
            body = self._scale_body(body)
            if is_flipped:
                body = cv2.flip(body, 1)
            return self._composite_body_on_canvas(canvas, body)

        # ── Compose ────────────────────────────────────────────────────────
        mouth = self._transform_mouth(mouth, emotion_id, pose_id)
        body  = self._paste_mouth_on_body(body, mouth, emotion_id, pose_id)
        body  = self._scale_body(body)

        if is_flipped:
            body = cv2.flip(body, 1)

        return self._composite_body_on_canvas(canvas, body)

    # ------------------------------------------------------------------
    # Mouth loading — plain + blended variants
    # ------------------------------------------------------------------

    def _load_image(
        self, path: Optional[Path], cache: Dict[str, np.ndarray]
    ) -> Optional[np.ndarray]:
        if path is None:
            return None
        key = str(path)
        if key in cache:
            return cache[key]
        if not path.exists():
            return None
        image = cv2.imread(key, cv2.IMREAD_UNCHANGED)
        if image is not None:
            cache[key] = image
        return image

    def _load_blended_mouth(
        self, state: BlendState, is_positive: bool
    ) -> Optional[np.ndarray]:
        """
        Load slot_a (and optionally slot_b) and alpha-composite them.

        When state.is_pure (weight ≈ 0 or slots identical), only slot_a
        is loaded — no blending cost.
        """
        path_a = self._mouth_file_path(state.slot_a, is_positive)
        img_a  = self._load_image(path_a, self.mouth_cache)
        if img_a is None:
            return None

        if state.is_pure:
            return img_a

        path_b = self._mouth_file_path(state.slot_b, is_positive)
        img_b  = self._load_image(path_b, self.mouth_cache)
        if img_b is None:
            return img_a   # fallback: use slot_a only

        # Ensure both images are BGRA for proper alpha blending
        if img_a.ndim == 3 and img_a.shape[2] == 3:
            img_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2BGRA)
        if img_b.ndim == 3 and img_b.shape[2] == 3:
            img_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2BGRA)

        return blend_mouth_images(img_a, img_b, state.weight)

    # ------------------------------------------------------------------
    # Mouth transform & compositing  (unchanged from v6)
    # ------------------------------------------------------------------

    def _transform_mouth(
        self, mouth: np.ndarray, emotion_id: int, pose_id: int
    ) -> np.ndarray:
        pose_index = emotion_id * POSE_COUNT + pose_id
        if pose_index >= len(self.mouth_coordinates):
            pose_index = pose_id % POSE_COUNT
        if pose_index >= len(self.mouth_coordinates):
            return mouth

        coords   = self.mouth_coordinates[pose_index]
        scale_x  = coords[2]
        scale_y  = coords[3]
        rotation = coords[4]

        if scale_x < 0:
            mouth   = cv2.flip(mouth, 1)
            scale_x = abs(scale_x)

        if scale_y != 1.0 or scale_x != 1.0:
            h, w   = mouth.shape[:2]
            new_h  = int(h * scale_y)
            new_w  = int(w * scale_x)
            if new_h > 0 and new_w > 0:
                mouth = cv2.resize(mouth, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        if rotation != 0:
            h, w            = mouth.shape[:2]
            center          = (w // 2, h // 2)
            rotation_matrix = cv2.getRotationMatrix2D(center, -rotation, 1.0)
            mouth           = cv2.warpAffine(
                mouth, rotation_matrix, (w, h), borderMode=cv2.BORDER_REPLICATE
            )

        return mouth

    def _paste_mouth_on_body(
        self, body: np.ndarray, mouth: np.ndarray, emotion_id: int, pose_id: int
    ) -> np.ndarray:
        pose_index = emotion_id * POSE_COUNT + pose_id
        if pose_index >= len(self.mouth_coordinates):
            pose_index = pose_id % POSE_COUNT
        if pose_index >= len(self.mouth_coordinates):
            return body

        coords   = self.mouth_coordinates[pose_index]
        anchor_x = int(coords[0] * self.coordinate_scale_factor)
        anchor_y = int(coords[1] * self.coordinate_scale_factor)

        m_h, m_w = mouth.shape[:2] if mouth.ndim >= 2 else (0, 0)
        if m_h == 0 or m_w == 0:
            return body

        paste_x = max(0, anchor_x - m_w // 2)
        paste_y = max(0, anchor_y - m_h // 2)

        body_h, body_w = body.shape[:2]
        if paste_x + m_w > body_w or paste_y + m_h > body_h:
            return body

        if mouth.ndim == 3 and mouth.shape[2] == 4:
            alpha       = (mouth[:, :, 3] / 255.0)[..., np.newaxis]
            body_region = body[paste_y:paste_y + m_h, paste_x:paste_x + m_w]
            body[paste_y:paste_y + m_h, paste_x:paste_x + m_w, :3] = (
                alpha * mouth[:, :, :3] + (1.0 - alpha) * body_region[:, :, :3]
            ).astype(np.uint8)
            if body.shape[2] == 4:
                body[paste_y:paste_y + m_h, paste_x:paste_x + m_w, 3] = np.maximum(
                    mouth[:, :, 3], body_region[:, :, 3]
                )
        else:
            body[paste_y:paste_y + m_h, paste_x:paste_x + m_w, :3] = mouth[:, :, :3]

        return body

    # ------------------------------------------------------------------
    # Body helpers  (unchanged from v6)
    # ------------------------------------------------------------------

    def _scale_body(self, body: np.ndarray, jiggle_factor: float = 1.0) -> np.ndarray:
        if jiggle_factor == 1.0:
            return body
        h, w   = body.shape[:2]
        new_h  = int(h * jiggle_factor)
        new_w  = int(w / jiggle_factor)
        return cv2.resize(body, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    def _composite_body_on_canvas(
        self, canvas: np.ndarray, body: np.ndarray
    ) -> np.ndarray:
        canvas_h, canvas_w = canvas.shape[:2]
        body_h,   body_w   = body.shape[:2]

        if body_h > canvas_h or body_w > canvas_w:
            scale = min(canvas_h / body_h, canvas_w / body_w)
            body  = cv2.resize(
                body,
                (int(body_w * scale), int(body_h * scale)),
                interpolation=cv2.INTER_LINEAR,
            )
            body_h, body_w = body.shape[:2]

        x = int(canvas_w * 0.75 - body_w // 2)
        y = canvas_h - body_h
        x = max(0, min(x, canvas_w - body_w))
        y = max(0, min(y, canvas_h - body_h))

        canvas_region = canvas[y:y + body_h, x:x + body_w]

        if body.ndim == 3 and body.shape[2] == 4:
            alpha    = (body[:, :, 3] / 255.0)[..., np.newaxis]
            body_rgb = body[:, :, :3]
            canvas[y:y + body_h, x:x + body_w] = (
                alpha * body_rgb + (1.0 - alpha) * canvas_region
            ).astype(np.uint8)
        else:
            canvas[y:y + body_h, x:x + body_w] = body[:, :, :3]

        return canvas

    # ------------------------------------------------------------------
    # Mouth coordinate loader  (unchanged)
    # ------------------------------------------------------------------

    def _load_mouth_coordinates(self) -> np.ndarray:
        coords = np.zeros((POSE_COUNT * EMOTION_COUNT, 5))
        if not self.mouth_coords_file.exists():
            return coords
        try:
            with open(self.mouth_coords_file, "r") as f:
                for i, line in enumerate(f):
                    if i >= POSE_COUNT * EMOTION_COUNT:
                        break
                    values = [float(x.strip()) for x in line.strip().split(",")]
                    if len(values) >= 5:
                        coords[i] = values[:5]
        except Exception as e:
            print(f"Warning: Failed to load mouth coordinates: {e}")
        return coords
