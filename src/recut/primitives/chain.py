from recut.audio import Audio


def chain(audio: Audio, *transforms) -> Audio:
    for transform in transforms:
        audio = transform(audio)
        if not isinstance(audio, Audio):
            raise TypeError(f"transform {transform} returned {type(audio)}, expected Audio")
    return audio
