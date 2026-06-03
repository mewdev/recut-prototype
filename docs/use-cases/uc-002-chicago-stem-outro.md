# UC-002 — Stem-based creative outro: chicago.mp3

## Use Case Card

```
ID:                    UC-002
Name:                  Trim from motif repeat + stem-based creative outro
Prompt:                "Start from ~1:01 till end. End has repetitive motif where there's space for a creative ending."
Genre tested:          Rock/pop (C major, 136 BPM, 4/4)
Track:                 chicago.mp3
Cut window:            61.56s → ~231s (stem-constructed outro)
Result file:           testing/02/chicago-cut-v16.mp3
Result quality:        4/5
Standard or non-linear: Non-linear (stem remix — independent volume envelopes per stem)
Manual intervention:   Yes — 16 iterative versions
```

**Information needed from audio:**
- Section labels (chorus boundary = vocal entry) — from allin1
- Phrase boundaries within sections — from chicago-full-phrases.json
- BPM and downbeat grid — 136 BPM, 1.765s/bar from allin1
- Stem files (drums, bass, vocals, other) — Demucs via allin1 pipeline
- Segment repetition: outro phrase A (182.46s) vs. phrase A repeat (196.68s) — detected by phrase analysis

---

## Training Triplet

```json
{
  "music_map": "testing/02/chicago-full.json",
  "instruction": "Start from ~1:01 where the motif begins repeating, keep until end. In the outro, strip down to piano only for a quiet, intimate exit.",
  "correct_edit": {
    "type": "stem_remix",
    "start_abs": 61.56,
    "segments": [
      {
        "role": "full_band",
        "source_window": [61.56, 196.68],
        "stems": ["drums", "bass", "vocals", "other"],
        "primitives": ["fade"],
        "params": {
          "fade_in": {"vol_start": 0.0, "vol_end": 1.0, "duration_s": 0.5, "apply_at": "start"}
        },
        "reason": "Full band from start point to phrase A repeat downbeat. 0.5s fade-in avoids entry click from jumping mid-track."
      },
      {
        "role": "drum_fade",
        "source_window": [196.68, 207.34],
        "stems": ["drums"],
        "primitives": ["fade"],
        "params": {
          "fade": {"vol_start": 1.0, "vol_end": 0.0}
        },
        "reason": "Drums fade out over 10.66s (phrase A repeat). Reach zero at 207.34s — 2 full bars before the piano exit at 210.90s. Must reach zero BEFORE the transition zone, not at it: kick transients bypass sustained-tone masking even at -21dB below piano. Linear fade, not filter_sweep — IIR filters resonate on percussive transients."
      },
      {
        "role": "bass_vox_cut",
        "source_window": [196.68, 196.98],
        "stems": ["bass", "vocals"],
        "primitives": ["fade"],
        "params": {
          "fade": {"vol_start": 1.0, "vol_end": 0.0, "duration_s": 0.3}
        },
        "reason": "Bass and vocals hard-cut at phrase A repeat boundary. Short 0.3s taper to avoid click. Vocals must be cut here, not at the chorus boundary (210.90s) — the 'chorus' segment label signals vocal entry: cutting there lets a vocal phrase enter at full volume 1s before the taper begins."
      },
      {
        "role": "piano_dry_eq",
        "source_window": [207.34, 210.90],
        "stems": ["other"],
        "primitives": ["eq"],
        "params": {
          "eq": {"cutoff": 4000, "type": "low"}
        },
        "reason": "3-second window: drums are silent, piano/cello is exposed. The kick was providing forward-masking (~20ms) over cello rhythmic attacks. Once drums are gone, the cello attack becomes the loudest transient and reads as a click. 4kHz low-pass rounds the attack edge without affecting body of the sound (other.wav is 98.7% sub-4kHz energy). Applied only to this slice — piano_end (from 210.90s) is unaffected."
      },
      {
        "role": "piano_exit",
        "source_window": [210.90, 231.0],
        "stems": ["other"],
        "primitives": ["fade", "filter_sweep", "reverb"],
        "params": {
          "fade_in": {"vol_start": 0.0, "vol_end": 1.0, "duration_s": 0.5, "apply_at": "start"},
          "filter_sweep": {
            "direction": "close",
            "freq_ceil": 8000,
            "freq_floor": 200,
            "curve": 2.5,
            "duration": 20.1
          },
          "reverb": {"wetness": 0.38, "reverb_type": "hall"},
          "fade_out": {"vol_start": 1.0, "vol_end": 0.0, "duration_s": 5.0, "apply_at": "end", "offset_from_end_s": 5.0}
        },
        "reason": "Piano-only exit. filter_sweep closes from 8kHz→200Hz over 20s — freq_ceil=8kHz (not 20kHz) because drum bleed in other.wav is constant amplitude but becomes perceptually dominant as musical signal fades. Curve=2.5 keeps cutoff near 8kHz early, closes fast at end. Hall reverb adds space. Fade-out covers final 5s only — last chord at 2:40 must remain fully audible before fade begins."
      }
    ],
    "mix": "sum all active stem layers at each sample position — no xfade_join between regions",
    "notes": "All stems are loaded for the full clip duration. Volume envelopes and effects are applied in-place per stem. The mix is the sum at any sample position. xfade_join must never be used for time-aligned stems — it overlaps content, shifts phrase timing, and causes phase doubling on continuous sources."
  }
}
```

---

## Session Log — Iterative Decision Trace

### Round 1 — Wrong direction
**Instruction:** "potřebovaly bychom to zkrátit od 1:01, když se začne znovu opakovat ten motif" (shorten from 1:01 when the motif repeats)
**Decision:** Trim at 61.56s, keep only the first minute. Fade out 3.5s.
**Problem:** Completely misread the intent — user wanted the second half, not the first.
**Learning:** "zkrátit od 1:01" = shorten starting from 1:01, not shorten to 1:01.

### Round 2 — Correct direction, no creativity
**Instruction:** "Start from cca 1:01 till the end. End has repetitive motif/loop where there's space for some creative end."
**Decision:** Trim from 61.56s to 228.63s. Simple fade-out at final outro loop (225.1s).
**Problem:** "Creative end" not implemented — just a trim with a generic fade.
**Learning:** User's prompt contained the edit architecture: "repetitive loop = space for creative exit". The outro loop is explicitly flagged as a design opportunity.

### Round 3 — Stem idea introduced, xfade bug
**Instruction:** "drums disappear and only piano stays"
**Decision:** First stem-based version. Drum drop at bar 9 of the outro (196.68s). Used `xfade_join` to splice piano segments.
**Problem:** `xfade_join` consumed 300ms from the start of piano_b, shifting the phrase repeat early. Phase doubling during crossfade.
**Learning:** xfade_join is wrong for time-aligned stems — it's a transition tool, not a mix tool.

### Round 4 — Phrase structure analysis; map gap identified
**Instruction:** "phrase A with full band, phrase A repeat with piano only, new phrase (chorus) — sweep + reverb + fade"
**Decision:** Hard drum cut at phrase A repeat downbeat (196.68s). Creative exit: filter_sweep(close) + reverb(hall) + fade.
**Key insight:** The map labeled "outro" (182.46s–210.90s) as a single 28s block with no internal phrase markers. The phrase A / phrase A repeat split was inferred from "halfway = bar 9" — correct by coincidence.
**Map gap:** Phrase-level segmentation below section granularity is missing. Repetition flag (is this segment a literal repeat?) would be the direct inference signal for "drop drums when it repeats."

### Round 5 — Additive mixing architecture (key decision)
**Decision:** All stems loaded for full clip duration. Volume envelopes applied in-place. Never split timeline.
**Problem with v4:** xfade_join overlap broke timing.
**Learning:** The fix is architectural: additive mixing on one shared timeline is the correct mental model for stem editing. "Transition" between states = changing each stem's envelope, not joining separate audio segments.
**New problem:** Drums with reverb at wet=0.85 kept 15% dry signal + passed kick fundamental into reverb → bass mud.

### Round 6 — eq primitive created; kick+reverb diagnosis
**Decision:** High-pass drums at 120Hz before reverb. New `eq` primitive (Butterworth, type as parameter).
**Problem:** 120Hz removed kick fundamental (60–100Hz) but not the body (100–300Hz). Kick body still created reverb bloom. Multiple kicks accumulated into constant bass rumble.
**Learning:** Reverb + kicks = bass mud. EQ belongs as a general primitive (high/low/band are the same Butterworth with type parameter).

### Round 7 — Push cutoff to 400Hz; signal path regression found
**Decision:** Drums EQ: 120Hz → 400Hz. Removes everything below upper-mids: only snare crack, hi-hat, cymbal shimmer survives reverb.
**Regression found:** v5 "fixed" the xfade timing by using the full mix for the creative exit section. But that pulled drums_rev into the filter_sweep+reverb chain. `reverb(reverb(drums))` = exponentially longer tail, undefined phase, washed-out mud.
**Fix:** Terminate drums_rev at sweep boundary. Creative exit = piano-only, identical signal path to v4's clean end but with v5's correct timing.

### Round 8 — Transparent sweep + ambient preparation layer
**Decision:** Add `other_ambient` (other.wav → reverb(0.75) × 0.35) as preparation layer in the middle phrase (2:15–2:29). filter_sweep starts at 2:15 with freq_ceil=20kHz (transparent), not at 2:29 (audible step).
**Learning:** "Transparent sweep" trick: freq_ceil near the Nyquist limit = filter exists but is inaudible. Gradual close over the full section removes all spectral step artifacts at boundaries.

### Round 9 — Simplification: drums don't reverb into ambience
**Decision:** Remove drums_rev entirely. Drums stay dry and punchy until exit. other_ambient as quiet preparation layer only.
**Core realization:** Isolated kick transients don't reverb into ambience — reverb stretches the impulse but doesn't create a wash. Ambience requires sustained sources. Piano reverb is the correct source for a spatial wash.

### Round 10 — Vocal timing bug (segment label as entry predictor)
**Decision:** Move vox taper from 2:29 (sweep_samp) to 2:15 (cut_samp).
**Problem:** Vocal phrase enters at 2:28 — one second before the 0.3s taper could silence it. Hit full volume before taper began.
**Learning:** Segment label "chorus" at 210.90s signals strong vocal entry at that boundary. Segment labels must be used to anticipate what enters, not just describe structure. Always cut a stem before its next entry boundary.

### Round 11 — Crossfade at 2:29; drum bleed suppression
**Decision:** Drums taper 1.5s, piano_end fades in 1.5s — crossfade instead of simultaneous switch. freq_ceil: 18kHz → 8kHz (drum bleed in other.wav is constant amplitude but becomes perceptually dominant as musical signal fades).
**Learning:** Drum bleed is always present — it only surfaces when the signal covering it fades. Filter the receiving stem (piano) from the transition point, not the drums.

### Round 12 — Remove other_ambient; drums swept out in last bar
**Decision:** Remove other_ambient entirely. Drums: filter_sweep(close) + fade over last bar before 2:29.
**Problem with other_ambient:** Parallel reverb copy at any wetness adds pre-delay coloration + stereo image shift + phase smearing on attack. The cello's clarity is its natural attack — no copy needed.
**Problem with taper timing in v11:** Drums taper started AT sweep_samp and extended 1.5s INTO the piano exit. Fix: process last bar BEFORE sweep_samp → drums are silent when piano_end begins.

### Round 13 — IIR filter click on kick
**Decision:** filter_sweep starts 2 bars early (207.37s, freq_ceil=16kHz) instead of cold on last bar.
**Root cause:** `sosfilt_zi * seg[ch, 0]` — filter state initialized from first sample amplitude. First sample was a high-amplitude kick attack (peak=0.39) → initialization vector large → overshoot on first output samples → click.
**Fix:** Start filter 2 bars early when drums are at 25% volume (already faded). No audible discontinuity when kick hits mid-sweep.

### Round 14 — filter_sweep wrong tool for percussive stems
**Decision:** Remove filter_sweep from drums entirely. Volume fade only.
**Root cause:** 2nd-order Butterworth resonance peaks at 1kHz. As sweep passed through 1kHz, each kick excited a tonal ring at the cutoff frequency — rhythmic clicks at <10% drum volume, maximally perceptible (equal-loudness peak at 1–4kHz).
**Rule:** filter_sweep is the right tool for sustained pitched sources (piano, pads, bass). It is the wrong tool for transient-heavy percussive sources. For drums: scalar amplitude envelope only.

### Round 15 — Transients bypass sustained-tone masking
**Decision:** End drum fade at 207.34s (2:25.78) instead of 210.90s (2:29). Drums reach zero 2 bars before the piano exit.
**Root cause:** At 2:28, drums at fade_amp=0.032 (peak_faded=0.012), piano peak=0.150 → drums at -21dB below piano. Sustained-tone masking requires ~40dB. But transient onset detection is separate: auditory onset detector fires independently of steady-state masking. Even at -21dB, a kick transient pops through sustained piano content.
**Rule:** Linear fade does not suppress transients — reach zero BEFORE the transient zone, not at it.

### Round 16 — Temporal masking (kick forward-masking cello)
**Decision:** Apply `eq(cutoff=4000, type="low")` to piano_dry (other.wav) from 207.34s to 210.90s only.
**Root cause:** Click at 2:28 was not drum bleed — confirmed by 1ms RMS shape (uncorrelated with drums). The cello/piano's own rhythmic attack, previously masked by the kick, became audible once drums were removed. Kick was providing temporal forward-masking (~20ms) over co-timed cello attacks. Remove kick → cello attack = loudest transient in the window → perceived as click.
**Fix:** 4kHz low-pass on the 3-second exposed window rounds the cello attack edge. Barely changes timbre (other.wav is 98.7% sub-4kHz). Applied as a slice, not to the full stem.
**Rule:** When removing a percussive element, check all other stems for co-timed attacks that were previously masked. Temporal masking is asymmetric: removing a masker exposes co-timed content in other stems.

---

## Map Gaps Identified (inference failures requiring human correction)

| Gap | Consequence | What the map needs |
|-----|-------------|-------------------|
| No phrase boundaries within sections | Bar 9 drop point inferred by symmetry, not data | Phrase-level segmentation (4–8 bar markers within sections) |
| No repetition flag | Couldn't infer "phrase A repeat = drop drums" without listening | Boolean `is_repeat_of: <segment_id>` per phrase |
| Segment label used as description, not prediction | Chorus label = vocal entry ahead; taper must happen before the boundary | Labels encode what starts at the boundary, not what's in the preceding segment |
| No per-stem energy curve | Drum bleed surfacing was invisible until it appeared in audio | Per-stem amplitude envelope (or RMS per beat per stem) |

---

## Primitives Added or Refined During This Session

| Primitive | Change |
|-----------|--------|
| `eq` | New. Butterworth filter, `type` parameter (high/low/band). Created in v6. |
| `filter_sweep` | Confirmed: transparent start (freq_ceil near Nyquist) removes transition artifacts. Confirmed: wrong tool for percussive stems. |
| `combine_stems` | Formalized additive mixing on a single timeline. |

---

## Future Work

- **Phrase repetition detection:** A repetition score per phrase (or similarity to preceding segment) would have made the drum-drop decision automatable from the map alone.
- **Per-stem energy envelope in the map:** Would surface drum bleed before it appears in audio. Essential for automated stem-exit timing.
- **Temporal masking check:** After removing any percussive stem, run a co-timed transient check on all remaining stems in a 3-beat window. Flag any with unexpected amplitude increase.
- **IIR filter safety check:** Before applying filter_sweep to a stem, check if it's transient-dominated (kick/snare ratio > threshold). If so, substitute scalar fade.
