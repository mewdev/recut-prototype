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

    def get_segment(self, label: str, index: int = 1) -> dict:

        segments = [segment for segment in self._map["segments"] if segment["label"] == label]

        if len(segments) < index:
            raise ValueError(f"No {label!r} segment at index {index}") 
        
        segment = segments[index - 1]
        
        return {"start": segment["start"],"end": segment["end"]}