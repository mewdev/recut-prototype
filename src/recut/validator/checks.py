from typing import Optional

from recut.compositor.nodes import AudioNode, XFade
from recut.map.parser import (
    bars_to_seconds,
    beats_to_seconds,
    first_segment,
    get_segment,
    last_segment,
)
from recut.map.schema import MusicMap
from recut.validator.types import ValidationResult


def check_label_exists(node: AudioNode, music_map: MusicMap) -> Optional[ValidationResult]:
    try:
        get_segment(music_map, node.segment_name, node.index)
    except ValueError as error:
        return ValidationResult(severity="error", message=str(error), node=node)
    return None


def check_duration_exceeds(node: AudioNode, music_map: MusicMap) -> Optional[ValidationResult]:
    try:
        segment = get_segment(music_map, node.segment_name, node.index)
    except ValueError:
        return None

    # Mirror compose()'s resolution order: offset shifts the effective start
    # before bars/beats measures a length from it — checking against
    # segment.start alone (ignoring offset_bars/offset_beats) misses overflows
    # that only happen because of the offset.
    start = segment.start
    if node.offset_bars is not None:
        start += bars_to_seconds(music_map, node.offset_bars)
    elif node.offset_beats is not None:
        start += beats_to_seconds(music_map, node.offset_beats)

    if node.bars is not None:
        requested_s = bars_to_seconds(music_map, node.bars)
        segment_duration_s = segment.end - segment.start
        if start + requested_s > segment.end:
            return ValidationResult(
                severity="error",
                message=f"{node.bars} bars ({requested_s:.2f}s) from offset exceeds '{node.segment_name}' segment duration ({segment_duration_s:.2f}s)",
                node=node,
            )
    elif node.beats is not None:
        requested_s = beats_to_seconds(music_map, node.beats)
        segment_duration_s = segment.end - segment.start
        if start + requested_s > segment.end:
            return ValidationResult(
                severity="error",
                message=f"{node.beats} beats ({requested_s:.2f}s) from offset exceeds '{node.segment_name}' segment duration ({segment_duration_s:.2f}s)",
                node=node,
            )
    return None


def check_sequence_boundaries(nodes: list[AudioNode], music_map: MusicMap) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    first_song_seg = first_segment(music_map)
    last_song_seg = last_segment(music_map)

    audio_nodes = [node for node in nodes if not isinstance(node, XFade)]
    if not audio_nodes:
        return []

    first_node = audio_nodes[0]

    try:
        seg = get_segment(music_map, first_node.segment_name, first_node.index)
        # Any fx on the boundary clip means the user already applied something to
        # smooth the entry (fade-in, reverb, filter sweep, ...) — this check can't
        # judge whether it's musically the *right* choice, so it doesn't second-guess
        # a deliberate effect, only a bare hard cut.
        if abs(seg.start - first_song_seg.start) > 0.1 and not first_node.fx:
            results.append(
                ValidationResult(
                    severity="warning",
                    message=(
                        f"Cut starts at {first_node.segment_name!r} (t={seg.start:.2f}s) "
                        f"but song begins at {first_song_seg.segment_name!r} (t={first_song_seg.start:.2f}s). "
                        "Hard cut at start will sound abrupt — apply an effect (e.g. fade-in, reverb tail) to smooth the entry."
                    ),
                    node=first_node,
                )
            )
    except ValueError:
        pass
    last_node = audio_nodes[-1]
    try:
        seg = get_segment(music_map, last_node.segment_name, last_node.index)
        if abs(seg.end - last_song_seg.end) > 0.1 and not last_node.fx:
            results.append(
                ValidationResult(
                    severity="warning",
                    message=(
                        f"Cut ends at {last_node.segment_name!r} (t={seg.end:.2f}s) "
                        f"but song ends at {last_song_seg.segment_name!r} (t={last_song_seg.end:.2f}s). "
                        "Hard cut at end will sound abrupt — apply an effect (e.g. fade-out, reverb tail) to smooth the exit."
                    ),
                    node=last_node,
                )
            )
    except ValueError:
        pass
    return results
