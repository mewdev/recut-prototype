# Learnings

Distilled rules from the improvement loop (`docs/IMPROVEMENT_LOOP.md`). Curated, not a log:
merge or remove lines instead of only appending; keep it under ~60 lines. Cutting agents
read it before cutting.

## Engine / levels
- The master limiter is transparent: audio under -1 dBTP passes bit-identical, only true-peak overs are pulled down locally. Keep the default master; don't remove it or replace it with a utility trim to "protect the original" (sessions: 20261118-fzsv, 20261118-ypag, 20261118-idzo; fix: #82)
- Sources are level-matched by the engine; don't add make-up gain on top (sessions: 20261118-jn7o; fix: #73)

## Song sequences and joins
- Songs back to back with no pause asked: the next song enters as the previous tail crosses about -50 dBFS. Count tail + gap + the next song's lead-in; shipped cuts had 0.5-1.4 s, rejected ones ~3 s. `song_change_gap` measures it (sessions: 20261118-5hiy, 20261118-ypag; fix: #83)
- A song change and a contiguous join (the song plays on) are not edits: no downbeat/key/bpm/phrase/jump checks there, so never add a fake 10 ms gap to quiet them (sessions: 20261118-5hiy, 20261118-ypag, 20261118-fwmf; fix: #83)
