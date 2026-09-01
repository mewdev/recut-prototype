import numpy as np

from recut.audio import Audio
from recut.compositor.effects import Reverb, ReverbSweep
from recut.compositor.nodes import Clip, Node, XFade
from recut.map.parser import bars_to_seconds, beats_to_seconds, get_segment
from recut.map.schema import MusicMap
from recut.primitives.curves import make_envelope
from recut.primitives.cut import cut
from recut.primitives.reverb import PRESETS as REVERB_PRESETS
from recut.primitives.xfade import xfade

# Re-export so existing callers (`from recut.compositor import Clip, XFade`) keep working
__all__ = ["Clip", "XFade", "Node", "compose"]


_TAIL_TAPER_MS = 20  # short fade into the padding — real audio essentially never
# ends at zero amplitude, so appending silence directly is a hard discontinuity
# (a click) at the seam, before the filters/reverb even run.


def _reverb_tail_padding(clip: Audio, reverb_fx: Reverb | ReverbSweep) -> Audio:
    """Append trailing silence so Reverb (a single-pass pedalboard call that
    returns exactly as many samples as it's given, no automatic tail
    extension) has room to decay into instead of being truncated at the
    clip boundary.
    # ponytail: room_size-scaled heuristic, not a real RT60 estimate —
    # pedalboard.Reverb exposes no decay-time param to derive one from.
    # Widen the multiplier here if a reverb tail still audibly truncates.
    """
    room_size = (
        reverb_fx.room_size
        if reverb_fx.room_size is not None
        else REVERB_PRESETS[reverb_fx.reverb_type]["room_size"]
    )
    tail_seconds = 1.5 + 2.5 * room_size
    pad_samples = int(tail_seconds * clip.sr)
    silence = np.zeros(clip.samples.shape[:-1] + (pad_samples,), dtype=clip.samples.dtype)

    taper_samples = min(int(_TAIL_TAPER_MS / 1000 * clip.sr), clip.samples.shape[-1])
    taper_env = make_envelope(1.0, 0.0, taper_samples, "qsin")
    tapered = clip.samples.copy()
    tapered[..., -taper_samples:] *= taper_env

    return Audio(np.concatenate([tapered, silence], axis=-1), clip.sr)


def compose(music_map: MusicMap, audio: Audio, *nodes: Node) -> Audio:
    """
    Execute a sequence of edit nodes against an audio file.

    Validate before calling if needed:
        results = validate(music_map, *nodes)

    Example:
        compose(music_map, audio, Clip("verse"), Clip("chorus", loop=2))
    """
    composition = []
    pending_xfade = None  # set when an XFade node is encountered, consumed on next clip

    for i, node in enumerate(nodes):
        if isinstance(node, XFade):
            if pending_xfade is not None:
                raise ValueError("Two XFades cannot be next to each other")
            pending_xfade = node
            continue

        segment = get_segment(music_map, node.segment_name, node.index)

        if node.snap_to_downbeat and segment.downbeats:
            start = segment.downbeats[0]
            end = segment.downbeats[-1]
            # NOTE: downbeats[-1] is the start of the segment's last bar, not
            # segment.end — see the CAUTION in Clip.snap_to_downbeat's docstring.
        else:
            start = segment.start
            end = segment.end

        if node.offset_bars is not None:
            start += bars_to_seconds(music_map, node.offset_bars)
        elif node.offset_beats is not None:
            start += beats_to_seconds(music_map, node.offset_beats)

        if node.bars is not None:
            end = start + bars_to_seconds(music_map, node.bars)
            if end > segment.end:
                raise ValueError(
                    f"{node.bars} bars exceeds segment length for {node.segment_name!r}"
                )
        elif node.beats is not None:
            end = start + beats_to_seconds(music_map, node.beats)
            if end > segment.end:
                raise ValueError(
                    f"{node.beats} beats exceeds segment length for {node.segment_name!r}"
                )

        clip = cut(start, end)(audio)

        if node.loop is not None:
            clip = Audio(np.concatenate([clip.samples] * node.loop, axis=-1), audio.sr)

        if i == len(nodes) - 1:
            reverb_fx = next((e for e in node.fx if isinstance(e, (Reverb, ReverbSweep))), None)
            if reverb_fx is not None:
                clip = _reverb_tail_padding(clip, reverb_fx)

        for effect in node.fx:
            clip = effect.to_fn()(clip)

        if pending_xfade is not None:
            if not composition:
                raise ValueError("XFade cannot be first node — nothing to crossfade into")
            prev = composition.pop()
            ms = (
                beats_to_seconds(music_map, pending_xfade.beats) * 1000
                if pending_xfade.beats is not None
                else pending_xfade.ms
            )
            clip = xfade(ms, pending_xfade.curve)(prev, clip)
            pending_xfade = None

        composition.append(clip)

    if pending_xfade is not None:
        raise ValueError("XFade cannot be last node — nothing to crossfade into")

    return Audio(np.concatenate([a.samples for a in composition], axis=-1), audio.sr)
