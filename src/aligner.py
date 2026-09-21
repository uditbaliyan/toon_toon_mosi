"""
Speech-to-text alignment clients.

GentleAligner  — HTTP client for a locally running Gentle Docker container.
MFAAligner     — subprocess client for the Montreal Forced Aligner (MFA).
                 No server/Docker needed; use this on Kaggle.

Both expose the same interface: align(audio_path, transcript) -> List[AlignedWord],
so callers (main.py) only need to swap which class they import/instantiate.

MFA setup on Kaggle — this exact recipe (once per session) is verified working,
including the two gotchas below (Kaggle's base image has no bare `conda`/`mamba`
on PATH pointing at a real conda install, and `mfa align` fails without a PATH fix):

    !wget -qO /tmp/miniforge.sh \\
        https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
    !bash /tmp/miniforge.sh -b -p /kaggle/working/miniforge
    !/kaggle/working/miniforge/bin/mamba create -y -n mfa -c conda-forge montreal-forced-aligner
    !/kaggle/working/miniforge/envs/mfa/bin/mfa model download acoustic english_us_arpa
    !/kaggle/working/miniforge/envs/mfa/bin/mfa model download dictionary english_us_arpa
    !pip install -q praatio

Then always call the `mfa` binary by its full path inside that env
("/kaggle/working/miniforge/envs/mfa/bin/mfa") — never a bare "mfa", and never
`mamba run -n mfa ...` / `conda activate mfa`. On Kaggle specifically,
`/usr/local/bin/mamba` is a *different*, pre-installed package (a Python BDD
test framework, not conda-forge's mamba) that silently shadows the real one.

Use the english_us_arpa dictionary + acoustic model pair, NOT english_mfa /
english_us_mfa. The *_mfa models use MFA's newer IPA-derived phone set;
*_us_arpa keeps the ARPABET inventory Gentle also produced (confirmed: its
phone tier emits labels like "AH0", "EH1", "spn" for OOV), so config.py's
PHONEME_MAP and MOUTH_SHAPE_CODES need zero changes. Turn the GPU accelerator
off in the notebook's session settings — MFA/Kaldi is CPU-only and you'll get
a faster queue and more CPU quota without it.

Also note the latency shape changes: Gentle keeps its acoustic model warm in
a running container, so align() is a fast HTTP round trip. MFA reloads
everything (feature extraction, decoding graph, model) from scratch on every
subprocess call — expect tens of seconds to a couple of minutes per call
depending on audio length. Since main.py only calls align() once per full
narration track (not per segment), this is a non-issue here — just don't
port this into a per-sentence loop without batching.
"""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

import requests

from .models import AlignedWord, PhonemeInterval


class GentleAligner:
    """
    Synchronous HTTP client for Gentle speech alignment API.

    Connects to a local Gentle Docker container instance running on
    http://localhost:8765 and processes audio/transcript pairs to produce
    frame-accurate phoneme timing.
    """

    def __init__(self, base_url: str = "http://localhost:8765"):
        """
        Initialize the Gentle API client.

        Args:
            base_url: Base URL of the Gentle API service.
        """
        self.base_url = base_url
        # FIX 1: Updated endpoint to include '/transcriptions?async=false'
        # Without this, Gentle returns HTML rather than JSON data.
        self.transcription_endpoint = f"{base_url}/transcriptions?async=false"

    def align(self, audio_path: str, transcript: str) -> List[AlignedWord]:
        """
        Perform phoneme-level alignment on audio against a transcript.

        Args:
            audio_path: Path to the audio file (.wav recommended).
            transcript: Clean transcript text to align.

        Returns:
            List of AlignedWord objects with phoneme timing.

        Raises:
            ConnectionError: If unable to reach the Gentle service.
            ValueError: If alignment fails or produces invalid response.
        """
        try:
            # Open audio file and prepare multipart form data
            with open(audio_path, "rb") as audio_file:
                files = {"audio": audio_file}
                data = {"transcript": transcript}

                # Send synchronous request
                response = requests.post(
                    self.transcription_endpoint,
                    files=files,
                    data=data,
                    timeout=300,  # Long timeout for processing
                )

            response.raise_for_status()
            result = response.json()

            # FIX 2: Gentle does not return a 'success' key.
            # We now safely check if the expected 'words' list exists instead.
            if "words" not in result:
                raise ValueError(
                    "Alignment failed: Invalid or empty response structure from Gentle."
                )

            # Parse the response into AlignedWord objects
            return self._parse_alignment_result(result)

        except requests.exceptions.ConnectionError as e:
            raise ConnectionError(
                f"Failed to connect to Gentle API at {self.base_url}. "
                "Verify local Docker container execution via: "
                "docker run -d -p 8765:8765 lowerquality/gentle"
            ) from e
        except FileNotFoundError as e:
            raise FileNotFoundError(f"Audio file not found: {audio_path}") from e

    def _parse_alignment_result(self, result: dict) -> List[AlignedWord]:
        """
        Parse JSON response from Gentle into AlignedWord objects.

        Args:
            result: JSON response dictionary from Gentle API.

        Returns:
            List of AlignedWord objects.
        """
        aligned_words = []

        words = result.get("words", [])
        for word_data in words:
            # Skip words not found in audio
            if word_data.get("case") == "not-found-in-audio":
                continue

            word_text = word_data.get("word")
            start_time = word_data.get("start")
            end_time = word_data.get("end")

            if start_time is None or end_time is None:
                continue

            # Parse phonemes for this word
            phones = []
            for phone_data in word_data.get("phones", []):
                phone_str = phone_data.get("phone", "sil")
                duration = phone_data.get("duration", 0.0)
                phones.append(PhonemeInterval(phone_str, duration))

            aligned_words.append(
                AlignedWord(
                    word=word_text,
                    start_time=start_time,
                    end_time=end_time,
                    phones=phones,
                )
            )

        return aligned_words


# Labels MFA emits for silence / non-speech noise / OOV filler across its word
# and phone tiers. Normalized to "sil" so config.PHONEME_MAP's "sil": "m" entry
# (and scheduler.py's explicit `code == "sil"` check) keep working unchanged.
_MFA_SILENCE_LABELS = {"", "sil", "sp", "spn", "silence"}

# Strips trailing ARPABET stress digits: "AH0" -> "AH", "IH1" -> "IH".
_STRESS_DIGIT_RE = re.compile(r"\d+$")


class MFAAligner:
    """
    Subprocess client for the Montreal Forced Aligner (MFA).

    Uses `mfa align` against a single-utterance corpus dir + praatio to read
    back the resulting TextGrid. This is the exact shape verified working on
    Kaggle (see module docstring) — not MFA's `align_one` shortcut, which
    hasn't been tested against this env/version and isn't worth the risk when
    the corpus-dir path is already proven.
    """

    def __init__(
        self,
        mfa_bin: str,
        dictionary: str = "english_us_arpa",
        acoustic_model: str = "english_us_arpa",
        num_jobs: int = 2,
        clean: bool = False,
        timeout: int = 1800,
    ):
        """
        Args:
            mfa_bin: Full path to the `mfa` executable inside its conda/mamba
                env, e.g. "/kaggle/working/miniforge/envs/mfa/bin/mfa". Do NOT
                rely on a bare "mfa" resolving via `conda activate`/`mamba
                run` — on Kaggle specifically, `/usr/local/bin/mamba` is an
                unrelated pre-installed package (a Python BDD test tool, not
                conda-forge's mamba) that shadows the real one and silently
                takes the wrong CLI arguments.
            dictionary: Pronunciation dictionary model name.
            acoustic_model: Acoustic model name.
            num_jobs: Parallel Kaldi jobs (moot for a single utterance, kept
                low). --single_speaker is always passed so a single speaker's
                one utterance doesn't trigger MFA's job-count warning.
            clean: Pass --clean to force MFA to wipe its own internal temp/
                cache dir first. Off by default to match the verified-working
                invocation; turn on if you hit stale-state errors across
                repeated calls in one notebook session.
            timeout: Max seconds to wait for a single align() call.
        """
        self.mfa_bin = mfa_bin
        self.mfa_bin_dir = str(Path(mfa_bin).parent)
        self.dictionary = dictionary
        self.acoustic_model = acoustic_model
        self.num_jobs = num_jobs
        self.clean = clean
        self.timeout = timeout

    def _subprocess_env(self) -> dict:
        """
        MFA's `align` command shells out to OpenFst/Kaldi binaries (fstcompile
        etc.) that live next to `mfa` in the same env's bin/ dir. Invoking
        `mfa` by its own absolute path does NOT put that dir on PATH for its
        *own* child processes — confirmed empirically: `mfa align ...` fails
        outright when called this way, and succeeds once the env's bin/ is
        prepended to PATH for the call. This is that fix.
        """
        env = os.environ.copy()
        env["PATH"] = f"{self.mfa_bin_dir}{os.pathsep}{env.get('PATH', '')}"
        return env

    def align(self, audio_path: str, transcript: str) -> List[AlignedWord]:
        """
        Perform phoneme-level alignment on audio against a transcript.

        Args:
            audio_path: Path to the audio file (.wav recommended).
            transcript: Clean transcript text to align.

        Returns:
            List of AlignedWord objects with phoneme timing.

        Raises:
            FileNotFoundError: If audio_path doesn't exist.
            ImportError: If praatio isn't installed (pip install praatio).
            ValueError: If MFA exits non-zero or produces no TextGrid.
        """
        audio_path = Path(audio_path)
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            from praatio import textgrid
        except ImportError as e:
            raise ImportError(
                "praatio is required to read MFA's TextGrid output: pip install praatio"
            ) from e

        with tempfile.TemporaryDirectory(prefix="toontoon_mfa_") as tmp_str:
            tmp = Path(tmp_str)
            corpus_dir = tmp / "corpus"
            output_dir = tmp / "output"
            corpus_dir.mkdir()

            stem = audio_path.stem
            shutil.copy(audio_path, corpus_dir / f"{stem}{audio_path.suffix}")
            (corpus_dir / f"{stem}.txt").write_text(transcript, encoding="utf-8")

            cmd = [
                self.mfa_bin,
                "align",
                str(corpus_dir),
                self.dictionary,
                self.acoustic_model,
                str(output_dir),
                "--single_speaker",
                "-j",
                str(self.num_jobs),
            ]
            if self.clean:
                cmd.append("--clean")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    env=self._subprocess_env(),
                )
            except FileNotFoundError as e:
                raise FileNotFoundError(
                    f"MFA binary not found at '{self.mfa_bin}'. Pass the full "
                    "path to the env it's installed in, e.g. "
                    "mfa_bin='/kaggle/working/miniforge/envs/mfa/bin/mfa'."
                ) from e
            except subprocess.TimeoutExpired as e:
                raise ValueError(
                    f"MFA alignment timed out after {self.timeout}s."
                ) from e

            if result.returncode != 0:
                raise ValueError(
                    f"MFA alignment failed (exit {result.returncode}):\n"
                    f"{result.stderr.strip()[-4000:]}"
                )

            grid_path = output_dir / f"{stem}.TextGrid"
            if not grid_path.exists():
                raise ValueError(
                    "MFA exited cleanly but produced no TextGrid — check for "
                    "OOV words or an empty/silent audio track.\n"
                    f"stderr: {result.stderr.strip()[-2000:]}"
                )

            tg = textgrid.openTextgrid(str(grid_path), includeEmptyIntervals=True)
            word_entries = tg.getTier("words").entries
            phone_entries_raw = tg.getTier("phones").entries

        return self._build_words(word_entries, phone_entries_raw)

    def _build_words(self, word_entries, phone_entries_raw) -> List[AlignedWord]:
        """Convert praatio's (start, end, label) tier entries into AlignedWords."""
        phone_entries = [
            (start, end, self._normalize_phone(label))
            for start, end, label in phone_entries_raw
        ]

        aligned_words: List[AlignedWord] = []
        for start, end, text in word_entries:
            text = text.strip()
            if not text or text.lower() in _MFA_SILENCE_LABELS:
                continue

            # Phone tier is a flat, file-wide timeline — bucket each phone
            # into the word interval it falls inside (with float slop).
            phones = [
                PhonemeInterval(phone=label, duration=p_end - p_start)
                for p_start, p_end, label in phone_entries
                if p_start >= start - 1e-3 and p_end <= end + 1e-3
            ]

            aligned_words.append(
                AlignedWord(word=text, start_time=start, end_time=end, phones=phones)
            )

        return aligned_words

    @staticmethod
    def _normalize_phone(label: str) -> str:
        label = label.strip().lower()
        if label in _MFA_SILENCE_LABELS:
            return "sil"
        return _STRESS_DIGIT_RE.sub("", label) or "sil"
