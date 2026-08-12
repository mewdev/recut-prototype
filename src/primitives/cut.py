from audio import Audio


def cut(start: float, end: float):
    def apply(audio: Audio) -> Audio:
        s = int(round(start * audio.sr))
        e = int(round(end * audio.sr))
        return audio.apply_to_channels(lambda ch: ch[s:e])

    return apply
