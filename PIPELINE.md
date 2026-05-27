# Recut Analysis & Edit Pipeline

## Analysis Stack (3 layers)

```
Audio file
    │
    ├── allin1 (Replicate: sakemin/all-in-one-music-structure-analyzer)
    │       beats, downbeats, beat_positions, segments (intro/verse/chorus/...)
    │
    ├── h1zero (HuggingFace: Izreals/h1zero-chord-detection)
    │       chords[], key, scale, roman_numerals, genre, tempo
    │
    └── MIDI transcription (Basic Pitch — pip install basic-pitch)
            note-level: pitch, onset, offset, velocity per frame
            → tonal zone detection (chromatic notes reveal modulations)
            → bass note tracking
            → note density per section
```

Merged into one JSON: `*-full.json`
- Every downbeat annotated with: chord, roman numeral, MIDI pitches, bass note, tonal zone
- Every segment annotated with: chord_at_start, chord_at_end, predominant_chord, tonal_zone, note_density
- Cadence map: authentic (V→I), plagal (IV→I), half (→V) — phrase endpoints and re-entry points
- Modulation map: timestamps where tonal center changes (detected via chromatic MIDI notes)


## Cut Primitives

### 1. hard_cut
```python
ffmpeg atrim(start, end) → wav segment
```
Use when: cut point is a perfect phrase boundary with harmonic match.

### 2. xfade_join (equal-power, decay-offset)
```python
# Extend section A by xfade_ms into its decay zone past the downbeat
# B's downbeat lands exactly at the junction — timing preserved
ramp_out = sqrt(linspace(1→0, xfade_samples))
ramp_out = sqrt(linspace(0→1, xfade_samples))
A[-xfade:] = A[-xfade:] * ramp_out + B[:xfade] * ramp_in
output = A + B[xfade:]
```
Use when: phrase/chord match is good but raw cut has click/pop.
Typical values: 40–120ms. Equal-power prevents 3dB dip on sustained notes.

### 3. (planned) energy_dip_xfade
Find minimum RMS within ±300ms of cut point → place xfade there.
Use when: no natural decay after downbeat (percussive, staccato material).

### 4. (planned) musicgen_bridge
Generate 2–4s transition via MusicGen conditioned on surrounding audio.
Use when: tonal zones are incompatible and no clean cut point exists.


## Cut Decision Logic

```
For each proposed cut point (src_end → dst_start):

1. TONAL ZONE CHECK (MIDI)
   same_zone = tonal_zone(src_end) == tonal_zone(dst_start)
   if not same_zone → flag as high-risk, consider different dst or musicgen_bridge

2. HARMONIC CHECK (h1zero)
   chord_src = chord_at(src_end)
   chord_dst = chord_at(dst_start)
   compatible = jaccard(pitches_src, pitches_dst) > 0.5
              OR cadence_type(chord_src → chord_dst) in (authentic, deceptive, plagal)
   if not compatible → find nearest compatible downbeat in dst section

3. PHRASE CHECK (allin1 + cadence map)
   is_phrase_start = dst_start is after an authentic/plagal cadence
   if not phrase_start → shift dst_start to next cadence resolution

4. CUT TYPE SELECTION
   if all checks pass + notes have natural decay at src_end → hard_cut
   if checks pass but no decay → xfade_join(40–80ms)
   if tonal match but phrase mismatch → xfade_join(120ms) + log warning
   if tonal mismatch → musicgen_bridge or reject
```


## What MIDI Adds Over Chord Detection

| Feature | h1zero alone | + MIDI |
|---|---|---|
| Chord at timestamp | ✓ | ✓ |
| Key / scale | ✓ (global) | ✓ (per section) |
| Modulation detection | ✗ | ✓ (chromatic notes) |
| Bass note | ✗ | ✓ |
| Note density | ✗ | ✓ |
| Pitch-level phrase shape | ✗ | ✓ |
| Exact harmonic content | estimated | ground truth |

Critical case: "Building A Family" — h1zero reported single key (A major) throughout.
MIDI revealed D# appearing at 54.81s → piece modulated to E/B major at that point.
Without MIDI, every extension attempt crossed the modulation boundary (harsh cut).


## To Add: Basic Pitch to Pipeline

```bash
pip install basic-pitch
```

```python
from basic_pitch.inference import predict
from basic_pitch import ICASSP_2022_MODEL_PATH

model_output, midi_data, note_events = predict("audio.mp3", ICASSP_2022_MODEL_PATH)
midi_data.write("transcription.mid")
# note_events: [{start_time, end_time, pitch_midi, velocity, pitch_bend}]
```

Replaces need for ChordMiniApp / SheetSage (which requires torch==1.4.0, complex Docker setup).
Basic Pitch: pip install, runs on CPU, ~30s for a 2min track.


## Files

```
recut-prototype/
├── replicate-prediction-*.json          allin1 output (Billie Jean)
├── modern-classic/
│   ├── modern-classic.json              allin1 output
│   ├── h1zero-chords.json               h1zero output
│   ├── modern-classic-full.json         merged analysis (beats+chords+MIDI+cadences)
│   ├── midi-transcription.mid           MIDI from ChordMiniApp/SheetSage
│   ├── midi-transcription-simplified.mid
│   ├── merge_analysis.py                allin1 + h1zero + MIDI → full JSON
│   └── make_extended_xfade.py           edit script with xfade primitives
├── h1zero-chord-detection/              cloned HF space (local Docker)
│   └── HOWTO.md
└── make_stem_remix.py                   stem-level edit primitives (Billie Jean)
```
