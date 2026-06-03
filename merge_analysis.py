#!/usr/bin/env python3
"""
Full analysis pipeline: MP3 + allin1 JSON + h1zero JSON -> *-full.json

Usage:
    python merge_analysis.py <audio.mp3> <allin1.json> <h1zero.json>
"""

import sys, json, pathlib, warnings
import numpy as np
from collections import Counter

warnings.filterwarnings("ignore")

if len(sys.argv) < 4:
    print("Usage: merge_analysis.py <audio.mp3> <allin1.json> <h1zero.json>")
    sys.exit(1)

AUDIO  = pathlib.Path(sys.argv[1])
ALLIN1 = pathlib.Path(sys.argv[2])
H1ZERO = pathlib.Path(sys.argv[3])

MIDI_CACHE = AUDIO.with_suffix(".midi-basicpitch.mid")
OUT        = AUDIO.with_suffix("").name + "-full.json"

NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
def pc(p):   return NOTE_NAMES[p % 12]
def name(p): return NOTE_NAMES[p % 12] + str(p // 12 - 1)

# Step 1: Basic Pitch
if not MIDI_CACHE.exists():
    print(f"Running Basic Pitch on {AUDIO.name}...")
    bp_model = pathlib.Path(__import__('basic_pitch').__file__).parent / \
               "saved_models/icassp_2022/nmp.onnx"
    from basic_pitch.inference import predict
    _, midi_data, _ = predict(
        str(AUDIO),
        model_or_model_path=bp_model,
        minimum_note_length=180,
        onset_threshold=0.5,
        frame_threshold=0.3,
        midi_tempo=120,
    )
    midi_data.write(str(MIDI_CACHE))
    print(f"  -> {MIDI_CACHE.name}")
else:
    print(f"Using cached MIDI: {MIDI_CACHE.name}")

# Step 2: Parse MIDI
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
print(f"MIDI: {len(notes)} notes, {notes[0]['start']:.2f}s - {notes[-1]['end']:.2f}s")

# Step 3: Load allin1 + h1zero
with open(ALLIN1) as f: allin1 = json.load(f)
with open(H1ZERO) as f: h1     = json.load(f)

db     = allin1["downbeats"]
chords = h1["chords"]

# Step 4: Helpers
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

# Step 5: Tonal zone detection
MODULATION_THRESHOLD = 2
zone_labels, current_zone, count = [], "zone_1", 0
for i, beat in enumerate(db):
    end = db[i+1] if i+1 < len(db) else beat + 1.95
    pcs = set(pcs_in(beat, end))
    has_chromatic = bool(pcs & {"D#", "G#"})
    if has_chromatic:
        count += 1
    else:
        count = 0
    if count >= MODULATION_THRESHOLD and current_zone == "zone_1":
        current_zone = "zone_2"
    zone_labels.append(current_zone)

modulation_time = None
for i, z in enumerate(zone_labels):
    if z == "zone_2":
        modulation_time = round(db[i], 3)
        break

print(f"Tonal zones: zone_1 until {modulation_time}s -> zone_2")

# Step 6: Enriched downbeats
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

# Step 7: Enriched segments
def predominant(notes_list):
    c = Counter(n["pc"] for n in notes_list)
    return c.most_common(1)[0][0] if c else None

enriched_segments = []
for seg in allin1["segments"]:
    s, e = seg["start"], seg["end"]
    in_seg   = [n for n in notes if n["start"] >= s and n["start"] < e]
    c_start  = chord_at(s)
    c_end    = chord_at(max(s, e - 0.1))
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

# Step 8: Cadence map
cadences = []
for i in range(len(chords) - 1):
    curr, nxt = chords[i]["chord"], chords[i+1]["chord"]
    t = chords[i+1]["time"]
    if curr in ("E","E7") and nxt in ("A","Amaj7"):
        cadences.append({"time": t, "type": "authentic", "from": curr, "to": nxt,
                         "note": "phrase end - strong cut point"})
    elif curr == "D" and nxt == "A":
        cadences.append({"time": t, "type": "plagal",    "from": curr, "to": nxt,
                         "note": "phrase end - soft cut point"})
    elif nxt in ("E","E7") and curr not in ("E","E7"):
        cadences.append({"time": t, "type": "half",      "from": curr, "to": nxt,
                         "note": "tension - good re-entry, avoid as exit"})

# Step 9: Assemble + write
merged = {
    "path":         str(AUDIO),
    "bpm":          allin1["bpm"],
    "bpm_h1zero":   round(h1["tempo"], 2),
    "time_signature": h1["time_signature"],
    "key":          h1["key"],
    "scale":        h1["scale"],
    "tonal_zones": {
        "zone_1": {"start": 0, "end": modulation_time},
        "zone_2": {"start": modulation_time, "end": None},
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
        "structure":  "sakemin/all-in-one-music-structure-analyzer",
        "harmony":    "Izreals/h1zero-chord-detection",
        "midi":       f"Basic Pitch ONNX - {MIDI_CACHE.name}",
    }
}

out_path = AUDIO.parent / OUT
with open(out_path, "w") as f:
    json.dump(merged, f, indent=2)

print(f"\n✓ {out_path}")
print(f"  beats: {len(merged['beats'])}  downbeats: {len(merged['downbeats'])}  "
      f"segments: {len(merged['segments'])}  chords: {len(merged['chords'])}  "
      f"cadences: {len(merged['cadences'])}  midi_notes: {len(merged['midi_notes'])}")
print(f"  modulation at {modulation_time}s")
print()
print("SEGMENTS:")
for s in merged["segments"]:
    print(f"  [{s['label']:6}] {s['start']:6.2f}-{s['end']:6.2f}s  "
          f"zone={s['tonal_zone']:8}  "
          f"chord_start={s['chord_at_start'] or '?':6}  "
          f"chord_end={s['chord_at_end'] or '?':6}  "
          f"notes={s['midi_note_count']:3}")
