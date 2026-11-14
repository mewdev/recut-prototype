"""Essentia key estimation for the map's key ranges (M2). The only Essentia call outside
`qc_essentia`; it shares that module's switch and Intel-Mac guard.

Essentia's wheel aborts the whole process on import on Intel Macs, so callers MUST check
`available()` (= `qc_essentia.available()`: installed, importable in a child process, and not
disabled by `RECUT_QC_ESSENTIA=0`) before calling `estimate_key`. `recut.map.musicdata` does,
and falls back to a librosa chroma + Krumhansl-Schmuckler estimate when it is False.
Essentia is AGPL-3.0: same non-commercial caveat as `qc_essentia`.
"""

import numpy as np

from recut import qc_essentia

ESSENTIA_SR = 44100


def available() -> bool:
    return qc_essentia.available()


def estimate_key(mono: np.ndarray, sr: int) -> tuple[str, str, float]:
    """(tonic, mode, strength 0-1) of a mono float signal via Essentia's KeyExtractor."""
    es = qc_essentia._module()
    if es is None:
        raise RuntimeError("essentia is not available")
    if sr != ESSENTIA_SR:
        import librosa

        mono = librosa.resample(mono, orig_sr=sr, target_sr=ESSENTIA_SR)
    key, scale, strength = es.KeyExtractor(sampleRate=ESSENTIA_SR)(
        np.ascontiguousarray(mono, dtype=np.float32)
    )
    return str(key), str(scale), float(strength)
