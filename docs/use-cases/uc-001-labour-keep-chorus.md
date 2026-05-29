# UC-001 — Keep the chorus: labour.mp3

## Use Case Card

```
ID:                    UC-001
Name:                  Keep the chorus with creative intro and echo tail
Prompt:                "keep only 0:51–1:29"
Genre tested:          Indie rock / guitar pop (B minor, 83 BPM)
Track:                 labour.mp3
Cut window:            51.15s – 89.01s
Result file:           testing/01/labour-edit2.4.mp3
Result quality:        4/5
Standard or non-linear: Non-linear (pre-roll + two-layer ending)
Manual intervention:   Yes — required iterative tuning (see session log below)
```

**Information needed from audio:**
- Section boundaries (chorus start/end) — from allin1
- BPM for delay sync — 83 BPM from allin1
- Cut points aligned to downbeats — beat positions from allin1

---

## Training Triplet

```json
{
  "music_map": "testing/01/labour-full.json",
  "instruction": "keep only the chorus section from 0:51 to 1:29, with a creative intro build-up and a natural echo tail ending",
  "correct_edit": {
    "type": "non_linear_join",
    "segments": [
      {
        "role": "intro",
        "source_window": [45.15, 51.15],
        "primitives": ["filter_sweep", "fade", "reverb"],
        "params": {
          "filter_sweep": {"direction": "open", "duration": 6.0, "freq_floor": 220, "freq_ceil": 20000, "curve": 6.0},
          "fade": {"vol_start": 0.0, "vol_end": 1.0},
          "reverb": {"wetness": 0.5, "reverb_type": "hall"}
        },
        "reason": "6s pre-roll from the section before the chorus, swept open from low frequencies to give the feeling of emerging from underwater. Reverb adds space. Curve=6 keeps it muted until the last moment, then opens suddenly on the downbeat."
      },
      {
        "role": "body_dry",
        "source_window": [51.15, 89.01],
        "primitives": ["fade"],
        "params": {
          "fade": {"vol_start": 1.0, "vol_end": 0.0, "duration_s": 2.0, "apply_at": "end"}
        },
        "reason": "Full chorus plays uninterrupted. 2s fade at the very end prevents hard cut but preserves vocals throughout — fading earlier would cut off meaningful lyrical content."
      },
      {
        "role": "body_wet",
        "source_window": [84.01, 89.01],
        "primitives": ["delay", "reverb"],
        "params": {
          "delay": {"delay_seconds": 0.723, "feedback": 0.5, "wetness": 1.0},
          "reverb": {"wetness": 0.35, "reverb_type": "hall"},
          "wet_level": 0.2,
          "fade_in_s": 2.0,
          "tail_extension_s": 5.0
        },
        "reason": "BPM-synced delay (1 beat @ 83 BPM = 0.723s) on the last 5s of the chorus, mixed underneath the dry layer at low level. Delay tail extends 5s past cut end so the echo rings out naturally — avoids the feeling of a hard stop. Wet layer fades in over 2s to avoid harsh onset."
      }
    ],
    "join": "xfade_join(intro, body_mix, xfade_ms=60)",
    "notes": "dry and wet body layers are mixed (summed) after aligning in time, not xfaded"
  }
}
```

---

## Session Log — Iterative Decision Trace

This documents the human reasoning behind each revision. Valuable as training signal for the reasoning layer.

### Round 1 — Basic cut
**Instruction:** "keep only 0:51–1:29"
**Decision:** Hard cut at [51.15, 89.01], xfade join.
**Problem:** Abrupt start — felt like audio just switched on.

### Round 2 — Intro build
**Instruction:** "we need some fade in into the beginning... ideally we would create some edit primitive for eq, then we choose segment we put before the beginning of the cut and apply the eq to it"
**Decision:** Take 6s pre-roll, apply low-pass filter sweep opening from 100Hz.
**Learning:** User thinks in pre-roll + effect zones, not just in/out points.

### Round 3 — Filter character
**Instruction:** "it should be more low cut so the voice is barely understandable wordwise and then full open on beginning of our cut. this is done in dance music"
**Decision:** Lower freq_floor to 220Hz, curve=6 (exponential — stays muted longer, bursts open at end).
**Learning:** DJ filter sweep reference — not a gentle fade, it's a dramatic reveal.

### Round 4 — Separate fade from filter
**Instruction:** "fade in and out volume wise should be different thing"
**Decision:** Split `filter_sweep` (frequency shaping only) from `fade` (volume envelope). Each is now a standalone primitive.
**Learning:** Single-responsibility primitives compose better. User's mental model separates timbral and volume changes.

### Round 5 — Reverb on intro
**Instruction:** "for the more dramatic feel, we could apply some reverb"
**Decision:** Add reverb(wetness=0.5, hall) after sweep+fade.
**Problem:** Initial click — reverb received non-zero first sample. Fix: apply fade before reverb, prepend 80ms silence.
**Learning:** Effect order matters. Volume must be near-zero before reverb to avoid initialization click.

### Round 6 — Ending: delay not preserving original
**Instruction:** "delay is not timed properly... we should also preserve the original audio... BPM is 83"
**Decision:** Two-layer approach: dry layer (original) + wet layer (delay+reverb). BPM-sync delay to ONE_BEAT = 0.723s.
**Learning:** User's instinct is additive (add an effect layer) not substitutive (replace audio with processed version).

### Round 7 — No harsh join at ending
**Instruction:** "0:38 and 0:39 has a strange cut... What about having one layer of the audio as it is and then you add the second layer"
**Decision:** Remove xfade between body and ending zone. Align layers in time and mix (sum) them.
**Learning:** An xfade between sections the user wants to hear simultaneously is wrong. Mix = blend, xfade = transition.

### Round 8 — Extend beyond cut end
**Instruction:** "leave the delay last... make sequence longer"
**Decision:** Append 5s silence to ending_src before delay processing. Output length extends past CUT_END.
**Learning:** The cut end is not the audio end. Echo tails need breathing room.

### Round 9 — Preserve vocals, shorter dry fade
**Instruction:** "i hear some artificial high end clicks... we also need to apply fade in in the second layer"
**Decision:** Reduce DRY_FADE from 5s to 0.4s. Add wet_env fade-in (0→0.5 over 2s). Increase warmup to > 1 delay cycle.
**Learning:** Fading out vocals early felt wrong — they're the main content. Keep them until the end, let echo carry the ending.

### Round 10 — Click source diagnosis and fix
**Instruction:** "0:44–0:48 still clicks, is this not from the sequence prolonging?"
**Root cause:** Sample discontinuity at both boundaries of ending_src (start and end), plus warmup < delay_seconds.
**Fix:** Micro-fade (10ms) at both boundaries + warmup = ONE_BEAT + 0.5s (1.22s).
**Learning:** Any boundary where audio concatenates to silence needs a micro-fade, not just the start. The delay feedback loop amplifies discontinuities.

---

## Future Work

- **Stem separation:** Intro sweep would be cleaner on isolated guitar loop stem (Demucs). Current version sweeps full mix including vocals — low frequencies are muddied by the vocal content.
- **Vocal-only ending layer:** The wet delay layer would be more musical if fed only the vocal stem, not the full mix. The guitar and drums create muddy delay echoes.
- **Auto cut point:** BPM-aligned cut detection — 51.15 was manually identified as the downbeat. Should be automatic from the beat grid in labour-full.json.
