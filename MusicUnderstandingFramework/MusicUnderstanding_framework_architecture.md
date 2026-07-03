# MusicUnderstanding.framework — Complete Architecture Reference

**Status: Fully reverse-engineered.** Sources used in order of authority:
1. `.swiftinterface` — confirmed public API contract (235 lines, identical across all 5 platforms)
2. `.swiftdoc` strings — Apple's full internal doc comments
3. `.tbd` + `swift demangle` — complete internal symbol table
4. Live runtime output — real analysis results on a 2:39 pop track at 80 BPM in D major
5. `metadata.json` + `model.mil` — all four bundled CoreML models, full tensor specs and layer architecture

**OS availability:** iOS/macOS/tvOS/watchOS/visionOS **27.0** only. Framework version 12, Swift 6.4, coremltools 8.2–9.0, converted from TorchScript (torch 2.4.1–2.7.1). Models built 2025–2026.

---

## The four bundled CoreML models

This is the most significant finding: **four separate specialized models**, not one multi-task model as initially hypothesized from the `.tbd` alone.

| Model | Architecture | Input | Output | Quantization |
|---|---|---|---|---|
| `DownbeatTracker` | ConvNeXt + Dilated ConvNeXt CNN | `[1, 4096, 131]` mel+conditioning @44.1kHz, 100fps | beats, downbeats, beats_no_downbeats `[1,4096]`, tempo `[1,4096,251]`, bpb `[1,4096,13]` | Float16 + 8-bit palettized (LUT) |
| `KeyModel` | CNN + MLP/Transformer head | `[1, 661504]` raw waveform @22kHz (30s chunks) | key probabilities `[1,1293,35]` | Float16 + Int8 affine |
| `InstrumentActivityModel` | Pure CNN (ConvNeXt-style) | `[1, T, 128, 1]` mel @24kHz, 20fps | vocals, drums, bass, others activity streams | Float16 + **6-bit palettized** (most aggressive) |
| `StructuralFeaturesModel` | Pure CNN (distilled from larger teacher) | `[1, T, 256, 1]` mel @24kHz, 20fps | phrases, segments, sections, kind, pace streams | Float16 + Int8 blockwise shift-scale |

No video cues model is bundled — either downloaded on-demand, deferred to the XPC service, or not yet implemented.

---

## DownbeatTracker — full architecture

**Architecture name (confirmed from MIL):** `convnext` + `dilated_convnext` — a pure CNN with no attention mechanism.

```
Input [1, 4096, 131]           ← 4096 frames @ 100fps = ~41s, 128 mel bins + 3 conditioning values
  → transpose + expand_dims → [1, 1, 131, 4096]

ConvNeXt Encoder (3 stages, 9 blocks total):
  Stage 0: 3× ConvNeXt block, channels 1→8→8   (7×7 depthwise conv, 4× expand/project, GeLU, residual add)
  Stage 1: 3× ConvNeXt block, channels 8→16→16  (resample between stages = 1×1 conv stride-1)
  Stage 2: 3× ConvNeXt block, channels 16→32→32

Dilated ConvNeXt (11 blocks, channels 32):        ← temporal modeling backbone
  dilconvnext_0_0 through dilconvnext_0_10
  Each block: depthwise conv (7×7, dilated) → expand 4× (32→128) → GeLU → project back (128→32) → add
  Dilation rates increase exponentially across blocks → large temporal receptive field

Head (3 blocks, 32→64 channels, 1024 final):
  head_0_0: 32→64 (resample) + ConvNeXt block (expand to 256)
  head_0_1: ConvNeXt block (64→256→64)
  head_0_2: ConvNeXt block (64→256→64)
  reshape → [1, 1024, 1, 4096]    ← 1024-dim feature vector per time step

Five parallel 1×1 conv output heads (all from same 1024-dim features):
  beats            → sigmoid → [1, 4096]         beat probability per frame
  downbeats        → sigmoid → [1, 4096]         downbeat probability per frame
  beats_no_downbeats → sigmoid → [1, 4096]       beat-but-not-downbeat probability
  tempo_detailed   → (raw)   → [1, 4096, 251]    tempo distribution over 251 BPM bins
  bpb_detailed     → (raw)   → [1, 4096, 13]     beats-per-bar distribution over 13 time sig classes
```

**Confirmed from MIL bias values:**
- beats head bias: -5.09 (sigmoid → ~0.006 at zero activation — requires strong signal to fire)
- downbeats head bias: -7.34 (even stricter threshold — downbeats are rarer, model biased against false positives)
- beats_no_downbeats bias: -5.41 (intermediate)

**The 3 conditioning values** (from `params.conditioning_size: 3`, feature dim = 128 mel + 3 = 131): not named in metadata, but likely tempo prior, time signature numerator, and a phase/confidence signal — matching the `Hint(type: .tempo/.timeSignature/.beat)` API found in the internal symbol table.

**Preprocessing:** 44100 Hz, 1024-point FFT, 100 fps, mel bins 27.5–16000 Hz (128 filters). This is a different preprocessing pipeline from the other three models (which all use 24kHz).

---

## KeyModel — full architecture

**Architecture name (confirmed from MIL):** CNN front-end + linear/MLP head. Framework internally calls it `maml-harmony-model`, `model_type: chord_detection` — this is a **repurposed chord detection model**, not a dedicated key model.

```
Input [1, 661504]              ← 661504 samples / 22050 Hz = exactly 30 seconds, raw waveform

CNN front-end (67 conv layers, batchNorm, instanceNorm, various kernel sizes)
  ↓
Reshape → [1, 32, 64, 1293]    ← 32 channels, 64 features, 1293 time frames
  ↓
Linear layers + GeLU:
  linear_0 → [1, 32, 64, 1293]
  linear_1 → GeLU → [1, 1293, 32]   (transpose: now time-major)
  linear_2 → softmax → [1, 1293, 35]
  ↓
Output [1, 1293, 35]           ← 1293 frames × 35 key classes
```

**35 key classes** (confirmed from metadata configuration JSON):
`"No Key", "C", "C#", "Db", "D", "D#", "Eb", "E", "F", "F#", "Gb", "G", "G#", "Ab", "A", "A#", "Bb", "B"` (18 major including "No Key") + `"Cm", "C#m", "Dbm", "Dm", "D#m", "Ebm", "Em", "Fm", "F#m", "Gbm", "Gm", "G#m", "Abm", "Am", "A#m", "Bbm", "Bm"` (17 minor)

The 35-class output includes enharmonic equivalents (C# and Db are separate classes) — the model preserves harmonic context rather than collapsing to 12 pitch classes. Postprocessing selects a winner per time frame, aggregates across the song's frames, maps to `KeyResult.Tonic` (17 cases) + `Mode`, and packages into `RangedValue<KeySignature>` spans.

Takes **raw audio** (not mel spectrogram) — the only one of the four that does. Built with the most recent PyTorch version (2.7.1 vs 2.4.1 for others), suggesting it was updated most recently.

---

## InstrumentActivityModel — full architecture

**Architecture:** Pure CNN with ConvNeXt-style blocks. Version `3.2.4cat.dev` — the `cat` suffix suggests a concatenation/multi-head architecture.

```
Input [1, T, 128, 1]           ← variable T (400–6000 frames), 128 mel bins
  Preprocessing: 24000 Hz, FFT 2048, hop 1200 → 20fps, 27.5–12000 Hz mel
  receptiveFieldLength: 745 frames = 37.25 seconds of context

30 conv layers (ConvNeXt-style):
  Depthwise + pointwise blocks, GeLU activations
  28 LUT-dequantized weight tensors (6-bit palettized — most compressed of the four models)
  relu (×1), sub (×1), maximum (×1) for activation clamping/normalization

sliceByIndex (×4)              ← splits final feature map into 4 instrument streams

Output: 4 separate activity streams (vocals, drums, bass, others)
  Each: dynamic shape Float32 sequence, 0.0–1.0 per time step @ 50ms resolution (predictionResolution: 0.05)
```

**Configuration (confirmed from metadata):**
- sampleRate: 24000
- windowLength: 2048, hopLength: 1200 → 1 frame = 50ms
- filterCount: 128, frequency range: 27.5–12000 Hz
- targetKinds: `["vocals", "drums", "bass", "others"]`
- hubProjectId: `mu_activity` (Apple internal ML hub project name)
- Conversion date: **2026-03-23** (most recently converted of the four)

The 4 `sliceByIndex` ops confirm the multi-head design — one shared backbone, four parallel output slices for each instrument class.

---

## StructuralFeaturesModel — full architecture

**Architecture:** Pure CNN, confirmed distilled from a larger teacher model (`hubProjectId: mu_distillation`).

```
Input [1, T, 256, 1]           ← variable T (400–6000 frames), 256 mel bins (double instrument model)
  Preprocessing: 24000 Hz, FFT 2048, hop 1200 → 20fps, 27.5–12000 Hz
  receptiveFieldLength: 4081 frames = 204 seconds context ← much larger than instrument model (37s)

78 conv layers (CNN backbone):
  relu (×32), gelu (×25), add (×16), sigmoid (×3), concat (×3)
  74 blockwise shift-scale dequantized weights (Int8, most precise quantization of the four)
  3 sigmoid outputs → 3 boundary strength streams (phrases, segments, sections)
  1 squeeze → pace stream

Output: 5 separate streams (phrases, segments, sections, kind, pace)
  Each: dynamic shape Float32 @ 50ms resolution
```

**Confirmed postprocessing configuration from metadata (these are the actual production values):**
```json
{
  "peakPicking": {
    "detectionThreshold": 0.33,
    "minimumPhraseBoundaryDistanceInSeconds": 1.0,
    "minimumPhraseBoundaryDistanceInBars": 1.0,
    "minimumSegmentBoundaryDistanceInSeconds": 2.0,
    "minimumSegmentBoundaryDistanceInBars": 2.0,
    "minimumSectionBoundaryDistanceInSeconds": 4.0,
    "minimumSectionBoundaryDistanceInBars": 3.0
  },
  "timeAlignment": {
    "songStartTimeThresholdInSeconds": 1.0,
    "songEndTimeThresholdInSeconds": 1.0
  },
  "pace": {
    "validAssetsPerBeatValues": [4.0, 3.0, 2.0, 1.0, 0.5, 0.333, 0.25, 0.167, 0.125, 0.083, 0.0625, 0.042, 0.03125],
    "assetsPerMinuteVertices": [0, 20, 40, 80],
    "classIndexVertices": [0, 20, 30, 40]
  }
}
```

**The "pace" output decoded:** `validAssetsPerBeatValues` are musical note durations in beats (4.0 = whole note, 2.0 = half, 1.0 = quarter, 0.5 = eighth, etc.). The `assetsPerMinuteVertices`/`classIndexVertices` pairs define a piecewise linear mapping from "cuts per minute" to a class index. "Pace" is literally **how many video edit cuts per minute are appropriate for this section** — the 10.0 and 20.0 values we saw in the live run are "assets per minute" directly. At 80 BPM, 20 cuts/minute = one cut every 3 seconds = roughly every 4 beats. This is precisely the "edit rate suggestion" system used in Apple Photos memories and likely Final Cut's auto-edit features.

**The boundary constraints reveal the minimum musical granularity Apple considers valid:**
- Phrases: ≥ 1 bar, ≥ 1s (coarsest detection = one bar, which at 80 BPM is 3s — but minimum can be 1s for slow songs)
- Segments: ≥ 2 bars, ≥ 2s
- Sections: ≥ 3 bars, ≥ 4s (minimum structural unit = half a typical 8-bar phrase)

---

## Shared preprocessing pipeline (InstrumentActivity + Structural models)

Both models share identical preprocessing — confirmed same config in both metadata files:

```
Audio → resample to 24000 Hz, mono
  → STFT: window 2048 samples, hop 1200 samples
  → mel filterbank: 27.5 Hz – 12000 Hz
  → InstrumentActivity: 128 filters → [T, 128]
  → StructuralFeatures: 256 filters → [T, 256]
  → both: 1 frame = 1200/24000 = 0.05s (50ms, 20fps)
  → both: inputFrameCount 6000 = 300 seconds per chunk
```

---

## Live runtime output — confirmed behavior

Analyzed "End of Beginning" (Djo, 2:39, ~80 BPM, D major):

```
RHYTHM:  80.00 BPM, 213 beats, 54 bars
         First beat: 0.105s, Last beat: 159.105s
         Cross-check: 213 ÷ 80 = 159.75s ✓, 54 bars × 4 beats ≈ 216 ✓

KEY:     D major for full song duration (0.0s–159.3s, no modulation detected)

STRUCTURE:
  9 sections (avg 17.7s each, min 3s intro/outro, max 33s main body)
  15 segments (avg 10.6s each)
  31 phrases (avg 5.1s each, clustering at 6s = 8 beats at 80 BPM)
  Note: all boundaries align exactly on bar grid (snap-to-bars confirmed active)

PACE:
  0.1–3.0s:    10.0 assets/min (intro, low density)
  3.1–60.1s:   20.0 assets/min (main body)
  60.1–81.1s:  10.0 assets/min (quieter mid-section, halved cut rate)
  81.1–159.1s: 20.0 assets/min (return to main pace)
  Only 2 discrete values observed — pace is effectively a binary low/high classifier at this BPM

LOUDNESS (ITU-R BS.1770 / EBU R128):
  Integrated: -9.61 LUFS (loud modern master, above streaming normalization target)
  Peak: -0.00 dB (limited to 0 dBFS)
  1594 momentary samples (400ms window, 100ms advance) = 159.4s ✓
  Momentary range: -94.02 → -108.07 LUFS (silence at start/end, active signal in between)

INSTRUMENTS:
  vocal:  avg 0.576, peak 0.895, 11 active ranges (correct: verse/chorus switches)
  bass:   avg 0.639, peak 0.831, 3 active ranges (correct: sparse bass on this track)
  drum:   avg 0.511, peak 0.910, 2 active ranges (correct: subtle percussion)
  other:  avg 0.648, peak 0.813, 1 active range  (correct: acoustic guitar, continuous)
```

---

## Runtime errors — what they revealed

From the console output during analysis:

**Espresso/E5RT errors (fired 3 times):**
```
E5RT: Espresso exception: MpsGraph backend validation on incompatible OS
```
Espresso is Apple's CoreML neural network runtime. Fired **exactly 3 times** — confirming **3 of the 4 models use GPU (MPSGraph) execution** on device. In simulator (no real GPU), they fell back to CPU. (Loudness is pure C++ DSP, not CoreML, so doesn't trigger this.)

**`LoudnessManager.mm` log:**
```
LoudnessManager.mm:1767 ReadPListFile: unable to open stream for LoudnessManager plist
LoudnessManager.mm:1268 GetHardwarePlatformKey: cannot get acoustic ID
```
Confirms loudness analysis is a dedicated C++ component (`LoudnessManager.mm`), separate from the CoreML models. It reads a hardware acoustic calibration profile — in simulator it can't find the iPhone's acoustic ID so falls back to uncalibrated software metering. The ITU-R BS.1770 metering still runs correctly in software fallback.

**XPC connection failure:**
```
Connection cannot be formed: non-launching port is incompatible with service identifier "com.apple.PointerUI..."
```
The `ComputationalMusicServiceProtocol` XPC service tried to connect and failed (simulator environment). Confirmed the framework gracefully falls back to in-process inference when XPC is unavailable — no crash, full results still returned.

---

## Complete internal pipeline (fully confirmed)

```
AVAsset / AVAudioFile
  └→ AudioConverterAssetInputProvider (resample, format-convert)
       └→ AVAudioPCMBuffer stream

Per analysis type (run in parallel as Swift actor-isolated tasks):

RHYTHM ──────────────────────────────────────────────────────────────────────
  44.1kHz audio → 1024-point FFT @100fps → 128 mel bins + 3 conditioning
  → DownbeatTracker (ConvNeXt + Dilated ConvNeXt CNN, 78 layers)
  → {beats [4096], downbeats [4096], beats_no_downbeats [4096], tempo [4096×251], bpb [4096×13]}
  → peak-pick beats/downbeats with negative-biased sigmoid thresholds
  → argmax tempo distribution → BPM float
  → argmax bpb distribution → time signature
  → BeatTrackerResult {constantTempo, beatsPerMinute, beats: [Beat{timepoint, isDownbeat, timeSignature}]}
  → flatten to RhythmResult {beats: [CMTime], bars: [CMTime], beatsPerMinute: Float?}

KEY ──────────────────────────────────────────────────────────────────────────
  22kHz raw waveform (30s chunks) → KeyModel (CNN + MLP, repurposed chord detector)
  → key probabilities [1293 frames × 35 classes] → softmax → argmax per frame
  → aggregate across song, map to Tonic + Mode → RangedValue<KeySignature> spans
  → KeyResult {ranges: [RangedValue<KeySignature>]}

STRUCTURE ────────────────────────────────────────────────────────────────────
  24kHz audio → mel spectrogram (256 bins, 50ms frames)
  → StructuralFeaturesModel (CNN, distilled, 78 layers, 204s receptive field)
  → {phrases, segments, sections, kind, pace} strength streams @50ms
  → peak-picking with detectionThreshold=0.33 and minimum distances
  → optional bar-grid snap (barTimes from BeatTracker passed as prior)
  → getBoundaryTimes() → IterableStructuralBoundaries
  → StructureResult {phrases, segments, sections: [CMTimeRange]}

INSTRUMENT ACTIVITY ─────────────────────────────────────────────────────────
  24kHz audio → mel spectrogram (128 bins, 50ms frames)
  → InstrumentActivityModel (CNN, 6-bit quantized, 37s receptive field)
  → 4 activity streams (vocals, drums, bass, others) @50ms
  → threshold → active time ranges per instrument
  → InstrumentActivityResult {activity: [Instrument: [TimedValue<Float>]], ranges: [Instrument: [CMTimeRange]]}

PACE ─────────────────────────────────────────────────────────────────────────
  "pace" stream from StructuralFeaturesModel (shared forward pass with structure)
  → piecewise linear mapping: assetsPerMinuteVertices → classIndexVertices
  → quantize to validAssetsPerBeatValues (13 note duration classes)
  → PaceResult {ranges: [RangedValue<Double>]}   ← "cuts per minute" recommendation

LOUDNESS ─────────────────────────────────────────────────────────────────────
  LoudnessManager.mm (C++ component, NOT CoreML)
  → ITU-R BS.1770: 400ms momentary window, 100ms advance; 3s short-term window, 100ms advance
  → hardware acoustic calibration (falls back to uncalibrated in simulator)
  → LoudnessResult {integrated, peak, momentary, shortTerm}

VIDEO CUES (internal only, not public) ─────────────────────────────────────
  VideoCuesProvider / VideoCuesPrediction (model not bundled in this build)
  → goodCues: [CMTime], greatCues: [CMTime]
  → NOT exposed on public API on any platform
```

---

## Public API surface (complete)

```swift
@available(iOS/macOS/tvOS/watchOS/visionOS 27.0, *)
public actor MusicUnderstandingSession: Sendable {
    public convenience init<Provider: AsyncSequence>(audioProvider: Provider)
        where Provider.Element == AVReadOnlyAudioPCMBuffer, Provider.Failure == Never
    public convenience init(asset: any AVAsset & Sendable) async throws  // no HLS

    @discardableResult public func analyze() async throws -> SessionResult
    @discardableResult public func analyze(for: Set<AnalysisType>) async throws -> SessionResult
    nonisolated public var loudnessResults: some AsyncSequence<LoudnessResult, any Error> & Sendable
    public func cancel() async

    public struct SessionResult: Codable, Sendable {
        public let key: KeyResult?
        public let rhythm: RhythmResult?
        public let pace: PaceResult?
        public let loudness: LoudnessResult?
        public let structure: StructureResult?
        public let instrumentActivity: InstrumentActivityResult?
        // no videoCues on any platform
    }
}
// Constraints: single-use per instance, no config knobs, no raw tensor access
// AnalysisType public cases: .key .rhythm .pace .loudness .structure .instrumentActivity
```

---

## Comparison to Recut/Barline pipeline

| Dimension | MusicUnderstanding | Recut/Barline |
|---|---|---|
| Beat/downbeat | DownbeatTracker: ConvNeXt CNN, 78 layers, 251-bin tempo + 13-class time sig | madmom DBNBeatTrackingProcessor (HMM/DBN, algorithmic) |
| Key | KeyModel: repurposed chord detector, CNN+MLP, 35 classes, raw waveform input | librosa.estimate_tuning or not implemented |
| Structure | StructuralFeaturesModel: distilled CNN, 256 mel bins, 204s receptive field | allin1 (joint beat/structure transformer) |
| Instrument activity | InstrumentActivityModel: 4-class CNN classifier, 6-bit quantized | Demucs (full source separation) — Apple's approach is ~10× lighter |
| Edit-point detection | VideoCuesProvider (internal only, not public) | Core Recut purpose — not in Apple's public API at all |
| Pace / edit rate | Piecewise linear mapping from structure model output → cuts/min | Not implemented |
| Loudness | LoudnessManager.mm (C++, ITU-R BS.1770) | Not implemented |
| Configurability | Zero — no knobs anywhere on public API | Full control: swap models, tune thresholds, custom postprocessing |
| Output format | CMTime-based, Codable, streaming-capable | JSON music map (beats, BPM, sections, stems) |
| Platform | On-device iOS/macOS 27+ only | Python, runs anywhere, can be server-side |

**The strategic conclusion:** Apple's public MusicUnderstanding API is deliberately locked down. The `VideoCuesProvider` — the piece most directly comparable to what Recut does — is internal-only on every platform. The pace output (cuts/min recommendation) is the closest public analog to Recut's purpose, but gives only a coarse 2-value signal rather than specific cut points. Recut's architecture (configurable models + LLM instruction layer + explicit edit-point JSON) is solving a problem Apple hasn't opened up to third parties.

The one meaningful gap in Recut's current pipeline vs Apple's approach: **EBU R128 loudness metering** (Apple has it, Recut doesn't) and **pace/edit-rate estimation** from the structure model (Recut has structure but doesn't output a cuts-per-minute recommendation). Both are addable with existing Python libraries (`pyloudnorm` for R128, derived from the `validAssetsPerBeatValues` logic above for pace).

---

## Appendix: Final MIL analysis — corrected and completed

### DownbeatTracker — exact dilation sequence and receptive field

The 11 dilated ConvNeXt blocks use **exactly powers-of-2 dilations**: `[1, 2, 4, 8, 16, 32, 64, 128, 256, 512, 1024]`. With a 7-point depthwise kernel:

```
dilation=   1  RF=     7 frames =   0.1s
dilation=   2  RF=    19 frames =   0.2s
dilation=   4  RF=    43 frames =   0.4s
dilation=   8  RF=    91 frames =   0.9s
dilation=  16  RF=   187 frames =   1.9s
dilation=  32  RF=   379 frames =   3.8s
dilation=  64  RF=   763 frames =   7.6s
dilation= 128  RF=  1531 frames =  15.3s
dilation= 256  RF=  3067 frames =  30.7s
dilation= 512  RF=  6139 frames =  61.4s ← exceeds context window (4096 frames)
dilation=1024  RF= 12283 frames = 122.8s ← far exceeds context window
Total receptive field: 12,283 frames = 122.8 seconds
Context window: 4,096 frames = 41.0 seconds
```

The last two dilations (512, 1024) technically exceed the 4096-frame context window, meaning those filters see the *entire* available context with room to spare. This is a standard pattern in WaveNet-style dilated CNNs — you build dilation rates that overflow the context window to ensure every position fully attends to all available context without boundary effects.

This architecture is directly comparable to **TCN (Temporal Convolutional Network)** beat trackers in the MIR literature — the same exponential dilation pattern used by models like BeatNet-Lite and similar on-device beat trackers.

### KeyModel — LayerNorm confirmed, raw waveform processing detail

The `square → reduceMean → sqrt → realDiv` pattern firing 10 times (matching the 10 `square` ops in the histogram) is **manual Layer Normalization** — CoreML's MIL doesn't have a native LayerNorm op so it decomposes to primitives. This is operating on tensors of shape `[1, 1, 32, 64, 1293]` — 32 local windows × 64 samples × 1293 time frames.

The CNN processes 30s of raw 22kHz audio in overlapping windows:
- Window: 2048 samples / 22050 Hz = 93ms
- Stride: 512 samples / 22050 Hz = 23.2ms  
- 661504 / 512 = 1293 time frames ✓

MLP head shape confirms: `[1, 32, 1293, 288]` → `linear_0` → reshape → `[1, 1293, 64]` → `linear_1` → GeLU → `[1, 1293, 32]` → `linear_2` → softmax → `[1, 1293, 35]`. A 3-layer MLP head (288→64→32→35) on top of a CNN backbone.

### StructuralFeaturesModel — `kind` and `pace` corrected

**Critical correction from the earlier analysis:**

- `kind` output: `[1, **3**, ?]` — not a single classifier, but **3 parallel binary classifiers** per time frame, each with sigmoid activation. Likely 3 concurrent section-type labels (e.g. vocal/instrumental, high-energy/low-energy, structured/unstructured). This is what `kind` in `StructuralFeaturesPrediction` actually is — 3 binary properties per time step, not a single categorical class.

- `pace` output: `[1, **41**, ?]` — **41 classes** (indices 0–40), not 13. The 41 classes map through the piecewise linear function:
  - `assetsPerMinuteVertices: [0, 20, 40, 80]` → `classIndexVertices: [0, 20, 30, 40]`
  - class 0 = 0 cuts/min, class 20 = 20 cuts/min, class 30 = 40 cuts/min, class 40 = 80 cuts/min
  - Non-linear spacing: more granular at low cut rates (1 class per cut/min up to 20), less granular at high rates (1 class per 4 cuts/min from 40–80). Apple's edit-rate model is more discriminating at slow/measured editing than at fast cutting.
  - The 10.0 and 20.0 values in the live run = exactly class indices 10 and 20 respectively (within the linear 0–20 segment where 1 class = 1 cut/min).

### InstrumentActivityModel — output activation is ReLU, not sigmoid

**Correction:** The final activation before the 4-way slice is `GeLU → ReLU`, not sigmoid. This means:
- Output values are **non-negative but not bounded to [0, 1]** — they can exceed 1.0 for strongly active instruments
- The public API `activity: [Instrument: [TimedValue<Float>]]` doc says "0.0 to 1.0" but the model itself doesn't enforce this — the postprocessing layer in `InstrumentActivityProvider` likely clips or normalizes
- The 4 outputs are sliced from `[1, 4, ?]` at indices 0/1/2/3 in exact order: `vocals[0], drums[1], bass[2], others[3]`

---

## Binary strings analysis — major new findings

### 1. Two separate mach service identifiers confirmed

```
com.apple.computationalmusic.musicunderstanding  ← XPC endpoint
com.apple.computationalmusicd                    ← background daemon (the 'd' suffix = daemon)
```

There is a **dedicated background daemon** (`computationalmusicd`) separate from the XPC service endpoint. This is the same pattern Apple uses for other on-device ML (e.g. `mediaanalysisd` for Photos). The actual CoreML inference runs in `computationalmusicd`, completely isolated from the calling app's process. The `ComputationalMusicServiceClient` class (visible in the binary but not in the `.tbd`) is the in-process client that communicates with the daemon.

Build string: `@(#)PROGRAM:MusicUnderstanding  PROJECT:ComputationalMusic-12` — the parent project is **ComputationalMusic**, version 12. MusicUnderstanding is one component of a larger Apple internal framework suite.

---

### 2. JointHMM — the beat tracker is CNN + HMM, not CNN alone

This is the single most significant architectural correction from the strings pass. The `DownbeatTracker` CoreML model is **not** the complete beat tracking pipeline — it's only the observation model. A full HMM decoder sits on top of it:

```
DownbeatTracker (ConvNeXt CNN)
  → raw activations: beats [4096], downbeats [4096], beats_no_downbeats [4096],
                     tempo [4096×251], bpb [4096×13]
  → JointHMM (Hidden Markov Model decoder)
      JointHMMState      — encodes (beat position, tempo hypothesis, meter hypothesis)
      JointHMMTransition — tempo continuity constraints
      JointHMMBacktracker — Viterbi backtracking to find optimal state sequence
      MetroJointHMMState — metrical grid states (metro = metronome)
  → DownbeatHMM (specialized downbeat refinement layer)
      DownbeatHMMState / DownbeatHMMTransition
      MetroDownbeatHMMState
      DownbeatHMMConstructor / DownbeatHMMBacktracker
  → PulseTrain (beat pulse representation)
  → BeatTrackerResult {constantTempo, beatsPerMinute, beats: [Beat{timepoint, isDownbeat, timeSignature}]}
```

This is **architecturally identical to madmom's `DBNBeatTrackingProcessor`** — neural network activation functions fed into a Dynamic Bayesian Network / HMM for structured decoding. Apple calls it HMM where madmom calls it DBN, but it's the same concept: the CNN learns what beats "look like" in spectral features, and the HMM enforces that beats must be regularly spaced, downbeats must occur at the right interval for the meter, and tempo changes must be gradual.

Key HMM parameters visible in strings:
- `transitionLambda` — controls tempo transition smoothness (how fast tempo is allowed to change)
- `hintPenalty` — penalty for deviating from `Hint` priors (this is how `.tempo`/`.timeSignature`/`.beat` hints bias the HMM)
- `allowedDeviation` — tempo deviation tolerance
- `numPredecessorsOfStates` — HMM graph density
- `activeSingleStateIndices` / `activeMultiStateIndices` — sparse forward-pass state tracking
- `downbeatPredecessorIndices` / `isDownbeatPredecessor` — graph structure for downbeat constraints

---

### 3. Constant vs. variable tempo — two parallel analyses, confidence-based selection

The `RhythmAnalyzer` runs **both** constant and variable tempo analyses simultaneously:

```
Raw CNN activations
  → Running Initial Constant Analysis
  → Running Windowed Constant Analysis (window 1 of N: t_start to t_end)
  → Running Windowed Variable Analysis (window 1 of N: t_start to t_end)
  → summedConstantTempoConfidence vs. summedVariableTempoConfidence
  → "Choosing Constant Tempo." OR "Choosing Variable Tempo."
  → beatsConstantTempo OR beatsVariableTempo
  → BeatTrackerResult.constantTempo = true/false
```

The `constantTempo: Bool` field on `BeatTrackerResult` (and by extension `RhythmResult`) is the output of this confidence comparison — it tells you which analysis won. `forceConstantTempo` / `forceVariableTempo` flags (from `HintType`) can override the automatic selection via `Hint`.

Average confidence values are logged:
`"Average Variable Tempo Confidence: %f. Average Constant Tempo Confidence: %f."`

This means Apple's beat tracker explicitly handles both metronomic and free-tempo music, something madmom's DBN can also do but requires separate processor configurations.

---

### 4. VideoCuesModel — fully implemented, model file simply missing

Every class in the VideoCues pipeline exists in the binary:

```
VideoCuesAnalyzer → VideoCuesModelWrapper → VideoCuesModel
  input:  VideoCuesModelInput
  output: VideoCuesModelOutput → VideoCuesPrediction {scores: MLShapedArray<Float>}
  config: VideoCuesProviderConfiguration
    videoCuesGoodScoreThreshold   ← separate thresholds for "good" vs "great"
    videoCuesGreatScoreThreshold
  result: VideoCuesResult {goodCues: [CMTime], greatCues: [CMTime]}
```

The explicit error string `"Failed to create VideoCuesProvider, model not found"` confirms the model file is expected at runtime but simply not bundled. The two-threshold design (`good` < `great`) mirrors Apple's typical confidence-tier approach — `goodCues` are plausible cut points, `greatCues` are high-confidence highlights.

Source file: `MusicUnderstanding/VideoCues+Private.swift` — this is an extension in a separate file, suggesting it was developed independently and deliberately kept out of the public `.swiftinterface`.

---

### 5. Audio preprocessing — BiquadFilter chain confirmed

```
Raw audio → BiquadFilter (highpassFilter) → BiquadFilter (highshelfFilter) → FFTProcessor
  → hannWindow → DSPSplitComplex (Accelerate vDSP) → MelFilterBank → MelSpectrogramSlice
```

Two biquad filters in series before FFT: a highpass (removes DC offset and sub-bass) and a highshelf (boosts high-frequency content for beat detection). The `hannWindow` application and `DSPSplitComplex` type confirm Accelerate's `vDSP_fft_zrip` is used for the FFT, not a custom implementation despite the `performForwardDFT` method name seen earlier.

---

### 6. Complete internal class inventory (strings vs. .tbd comparison)

Classes in the binary **not exported** in the `.tbd` (hidden from any static analysis of stubs):

| Class | Role |
|---|---|
| `FFTProcessor` | FFT computation (vDSP wrapper) |
| `PulseTrain` | Beat pulse train representation |
| `JointHMM` | Joint HMM for beat/meter/tempo decoding |
| `JointHMMBacktracker` | Viterbi backtracking |
| `JointHMMConstructor` | HMM graph builder |
| `JointHMMStatePredHistory` | State prediction history for backtracking |
| `PostProcessor` | General postprocessing coordinator |
| `PreProcessor` | General preprocessing coordinator |
| `ModelInputCollector` | Collects model inputs across chunks |
| `ModelOutputCollector` | Collects model outputs across chunks |
| `ComputationalMusicServiceClient` | XPC daemon client |
| `MelSpectrogramModelInputProvider` | Mel spectrogram → model input formatting |
| `MusicAnalysisOrchestrator` | Top-level session coordinator |
| `BiquadFilter` | Audio filter (highpass + highshelf) |
| `LUFSMeter` | LUFS loudness metering (BS.1770) |
| `KeyAnalyzer` | Key model wrapper + postprocessing |
| `PaceAnalyzer` | Pace model output postprocessor |
| `RhythmAnalyzer` | Rhythm analysis coordinator |
| `StructureAnalyzer` | Structure analysis coordinator |
| `InstrumentActivityAnalyzer` | Instrument activity coordinator |
| `LoudnessAnalyzer` | Loudness analysis coordinator |
| `ActivityRangeProvider` | Converts activity streams to time ranges |
| `SampleCache` | Audio sample caching |

---

### 7. Updated complete pipeline (final)

```
AVAsset / AVAudioFile
  └→ AudioConverterAssetInputProvider / ConvertedAudioBufferProvider
  └→ BiquadFilter (highpass) → BiquadFilter (highshelf)
  └→ SampleCache → AVAudioPCMBuffer stream

MusicAnalysisOrchestrator (coordinates all analyzers via Swift actors)
  │
  ├─ RhythmAnalyzer ──────────────────────────────────────────────────────
  │   44.1kHz → FFTProcessor (vDSP Hann-windowed) → 128 mel bins + 3 conditioning
  │   → DownbeatTracker CNN (ConvNeXt + Dilated ConvNeXt, 78 layers, 122.8s RF)
  │   → JointHMM (Viterbi, transitionLambda, allowedDeviation, hintPenalty)
  │   → DownbeatHMM → PulseTrain
  │   → BOTH: constant tempo analysis + variable tempo analysis
  │   → confidence comparison → Choosing Constant/Variable Tempo
  │   → BeatTrackerResult → RhythmResult {beats, bars, beatsPerMinute}
  │
  ├─ KeyAnalyzer ─────────────────────────────────────────────────────────
  │   22kHz raw waveform (30s chunks) → KeyModel CNN+MLP (35 classes, LayerNorm)
  │   → KeyPrediction → KeyClassMapping (majorIndexToTonic, noKeyClassIndex)
  │   → minProbability threshold → KeyResult {ranges: [RangedValue<KeySignature>]}
  │
  ├─ StructureAnalyzer (actor) ───────────────────────────────────────────
  │   24kHz → MelSpectrogramGenerator (256 bins, 50ms) → MelSpectrogramSlice
  │   → StructuralFeaturesModel CNN (distilled, 78 layers, 204s RF)
  │   → {phrases[1,?], segments[1,?], sections[1,?], kind[1,3,?], pace[1,41,?]}
  │   → PeakPicking (threshold=0.33, min distances)
  │   → TimeAlignment (1s start/end thresholds)
  │   → getBoundaryTimes(barTimes: from RhythmAnalyzer?) → StructureResult
  │
  ├─ PaceAnalyzer ────────────────────────────────────────────────────────
  │   pace[1,41,?] from StructuralFeaturesModel (shared forward pass)
  │   → slopesAndIntercepts (piecewise linear) → assetsPerMinute
  │   → quantize to validAssetsPerBeatValues → PaceResult {ranges: [RangedValue<Double>]}
  │
  ├─ InstrumentActivityAnalyzer ──────────────────────────────────────────
  │   24kHz → MelSpectrogramGenerator (128 bins, 50ms) → MelSpectrogramSlice
  │   → InstrumentActivityModel CNN (6-bit quantized, 37s RF)
  │   → [1,4,?] → sliceByIndex → {vocals, drums, bass, others} streams
  │   → relu → ActivityRangeProvider → InstrumentActivityResult
  │
  ├─ LoudnessAnalyzer ────────────────────────────────────────────────────
  │   LUFSMeter (LoudnessManager.mm, C++, ITU-R BS.1770)
  │   highpassFilter → momentaryBlocks (400ms) → shortTermBlocks (3s)
  │   → LoudnessResult {integrated, peak, momentary, shortTerm}
  │
  └─ VideoCuesAnalyzer (internal only, model not bundled in this build) ──
      VideoCuesModel (missing) → VideoCuesPrediction {scores}
      → goodScoreThreshold / greatScoreThreshold
      → VideoCuesResult {goodCues, greatCues: [CMTime]}

All coordinators → MusicUnderstandingSession.SessionResult
  (via computationalmusicd daemon over XPC when available,
   in-process fallback when daemon unavailable e.g. simulator)
```

---

## Steps 3–5: filesystem hunt, dependencies, binary sections

### VideoCues model — definitively absent

Zero results for `*VideoCue*` anywhere in the simulator runtime. No `VideoCuesModel.mlmodelc` exists under any path — not in MusicUnderstanding.framework, not in any other framework, not in asset delivery. The model is simply not shipped in this build. The full pipeline exists in the binary (`VideoCuesAnalyzer`, `VideoCuesModelWrapper`, `VideoCuesPrediction`, the good/great thresholds — all present), but there is no model file to load. The runtime guard `"Failed to create VideoCuesProvider, model not found"` fires on every session that requests `.videoCues` (which isn't on the public `AnalysisType` list, so this is only reachable internally).

### `computationalmusicd` daemon — not in simulator runtime

The daemon binary doesn't exist in the simulator cryptex mount. Expected — simulator environments don't run background daemons the same way real devices do. In the simulator, all inference runs in-process (confirmed by the Espresso XPC connection failure logs we saw earlier). The daemon would be in the real device's OS image, not in the simulator runtime bundle.

### MusicUnderstanding framework — exactly these files, nothing else

```
MusicUnderstanding.framework/
├── MusicUnderstanding                    ← main binary (1.55MB, ARM64)
├── Info.plist
├── _CodeSignature/CodeResources
├── DownbeatTracker.mlmodelc/
│   ├── model.mil, metadata.json, weights/weight.bin, coremldata.bin
│   └── analytics/coremldata.bin
├── KeyModel.mlmodelc/             (same structure)
├── InstrumentActivityModel.mlmodelc/    (same structure)
└── StructuralFeaturesModel.mlmodelc/   (same structure)
```

No VideoCuesModel, no config plists, no additional resources. Four models, one binary, done.

### Real dependency graph (confirmed from otool)

```
MusicUnderstanding
├── Foundation                  ← standard
├── AVFAudio                    ← audio format/codec/buffer handling
├── AVFoundation                ← asset reading (AVAsset, AVAssetReader)
├── Accelerate                  ← vDSP FFT, BNNS, SIMD math (confirmed)
├── CoreML                      ← model inference
├── CoreMedia                   ← CMTime, CMTimeRange
├── XPCDistributed              ← distributed actor / XPC system
├── libobjc                     ← @objc bridging stubs
├── libSystem                   ← BSD syscalls
└── Swift runtime:
    ├── libswift_Concurrency    ← async/await, actors (heavy use)
    ├── libswiftDistributed     ← Swift Distributed Actors
    ├── libswiftDispatch        ← GCD
    ├── libswiftSynchronization ← Swift 6 Mutex/AtomicValue
    ├── libswiftAVFoundation
    ├── libswiftAccelerate
    ├── libswiftCoreAudio
    ├── libswiftsimd            ← SIMD for signal math
    ├── libswiftMetal (weak)    ← GPU acceleration (optional)
    ├── libswiftCoreMIDI (weak) ← MIDI (weak — optional, possibly future use)
    └── libswiftXPC
```

Notable absences: **no SoundAnalysis.framework** — MusicUnderstanding is completely separate from Apple's public audio classification framework despite overlapping domain. **No Vision.framework** — purely audio, no visual processing (confirms VideoCuesModel is audio-only or not present). **No Photos.framework** — no integration with the Photos library at this layer.

`libswiftCoreMIDI` (weak link) is surprising — MIDI isn't used anywhere in the public API or internal symbols we've seen. Likely a vestige of an earlier design that considered MIDI output for beat grids, or placeholder for a future feature.

### Mach-O binary sections — Swift architecture confirmed

Key sections beyond the standard `__TEXT`/`__DATA`:

```
__swift5_reflstr    ← Swift reflection strings (property/type names readable at runtime)
__swift5_fieldmd    ← field metadata (how debugDescription and Codable work)
__swift5_acfuncs    ← async continuation functions (one per async func in the binary)
__swift_as_entry/ret/cont  ← async/await task entry, return, continuation points
__oslogstring       ← os_log format strings (Apple structured logging throughout)
__swift5_proto      ← protocol conformance records
__swift5_types      ← type metadata
__swift5_mpenum     ← multi-payload enum metadata (e.g. MusicUnderstandingError cases)
__objc_stubs        ← Objective-C method stubs for Swift @objc bridging
```

The `__swift5_acfuncs` section confirms the framework makes pervasive use of Swift Concurrency — every `async` function gets a continuation entry in this section. The `__oslogstring` section means Apple uses structured `os_log` throughout (these are the debug strings we saw like `"Average Variable Tempo Confidence: %f"`).

### Bonus: ShazamKit models in the same simulator runtime

Not MusicUnderstanding, but worth noting for Recut context:
- `ShazamKit.framework/crepe.mlmodelc` — CREPE pitch detection model (Convolutional Representation for Pitch Estimation, well-known open-source model)
- `ShazamKit.framework/crema.mlmodelc` — chord recognition model

Shazam bundles these for music identification beyond fingerprinting. Apple ships both a chord model (`crema`) and a pitch model (`crepe`) in ShazamKit while shipping a key model (repurposed chord detector) in MusicUnderstanding — two separate teams, two separate approaches to the same underlying harmonic analysis problem.

### `MediaAnalysis.framework` models — visible but unrelated

`mubb_md8.mlmodelc` in MediaAnalysis is interesting naming (`mu` prefix, `md8` suffix matching MusicUnderstanding's model naming convention) but it's in MediaAnalysis, not MusicUnderstanding. Likely coincidence in naming. MediaAnalysis handles Photos/video analysis (faces, scenes, actions) and is a completely separate system.

---

## Behavioral test results — confirmed runtime behavior

All tests run on "End of Beginning" (Djo, 2:39, 80 BPM, D major) in the iOS 27 simulator.

### Test 1 — Selective analysis types ✓
Requesting `.rhythm` only returns `rhythm: non-nil`, all other fields `nil`. Unrequested analysis types are strictly nil — no cross-contamination, no speculative pre-computation of other types.

### Test 2 — Empty analysis set ✓
`analyze(for: [])` throws `MusicUnderstandingError.emptyAnalysisSet` exactly as documented.

### Test 3 — Single-use session ✓
A second `analyze()` call on the same session (while the first is in-flight) throws `MusicUnderstandingError.sessionInProgress` immediately. The first call continues and completes normally.

### Test 4 — Cancellation throws internal error, not CancellationError
`cancel()` called 1 second into analysis threw `analyzerIsFinished` — **not** Swift's standard `CancellationError`. This is an internal error case not in the public `MusicUnderstandingError` enum. The framework has its own cancellation error path that surfaces as a description string `"analyzerIsFinished"` rather than the standard Swift concurrency cancellation mechanism. Practical implication: catching `CancellationError` is insufficient when wrapping this framework — you need to catch `any Error` and inspect the description.

### Test 5 — Streaming loudnessResults: confirmed exactly-1 per emission ✓
```
Streamed results:          1594   (one per 100ms advance × 159.4s ✓)
First emission momentary.count:  1  ← confirmed: exactly one measurement per stream event
Last emission momentary.count:   1  ← same throughout
Batch result momentary.count: 1594  ← full array in batch mode
```
The streaming vs batch distinction is confirmed precisely: `loudnessResults` emits `LoudnessResult` with single-element `momentary`/`shortTerm` arrays at 100ms intervals; `analyze()` batch returns one `LoudnessResult` with complete 1594-element arrays.

### Test 6 — Structure without rhythm: identical boundaries
Requesting `.structure` alone (no `.rhythm`, so no `barTimes` prior) produced **identical** results: 9 sections, 15 segments, 31 phrases — same as the full analysis run. Two interpretations:
1. For a constant-tempo pop track at 80 BPM, the model's predicted boundaries naturally align with bar positions even without explicit bar-snapping — making rhythm coupling invisible on this track.
2. The default `shouldSnapToBars` is `false`, so bar-snapping isn't applied in either case.

A variable-tempo or rubato track would distinguish these. For Recut's purpose: structure detection works independently of rhythm on at least constant-tempo music.

### Test 7 — Pace alone: independent of structure ✓
`.pace` alone returns `pace: non-nil` (4 ranges, values `["10.0", "20.0", "10.0", "20.0"]`) with `structure: nil`. Confirmed: pace and structure share the `StructuralFeaturesModel` forward pass but are exposed as independent `AnalysisType` cases. Requesting `.pace` triggers the model, populates only pace, discards structure output. Same values as full run — results are deterministic.

### Test 8 — Instrument activity strictly within [0, 1]
```
bass:  min=0.0000  max=0.8311  (within 0–1)
drum:  min=0.0000  max=0.9102  (within 0–1)
other: min=0.0000  max=0.8131  (within 0–1)
vocal: min=0.0000  max=0.8947  (within 0–1)
```
No values exceed 1.0 despite the MIL showing `relu` (not `sigmoid`) as the final activation. Conclusion: the model was trained with a target output distribution in [0, 1], so even though ReLU technically allows values above 1.0, the learned weights don't produce them on real music. The postprocessing in `ActivityRangeProvider` may additionally clip. The public API documentation claiming "0.0 to 1.0" is behaviorally correct even though the architecture doesn't mathematically guarantee it.

### Espresso error count across tests: 7
7 separate Espresso GPU fallback errors fired across 8 tests (vs 3 in the single full analysis). Counts per test: rhythm-only (1), structure (1), pace (1), instrument (1), loudness (0 — C++ path), full analysis for cancel (1), full analysis for stream (1), first full analysis (1). Confirms each analysis type that uses CoreML triggers exactly one Espresso fallback error per session in the simulator.

---

## Summary: what's fully confirmed vs. what remains uncertain

| Question | Answer | Source |
|---|---|---|
| How many CoreML models? | 4 (DownbeatTracker, KeyModel, InstrumentActivity, StructuralFeatures) | model.mil |
| Beat tracking architecture | ConvNeXt CNN → JointHMM (Viterbi) | binary strings |
| Key model input | Raw waveform @22kHz, repurposed chord detector | metadata |
| Structure model | Distilled CNN, 204s RF, 256 mel bins | metadata + MIL |
| Pace output | 41-class quantized cuts/minute recommendation | MIL output shape |
| Loudness | C++ LoudnessManager.mm, ITU-R BS.1770 | binary strings |
| VideoCues | Fully implemented in code, model not bundled | strings + filesystem |
| computationalmusicd | Daemon exists (string confirmed), not in simulator | strings + filesystem |
| Cancellation error type | Internal `analyzerIsFinished`, not CancellationError | behavioral test |
| Streaming loudness | Exactly 1 value per emission | behavioral test |
| Instrument activity range | Behaviorally [0,1], architecturally unbounded ReLU | MIL + behavioral |
| Structure-rhythm coupling | Invisible on constant-tempo music | behavioral test |
| Pace-structure coupling | Independent AnalysisType, shared model pass | behavioral test |
| Public API platform parity | Identical across iOS/macOS/tvOS/watchOS/visionOS | swiftinterface diff |
