# Skill: Transitions

How to move cleanly between sections — full band → stems-only → piano-only → silence.

---

## The Masking Problem

When you remove a stem, you expose content in remaining stems that was previously masked. This is the source of most "unexpected clicks" in cutting work.

**Temporal masking:** a kick's onset (~20ms) suppresses other co-timed transients in the ear's forward masking window. Remove the kick → co-timed cello bow strokes or piano attacks become the loudest transient. They read as "click" because they're rhythmically precise.

**Spectral masking:** a loud low-mid element (bass, kick body) raises the masking threshold across the spectrum. Remove it → previously inaudible content in other stems surfaces.

**Checklist before removing any stem:**
1. What transients exist at the same beat positions in other stems?
2. Is there drum bleed in `other.wav` or `bass.wav` that will be exposed?
3. Will the remaining stems feel "empty" or "unbalanced"?

---

## Transition Stagger Rule

**Never remove multiple stems simultaneously.** Simultaneous switches sound like a system turning off.

Stagger exits across bars:
- Bar N: bass + vocals cut
- Bar N+2: drums fade completes
- Bar N+4: piano-only section begins with processing

Each removal gives the listener time to adjust to the new texture before the next one.

---

## Fade Completion Timing

**End fades BEFORE the next audible transient, not at it.**

| Situation | Correct approach |
|-----------|-----------------|
| Drums must be silent by beat B | End drum fade 2 bars before B |
| Vocals must be gone before chorus | Taper vox at previous section boundary |
| Bass exit must be clean | Hard taper at downbeat; 0.3s is enough |

A linear fade reaching zero AT the target beat still has audible amplitude on the 2–3 beats before it. Transient sources (kicks) bypass masking at 5–12% amplitude in a quiet mix.

---

## Avoiding Transition Click at Effect Onset

When switching from dry to processed audio (e.g., piano enters filter_sweep):

**Problem:** starting a `filter_sweep` at `freq_ceil=8000` on a live signal creates an instant spectral change — the ear hears a "thud" or "room switch."

**Solutions in order of preference:**
1. **Transparent start:** `freq_ceil=18000`, `curve=2.5` — filter is inaudible at t=0, descends naturally
2. **Fade-in the processed signal:** 0.5–1.5s volume fade-in on the processed stem while dry tapers out — sounds like a crossfade, not a switch
3. **Start processing earlier** in a quieter zone — IIR filter warms up before the loud content arrives

**IIR initialization rule:** `filter_sweep` initializes filter state with `sosfilt_zi * first_sample`. If `first_sample` is a loud transient, the initialization vector is large → overshoot → click. Start the filter when the signal is at <30% amplitude.

---

## Transition Between Dry and Processed Piano

The safe pattern for entering a sweep+reverb exit from a dry piano section:

```python
# piano_dry: taper out over 0.3s at sweep_samp
piano_dry[:, sweep_samp:sweep_samp+taper] *= np.linspace(1.0, 0.0, taper)
piano_dry[:, sweep_samp+taper:] = 0.0

# piano_end: apply processing, then fade IN over 0.5s
piano_end = chain(piano[sweep_samp:], sr,
    (filter_sweep, dict(freq_ceil=8000, ...)),
    (reverb, dict(wetness=0.38, ...)),
)
piano_end[:, :fi] *= np.linspace(0.0, 1.0, fi)  # 0.5s fade-in

# Add to mix — no xfade_join
mix[:, sweep_samp:] += piano_end
```

The 0.3s taper on piano_dry and 0.5s fade-in on piano_end create a brief overlap where both contribute — the ear hears a smooth room transition, not a switch.

---

## Ambient Preparation Layers

If a section transition is abrupt (e.g., full band → piano solo), adding a reverb layer in the bars before the transition prepares the listener's ear for the space.

**Rules for ambient prep layers:**
- Use a sustained source (piano, strings) — not drums
- Keep it quiet (×0.2–0.3 volume)
- Use minimal reverb (wet≤0.15 for strings, wet≤0.4 for piano)
- Fade it OUT before the second reverb chain starts — reverb on reverb = bloom
- Do not EQ strings before reverb — their warmth is their character
