# Skill: Prompt Disambiguation

Before executing any cut, resolve ambiguity in the user prompt. Most cutting prompts are underspecified. Wrong interpretation = wrong edit.

---

## Common Vague Patterns

### "Shorten it from [timestamp]"
**Ambiguous:** does "from" mean:
- A) Keep from that point → end (trim the beginning)
- B) Cut from that point → remove the tail

**Ask:** "Do you want to start the track at [timestamp], or end it there?"

**Signal:** if the user describes a repetition or loop at that point ("when the motif repeats"), they usually mean **start there** — the repetition is what they want to keep or escape from.

### "Make it shorter"
**Ask:** Where does it feel too long? Beginning, end, or a section in the middle?

### "Creative ending"
**This is not a prompt — it's an invitation.** The user wants you to propose something. Do not execute blindly.

**Ask:** Does the song have a natural loop or vamp at the end? What's the last musical event they want to land on?

### "Cut when it repeats"
The user hears the repetition as the problem. Options:
- End just before the repetition starts (keep the first pass only)
- Start at the repetition (use it as the body of a shorter version)

**Clarify which before cutting.**

---

## What to Read Before Interpreting

1. **Segment labels** — do they suggest a loop or outro near the mentioned timestamp?
2. **Downbeats** — find the nearest bar-aligned point to the user's timestamp
3. **Song duration** — if the timestamp is near the middle, the user probably wants to keep one half. If near the end, they want to trim the tail.

---

## Rule
**Never execute an edit on a vague prompt without stating your interpretation explicitly first.**
Write it in the plan: "I'm interpreting this as: keep from X, cut everything after Y."
If wrong, the user corrects you before you waste iterations.
