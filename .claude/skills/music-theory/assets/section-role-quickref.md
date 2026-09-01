# Section Role Quick Reference

Fast lookup — quote directly. Full rationale in `../references/song-form-and-sections.md`, `../references/energy-arcs-and-density.md`, `../references/hooks-and-highlights.md`.

| `SegmentName` | Typical density (0–10) | Cadence risk at its end | Hook likelihood |
|---|---|---|---|
| `intro` | 2–3 | Low — usually resolves or fades, not a hard boundary | Low, unless it carries the instrumental hook |
| `verse` | 4–5 | Medium — often HC or deceptive on purpose (keeps momentum into pre-chorus) | Low–medium |
| `pre-chorus` | 5–6 | **High** — designed to end on `V` of the chorus key; cutting its end is inherently cutting mid-tension | Low (it's transition machinery, not payoff) |
| `chorus` | 7–8 | Low–medium — often PAC/IAC, but pop sometimes avoids full resolution to stay propulsive | **High** — default hook location |
| `bridge` | 3–5 | Medium — often modulates, check the modulation caveat before assuming a clean boundary | Low–medium |
| `outro` / `ending` | 4→2 | Low — designed to resolve/fade | Low, unless it's a coda reprising the hook |
| `inst` | Variable — check `loudness_db` | Variable | Check — could be a solo (low hook value) or a drop/hook restatement (high) |

## One-line rule per column

- **Density**: use as a prior for the sequencing checks in `../references/energy-arcs-and-density.md`, not a hard constraint — always confirm against the actual `loudness_db`.
- **Cadence risk**: "High" means don't cut right at this section's natural end without checking the chord at the boundary (`../references/cut-points-and-cadences.md`); "Low" means the section's own ending is already built to be a safe cut point.
- **Hook likelihood**: a starting hypothesis for `../references/hooks-and-highlights.md`'s selection criteria, not a substitute for checking repetition/distinctiveness directly.
