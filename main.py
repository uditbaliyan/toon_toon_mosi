#!/usr/bin/env python3
"""
ToonToon: Unified Animation Pipeline Orchestrator
"""

import argparse
import signal
import sys
import time
from pathlib import Path
import logging
import json

from src.aligner import GentleAligner
from src.compositor import FFmpegCompositor
from src.config import (
    BACKGROUND_MUSIC_VOLUME,
    FRAME_RATE,
)
from src.parser import ScriptParser
from src.renderer import FrameRenderer
from src.scheduler import AnimationScheduler
from src.mouth_blender import MouthBlender
from src.subtitle_generator import generate_ass


# ---------------------------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------------------------
logger = logging.getLogger("ToonToon")
logger.setLevel(logging.DEBUG)  # Capture everything down to DEBUG

# Prevent duplicate handlers if script is imported or re-run
if not logger.handlers:
    # Create file handler for detailed pipeline traces
    file_handler = logging.FileHandler('logs/toontoon_pipeline.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # Create formatter with timestamps and log levels
    formatter = logging.Formatter('%(asctime)s - [%(levelname)s] - %(name)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)


# ---------------------------------------------------------------------------
# Globals used by the signal handler (set after compositor is created)
# ---------------------------------------------------------------------------
_compositor: FFmpegCompositor | None = None


def _handle_interrupt(sig, frame):
    msg = f"System Interruption Signal ({sig}) received! Shutting down FFmpeg..."
    print(f"\n\n[ToonToon] {msg}", flush=True)
    logger.warning(msg)
    
    if _compositor is not None:
        logger.info("Terminating active FFmpeg compositor process...")
        _compositor.terminate()
        
    sys.exit(1)


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------

def main():
    global _compositor

    parser = argparse.ArgumentParser(
        description="ToonToon: High-Performance Animation Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--script",       required=True,  help="Annotated script (.txt)")
    parser.add_argument("--audio",        required=True,  help="Voice audio track (.wav)")
    parser.add_argument("--character",    default="cary", help="Character assets folder name")
    parser.add_argument("--output",       required=True,  help="Output video (.mp4)")
    parser.add_argument("--bg_video",     default=None,   help="Background video (optional)")
    parser.add_argument("--bg_music",     default=None,   help="Background music (optional)")
    parser.add_argument("--music_volume", default=BACKGROUND_MUSIC_VOLUME, type=float)
    parser.add_argument("--use_blender",  default="true", choices=["true", "false"],
                        help="Use MouthBlender coarticulation")
    parser.add_argument("--subtitles",    default="true", choices=["true", "false"],
                        help="Burn JarToon-style subtitles into the output video")
    args = parser.parse_args()
    
    # Parse string flags to booleans
    args.use_blender = args.use_blender.lower() == "true"
    args.subtitles   = args.subtitles.lower()   == "true"

    logger.info("================ Pipeline Initialization ================")
    logger.info(f"Arguments parsed: {vars(args)}")

    # Register Ctrl+C handler early
    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)

    script_path = Path(args.script)
    audio_path  = Path(args.audio)
    output_path = Path(args.output)

    # ── 1. VALIDATE ──────────────────────────────────────────────────────────
    print("[ToonToon] Validating inputs...")
    logger.info("Validating input file paths...")
    
    for p, label in [(script_path, "Script"), (audio_path, "Audio")]:
        if not p.exists():
            err_msg = f"{label} file not found at expected path: {p.resolve()}"
            print(f"[ERROR] {err_msg}")
            logger.error(err_msg)
            sys.exit(1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Input validation successful. Target output directory: {output_path.parent.resolve()}")

    # ── 2. PARSE SCRIPT ───────────────────────────────────────────────────────
    print("[ToonToon] Parsing annotated script...")
    logger.info(f"Reading target script: {script_path.name}")
    try:
        script_parser = ScriptParser()
        script_text   = script_path.read_text(encoding="utf-8")
        
        logger.debug("Executing ScriptParser rules on raw input string...")
        metadata      = script_parser.parse(script_text)
        clean_script  = metadata.clean_text
        
        print(f"[ToonToon] Clean transcript: {len(clean_script)} chars")
        logger.info(f"Script parsing successful. Extracted clean transcript length: {len(clean_script)} characters.")

        # --- LOGGING DUMP (Single-Line JSON for structural inspection) ---
        log_data = {
            "clean_text": metadata.clean_text,
            "emotion_events": [{"emotion": e.emotion_code, "pos": e.position} for e in metadata.emotion_events],
            "line_breaks": metadata.line_breaks,
            "paragraph_breaks": metadata.paragraph_breaks
        }
        logger.debug(f"Parsed Script Metadata Metrics: {json.dumps(log_data,indent=4)}")
        logger.info(
            f"Emotion markers found: "
            f"{[(e.emotion_code, e.position) for e in metadata.emotion_events]}"
        )
        # ------------------------------------------------------------------

    except Exception as e:
        print(f"[ERROR] Script parse failed: {e}")
        logger.exception("Fatal failure during script processing phase.")
        sys.exit(1)

    # ── 3. ALIGN AUDIO ────────────────────────────────────────────────────────
    print("[ToonToon] Aligning audio with Gentle API...")
    logger.info("Contacting Gentle forced-aligner endpoint...")
    try:
        aligner       = GentleAligner()
        aligned_words = aligner.align(str(audio_path), transcript=clean_script)
        
        if not aligned_words:
            err_msg = "Gentle alignment engine execution succeeded but returned 0 aligned tokens."
            print(f"[ERROR] {err_msg}")
            logger.error(err_msg)
            sys.exit(1)
        # Logs each item on a new line with an indented bullet
        formatted_list = '\n - '.join(map(str, aligned_words))
        logger.debug(f"Gentle aligned format: {formatted_list}")
        total_duration = max(w.end_time for w in aligned_words)
        print(f"[ToonToon] Aligned {len(aligned_words)} words (~{total_duration:.1f}s)")
        logger.info(f"Alignment completed: {len(aligned_words)} tokens mapped. Estimated video duration: {total_duration:.2f} seconds.")
        
    except ConnectionError as e:
        print(f"[ERROR] {e}")
        logger.exception("Network connection failure trying to communicate with local/remote Gentle service.")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Alignment failed: {e}")
        logger.exception("Unexpected error occurred while running phonetic timeline synchronization.")
        sys.exit(1)

    # ── 3.5. GENERATE SUBTITLES ───────────────────────────────────────────────
    # Done right after alignment — we have exact word timings and don't need
    # to wait for frame scheduling. Non-fatal: a failure skips subtitles but
    # lets the render continue normally.
    subtitles_path = None
    if args.subtitles:
        print("[ToonToon] Generating subtitles...")
        logger.info("Building ASS subtitle file from Gentle word timings...")
        try:
            # Place the .ass file alongside the output video
            subtitles_path = output_path.with_suffix(".ass")
            generate_ass(aligned_words, subtitles_path)
            print(f"[ToonToon] Subtitles written → {subtitles_path.name}")
            logger.info(f"Subtitle file ready: {subtitles_path.resolve()}")
        except Exception as e:
            print(f"[WARN] Subtitle generation failed (non-fatal): {e}")
            logger.warning(f"Subtitle generation skipped due to error: {e}", exc_info=True)
            subtitles_path = None
    else:
        print("[ToonToon] Subtitles disabled (--subtitles false)")
        logger.info("Subtitle generation skipped by user flag.")

    # ── 4. SCHEDULE FRAMES ────────────────────────────────────────────────────
    print("[ToonToon] Scheduling animation frames...")
    logger.info("Evaluating frame scheduler mapping targets across track timelines...")
    try:
        scheduler                 = AnimationScheduler()
        # Add metadata as an explicit keyword argument here:
        phonemes, poses, emotions = scheduler.schedule_frames(
            aligned_words, total_duration, clean_script, parser_metadata=metadata
        )

        logger.info(
            f"Passing metadata into scheduler. "
            f"Emotion events={len(metadata.emotion_events)} "
            f"Line breaks={len(metadata.line_breaks)} "
            f"Paragraph breaks={len(metadata.paragraph_breaks)}"
        )
        import numpy as np

        unique_emotions = np.unique(emotions)

        logger.info(
            f"Emotion IDs present in final schedule: "
            f"{unique_emotions.tolist()}"
        )
        total_frames = int(total_duration * FRAME_RATE)
        print(f"[ToonToon] Scheduled {total_frames} frames")
        logger.info(f"Scheduling matrices built. Frame vectors lengths - Phonemes: {len(phonemes)}, Poses: {len(poses)}, Emotions: {len(emotions)} at target FPS: {FRAME_RATE}")

        # Execute MouthBlender coarticulation processing if active
        blend_states = None
        if args.use_blender:
            print("[ToonToon] Activating MouthBlender coarticulation post-processor...")
            logger.info("MouthBlender processor activated. Running phonetic lip sync transition optimization...")
            blender = MouthBlender()
            blend_states = blender.process(phonemes)

    except Exception as e:
        print(f"[ERROR] Scheduling failed: {e}")
        logger.exception("Critical error state reached mapping animation states to chronological frames.")
        sys.exit(1)

    # ── 5. INIT RENDERER ──────────────────────────────────────────────────────
    print("[ToonToon] Initializing renderer...")
    try:
        character_path = Path("assets") / "characters" / args.character
        logger.info(f"Locating visual sprite directory at structural path: {character_path.resolve()}")
        
        if not character_path.exists():
            err_msg = f"Character assets layer directory cannot be found: {character_path.resolve()}"
            print(f"[ERROR] {err_msg}")
            logger.error(err_msg)
            sys.exit(1)
            
        renderer = FrameRenderer(str(character_path))
        print(f"[ToonToon] Loaded character: {args.character}")
        logger.info(f"FrameRenderer initialized successfully for identity template profile: '{args.character}'")
        
    except Exception as e:
        print(f"[ERROR] Renderer init failed: {e}")
        logger.exception("Error mounting character template assets context inside internal canvas memory.")
        sys.exit(1)

    # ── 6. INIT COMPOSITOR ────────────────────────────────────────────────────
    print("[ToonToon] Starting FFmpeg pipeline...")
    logger.info("Binding output descriptors to FFmpeg subprocess pipe channels...")
    try:
        _compositor = FFmpegCompositor(
            str(output_path),
            str(audio_path),
            args.bg_music,
            args.music_volume,
            subtitles_path=str(subtitles_path) if subtitles_path else None,
        )
        _compositor.start()

        sub_status = f"with subtitles ({subtitles_path.name})" if subtitles_path else "without subtitles"
        logger.info(f"FFmpeg subprocess engine spawned {sub_status}; streaming channels active.")
        
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        logger.exception("Subprocess execution system failure starting external composite compiler pipeline.")
        sys.exit(1)

    # ── 7. RENDER + STREAM ────────────────────────────────────────────────────
    print("[ToonToon] Rendering and streaming frames...")
    logger.info(f"Looping frame generation pool for target runtime limit: {total_frames} loops.")

    background = None   # TODO: background video support
    start_time   = time.time()
    frame_times  = []   # rolling window for FPS smoothing

    try:
        for frame_idx in range(total_frames):
            emotion_id = int(emotions[frame_idx]) if frame_idx < len(emotions) else 0
            pose_id    = int(poses[frame_idx])    if frame_idx < len(poses)    else 0
            mouth_id   = int(phonemes[frame_idx]) if frame_idx < len(phonemes) else 4

            # Dynamic Blinking resolution from character manifest if present
            blink_state = 0   # default open
            if renderer.manifest_data and "blinking" in renderer.manifest_data:
                blinking_cfg = renderer.manifest_data["blinking"]
                frame_modulus = blinking_cfg.get("frame_modulus", 60)
                blink_cycle = frame_idx % frame_modulus
                states_cfg = blinking_cfg.get("states", {})
                
                closed_cfg = states_cfg.get("closed", {})
                half_cfg = states_cfg.get("half", {})
                
                if blink_cycle in closed_cfg.get("trigger_frames", [57, 58]):
                    blink_state = closed_cfg.get("id", 2)
                elif blink_cycle in half_cfg.get("trigger_frames", [56, 59]):
                    blink_state = half_cfg.get("id", 1)
                else:
                    blink_state = states_cfg.get("open", {}).get("id", 0)
            else:
                blink_cycle = frame_idx % 60
                if blink_cycle in (57, 58):
                    blink_state = 2   # fully closed
                elif blink_cycle in (56, 59):
                    blink_state = 1   # half closed
                else:
                    blink_state = 0   # open
            
            # Periodically log matrix indexing details to file every 300 frames to avoid file bloating
            if frame_idx % 300 == 0:
                logger.debug(f"Render progress check: Frame {frame_idx}/{total_frames} | State vector markers -> Emotion: {emotion_id}, Pose: {pose_id}, Mouth/Phoneme: {mouth_id}")

            # Grab current frame's BlendState if available
            blend_state = blend_states[frame_idx] if blend_states is not None else None

            frame = renderer.render_frame(
                background, emotion_id, pose_id, mouth_id, blink_state,
                is_flipped=False, blend_state=blend_state,
            )
            _compositor.write_frame(frame)

            # ── progress display ─────────────────────────────────────────
            now = time.time()
            frame_times.append(now)
            if len(frame_times) > 30:
                frame_times.pop(0)

            if len(frame_times) >= 2:
                fps = (len(frame_times) - 1) / (frame_times[-1] - frame_times[0])
            else:
                fps = 0.0

            elapsed         = now - start_time
            remaining       = (total_frames - frame_idx - 1) / fps if fps > 0 else 0
            elapsed_str     = f"{int(elapsed)//60:02d}:{int(elapsed)%60:02d}"
            eta_str         = f"{int(remaining)//60:02d}:{int(remaining)%60:02d}"
            progress_pct    = (frame_idx + 1) / total_frames * 100

            bar_filled = int(progress_pct / 5)
            bar = "█" * bar_filled + "░" * (20 - bar_filled)

            sys.stdout.write(
                f"\r[{bar}] {progress_pct:5.1f}% | "
                f"Frame {frame_idx+1}/{total_frames} | "
                f"{fps:5.1f} fps | "
                f"⏱ {elapsed_str} | ETA {eta_str}  "
            )
            sys.stdout.flush()

        render_duration = time.time() - start_time
        print(f"\n[ToonToon] Render complete in {render_duration:.1f}s")
        logger.info(f"Canvas multi-frame sequence stream generation process safely terminated. Render phase duration: {render_duration:.2f} seconds.")

    except KeyboardInterrupt:
        print("\n[ToonToon] Interrupted during render.")
        logger.warning("Pipeline interrupted by User Keyboard command sequence during raw assembly render execution loop.")
        _compositor.terminate()
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Render failed: {e}")
        logger.exception("Critical unexpected canvas rendering loop exception encountered.")
        _compositor.terminate()
        sys.exit(1)

    # ── 8. FINALIZE ───────────────────────────────────────────────────────────
    print("[ToonToon] Finalizing video composition...")
    logger.info("Invoking downstream asset mixing and rendering file wrap processing routines...")
    try:
        _compositor.finish()
        if output_path.exists():
            size_mb = output_path.stat().st_size / (1024 * 1024)
            success_msg = f"✓ Done! Saved: {output_path.resolve()} ({size_mb:.1f} MB)"
            print(f"[ToonToon] {success_msg}")
            logger.info(f"Target process completion successful. Container artifact properties: {success_msg}")
        else:
            err_msg = f"FFmpeg compilation loop concluded but target output binary file cannot be verified on disk: {output_path.resolve()}"
            print(f"[ERROR] {err_msg}")
            logger.error(err_msg)
            sys.exit(1)
            
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        logger.exception("Downstream multiplexing encoding block crash detected during file wrapper finalization.")
        sys.exit(1)


if __name__ == "__main__":
    start = time.time()
    logger.info("--- ToonToon Orchestrator Process Fired up ---")
    main()
    execution_total = time.time() - start
    logger.info(f"--- ToonToon Script Closed down. Lifetime Run duration: {execution_total:.4f}s ---")