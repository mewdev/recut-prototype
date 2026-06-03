# Analysis Pipeline Findings

Observations, failure modes, and proposed solutions from testing the ChordMini analysis stack.

---

## Stack

| Component | Tool |
|-----------|------|
| Beat tracking | madmom (RNNBeatProcessor + DBNBeatTrackingProcessor) |
| Chords | Chord-CNN-LSTM |
| Structure | SongFormer |

Models run independently and outputs are merged into a single JSON map.

---

## Finding 1: Segment boundaries don't land on downbeats

**Observed in:** `end_of_beginning.mp3` (testing/04), `billie_jean.mp3` (testing/03)

**Problem:** ChordMini's structure boundaries are typically 20–400ms offset from the nearest registered downbeat. When exporting segments, cuts land slightly before or after the true bar start — audible as a kick drum appearing at the end of the previous segment.

**Root cause:** Structure detection (SongFormer) and beat tracking (madmom) run independently with no shared state. Their outputs aren't guaranteed to align.

**Solution implemented:** `snap_to_downbeat()` in `map/make_map.py` — snaps each boundary to the first downbeat ≥ `(t - tolerance)`, with a `fallback_threshold` that falls back to the raw ChordMini value when no nearby downbeat exists.

```python
def snap_to_downbeat(t, downbeats, tolerance=0.4, fallback_threshold=0.5):
    for downbeat in downbeats:
        if downbeat >= t - tolerance:
            if abs(downbeat - t) <= fallback_threshold:
                return downbeat
            return t  # beat tracker has drifted — trust raw value
    return t
```

---

## Finding 2: Beat tracker drift after dynamic transitions

**Observed in:** `end_of_beginning.mp3` from ~88s onward

**Problem:** madmom's DBN beat tracker miscounted beats around a dynamic song transition (~88s), causing the downbeat grid to drift by ~1.5 bars for the remainder of the track. All segment boundaries after that point had no registered downbeat within 1.5s — the nearest candidates were always ~half a bar away on either side.

**Root cause:** DBN beat trackers can lose sync at sudden energy changes (e.g. verse→chorus transitions with strong transients). Once the grid drifts, it tends to stay drifted.

**Solution:** The `fallback_threshold` in `snap_to_downbeat` handles this — when no downbeat is within 0.5s, we fall back to ChordMini's raw boundary value, which is generally more reliable than snapping to a drifted grid.

**Longer-term:** A lightweight GUI correction tool (`overrides.json` per track) for cases where neither automatic strategy is reliable. See proposed architecture below.

---

## Proposed: Map correction GUI

**Purpose:** Let a user play each segment, confirm or drag boundaries, and save corrections. Not part of the core pipeline — a one-time QA step per track.

**Architecture:**
- Simple web app (HTML + WaveSurfer.js)
- Loads the audio file + current map JSON
- Renders waveform with draggable segment markers
- On save, writes `<track>-overrides.json` with only the corrected boundaries
- `make_map.py` merges overrides as a final post-processing step

**Why separate overrides file:**
- Keeps the automated pipeline output intact and reproducible
- Overrides are explicit, auditable, and can be version-controlled
- Re-running the pipeline doesn't wipe manual corrections

**Expected coverage:** Automated snapping gets ~60–70% of boundaries right. The GUI handles the remaining edge cases without blocking automation.

---

## General notes

- ChordMini gets segment *labels* (verse/chorus/bridge) right more often than boundaries
- Boundary accuracy degrades on songs with unusual structure or sudden energy shifts
- Bar count per segment is a reliable sanity check — if bars don't match expected song structure, the boundary is likely wrong
