# Validation Workflow

**Always call `validate(music_map, *nodes)` before `compose()`.** It's cheap (no audio processing) and catches structural mistakes before you spend time rendering.

```python
from recut.validator import validate

issues = validate(music_map, *nodes)
for i in issues:
    print(i.severity, i.message)
if any(i.severity == "error" for i in issues):
    # fix the composition before compose()ing
    ...
```

The CLI equivalent is `recut validate <composition-name>`; `recut render` runs this automatically and aborts on any `error` unless `--force`.

## `warning`-severity results: surface them, don't just log them

An agent building a composition (as opposed to a human typing `recut render` themselves)
must not silently render past a `warning`. Printing it to a tool-output log the user may
not read is not the same as telling them. Before calling `compose()` / `recut render`:

- Show every `warning` message to the user directly, in your response — not just in a
  code block's stdout.
- State plainly what it means and what proceeding without addressing it will sound like
  (e.g. "hard cut into a mid-song segment, no fade-in").
- Let the user decide whether to add the suggested effect, accept the hard cut
  deliberately, or change the composition — don't pick for them and don't render first
  and mention it after.

This matters most for `sequence_boundaries` (starting/ending off the song's natural
first/last segment) since it's the one rule that's a judgment call by design, not a
correctness bug — see `prompt-disambiguation.md` on why a deliberate rearrangement is
common and not itself wrong.

## What the current rules actually catch (`src/recut/validator/checks.py`)

| Rule | Catches |
|---|---|
| `label_exists` | A `Clip.segment_name`/`index` that doesn't exist in this song's map |
| `duration_exceeds` | A `bars`/`beats` request longer than the segment actually is |
| `sequence_boundaries` | First/last `Clip` in the sequence doesn't align with the song's actual first/last non-silence segment — flags a hard cut that will sound abrupt, as a `warning` |

That's the complete rule set — three checks, `src/recut/validator/rules.py`.

## What it does NOT catch — this is not a musical-quality linter

`validate()` only checks structural validity against the map. It will happily pass a composition that is musically wrong:

- Two `Reverb`s stacked in one `fx` chain (bloom)
- A `FilterSweep` applied over a percussion-dense section (audible ringing)
- A fade that doesn't reach zero before the next transient (click)
- A key or energy discontinuity across an `XFade`
- Effects applied in a bad order (see `effects-routing.md`)

None of these are mechanically checked today. Passing `validate()` means "this composition can be rendered without crashing and roughly respects the map's structure" — it does **not** mean "this will sound good." Apply the judgment in `effects-routing.md`, `transitions-and-masking.md`, and `exit-design.md` yourself; don't treat a clean `validate()` result as musical approval.
