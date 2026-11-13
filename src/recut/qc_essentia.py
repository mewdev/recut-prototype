"""Essentia detectors for the audio QC (Q1). Every Essentia call in recut lives in this file.

Essentia is AGPL-3.0. The prototype is non-commercial, so it's allowed; before any commercial
use this file is removed or replaced with permissively licensed detectors (docs/workstreams/
Q-quality.md, "Before any commercial use"). `recut.qc` falls back to numpy/scipy detectors
whenever `available()` is False (not installed, or `RECUT_QC_ESSENTIA=0`).

Essentia's detectors are frame-by-frame Python calls, about 3.7 s for a 3-minute track in
total, so `detect()` runs them once on the mono render.
"""

import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field

import numpy as np

_ES = None  # the essentia.standard module once imported; False if the import failed


# Intel-Mac Essentia wheels abort the whole process on import ("Failed loading SDL2 library"),
# which no try/except can catch and which would kill `recut serve`. So: off by default there,
# and wherever it is on, the import is probed once in a child process first.
_BROKEN_PLATFORM = sys.platform == "darwin" and platform.machine() == "x86_64"
_PROBE_OK = None


def _probe() -> bool:
    global _PROBE_OK
    if _PROBE_OK is None:
        try:
            r = subprocess.run([sys.executable, "-c", "import essentia.standard"],
                               capture_output=True, timeout=60)
            _PROBE_OK = r.returncode == 0
        except Exception:
            _PROBE_OK = False
    return _PROBE_OK


def _module():
    global _ES
    if _ES is None:
        if not _probe():
            _ES = False
            return None
        try:
            import essentia

            essentia.log.infoActive = False
            essentia.log.warningActive = False
            import essentia.standard as es

            _ES = es
        except Exception:  # ImportError, or a wheel that can't load on this platform
            _ES = False
    return _ES or None


def enabled() -> bool:
    default = "0" if _BROKEN_PLATFORM else "1"
    return os.environ.get("RECUT_QC_ESSENTIA", default).strip().lower() not in ("0", "false", "off", "no")


def available() -> bool:
    return enabled() and _module() is not None


@dataclass
class Detections:
    clicks: list[float] = field(default_factory=list)          # seconds
    discontinuities: list[float] = field(default_factory=list)  # seconds
    saturation: list[tuple[float, float]] = field(default_factory=list)
    gaps: list[tuple[float, float]] = field(default_factory=list)


def dedupe_times(times: list[float], within: float = 0.005) -> list[float]:
    out: list[float] = []
    for t in sorted(times):
        if not out or t - out[-1] > within:
            out.append(t)
    return out


def detect(mono: np.ndarray, sr: int) -> Detections:
    """Click, discontinuity, saturation and gap detection on a mono float32 render."""
    es = _module()
    if es is None:
        raise RuntimeError("essentia is not available")
    x = np.ascontiguousarray(mono, dtype=np.float32)
    fs, hop = 512, 256
    click = es.ClickDetector(frameSize=fs, hopSize=hop, sampleRate=sr)
    disc = es.DiscontinuityDetector(frameSize=fs, hopSize=hop)
    sat = es.SaturationDetector(frameSize=fs, hopSize=hop, sampleRate=sr, minimumDuration=0.5)
    gaps = es.GapsDetector(frameSize=2048, hopSize=1024, sampleRate=sr, silenceThreshold=-60,
                           minimumTime=100)
    out = Detections()
    clicks: list[float] = []
    for k, fr in enumerate(es.FrameGenerator(x, frameSize=fs, hopSize=hop, startFromZero=True)):
        clicks += [float(t) for t in click(fr)[0]]
        out.discontinuities += [(float(i) + k * hop) / sr for i in disc(fr)[0]]
        s0, s1 = sat(fr)
        out.saturation += [(float(a), float(b)) for a, b in zip(s0, s1)]
    for fr in es.FrameGenerator(x, frameSize=2048, hopSize=1024, startFromZero=True):
        g0, g1 = gaps(fr)
        out.gaps += [(float(a), float(b)) for a, b in zip(g0, g1)]
    out.clicks = dedupe_times(clicks)
    out.discontinuities = dedupe_times(out.discontinuities)
    return out
