# JSONMusicMap Prototype — Agent Plan

## Context
You are helping build a proof-of-concept for JSONMusicMap — a structured JSON
representation of a music track's properties (BPM, key, sections, beats) designed
for LLM reasoning and programmatic audio editing.

The goal is a working demo in ~2 hours showing the full loop:
**audio file → JSONMusicMap → agent edit decision → Remotion visualization**

---

## Prerequisites
Before starting, verify these are installed:
- Python 3.10+
- Node.js 18+
- ffmpeg (`brew install ffmpeg` on Mac)
- A test MP3 file (ideally a well-documented pop track like Billie Jean)
- Anthropic API key (for Claude API call)

---

## Step 1 — Generate the JSONMusicMap

### 1.1 Install dependencies (in conda env in root of the working directory)
```bash
pip install librosa numpy scipy
```

### 1.2 Create `analyze.py`
```python
import librosa
import json
import sys

def analyze(path):
    print(f"Analyzing {path}...")
    y, sr = librosa.load(path, duration=120)  # first 2 mins, faster

    # BPM + beats
    tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beats, sr=sr).tolist()

    # Key from chroma
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = chroma.mean(axis=1)
    keys = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    key = keys[chroma_mean.argmax()]

    # Section boundaries (no labels — 6 sections)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    bounds = librosa.segment.agglomerative(mfcc, 6)
    bound_times = librosa.frames_to_time(bounds, sr=sr).tolist()

    sections = []
    for i, start in enumerate(bound_times):
        end = bound_times[i+1] if i+1 < len(bound_times) else float(len(y)/sr)
        sections.append({
            "id": i + 1,
            "start": round(start, 2),
            "end": round(end, 2),
            "duration": round(end - start, 2)
        })

    music_map = {
        "file": path,
        "duration": round(float(len(y) / sr), 2),
        "bpm": round(float(tempo), 1),
        "key": key,
        "beats": [round(b, 3) for b in beat_times[:32]],
        "sections": sections
    }

    return music_map

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "track.mp3"
    result = analyze(path)
    with open("music.map.json", "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print("\n✅ Saved to music.map.json")
```

### 1.3 Run it
```bash
python analyze.py billie_jean.mp3
```

### 1.4 Verify output
Expected `music.map.json`:
```json
{
  "file": "billie_jean.mp3",
  "duration": 119.8,
  "bpm": 116.1,
  "key": "F#",
  "beats": [0.43, 0.87, 1.30, "..."],
  "sections": [
    { "id": 1, "start": 0.0,  "end": 29.3, "duration": 29.3 },
    { "id": 2, "start": 29.3, "end": 58.1, "duration": 28.8 },
    { "id": 3, "start": 58.1, "end": 91.4, "duration": 33.3 },
    { "id": 4, "start": 91.4, "end": 119.8, "duration": 28.4 }
  ]
}
```

**Validation:** BPM should be close to known value. Key should be plausible.
If BPM is wildly wrong (e.g. exactly double or half) — this is normal, librosa
sometimes halves/doubles. Acceptable for prototype.

---

## Step 2 — Agent Edit Decision

### 2.1 Upload map to Claude.ai
Open claude.ai, upload `music.map.json`, send this prompt:

```
Here is a JSONMusicMap of a song. I need to shorten it to 60 seconds
for a podcast intro. It should end at a natural section boundary,
not mid-phrase.

Return ONLY valid JSON, no prose, no markdown:
{
  "keep_from": <seconds>,
  "keep_to": <seconds>,
  "fade_out_start": <seconds>,
  "fade_out_duration": <seconds>,
  "reasoning": "<one sentence>"
}
```

### 2.2 Expected agent output
```json
{
  "keep_from": 0,
  "keep_to": 58.1,
  "fade_out_start": 54.0,
  "fade_out_duration": 4.1,
  "reasoning": "Cuts at section 2→3 boundary at 58.1s, natural phrase ending"
}
```

### 2.3 Save as `edit.json`
Copy the agent output and save it as `edit.json` in your project folder.

---

## Step 3 — Execute the Edit

### 3.1 Run ffmpeg
```bash
ffmpeg -i billie_jean.mp3 \
  -ss 0 \
  -to 58.1 \
  -af "afade=t=out:st=54.0:d=4.1" \
  podcast_intro.mp3
```

### 3.2 Listen
Open `podcast_intro.mp3`. Ask yourself:
- Does it feel complete or cut off?
- Does the fade feel natural?
- Does it end at a musically sensible moment?

This is your ground truth validation. If it sounds wrong —
the section detection needs tuning (more sections, different algorithm).

---

## Step 4 — Remotion Visualization

### 4.1 Create Remotion project
```bash
npm create video@latest my-music-map
cd my-music-map
npm install
```

### 4.2 Copy files into project
```bash
cp ../music.map.json src/music.map.json
cp ../billie_jean.mp3 public/billie_jean.mp3
cp ../edit.json src/edit.json
```

### 4.3 Create `src/AudioEdit.tsx`
```tsx
import { Audio, AbsoluteFill, useVideoConfig } from "remotion";
import map from "./music.map.json";
import edit from "./edit.json";

// Color per section for visualization
const COLORS = ["#2563eb","#16a34a","#dc2626","#d97706","#7c3aed","#0891b2"];

export const AudioEdit = () => {
  const { fps, durationInFrames } = useVideoConfig();
  const totalSecs = durationInFrames / fps;

  return (
    <AbsoluteFill style={{
      background: "#0a0a0a",
      color: "#fff",
      fontFamily: "monospace",
      padding: 40
    }}>

      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ fontSize: 28, margin: 0 }}>JSONMusicMap</h1>
        <p style={{ color: "#888", margin: "8px 0 0" }}>
          {map.bpm} BPM · Key of {map.key} · {map.duration}s original
        </p>
      </div>

      {/* Section timeline */}
      <div style={{ marginBottom: 24 }}>
        <p style={{ color: "#666", fontSize: 12, marginBottom: 8 }}>
          SECTIONS
        </p>
        <div style={{ display: "flex", height: 48, borderRadius: 6, overflow: "hidden" }}>
          {map.sections.map((s: any) => (
            <div
              key={s.id}
              style={{
                width: `${(s.duration / map.duration) * 100}%`,
                background: COLORS[s.id - 1] || "#333",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 11,
                borderRight: "1px solid #000"
              }}
            >
              §{s.id}
            </div>
          ))}
        </div>

        {/* Edit range overlay */}
        <div style={{
          position: "relative",
          height: 4,
          background: "#222",
          marginTop: 4,
          borderRadius: 2
        }}>
          <div style={{
            position: "absolute",
            left: `${(edit.keep_from / map.duration) * 100}%`,
            width: `${((edit.keep_to - edit.keep_from) / map.duration) * 100}%`,
            height: "100%",
            background: "#fff",
            borderRadius: 2
          }} />
        </div>
        <p style={{ color: "#666", fontSize: 11, marginTop: 4 }}>
          ▓ kept: {edit.keep_from}s → {edit.keep_to}s ({edit.keep_to - edit.keep_from}s)
        </p>
      </div>

      {/* Edit decision */}
      <div style={{
        background: "#111",
        border: "1px solid #222",
        borderRadius: 8,
        padding: 16,
        marginBottom: 24,
        fontSize: 13
      }}>
        <p style={{ color: "#666", fontSize: 11, margin: "0 0 8px" }}>
          AGENT REASONING
        </p>
        <p style={{ margin: 0, lineHeight: 1.6 }}>
          {edit.reasoning}
        </p>
      </div>

      {/* Section list */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {map.sections.map((s: any) => (
          <div key={s.id} style={{
            background: "#111",
            border: `1px solid ${COLORS[s.id-1] || "#333"}`,
            borderRadius: 6,
            padding: "8px 12px",
            fontSize: 12
          }}>
            <div style={{ color: COLORS[s.id-1], fontWeight: "bold" }}>
              Section {s.id}
            </div>
            <div style={{ color: "#888", marginTop: 2 }}>
              {s.start}s → {s.end}s
            </div>
          </div>
        ))}
      </div>

      {/* Audio — trimmed per agent decision */}
      <Audio
        src="/billie_jean.mp3"
        trimBefore={edit.keep_from * fps}
        trimAfter={edit.keep_to * fps}
        volume={(f) => {
          const fadeStart = edit.fade_out_start * fps;
          const fadeEnd = edit.keep_to * fps;
          if (f < fadeStart) return 1;
          return Math.max(0, 1 - (f - fadeStart) / (fadeEnd - fadeStart));
        }}
      />

    </AbsoluteFill>
  );
};
```

### 4.4 Update `src/Root.tsx`
```tsx
import { Composition } from "remotion";
import { AudioEdit } from "./AudioEdit";
import map from "./music.map.json";
import edit from "./edit.json";

export const RemotionRoot = () => (
  <Composition
    id="AudioEdit"
    component={AudioEdit}
    durationInFrames={Math.ceil(edit.keep_to * 30)}
    fps={30}
    width={1280}
    height={720}
  />
);
```

### 4.5 Run
```bash
npm run dev
# Open http://localhost:3000
# Press play — hear the edited audio, see the section map
```

---

## Validation Checklist

After completing all steps, verify:

- [ ] `music.map.json` generated with plausible BPM and key
- [ ] Sections detected (at least 3-4 boundaries)
- [ ] Agent returned a cut at an actual section boundary
- [ ] `podcast_intro.mp3` sounds complete, not cut off
- [ ] Remotion shows colored section blocks
- [ ] Audio plays trimmed in Remotion with fade
- [ ] Agent reasoning is visible in UI

---

## What This Proves

- The JSONMusicMap concept works — audio becomes structured data
- An LLM can reason over musical structure to make intelligent edit decisions
- Remotion can consume the map and visualize + execute the edit
- The full loop (analyze → map → agent → edit → visualize) is feasible

---

## What This Does NOT Prove (yet)

- Chord detection accuracy
- Section label accuracy (verse/chorus)
- Complex crossfades
- Mood analysis
- Performance on jazz or complex music

These are v2 problems.

---

## Troubleshooting

**librosa install fails:**
```bash
pip install --upgrade pip
pip install librosa
```

**BPM is exactly double/half expected:**
Normal librosa behavior. Divide or multiply by 2. Not a bug for prototype.

**Sections look wrong:**
Try changing `6` in `agglomerative(mfcc, 6)` to `4` or `8`.

**Remotion audio not playing:**
Make sure MP3 is in `/public` folder, not `/src`.

**ffmpeg not found:**
```bash
# Mac
brew install ffmpeg
# Ubuntu
sudo apt install ffmpeg
```