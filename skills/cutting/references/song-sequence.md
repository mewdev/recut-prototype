# Song Sequence: one song after another

Requests like "play song A, then song B", "put these songs back to back" or "B follows when
A's natural end has dissolved". Often for dancers: they move to the last sound, so the next
song must come in as A's tail fades, not after an extra pause.

## The plan

Song A's clips, then song B's clips, on the `main` track. No `xfade` between the songs unless
a blend was asked for: A's own recorded tail *is* the transition. B usually starts at its
first section (index 1) with its own short lead-in kept.

## Where B enters: as A's tail fades

- **No pause asked = no dead air.** B enters when A's tail is about **-50 dBFS** (inaudible
  in a room), with a fraction of a second of silence at most. Never wait for -90 dB, and
  don't add a "breath" `gap` nobody asked for.
- **Count all the silence.** What the listener hears as the pause is: A's tail below -50 dB
  + any `gap` + **B's own lead-in** before its first sound. A 1.5 s `gap` on top of a 1 s
  quiet tail and a 0.3 s lead-in is ~3 s of dead air: operators rejected exactly that
  (20261118-5hiy, -ypag it2); the shipped versions had 0.5-1.4 s.
- **How to place it:** end A's clip inside its `silence` section (`beats` on the
  `silence#1` clip) at the point where the tail crosses -50 dB, or keep the whole section
  when its quiet part is short. `song_change_gap` in `recut ticket render` reports the
  measured silence at every song change ("1.4 s of audible silence: 1.1 s tail + 0.0 s
  between the clips + 0.3 s lead-in") and warns above 2 s. Use its numbers; write them in
  `plan.notes`.
- **Don't fake joins to quiet the checks.** A song change is not a beat-matched join: the
  linter skips `downbeat`, `phrase_align`, `key_compat`, `bpm_gap`, `loudness_jump` and
  `qc_gain_jump` there. Never insert a tiny `gap` to silence them.

## When a pause is asked for

- **A pause asked in seconds is the audible silence.** If A already ends in a rest or a
  decaying tail, that counts: `gap length` = requested pause − the quiet A's clip already
  keeps − B's lead-in. Check the `song_change_gap` number against the request (it warns above
  2 s: expected here, say so in the notes).
- Say in `plan.notes` how you read "pause" (total silence vs. added time) so the operator can
  flip it if the client meant the other.
- Use a `gap` node: `{"id": "p1", "type": "gap", "length": "5s"}`. Return tails keep ringing
  through it. Nothing joins across a gap, so no splice checks run there; `song_change_gap`
  still measures it.

## Levels

Songs from different records are level-matched by the engine (one integrated loudness), so
don't add clip gain to "match" them. The master limiter only touches true-peak overs; keep it.
