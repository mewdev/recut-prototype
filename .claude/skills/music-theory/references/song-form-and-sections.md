# Song Form and Sections

What each section type is actually *for*. This is recognition, not construction — you're reading an existing recording's structure, then deciding what a short edit needs to keep to still function as a song.

## Mapped to recut's `SegmentName`

recut's map only labels `intro | verse | pre-chorus | chorus | bridge | inst | outro | silence | interlude | ending` (`src/recut/map/schema.py`). Some section concepts below (post-chorus, drop, build, breakdown) are common and useful mental models but **have no corresponding `SegmentName`** — they're sub-segment phenomena you infer from `loudness_db`/`phrases` inside a labeled segment (often inside `chorus` or `inst`), not a label the map hands you directly.

## What each section does

| Section | Function | Typical shape |
|---|---|---|
| `intro` | Establishes key, tempo, groove, sometimes the hook; "earns" attention | Often instrumental; modern intros trend short (1–4 bars) |
| `verse` | Tells the story, gives information, lower tessitura, more syllabically dense | Same melody each time, different lyrics |
| `pre-chorus` | **Pure transition machinery** — exists to deliver the listener to the chorus, not for its own content | Rising tessitura, increasing density, harmonically leans toward chorus's `V` |
| `chorus` | The hook. Same melody+lyrics each time. The structural payoff, what listeners remember | Higher tessitura, denser, often contains the title |
| `bridge` | Contrast and relief before the final chorus; new emotional angle; sometimes modulates | Different melody/lyrics/chords; sometimes thinner arrangement to set up an elevated final chorus |
| `outro` / `ending` | Releases tension | Fade, tag/vamp, or a contrasting coda |
| `inst` | Instrumental passage — could be functioning as a drop, a solo, or a breakdown depending on density (see `energy-arcs-and-density.md`) | Check `loudness_db`/`phrases` to tell which |
| `interlude` | Brief connective material between named sections | Usually short, low structural weight |
| `silence` | Literal gap | Not a musical section — don't treat as content |

## Failure modes for a short edit — what breaks if a section is cut without its neighbor

- **Cutting straight into a `chorus` without its `pre-chorus`**: the arrival feels sudden/unearned — the pre-chorus's entire job was to make this feel prepared. If you must cut the pre-chorus for length, consider whether the chorus can survive the loss (a fine trade in many short edits) or whether a quick `XFade` softens the jump.
- **Cutting a `bridge` in without its lead-in `chorus`**: the bridge is defined by contrast — contrast against nothing reads as just "a different song started."
- **Final `chorus` not elevated**: if the source recording's last chorus is meant to feel bigger (modulation, added vocals, fuller arrangement) and your edit's final section is an earlier, smaller chorus instead, the edit's ending will undersell relative to what the full song does.
- **Too many sections**: most songs run 5–8 sections; a short edit assembled from more than a handful of sections stitched together starts to feel like a medley, not an edit of one song.

## Standard verse-chorus skeleton (for reference)

```
intro → verse → pre-chorus → chorus → verse → pre-chorus → chorus → bridge → chorus → outro
```

Modern pop variants add a post-chorus hook after each `chorus` (still labeled `chorus` or `inst` in recut's map, not its own `SegmentName`) and sometimes elevate the final chorus with a key change. Recognizing this skeleton in a source song tells you which section is expendable (a repeated verse, most bridges) versus load-bearing (the first full verse+chorus pair, the final chorus) when compressing to a short edit.

## Common pitfalls

- Don't assume every song follows verse-chorus form — strophic (all verses, no chorus) and through-composed songs exist and won't fit this skeleton; check the actual segment sequence before assuming a shape.
- Don't treat `bridge` as automatically skippable — in some songs it's the emotional peak, not filler.
- A repeated `verse`/`chorus` pair (`index=2`) is often near-identical content to `index=1` — a strong candidate to drop for length without losing the song's function, unless the lyrics/arrangement meaningfully differ.
