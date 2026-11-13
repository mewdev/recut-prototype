import numpy as np

from recut.map.make_map import build_segment


def test_last_segment_runs_to_end_of_audio():
    sr = 100
    audio = np.zeros(10 * sr, dtype=np.float32)  # 10s
    downbeats = [0.0, 2.0, 4.0]
    seg = {"start": 8.5, "end": 10.0, "label": "silence"}

    snapped = build_segment(seg, 0, downbeats, [], [], audio, sr)
    last = build_segment(seg, 0, downbeats, [], [], audio, sr, is_last=True)

    assert snapped.duration == 0.0
    assert last.start == 4.0
    assert last.end == 10.0
