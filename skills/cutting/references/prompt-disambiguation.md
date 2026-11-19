# Prompt Disambiguation

Before building any composition, resolve ambiguity in the request. Most cutting prompts are underspecified. Wrong interpretation = wrong edit, and re-rendering audio is expensive — cheaper to ask or state an assumption up front.

## Common vague patterns

### "Shorten it from [timestamp]"
Ambiguous — does "from" mean:
- **A)** Keep from that point → end (trim the beginning), or
- **B)** Cut from that point → remove the tail

**Ask:** "Do you want to start the track at [timestamp], or end it there?"

**Signal:** if the user describes a repetition or loop at that point ("when the motif repeats"), they usually mean **start there** — the repetition is what they want to keep or escape from.

### "Shorten to [time], fade out" (e.g. "zkrátit cca na 3:15, do ztracena")
Two distinct edits:
- **A)** Keep the original timing and fade out at that time (a tail trim). Nothing before it moves.
- **B)** Remove material from the middle so the whole song fits the time, ending with its own fade.

**Default to A.** A target time plus "fade out" usually names the point where the music may stop, and
clients who dance, skate or perform to the track (school classes, dance groups) have a choreography set
to the original timing: an internal cut shifts every move after it. Evidence: ticket 20261119-qdor cut 8
bars of organ solo at 2:50 to keep the song's own fade (B); the client answered "the choreography is done
till 3:15, then fade out". Only use B when the request asks to keep the ending or says the length is a
hard limit with no fixed timing; say which one you built in `intent.json`.

For A, play the original to the first downbeat after the time and fade from there (2-4 bars), so the
fade starts after the given moment rather than eating into it.

### "Make it shorter"
**Ask:** where does it feel too long — beginning, end, or a section in the middle?

### "Creative ending"
This is not a fully-specified prompt — it's an invitation. Propose 2–3 concrete options from `exit-design.md` rather than picking one silently.

**Ask:** does the song have a natural loop or vamp at the end? What's the last musical event they want to land on?

### "Crossfade" (especially quoted from a DAW screenshot or reference doc)
When a user points at a marker labeled "CROSSFADE" in a screenshot or reference project, treat it as **an edit point, not a request for overlapping audio**. Default interpretation: a short click-fade (~10ms) at that point, not an `XFade` with a long blend — "crossfade" in casual/DAW usage often just means "the seam is here," not "blend these two sections." Confirm before assuming a longer `XFade` duration.

### "Cut when it repeats"
The user hears the repetition as the problem. Two distinct outcomes:
- End just before the repetition starts (keep the first pass only)
- Start at the repetition (use it as the body of a shorter version)

Clarify which before cutting.

## What to check before interpreting

1. **Segment labels** (`map-interpretation.md`) — does the mentioned timestamp fall near a loop/outro/repeat?
2. **Downbeats** — find the nearest bar-aligned point to any user-given timestamp.
3. **Song duration** — a timestamp near the middle usually means "keep one half"; near the end usually means "trim the tail."

## Rule

**Never build a composition from a vague prompt without stating your interpretation first.** Write it out: "I'm interpreting this as: keep from X, cut everything after Y." If wrong, the user corrects you before a render is wasted.
