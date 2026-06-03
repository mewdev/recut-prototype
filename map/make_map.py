# TODO: post-process segment labels using chord data — segments labeled "verse"
# whose chord_at_end is a dominant 7th could be relabeled "pre-chorus".
# Requires key detection first (to know which chord is the dominant).
# Not always reliable — depends on song structure.

import json
import numpy as np
import numpy.typing as npt
import librosa
import pathlib
from typing import Any, Optional, TypedDict
class Sources(TypedDict):
    beats: str
    chords: str
    structure: str

class ChordEntry(TypedDict):
    start: float
    end: float
    chord: str

class SegmentEntry(TypedDict):
    start: float
    end: float
    label: str
class MusicData(TypedDict):
    path: str
    bpm: float
    time_signature: str
    beats: list[float]
    downbeats: list[float]
    segments: list[SegmentEntry]
    chords: list[ChordEntry]
    _sources: Sources

# --- Output types (provided) ---
class EnrichedSegment(TypedDict):
    index: int
    label: str
    start: float
    end: float
    duration: float
    bars: int
    chords: list[str]
    chord_at_start: Optional[str]
    chord_at_end: Optional[str]
    loudness_db: float
    loudness_start_db: float
    loudness_end_db: float

class MusicMap(TypedDict):
    path: str
    bpm: float
    time_signature: str
    duration: float
    segments: list[EnrichedSegment]
    _sources: Sources


def make_map(json_path: str, audio_path: str) -> MusicMap:
    with open(json_path) as f:
        data: MusicData = json.load(f)

    AUDIO_PATH = pathlib.Path(audio_path)

    # mono=False preserves stereo; sr=None keeps native sample rate

    # librosa.load returns (ndarray[Unknown], int|float) — we cast to our expected types
    _audio, _sr = librosa.load(str(AUDIO_PATH), sr=None, mono=False)  # type: ignore[misc]
    audio: npt.NDArray[np.float32] = np.asarray(_audio, dtype=np.float32)
    sr: int = int(_sr)
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]

    REQUIRED: dict[str, Any] = {
        "path": str,
        "bpm": (int, float),
        "beats": list,
        "downbeats": list,
        "segments": list,
        "chords": list,
    }

    # add runtime validator leter
    def validate(data: Any) -> None:
        for key, expected_type in REQUIRED.items():
            if key not in data:
                raise ValueError(f"{key} expected {expected_type}, got {type(data[key])}")
            if not isinstance(data[key], expected_type):
                raise ValueError(f"{key}, expected {expected_type}, got {type(data[key])}")

    def chord_at(chords: list[ChordEntry], t: float) -> Optional[str]:
        result: Optional[str] = None
        for chord in chords:
            if chord["start"] <= t:
                result = chord["chord"]
        return result if result != "N" else None

    def chords_in(chords: list[ChordEntry], start: float, end: float) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for chord in chords:
            if chord["chord"] != "N" and start <= chord["start"] < end:
                if chord["chord"] not in seen:
                    seen.add(chord["chord"])
                    result.append(chord["chord"])
        return result

    def snap_to_downbeat(t: float, downbeats: list[float], tolerance: float = 0.4, fallback_threshold: float = 0.5) -> float:
        """Snap t to first downbeat >= (t - tolerance), but only if it's within fallback_threshold.
        Falls back to raw ChordMini value when beat tracker has no nearby downbeat (e.g. after drift)."""
        for downbeat in downbeats:
            if downbeat >= t - tolerance:
                if abs(downbeat - t) <= fallback_threshold:
                    return downbeat
                return t  # nearest candidate too far — trust raw value
        return t

    def snap_to_first_beat(segments: list[SegmentEntry], data: MusicData) -> list[SegmentEntry]:
        downbeats = data["downbeats"]

        snapped: list[SegmentEntry] = []
        for seg in segments:
            snapped.append({
                "label": seg["label"],
                "start": snap_to_downbeat(seg["start"], downbeats),
                "end": snap_to_downbeat(seg["end"], downbeats),
            })

        # Prepend silence segment if first segment doesn't start at 0
        if snapped[0]["start"] > 0.0:
            empty_segment: SegmentEntry = {
                "label": "silence",
                "start": 0.0,
                "end": snapped[0]["start"],
            }
            return [empty_segment, *snapped]

        return snapped


    def bars_in(downbeats: list[float], start: float, end: float) -> int:
        return sum(1 for downbeat in downbeats if start <= downbeat < end)

    # RMS (root mean square) measures average signal power over a time window.
    # Converting to dB (20 * log10) maps to a perceptual scale where equal dB
    # steps sound equally loud. 1e-10 floor prevents log(0) on silent segments.

    def loudness_rms_db(audio: npt.NDArray[np.float32], sr: int, start: float, end: float) -> float:
        s = int(start * sr)
        e = int(end * sr)
        chunk = audio[:, s:e]
        rms = float(np.sqrt(np.mean(chunk ** 2)))
        return round(20 * np.log10(rms + 1e-10), 1)


    def run(data: MusicData) -> MusicMap:

        validate(data)

        segments = snap_to_first_beat(data["segments"], data)

        enriched: list[EnrichedSegment] = []
        for i, segment in enumerate(segments):
            segment_chords = chords_in(data["chords"], segment["start"], segment["end"])
            enriched.append({
                "index": i,
                "label": segment["label"],
                "start": segment["start"],
                "end": segment["end"],
                "duration": round(segment["end"] - segment["start"], 2),
                "bars": bars_in(data["downbeats"], segment["start"], segment["end"]),
                "chords": segment_chords,
                "chord_at_start": segment_chords[0] if segment_chords else None,
                "chord_at_end": chord_at(data["chords"], segment["end"] - 0.1) if segment_chords else None,
                "loudness_db": loudness_rms_db(audio, sr, segment["start"], segment["end"]),
                "loudness_start_db": loudness_rms_db(audio, sr, segment["start"], segment["start"] + 0.5),
                "loudness_end_db": loudness_rms_db(audio, sr, max(segment["start"], segment["end"] - 0.5), segment["end"]),
            })

        result: MusicMap = {
            "path": data["path"],
            "bpm": data["bpm"],
            "time_signature": data["time_signature"],
            "duration": round(float(data["beats"][-1]), 2),
            "segments": enriched,
            "_sources": data["_sources"],
        }

        return result
    
    return run(data)


if __name__ == "__main__":

    import sys

    result = make_map(sys.argv[1], sys.argv[2])
    with open(sys.argv[3], "w") as f:
        json.dump(result, f, indent=2)
