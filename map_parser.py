from abc import ABC, abstractmethod


class MapParser(ABC):
    """Abstract base — one implementation per map format (our map, MUF)."""

    @abstractmethod
    def get_segment(self, label: str, index: int = 1) -> dict:
        """Return {start, end} for Nth occurrence of label (1-based)."""
        ...

    @abstractmethod
    def get_bpm(self) -> float:
        """Return BPM from map."""
        ...

    @abstractmethod
    def bars_to_seconds(self, bars: float) -> float:
        """Convert bar count to seconds using map BPM + time signature."""
        ...

    def beats_to_seconds(self, beats: float) -> float:
        """Convert beat count to seconds. Default: 1 beat = 60/bpm."""
        return beats * (60.0 / self.get_bpm())

    @abstractmethod
    def first_segment(self) -> dict:
        """Return {label, start, end} for the first segment of the song."""
        ...

    @abstractmethod
    def last_segment(self) -> dict:
        """Return {label, start, end} for the last meaningful segment (excluding silence)."""
        ...


class OurMapParser(MapParser):
    """Parser for our JSON map format (map/examples/*.json)."""

    def __init__(self, map_path: str):
        import json
        with open(map_path) as f:
            self._map = json.load(f)

    def get_bpm(self) -> float:
        return self._map["bpm"]

    def bars_to_seconds(self, bars: float) -> float:
        beats_per_bar = int(self._map["time_signature"].split("/")[0])
        seconds_per_beat = 60/self._map["bpm"]
        return bars * beats_per_bar * seconds_per_beat

    def first_segment(self) -> dict:
        s = self._map["segments"][0]
        return {"label": s["label"], "start": s["start"], "end": s["end"]}

    def last_segment(self) -> dict:
        non_silence = [s for s in self._map["segments"] if s["label"] != "silence"]
        s = non_silence[-1] if non_silence else self._map["segments"][-1]
        return {"label": s["label"], "start": s["start"], "end": s["end"]}

    def get_segment(self, label: str, index: int = 1) -> dict:

        segments = [segment for segment in self._map["segments"] if segment["label"] == label]

        if len(segments) < index:
            raise ValueError(f"No {label!r} segment at index {index}") 
        
        segment = segments[index - 1]
        
        result = {"start": segment["start"], "end": segment["end"]}
        if "downbeats" in segment:
            result["downbeats"] = segment["downbeats"]
            # TODO: learn later why this matters
            # audio_start = first downbeat (skips pre-roll silence before first beat)
            # audio_end = last downbeat + 1 bar (ensures cut lands after full last bar, not at ML boundary)
            result["audio_start"] = segment["downbeats"][0]
            result["audio_end"] = segment["downbeats"][-1]
        return result


class MUFParser(MapParser):
    """Parser for Apple MUF format (MusicUnderstandingFramework/*.json).

    MUF has no segment labels — get_segment() uses index only (label ignored).
    Sections are sample-based: value / timescale = seconds.
    """

    def __init__(self, muf_path: str):
        import json
        with open(muf_path) as f:
            self._map = json.load(f)

    def _to_seconds(self, ts: dict) -> float:
        """Convert MUF timestamp dict to seconds."""
        return ts["value"] / ts["timescale"]

    def get_bpm(self) -> float:
        return self._map["rhythm"]["beatsPerMinute"]

    def bars_to_seconds(self, bars: float) -> float:
        # MUF has no time_signature field — assuming 4/4
        return bars * 4 * (60.0 / self.get_bpm())

    def first_segment(self) -> dict:
        sections = self._map["structure"]["sections"]
        s = sections[0]
        return {"label": "section_1", "start": self._to_seconds(s["start"]),
                "end": self._to_seconds(s["start"]) + self._to_seconds(s["duration"])}

    def last_segment(self) -> dict:
        sections = self._map["structure"]["sections"]
        s = sections[-1]
        return {"label": f"section_{len(sections)}", "start": self._to_seconds(s["start"]),
                "end": self._to_seconds(s["start"]) + self._to_seconds(s["duration"])}

    def get_segment(self, label: str, index: int = 1) -> dict:
        """Return {start, end} for section at index (label ignored — MUF has no labels)."""
        sections = self._map["structure"]["sections"]

        if len(sections) < index:
                    raise ValueError(f"No section at index {index}") 

        section = sections[index - 1]

        return {
            "start": self._to_seconds(section["start"]),
            "end": self._to_seconds(section["start"]) + self._to_seconds(section["duration"])
        }