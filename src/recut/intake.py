"""Intake check (Q0): warn the operator about poor-quality source files before a ticket exists.

`check_audio(path)` returns an `IntakeResult`. Blocking problems need `--override` (CLI) or the
"Upload anyway" checkbox (`/new`); `info`-level ones (fake stereo, clipped source) never block.
The messages are plain words so the operator can forward them to the client.

The bitrate in a file can lie (a 128 kbps MP3 re-saved as 320, or as WAV), so the real
bandwidth of 30 s from the middle of the track is always measured too (`qc.bandwidth_hz`).
Runs in well under a second for a 5-minute file: ffprobe for the metadata, then only the
middle 30 s is decoded. Clipping uses the numpy detector of `recut.qc` (the Essentia detectors
there are frame-by-frame Python calls, far too slow for an intake check).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MIN_BITRATE_KBPS = 256
MIN_BANDWIDTH_HZ = 18_000
MIN_SAMPLERATE = 44_100
MIN_DURATION_S = 20.0
MAX_DURATION_S = 15 * 60.0
WINDOW_S = 30.0
FAKE_STEREO_CORR = 0.999

_LOSSY = {"mp3", "aac", "vorbis", "opus", "wmav1", "wmav2", "ac3", "eac3", "mp2", "amr_nb", "amr_wb"}


@dataclass
class IntakeResult:
    problems: list[dict] = field(default_factory=list)  # {code, message, blocking}
    info: dict = field(default_factory=dict)

    @property
    def blocking(self) -> list[dict]:
        return [p for p in self.problems if p["blocking"]]

    @property
    def ok(self) -> bool:
        return not self.blocking

    def to_dict(self) -> dict:
        return {"ok": self.ok, "problems": self.problems, "info": self.info}

    def _add(self, code: str, message: str, blocking: bool = True) -> None:
        self.problems.append({"code": code, "message": message, "blocking": blocking})


def _probe(path: Path) -> dict | None:
    """ffprobe summary, {"error": True} for an unprobeable file, None when ffprobe is missing."""
    if shutil.which("ffprobe") is None:
        return None
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
             "stream=codec_name,sample_rate,channels,bit_rate,duration:format=bit_rate,duration",
             "-of", "json", str(path)], capture_output=True, timeout=20)
        d = json.loads(r.stdout or b"{}")
    except Exception:
        return None
    if r.returncode != 0 or not d.get("streams"):
        return {"error": True}
    s, f = d["streams"][0], d.get("format", {})

    def num(*vals):
        for v in vals:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
        return None

    return {"codec": s.get("codec_name"), "sample_rate": int(num(s.get("sample_rate")) or 0) or None,
            "channels": s.get("channels"), "bit_rate": num(s.get("bit_rate"), f.get("bit_rate")),
            "duration": num(s.get("duration"), f.get("duration"))}


def _decode_window(path: Path, start: float, sr: int, channels: int) -> np.ndarray | None:
    """(channels, n) float32 of up to WINDOW_S seconds from `start`; None if nothing decodes."""
    ch = max(1, min(int(channels or 2), 2))
    if shutil.which("ffmpeg"):
        try:
            r = subprocess.run(
                ["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{WINDOW_S}", "-i", str(path),
                 "-vn", "-ac", str(ch), "-ar", str(sr), "-f", "f32le", "-"],
                capture_output=True, timeout=30)
            if r.returncode == 0 and len(r.stdout) >= 4 * ch * sr:
                return np.frombuffer(r.stdout, dtype="<f4").reshape(-1, ch).T.copy()
        except Exception:
            pass
    try:
        import soundfile as sf

        with sf.SoundFile(str(path)) as f:
            f.seek(min(int(start * f.samplerate), max(0, f.frames - 1)))
            x = f.read(int(WINDOW_S * f.samplerate), dtype="float32", always_2d=True)
        return x[:, :2].T.copy() if x.size else None
    except Exception:
        pass
    try:
        import librosa

        x, _ = librosa.load(str(path), sr=sr, mono=False, offset=start, duration=WINDOW_S)
        x = np.atleast_2d(x)
        return x[:2].astype(np.float32) if x.size else None
    except Exception:
        return None


def check_audio(path) -> IntakeResult:
    """Check one audio file. Never raises: an unreadable file is an `undecodable` problem."""
    from recut import qc

    path = Path(path)
    res = IntakeResult()
    unreadable = "We couldn't read this file. Please export it again (WAV or FLAC is best)."
    if not path.is_file():
        res._add("undecodable", unreadable)
        return res

    meta = _probe(path)
    if meta is not None and meta.get("error"):
        res._add("undecodable", unreadable)
        return res
    if meta is None:  # no ffprobe: soundfile knows WAV/FLAC/AIFF/OGG (+ MP3 on recent builds)
        try:
            import soundfile as sf

            i = sf.info(str(path))
            meta = {"codec": None, "sample_rate": i.samplerate, "channels": i.channels,
                    "bit_rate": None, "duration": i.duration,
                    "lossless": i.format in ("WAV", "FLAC", "AIFF", "CAF", "W64")}
        except Exception:
            meta = {"codec": None, "sample_rate": None, "channels": 2, "bit_rate": None, "duration": None}

    codec = (meta.get("codec") or "").lower()
    lossy = codec in _LOSSY
    lossless = bool(meta.get("lossless")) or (bool(codec) and not lossy)
    sr = meta.get("sample_rate") or 44100
    dur = meta.get("duration")
    kbps = round(meta["bit_rate"] / 1000) if meta.get("bit_rate") else None
    res.info = {"codec": codec or None, "lossless": lossless, "sample_rate": sr, "channels": meta.get("channels"),
                "bitrate_kbps": kbps, "duration_s": round(dur, 2) if dur else None}

    start = max(0.0, (dur or WINDOW_S) / 2 - WINDOW_S / 2)
    x = _decode_window(path, start, sr, meta.get("channels") or 2)
    if x is None:
        if dur is not None and dur < 1.0:  # decodes, but far too short for a 1 s window
            res._add("too_short", f"This file is only {dur:.1f} s long. Is it the whole track?")
        else:
            res._add("undecodable", unreadable)
        return res

    if lossy and kbps is not None and kbps < MIN_BITRATE_KBPS * 0.98:
        res._add("low_bitrate", f"This is a {kbps} kbps file. Please send WAV/FLAC, or an MP3/AAC of at least "
                                f"{MIN_BITRATE_KBPS} kbps.")
    if sr < MIN_SAMPLERATE:
        res._add("low_samplerate", f"This file's sample rate is {sr / 1000:g} kHz. Please send it at 44.1 kHz "
                                   "or higher.")
    if dur is not None and dur < MIN_DURATION_S:
        res._add("too_short", f"This file is only {dur:.0f} s long. Is it the whole track? (minimum "
                              f"{MIN_DURATION_S:.0f} s)")
    if dur is not None and dur > MAX_DURATION_S:
        res._add("too_long", f"This file is {dur / 60:.0f} minutes long. Is it one track? (maximum "
                             f"{MAX_DURATION_S / 60:.0f} minutes)")

    bw = qc.bandwidth_hz(x, sr)
    res.info["bandwidth_hz"] = round(bw) if bw is not None else None
    # a low sample rate is reported by low_samplerate; its ceiling isn't a codec lowpass
    if bw is not None and bw < MIN_BANDWIDTH_HZ and sr >= MIN_SAMPLERATE:
        res._add("low_bandwidth", f"This file sounds like it came from a low-quality MP3 (nothing above "
                                  f"{bw / 1000:.0f} kHz). Do you have the original?")

    if x.shape[0] == 2 and float(np.abs(x).max()) > 1e-4:
        a, b = x[0] - x[0].mean(), x[1] - x[1].mean()
        den = float(np.sqrt((a * a).sum() * (b * b).sum()))
        same = np.abs(x[0] - x[1]).max() < 1e-6
        if same or (den > 0 and float((a * b).sum()) / den > FAKE_STEREO_CORR):
            res._add("fake_stereo", "Left and right channels are identical (mono saved as stereo).", False)
    runs = qc.clip_runs(np.abs(x).max(0), sr)
    if runs:
        res.info["clip_runs"] = len(runs)
        res._add("clipped_source", f"The source clips (flat-topped peaks, {len(runs)} runs in the sampled "
                                   "30 s). The cut can't repair that.", False)
    return res


def format_result(name: str, res: IntakeResult) -> str:
    """Plain-text block for the CLI."""
    i = res.info
    bits = [i.get("codec") or "?", f"{(i.get('sample_rate') or 0) / 1000:g} kHz"]
    if i.get("bitrate_kbps"):
        bits.append(f"{i['bitrate_kbps']} kbps")
    if i.get("bandwidth_hz"):
        bits.append(f"bandwidth {i['bandwidth_hz'] / 1000:.1f} kHz")
    if i.get("duration_s"):
        bits.append(f"{i['duration_s']:.0f} s")
    lines = [f"{name}: {'OK' if res.ok else 'PROBLEMS'} ({', '.join(bits)})"]
    for p in res.problems:
        lines.append(f"  - [{p['code']}{'' if p['blocking'] else ', info'}] {p['message']}")
    return "\n".join(lines)
