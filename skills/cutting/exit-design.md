# Skill: Exit Design

How to end a cut track. The exit is the listener's last impression — it should feel intentional, not truncated.

---

## Choosing the Exit Point

**Always snap to a downbeat.** Never cut mid-bar. Use the `downbeats` array from the music map.

**Best exit zones (in order of preference):**
1. End of a chorus — highest emotional resolution
2. End of an outro loop — listener expects closure there
3. End of a phrase repeat — the repetition itself signals "this is ending"
4. Mid-section only if there's a natural breath (held note, drum break)

**Bar-align the cut, then work backwards** from it to design the exit.

---

## Exit Types

### 1. Hard edit (V2 style)
Fade out over the last 2–4 bars of the final section. Clean, professional, fast to execute.

```python
# Fade out over last 4 bars
fade_start = CLIP_END - 4 * bar_dur
mix[:, int(fade_start*sr):] = fade(mix[:, int(fade_start*sr):], sr, 1.0, 0.0)
```

**When to use:** the track has a natural ending zone (outro, vamp, loop). The user wants a usable edit quickly. This is often the right answer.

### 2. Stem dissolve
Remove stems progressively over the final 2–4 sections:
- Full band → minus bass+vox → minus drums → piano only → fade

**When to use:** creative brief asks for something intentional. User wants to feel the track wind down, not just stop.

**Minimum time required:** 3–4 sections (~30–60s). Don't try to execute a stem dissolve in less than 16 bars.

### 3. Filter sweep exit
Apply `filter_sweep(close)` to the remaining melodic stem over the final section, combined with reverb and fade.

**When to use:** after drums and bass are gone, piano is carrying the end. Creates a "dissolving into space" effect.

**Parameters that work:**
- `freq_ceil=8000` — slight initial dullness that removes drum bleed
- `freq_floor=200` — musical, not complete silence
- `curve=2.5` — stays near the ceiling most of the time, drops fast at the end
- Fade out only the **last 25%** of the section — the chord before the fade should be fully audible

---

## Fade Timing

**Common mistake:** starting the fade too early. The listener wants to hear the last chord.

**Rule:** fade should cover no more than the last 4 bars. If the exit section is 20s, fade starts at 15s — not at 0s.

```python
FADE_OUT_START = exit_dur * 0.75  # last 25% of exit section
fo_start = int(FADE_OUT_START * sr)
audio[:, fo_start:] *= np.linspace(1.0, 0.0, audio.shape[1] - fo_start)
```

---

## Reverb in Exits

Reverb on the final piano/melodic stem makes the exit feel like dissolving into a room rather than stopping.

**Settings that work:**
- `reverb_type="hall"` — spacious, appropriate for endings
- `wetness=0.35–0.45` — wet enough to feel spatial, dry enough to stay musical
- Apply reverb **after** filter_sweep in the chain — not before

**Do not reverb the whole track.** Apply only to the final exit segment.

---

## Drum Bleed at Exit

As the musical signal fades, drum bleed in the piano/other stem becomes perceptually dominant. The hi_ratio of `other.wav` spikes when its own musical content fades (~2:44 in the chicago edit).

`filter_sweep` starting at `freq_ceil=8000` eliminates this bleed from the start of the exit section — the sweep progressively removes the frequency range where bleed lives.

If bleed is severe, apply `eq(cutoff=5000, type="low")` to the exit segment before the filter_sweep.

---

## Quick Reference — What Went Wrong and Why

| Symptom | Cause | Fix |
|---------|-------|-----|
| Audible "room switch" at exit start | `filter_sweep` started at audible cutoff | Use `freq_ceil=18000` or fade-in the processed signal |
| Click at transition | Multiple stems switch simultaneously | Stagger exits across bars |
| Drums audible after "silence" | Linear fade didn't reach zero before transient zone | End drum fade 2 bars earlier |
| Bass mud in reverb exit | Kick reverb without high-pass | EQ drums at 400Hz before reverb |
| Bloom at end | Reverb on reverb | Terminate reverb stems before second reverb chain |
| Exit feels truncated | Fade started too early | Fade last 25% only |
