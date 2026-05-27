#!/usr/bin/env python3
"""
stem-remix_negative_space.mp3
Uses downbeats from replicate JSON for bar-precise stem switching.
"""

import json
import subprocess
import os
import tempfile

JSON_PATH = "replicate-prediction-z8df0cxpw1rne0cybyv903k14w.json"
STEMS = {
    "D": "stems_v0/HT-demucs_drums_1779736462042.wav",
    "B": "stems_v0/HT-demucs_bass_1779736462042.wav",
    "O": "stems_v0/HT-demucs_other_1779736462042.wav",
    "V": "stems_v0/HT-demucs_vocals_1779736462042.wav",
}
OUT = "stem-remix_negative_space.mp3"

with open(JSON_PATH) as f:
    data = json.load(f)

db = data["downbeats"]  # db[i] = start time of bar i+1

# ── Edit plan ─────────────────────────────────────────────────────────────────
# Each entry: (start, end, [stem_keys], label)
# All start/end times come from downbeats[] or segment boundaries in the JSON.
#
# INTRO  (segment 0.24–29.0)
#   bars  1-4  (db[0]-db[4]):   B+O     — no drums, inverts expectation
#   bars  5-8  (db[4]-db[8]):   D+B+O+V — drums smash in as early drop
#   bars  9-14 (db[8]-db[14]):  D+B     — strip to pulse, pre-verse tension
#
# VERSE 1 (segment 29.0–53.63)
#   bars  1-2  (db[14]-db[16]): V+B     — just MJ + bass, intimate
#   bars  3-4  (db[16]-db[18]): D+B+O+V — full band
#   bars  5-6  (db[18]-db[20]): V+B     — strip again, call/response
#   bars  7-8  (db[20]-db[22]): D+B+O+V — full
#   bars  9-12 (db[22]-db[26]): D+B+O   — vocals vanish, builds tension
#
# VERSE 2 (segment 53.63–70.04)
#   bars  1-4  (db[26]-db[30]): V+B     — intimate re-entry
#   bars  5-8  (db[30]-db[34]): D+B+O+V — full, heading into verse 3
#
# CHORUS 1 (segment 86.45–106.95)
#   bars  1-4  (db[42]-db[46]): D+B+O+V — full hit
#   bars  5-8  (db[46]-db[50]): D+V     — bass+other DROP OUT (stark/unusual)
#   bars  9-10 (db[50]-db[52]): D+B+O+V — back full for the end punch
#
# POST-CHORUS (segment 106.95–115.14, 4 bars)
#   bars  1-4  (db[52]-db[56]): D       — drums ONLY, complete strip
#
# VERSE 4 (115.14–131.55)
#   bars  5-12 (db[56]-db[64]): V+B     — quiet rebuild, voice + groove only
#
# BIG CHORUS 2 (segment 168.43–209.37)
#   bars  1-2  (db[82]-db[84]): D+B     — hold back once more
#   bars  3-10 (db[84]-db[90]): D+B+O+V — the real drop, 6 bars of full
#   bars 11-12 (db[90]-db[92]): V+B     — sudden intimate hole mid-chorus
#   bars 13-20 (db[92]-db[102]):D+B+O+V — locked in all the way out
#
# BRIDGE (segment 209.37–223.72)
#   full bridge: V+O               — atmospheric, no drums at all
#
# CHORUS 3 (segment 223.72–254.41)
#   bars  1-8  (db[109]-db[117]):D+B+O+V — full
#   bars  9-16 (db[117]-db[125]):D+B     — go instrumental, voice fades
#
# END (segment 289.22–293.81)
#   D+B+O+V                        — full close

edit = [
    # INTRO
    (db[0],  db[4],  ["B","O"],         "intro-b1-4-no-drums"),
    (db[4],  db[8],  ["D","B","O","V"], "intro-b5-8-all"),
    (db[8],  db[14], ["D","B"],         "intro-b9-14-pulse"),
    # VERSE 1
    (db[14], db[16], ["V","B"],         "v1-b1-2-intimate"),
    (db[16], db[18], ["D","B","O","V"], "v1-b3-4-full"),
    (db[18], db[20], ["V","B"],         "v1-b5-6-intimate"),
    (db[20], db[22], ["D","B","O","V"], "v1-b7-8-full"),
    (db[22], db[26], ["D","B","O"],     "v1-b9-12-no-vocals"),
    # VERSE 2
    (db[26], db[30], ["V","B"],         "v2-b1-4-intimate"),
    (db[30], db[34], ["D","B","O","V"], "v2-b5-8-full"),
    # CHORUS 1
    (db[42], db[46], ["D","B","O","V"], "ch1-b1-4-full"),
    (db[46], db[50], ["D","V"],         "ch1-b5-8-drums-vox-only"),
    (db[50], db[52], ["D","B","O","V"], "ch1-b9-10-full"),
    # POST-CHORUS strip
    (db[52], db[56], ["D"],             "post-ch-drums-only"),
    # VERSE 4 rebuild
    (db[56], db[64], ["V","B"],         "v4-rebuild-vox-bass"),
    # BIG CHORUS 2
    (db[82], db[84], ["D","B"],         "ch2-b1-2-holdback"),
    (db[84], db[90], ["D","B","O","V"], "ch2-b3-10-drop"),
    (db[90], db[92], ["V","B"],         "ch2-b11-12-intimate-hole"),
    (db[92], db[102],["D","B","O","V"], "ch2-b13-20-full"),
    # BRIDGE
    (209.37, 223.72, ["V","O"],         "bridge-atmospheric"),
    # CHORUS 3
    (db[109],db[117],["D","B","O","V"], "ch3-b1-8-full"),
    (db[117],db[125],["D","B"],         "ch3-b9-16-instrumental"),
    # END
    (289.22, 293.81, ["D","B","O","V"], "end-full"),
]

# ── Render each section ───────────────────────────────────────────────────────
tmp_files = []

for i, (start, end, keys, label) in enumerate(edit):
    inputs = [STEMS[k] for k in keys]
    tmp = f"/tmp/srem2_s{i:02d}_{label}.wav"
    tmp_files.append(tmp)

    filter_parts = []
    mix_labels = []
    for j, _ in enumerate(inputs):
        lbl = f"s{j}"
        filter_parts.append(
            f"[{j}:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[{lbl}]"
        )
        mix_labels.append(f"[{lbl}]")

    if len(inputs) == 1:
        filter_str = filter_parts[0].replace(f"[s0]", "[out]")
    else:
        mix_in = "".join(mix_labels)
        filter_str = ";".join(filter_parts) + f";{mix_in}amix=inputs={len(inputs)}:normalize=0[out]"

    cmd = ["ffmpeg", "-y"] + sum([["-i", p] for p in inputs], []) + [
        "-filter_complex", filter_str,
        "-map", "[out]",
        tmp
    ]
    print(f"  [{i+1:02d}/{len(edit)}] {label}  ({start:.2f}–{end:.2f}s, stems: {''.join(keys)})")
    subprocess.run(cmd, check=True, capture_output=True)

# ── Concatenate ───────────────────────────────────────────────────────────────
concat_list = "/tmp/srem2_concat.txt"
with open(concat_list, "w") as f:
    for t in tmp_files:
        f.write(f"file '{t}'\n")

print(f"\nConcatenating {len(tmp_files)} sections → {OUT}")
subprocess.run([
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0", "-i", concat_list,
    "-ar", "44100", "-ac", "2",
    OUT
], check=True, capture_output=True)

import os
size_mb = os.path.getsize(OUT) / 1_048_576
dur_s = sum(e - s for s, e, _, _ in edit)
print(f"Done: {OUT}  ({dur_s:.1f}s / {size_mb:.1f} MB)")
