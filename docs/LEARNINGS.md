# Learnings

Distilled rules from the improvement loop (`docs/IMPROVEMENT_LOOP.md`). Curated, not a log:
merge or remove lines instead of only appending; keep it under ~60 lines. Cutting agents
read it before cutting.

## Engine / levels
- The master limiter is transparent: audio under -1 dBTP passes bit-identical, only true-peak overs are pulled down locally. Keep the default master; don't remove it or replace it with a utility trim to "protect the original" (sessions: 20261118-fzsv, 20261118-ypag, 20261118-idzo; fix: PR fix/transparent-limiter)
- Sources are level-matched by the engine; don't add make-up gain on top (sessions: 20261118-jn7o; fix: #73)
