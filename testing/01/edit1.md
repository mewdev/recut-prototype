# Edit 1 — Labour

## User Request
> "Ahoj, tak prosím nechej mi z té písničky jen část od 0:51 do 1:29, zbytek smazat."
> (Keep only 0:51–1:29, delete the rest.)

## Analysis
- **BPM:** 83 | **Key:** B minor | **Time sig:** 4/4
- Requested range: 51.0s – 89.0s (38s excerpt)
- Both points fall mid-verse (no natural segment boundary nearby)

## Cut Decision
Snap to nearest **beat** for clean rhythmic alignment:

| Point | Requested | Snapped to |
|-------|-----------|------------|
| In    | 0:51.000  | **0:51.15** (beat) |
| Out   | 1:29.000  | **1:29.01** (beat) |

- In point chord: G (verse, mid-phrase)
- Out point chord: Bm7 (verse, mid-phrase)
- Duration: **37.86s**

## No fade — hard cut at beat boundaries as requested.

## Output
`labour-edit1.mp3`
