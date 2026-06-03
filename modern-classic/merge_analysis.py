#!/usr/bin/env python3
"""
Full analysis pipeline: MP3 + allin1 JSON + h1zero JSON → *-full.json

Usage:
    python merge_analysis.py <audio.mp3> <allin1.json> <h1zero.json>

Defaults to Building A Family files if no args given.

Steps:
    1. Run Basic Pitch on the audio (if MIDI not already cached)
    2. Parse MIDI notes → pitch classes per downbeat
    3. Detect tonal zones via chromatic notes (e.g. D# signals modulation)
    4. Merge allin1 (structure) + h1zero (chords) + MIDI (notes)
    5. Enrich segments with chord + MIDI data
    6. Build cadence map (natural cut/re-entry points)
    7. Write *-full.json
"""

import sys, json, pathlib, warnings
import numpy as np
from collections import Counter

warnings.filterwarnings("ignore")

# ── Args ──────────────────────────────────────────────────────────────────────
if len(sys.argv) == 4:
    AUDIO   = pathlib.Path(sys.argv[1])
    ALLIN1  = pathlib.Path(sys.argv[2])
    H1ZERO  = pathlib.Path(sys.argv[3])
else:
    AUDIO  = pathlib.Path("Building A Family (1).mp3")
    ALLIN1 = pathlib.Path("modern-classic.json")
    H1ZERO = pathlib.Path("h1zero-chords.json")

MIDI_CACHE = AUDIO.with_suffix(".midi-basicpitch.mid")
OUT        = AUDIO.with_suffix("").name + "-full.json"

NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
NOTE_TO_PC = {n: i for i, n in enumerate(NOTE_NAMES)}
MAJOR_INTERVALS = [0, 2, 4, 5, 7, 9, 11]
MINOR_INTERVALS = [0, 2, 3, 5, 7, 8, 10]
def pc(p):   return NOTE_NAMES[p % 12]
def name(p): return NOTE_NAMES[p % 12] + str(p // 12 - 1)

# ── Step 1: Basic Pitch ───────────────────────────────────────────────────────
if not MIDI_CACHE.exists():
    print(f"Running Basic Pitch on {AUDIO.name}...")
    import pathlib as _pl
    bp_model = _pl.Path(__import__('basic_pitch').__file__).parent / \
               "saved_models/icassp_2022/nmp.onnx"
    from basic_pitch.inference import predict
    _, midi_data, _ = predict(
        str(AUDIO),
        model_or_model_path=bp_model,
        minimum_note_length=180,   # ms — filters passing tones, closer to ChordMini simplified
        onset_threshold=0.5,
        frame_threshold=0.3,
        midi_tempo=120,
    )
    midi_data.write(str(MIDI_CACHE))
    print(f"  → {MIDI_CACHE.name}")
else:
    print(f"Using cached MIDI: {MIDI_CACHE.name}")

# ── Step 2: Parse MIDI ────────────────────────────────────────────────────────
import mido

def midi_to_notes(path):
    mid = mido.MidiFile(str(path))
    tempo = 500000
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo": tempo = msg.tempo; break
    tick = tempo / mid.ticks_per_beat / 1_000_000
    notes, active, t = [], {}, 0.0
    for msg in mid.tracks[-1]:
        t += msg.time * tick
        if msg.type == "note_on" and msg.velocity > 0:
            active[msg.note] = (t, msg.velocity)
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            if msg.note in active:
                s, v = active.pop(msg.note)
                notes.append({
                    "pitch": msg.note, "name": name(msg.note), "pc": pc(msg.note),
                    "start": round(s, 3), "end": round(t, 3), "velocity": v,
                })
    return sorted(notes, key=lambda n: n["start"])

notes = midi_to_notes(MIDI_CACHE)
print(f"MIDI: {len(notes)} notes, {notes[0]['start']:.2f}s – {notes[-1]['end']:.2f}s")

# ── Step 3: Load allin1 + h1zero ──────────────────────────────────────────────
with open(ALLIN1) as f: allin1 = json.load(f)
with open(H1ZERO) as f: h1     = json.load(f)

db     = allin1["downbeats"]
chords = h1["chords"]

# ── Step 4: Helpers ───────────────────────────────────────────────────────────
def chord_at(t):
    result = None
    for c in chords:
        if c["time"] <= t + 0.05: result = c
        else: break
    return result

def pcs_in(t, end, min_velocity=10):
    seen, out = set(), []
    for n in notes:
        if n["start"] < end and n["end"] > t and n["velocity"] >= min_velocity:
            if n["pc"] not in seen:
                seen.add(n["pc"]); out.append(n["pc"])
    return out

def bass_at(t, end):
    active = [n for n in notes if n["start"] < end and n["end"] > t]
    return min(active, key=lambda n: n["pitch"])["pc"] if active else None

# ── Step 5: Tonal zone detection ──────────────────────────────────────────────
MODULATION_THRESHOLD = 2              # bars in a row with chromatic notes = new zone

root_pc    = NOTE_TO_PC[h1["key"]]
intervals  = MAJOR_INTERVALS if h1["scale"] == "major" else MINOR_INTERVALS
diatonic_pcs     = {(root_pc + i) % 12 for i in intervals}
chromatic_notes  = {NOTE_NAMES[i] for i in range(12) if i not in diatonic_pcs}
zone_label_1     = f"{h1['key']}_{h1['scale']}"
zone_label_2     = "modulation"

zone_labels, current_zone, count = [], zone_label_1, 0
for i, beat in enumerate(db):
    end = db[i+1] if i+1 < len(db) else beat + 1.95
    pcs = set(pcs_in(beat, end))
    has_chromatic = bool(pcs & chromatic_notes)
    if has_chromatic:
        count += 1
    else:
        count = 0
    if count >= MODULATION_THRESHOLD and current_zone == zone_label_1:
        current_zone = zone_label_2
    zone_labels.append(current_zone)

modulation_time = None
for i, z in enumerate(zone_labels):
    if z == zone_label_2:
        modulation_time = round(db[i], 3)
        break

print(f"Tonal zones: {zone_label_1} until {modulation_time}s → modulation")

# ── Step 6: Enriched downbeats ────────────────────────────────────────────────
downbeats_with_chords = []
for i, (beat, zone) in enumerate(zip(db, zone_labels)):
    end = db[i+1] if i+1 < len(db) else beat + 1.95
    c   = chord_at(beat)
    downbeats_with_chords.append({
        "time":        round(beat, 3),
        "chord":       c["chord"]  if c else None,
        "roman":       c.get("roman", "") if c else None,
        "tonal_zone":  zone,
        "midi_pitches": pcs_in(beat, end),
        "bass_note":   bass_at(beat, end),
    })

# ── Step 7: Enriched segments ─────────────────────────────────────────────────
def predominant(notes_list):
    c = Counter(n["pc"] for n in notes_list)
    return c.most_common(1)[0][0] if c else None

enriched_segments = []
for seg in allin1["segments"]:
    s, e = seg["start"], seg["end"]
    in_seg   = [n for n in notes if n["start"] >= s and n["start"] < e]
    c_start  = chord_at(s)
    c_end    = chord_at(max(s, e - 0.1))
    # tonal zone = zone of first downbeat in segment
    seg_zones = [z for b, z in zip(db, zone_labels) if s <= b < e]
    seg_zone  = seg_zones[0] if seg_zones else "unknown"

    enriched_segments.append({
        **seg,
        "chord_at_start":    c_start["chord"] if c_start else None,
        "chord_at_end":      c_end["chord"]   if c_end   else None,
        "tonal_zone":        seg_zone,
        "midi_pitch_classes": list(dict.fromkeys(n["pc"] for n in in_seg)),
        "midi_note_count":   len(in_seg),
        "predominant_midi_pc": predominant(in_seg),
        "chords_in_segment": [
            {"time": c["time"], "chord": c["chord"],
             "roman": c.get("roman",""), "confidence": round(c["confidence"],3)}
            for c in chords if s <= c["time"] < e
        ],
    })

# ── Step 8: Cadence map ───────────────────────────────────────────────────────
degree_1 = NOTE_NAMES[root_pc]
degree_4 = NOTE_NAMES[(root_pc + 5) % 12]
degree_5 = NOTE_NAMES[(root_pc + 7) % 12]

if h1["scale"] == "major":
    tonic_chords      = {degree_1, degree_1 + "maj7"}
    subdominant_chords = {degree_4, degree_4 + "maj7"}
    dominant_chords   = {degree_5, degree_5 + "7"}
else:  # minor — V is major (harmonic minor)
    tonic_chords      = {degree_1 + "m", degree_1 + "m7"}
    subdominant_chords = {degree_4 + "m", degree_4 + "m7"}
    dominant_chords   = {degree_5, degree_5 + "7"}

cadences = []
for i in range(len(chords) - 1):
    curr, nxt = chords[i]["chord"], chords[i+1]["chord"]
    t = chords[i+1]["time"]
    if curr in dominant_chords and nxt in tonic_chords:
        cadences.append({"time": t, "type": "authentic", "from": curr, "to": nxt,
                         "note": "phrase end — strong cut point"})
    elif curr in subdominant_chords and nxt in tonic_chords:
        cadences.append({"time": t, "type": "plagal",    "from": curr, "to": nxt,
                         "note": "phrase end — soft cut point"})
    elif nxt in dominant_chords and curr not in dominant_chords:
        cadences.append({"time": t, "type": "half",      "from": curr, "to": nxt,
                         "note": "tension — good re-entry, avoid as exit"})

# ── Step 9: Assemble + write ──────────────────────────────────────────────────
merged = {
    "path":         str(AUDIO),
    "bpm":          allin1["bpm"],
    "bpm_h1zero":   round(h1["tempo"], 2),
    "time_signature": h1["time_signature"],
    "key":          h1["key"],
    "scale":        h1["scale"],
    "tonal_zones": {
        "zone_1": {"label": zone_label_1, "start": 0, "end": modulation_time},
        "zone_2": {"label": zone_label_2, "start": modulation_time, "end": None},
    },
    "modulation_time": modulation_time,
    "unique_chords":   h1["unique_chords"],
    "genre":           h1.get("genre"),
    "beats":           allin1["beats"],
    "downbeats":       allin1["downbeats"],
    "beat_positions":  allin1["beat_positions"],
    "downbeats_with_chords": downbeats_with_chords,
    "segments":        enriched_segments,
    "chords":          chords,
    "cadences":        cadences,
    "midi_notes":      notes,
    "_sources": {
        "structure":  "sakemin/all-in-one-music-structure-analyzer (Replicate)",
        "harmony":    "Izreals/h1zero-chord-detection (HuggingFace Space)",
        "midi":       f"Basic Pitch ONNX — {MIDI_CACHE.name}",
    }
}

with open(OUT, "w") as f:
    json.dump(merged, f, indent=2)

print(f"\n✓ {OUT}")
print(f"  beats: {len(merged['beats'])}  downbeats: {len(merged['downbeats'])}  "
      f"segments: {len(merged['segments'])}  chords: {len(merged['chords'])}  "
      f"cadences: {len(merged['cadences'])}  midi_notes: {len(merged['midi_notes'])}")
print(f"  modulation: A major → E/B major at {modulation_time}s")
print()
print("SEGMENTS:")
for s in merged["segments"]:
    print(f"  [{s['label']:6}] {s['start']:6.2f}–{s['end']:6.2f}s  "
          f"zone={s['tonal_zone']:10}  "
          f"chord_start={s['chord_at_start'] or '?':6}  "
          f"chord_end={s['chord_at_end'] or '?':6}  "
          f"notes={s['midi_note_count']:3}")
