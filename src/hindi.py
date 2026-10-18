"""
Hindi helpers for the MFA aligner.

1. prepare_transcript(): NFC-normalise + strip danda/punctuation so MFA's
   tokenizer sees bare Devanagari words (hindi_cv's dict has entries with
   punctuation glued on, so don't rely on MFA stripping it).
2. build_oov_dictionary(): hindi_cv covers ~11k words. Anything else becomes
   <unk>/spn -> closed mouth for that whole word. We G2P the missing Devanagari
   words with Epitran (same phone set hindi_cv was built from), filter to
   phones the acoustic model knows, and write base+extra to a temp dict.

Needs: pip install epitran   (only for OOV generation)
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

from .config import HINDI_CV_PHONES

logger = logging.getLogger("ToonToon.Hindi")

_PUNCT_RE = re.compile(r"[।॥.,!?;:\"'“”‘’()\[\]{}\-–—…]")
_DEVANAGARI_RE = re.compile(r"[\u0900-\u097F]")


def prepare_transcript(text: str) -> str:
    """NFC + replace danda/punctuation with spaces + collapse whitespace
    (newlines kept; they only matter for scheduler line-break logic, which
    runs on the original clean_script, not this)."""
    text = unicodedata.normalize("NFC", text)
    text = _PUNCT_RE.sub(" ", text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _tokens(text: str) -> List[str]:
    return [t for t in text.split() if t]


def find_dictionary(name: str, mfa_bin: str) -> Path:
    """Locate a downloaded pretrained dictionary file."""
    roots = []
    if os.environ.get("MFA_ROOT_DIR"):
        roots.append(Path(os.environ["MFA_ROOT_DIR"]))
    roots += [Path.home() / "Documents" / "MFA", Path.home() / ".local" / "share" / "mfa"]
    for root in roots:
        d = root / "pretrained_models" / "dictionary"
        for cand in (d / f"{name}.dict", d / f"{name}.txt"):
            if cand.exists():
                return cand
        if d.exists():
            hits = sorted(d.glob(f"{name}*"))
            if hits:
                return hits[0]
    raise FileNotFoundError(
        f"Dictionary '{name}' not found under MFA root. Run "
        f"`{mfa_bin} model download dictionary {name}` first "
        "(or set $MFA_ROOT_DIR)."
    )


def _load_vocab(dict_path: Path) -> Set[str]:
    vocab: Set[str] = set()
    with open(dict_path, encoding="utf-8") as f:
        for line in f:
            w = line.split("\t", 1)[0].split(" ", 1)[0].strip()
            if w:
                vocab.add(unicodedata.normalize("NFC", w))
    return vocab


def _g2p(words: Iterable[str]) -> List[Tuple[str, List[str]]]:
    try:
        import epitran
    except ImportError as e:
        raise ImportError("pip install epitran (needed for Hindi OOV words)") from e
    epi = epitran.Epitran("hin-Deva")
    out = []
    for w in words:
        phones = [unicodedata.normalize("NFC", p) for p in epi.trans_list(w)]
        kept = [p for p in phones if p in HINDI_CV_PHONES]
        dropped = [p for p in phones if p not in HINDI_CV_PHONES]
        if dropped:
            logger.debug("G2P %r dropped phones not in acoustic model: %s", w, dropped)
        if kept:
            out.append((w, kept))
    return out


def build_oov_dictionary(
    transcript: str, base_dict: Path, out_path: Path
) -> Optional[Path]:
    """
    Write base_dict + Epitran pronunciations for transcript words missing from
    it. Returns out_path, or None if nothing was missing (use base_dict as is).
    Latin-script OOV words are left alone (they stay <unk>).
    """
    vocab = _load_vocab(base_dict)
    missing = sorted(
        {
            t
            for t in _tokens(prepare_transcript(transcript))
            if t not in vocab and _DEVANAGARI_RE.search(t)
        }
    )
    if not missing:
        return None
    entries = _g2p(missing)
    logger.info("Hindi OOV: %d missing, %d given Epitran pronunciations", len(missing), len(entries))
    base = base_dict.read_text(encoding="utf-8")
    if not base.endswith("\n"):
        base += "\n"
    extra = "".join(f"{w}\t{' '.join(ph)}\n" for w, ph in entries)
    out_path.write_text(base + extra, encoding="utf-8")
    return out_path
