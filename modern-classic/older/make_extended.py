#!/usr/bin/env python3
"""
Extends "Building A Family" from ~1:57 to ~2:55 (cca 3 min).
Uses downbeats from modern-classic.json for bar-accurate cuts.

Structure (sonata-like recapitulation):
  0→81.7       Exposition: all intros + inst as original
  24.17→68.24  Recapitulation: 2nd+3rd intro theme returns
  68.24→81.7   Inst: final statement
  81.7→117.4   Coda: outro + end

All cut points verified against downbeats[]:
  24.17 = db[11]  (start of 2nd intro)
  68.24 = db[34]  (start of inst)
  81.7  = db[41]  (start of outro)
"""

import json, subprocess, os

JSON   = "modern-classic.json"
SRC    = "Building A Family (1).mp3"
OUT    = "Building A Family - extended.mp3"

with open(JSON) as f:
    data = json.load(f)

db = data["downbeats"]

# Verify our key timestamps exist in downbeats
key_ts = {24.17: 11, 68.24: 34, 81.7: 41}
for ts, idx in key_ts.items():
    assert abs(db[idx] - ts) < 0.05, f"Mismatch at db[{idx}]: {db[idx]} != {ts}"

edit = [
    # Original play-through
    (0,     81.7,  "original-open-to-inst"),
    # Recapitulation (extension in second part, after 1:15)
    (24.17, 68.24, "recap-2nd-3rd-intro"),
    (68.24, 81.7,  "inst-final-statement"),
    # Coda
    (81.7,  117.4, "coda-outro-end"),
]

total = sum(e - s for s, e, _ in edit)
print(f"Total duration: {total:.1f}s = {int(total//60)}:{int(total%60):02d}")
print()

tmp_files = []
for i, (start, end, label) in enumerate(edit):
    tmp = f"/tmp/ext_s{i:02d}_{label}.wav"
    tmp_files.append(tmp)
    cmd = [
        "ffmpeg", "-y", "-i", SRC,
        "-filter_complex",
        f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[out]",
        "-map", "[out]", tmp
    ]
    print(f"  [{i+1}/{len(edit)}] {label}  ({start:.2f}→{end:.2f}s)")
    subprocess.run(cmd, check=True, capture_output=True)

# Concatenate
concat = "/tmp/ext_concat.txt"
with open(concat, "w") as f:
    for t in tmp_files:
        f.write(f"file '{t}'\n")

print(f"\nMerging → {OUT}")
subprocess.run([
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0", "-i", concat,
    "-ar", "44100", "-ac", "2",
    "-codec:a", "libmp3lame", "-q:a", "2",
    OUT
], check=True, capture_output=True)

size = os.path.getsize(OUT) / 1_048_576
print(f"Done: {OUT}  ({total:.0f}s / {size:.1f} MB)")
print()
print("⚠ Listen carefully at these cut joints for tonal clashes:")
print(f"  81.7s  → 24.17s  (inst end → 2nd intro start)")
print(f"  68.24s → 81.7s   (3rd intro end → inst start, same as original — should be clean)")
print(f"  81.7s  → outro   (inst end → outro start, same as original — should be clean)")
print()
print("If the first joint (81.7→24.17) sounds harsh, harmony analysis")
print("(chords/key at those moments) would be needed for a smoother edit.")
