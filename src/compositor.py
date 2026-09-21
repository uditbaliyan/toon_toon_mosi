"""
FFmpeg pipeline orchestration for streaming animation frames and mixing audio.
Manages subprocess pipes for real-time video and audio composition.
"""

import subprocess
import os
import sys
import tempfile
import threading
import queue
from typing import Optional, List
from pathlib import Path
import numpy as np

from .config import CANVAS_WIDTH, CANVAS_HEIGHT, FRAME_RATE, BACKGROUND_MUSIC_VOLUME


class FFmpegCompositor:
    """
    Manages FFmpeg subprocess for streaming raw video and audio.

    Key fixes vs previous version:
    - stderr redirected to a temp file to prevent pipe deadlock
    - Frame writes happen on a background thread (producer/consumer queue)
      so the render loop is never blocked by a full pipe buffer
    - Proper Ctrl+C / SIGTERM cleanup via signal handlers
    - Optional .ass subtitle burn-in via subtitles_path
    """

    def __init__(
        self,
        output_path: str,
        audio_path: str,
        background_music_path: Optional[str] = None,
        music_volume: float = BACKGROUND_MUSIC_VOLUME,
        frame_queue_size: int = 16,
        subtitles_path: Optional[str] = None,
    ):
        self.output_path = output_path
        self.audio_path = audio_path
        self.background_music_path = background_music_path
        self.music_volume = music_volume
        self.frame_queue_size = frame_queue_size
        self.subtitles_path = subtitles_path

        self.process: Optional[subprocess.Popen] = None
        self._stderr_file = None          # temp file for ffmpeg stderr
        self._frame_queue: queue.Queue = queue.Queue(maxsize=frame_queue_size)
        self._writer_thread: Optional[threading.Thread] = None
        self._writer_error: Optional[Exception] = None  # surfaced after finish()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Launch FFmpeg and start the background writer thread."""
        if self.process is not None:
            raise RuntimeError("Compositor already started.")

        cmd = self._build_ffmpeg_command()

        # Windows: prevent FFmpeg from being in the same console group so
        # Ctrl+C reaches our Python process first.
        creation_flags = 0
        if os.name == "nt":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        # FIX: stderr → temp file, NOT subprocess.PIPE.
        # Piping stderr and then not draining it causes a deadlock once the
        # OS pipe buffer (~64 KB) fills up: FFmpeg blocks on stderr writes
        # while we block on stdin writes → neither side makes progress.
        self._stderr_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".log", delete=False, prefix="toontoon_ffmpeg_"
        )

        try:
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,   # we don't need stdout
                stderr=self._stderr_file,    # log to temp file, not PIPE
                creationflags=creation_flags,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg not found. Install it with:\n"
                "  Linux : sudo apt-get install ffmpeg\n"
                "  macOS : brew install ffmpeg\n"
                "  Windows: https://ffmpeg.org/download.html"
            )

        # Background thread drains the frame queue into FFmpeg stdin so the
        # render loop is never blocked by a full OS pipe buffer.
        self._writer_thread = threading.Thread(
            target=self._writer_loop, daemon=True, name="ffmpeg-writer"
        )
        self._writer_thread.start()

    def write_frame(self, frame: np.ndarray) -> None:
        """
        Enqueue a BGR24 frame for writing to FFmpeg.
        Blocks only if the queue is full (back-pressure), never on the pipe.
        """
        if self._writer_thread is None:
            raise RuntimeError("Compositor not started. Call start() first.")
        if self._writer_error is not None:
            raise RuntimeError(f"Writer thread failed: {self._writer_error}") from self._writer_error
        # Put with timeout so Ctrl+C can still interrupt
        while True:
            try:
                self._frame_queue.put(frame, timeout=0.5)
                break
            except queue.Full:
                if self._writer_error is not None:
                    raise RuntimeError(f"Writer thread failed: {self._writer_error}") from self._writer_error
                continue

    def finish(self) -> None:
        """Signal end-of-stream, wait for FFmpeg to finish, surface any errors."""
        if self._writer_thread is None:
            return

        # Sentinel value tells the writer thread to close stdin and exit
        self._frame_queue.put(None)
        self._writer_thread.join(timeout=360)

        if self._writer_error is not None:
            self._log_ffmpeg_stderr()
            raise RuntimeError(f"FFmpeg writer error: {self._writer_error}")

        if self.process is not None:
            try:
                self.process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                self.process.kill()
                raise RuntimeError("FFmpeg timed out during finalization.")

            if self.process.returncode != 0:
                self._log_ffmpeg_stderr()
                raise RuntimeError(
                    f"FFmpeg exited with code {self.process.returncode}. "
                    "See ffmpeg log above."
                )

        self._cleanup_stderr_file()

    def terminate(self) -> None:
        """Forcefully stop FFmpeg (called from signal handler on Ctrl+C)."""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self._cleanup_stderr_file()

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.finish()
        else:
            self.terminate()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _writer_loop(self) -> None:
        """
        Background thread: pulls frames from the queue and writes to FFmpeg stdin.
        Exits when it receives the None sentinel.
        """
        try:
            while True:
                frame = self._frame_queue.get()
                if frame is None:           # sentinel → done
                    break
                frame_bytes = frame.astype(np.uint8).tobytes()
                self.process.stdin.write(frame_bytes)
            self.process.stdin.close()
        except Exception as exc:
            self._writer_error = exc
            # Close stdin so FFmpeg doesn't hang waiting for more data
            try:
                self.process.stdin.close()
            except Exception:
                pass

    def _log_ffmpeg_stderr(self) -> None:
        """Print the FFmpeg log file to stderr for debugging."""
        if self._stderr_file is None:
            return
        log_path = self._stderr_file.name
        try:
            with open(log_path, "r", errors="replace") as f:
                content = f.read().strip()
            if content:
                print("\n[FFmpeg log] ─────────────────────────────", file=sys.stderr)
                # Show last 40 lines — the error is always at the end
                lines = content.splitlines()
                for line in lines[-40:]:
                    print(f"  {line}", file=sys.stderr)
                print("[FFmpeg log] ─────────────────────────────\n", file=sys.stderr)
        except Exception:
            pass

    def _cleanup_stderr_file(self) -> None:
        if self._stderr_file is not None:
            try:
                self._stderr_file.close()
                os.unlink(self._stderr_file.name)
            except Exception:
                pass
            self._stderr_file = None

    def _build_ffmpeg_command(self) -> List[str]:
        cmd = [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-vcodec", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{CANVAS_WIDTH}x{CANVAS_HEIGHT}",
            "-r", str(FRAME_RATE),
            "-i", "-",
            "-i", self.audio_path,
        ]

        if self.background_music_path:
            cmd.extend(["-i", self.background_music_path])
            filter_graph = (
                f"[2:a]volume={self.music_volume}[music];"
                f"[1:a][music]amix=inputs=2:duration=first[aout]"
            )
            cmd.extend([
                "-filter_complex", filter_graph,
                "-map", "0:v:0",
                "-map", "[aout]",
            ])
        else:
            cmd.extend(["-map", "0:v:0", "-map", "1:a:0"])

        # ── Subtitle burn-in ─────────────────────────────────────────────
        # FFmpeg's `ass` filter hardcodes the subtitle glyphs into the video
        # pixels — no separate subtitle track, works in any player.
        # Path separators and colons must be escaped for the filter graph.
        if self.subtitles_path:
            safe_path = (
                str(self.subtitles_path)
                .replace("\\", "/")      # Windows paths → forward slashes
                .replace(":", "\\:")     # Drive letter colon (C:\…) must be escaped
            )
            cmd.extend(["-vf", f"ass={safe_path}"])

        cmd.extend([
            "-c:v", "libx264",
            "-crf", "23",
            "-preset", "ultrafast",
            "-tune", "zerolatency",   # minimises encoder latency on the pipe
            "-c:a", "aac",
            "-b:a", "192k",
            str(self.output_path),
        ])

        return cmd