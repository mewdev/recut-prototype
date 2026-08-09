from pedalboard import Delay, Pedalboard  # type: ignore

from audio import Audio


def delay(
    delay_seconds: float = 0.5,  # echo time in seconds
    feedback: float = 0.0,       # 0.0 = one echo, 1.0 = infinite repeats
    mix: float = 0.5,            # dry/wet mix (0 = dry only, 1 = wet only)
):
    def apply(audio: Audio) -> Audio:
        board = Pedalboard([Delay(delay_seconds = delay_seconds, feedback = feedback, mix = mix)])
        out = board(audio.samples.astype("float32"), audio.sr)
        return Audio(out, audio.sr)
    
    return apply
