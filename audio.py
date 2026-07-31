#TODO: make sure you understand this code more in depth (classes, self...)

import numpy as np
from librosa import load

class Audio:
    def __init__(self, samples: np.ndarray, sr:int) -> None:
        self.samples = samples
        self.sr = sr

    @property
    def is_mono(self) -> bool:
        return self.samples.ndim == 1

    @property
    def num_samples(self) -> int:
        return self.samples.shape[-1]

    def apply_to_channels(self, fn) -> "Audio":
        if self.is_mono:
            return Audio(fn(self.samples), self.sr)

        return Audio(np.stack([fn(self.samples[i]) for i in range(self.samples.shape[0])]), self.sr)

    @classmethod
    def load(cls, path:str) -> "Audio":
        samples, sr = load(path, sr=None, mono=False)
        return cls(samples, int(sr))