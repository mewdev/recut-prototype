# Analysis Pipeline

Replace `testing/02/chicago.mp3` with your audio file path throughout.

---

## 1) allin1 (Modal GPU)

```
/Users/michal/miniconda3/envs/recut/bin/modal run modal_pipeline.py --path testing/02/chicago.mp3
```

Output: `testing/02/chicago-allin1.json`

---

## 2) h1zero (HuggingFace remote)

```
curl -X POST https://Izreals-h1zero-chord-detection.hf.space/analyze -F "file=@testing/02/chicago.mp3" | tee testing/02/chicago-h1zero.json
```

Slow — cold start can take a few minutes. Add `-v` to see progress.

---

Steps 1 and 2 can run in parallel.

---

## 3) Merge → full JSON map

```
/Users/michal/miniconda3/envs/recut/bin/python merge_analysis.py testing/02/chicago.mp3 testing/02/chicago-allin1.json testing/02/chicago-h1zero.json
```

Runs Basic Pitch internally (ONNX, ~30s). Output: `testing/02/chicago-full.json`
