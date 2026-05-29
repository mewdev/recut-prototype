# Todo & Ideas

## Analysis
- [ ] Vocal position detection — detect where vocals are present/absent in a track.
      Needed for: smarter fade-out placement (avoid cutting mid-phrase/mid-word),
      better cut point selection, section labeling refinement.
      Tools to explore: pyannote.audio, Demucs vocal stem + energy envelope.

## Primitives
## Editing
## Pipeline
## Stems

-  allinone default stem demucs is fine for vocals, but the rest of stems could have better separation quality


## Documenting testing cases for cutting model traning:

- how to write training data which comes from documenting manual editing decisions — every intervention is a future training example. The reason field is the most important — it's where musical intelligence gets encoded.-