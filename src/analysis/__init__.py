from abc import ABC, abstractmethod
from pathlib import Path
from typing import cast

from map.schema import RawAnalysis

from analysis.pipeline import analyze_all


class AnalysisPipeline(ABC):
    @abstractmethod
    def analyze(self, audio_path: str) -> RawAnalysis: ...


class ModalPipeline(AnalysisPipeline):
    def analyze(self, audio_path: str) -> RawAnalysis:
        audio_bytes = Path(audio_path).read_bytes()
        filename = Path(audio_path).name

        return cast(RawAnalysis, analyze_all.remote(audio_bytes, filename))
