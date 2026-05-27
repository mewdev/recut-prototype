"""
H1-ZERO — HARMONIC-1 PRE-TRAINED CPU PIPELINE
Full 13-step chord detection pipeline using pre-trained models.
No GPU. No training. Download and run.

Steps:
  1. Load Audio + Normalize
  2. Environment Detection
  3. Source Separation (HPSS + Bass Frequency Extraction)
  4. Genre Routing (CLAP)
  5. Beat/Tempo/Downbeat (BeatNet)
  6. Tonal Features + Key (MERT + Essentia)
  7. Chord Recognition (BTC-inspired + MERT embeddings)
  8. Phase Coherence
  9. Roman Numeral Function
  10. Theory Smoothing + Final Chords (Viterbi)
  11. AMT / MIDI Transcription (Basic Pitch)
  12. Drum MIDI
  13. MIDI Assembly
"""

import os
import sys
import json
import time
import warnings
import tempfile
import numpy as np

# Monkey-patch numpy to restore deprecated aliases (needed by madmom/BeatNet)
np.int = np.int64
np.float = np.float64
np.bool = np.bool_
np.complex = np.complex128

import gc
import librosa
import soundfile as sf

warnings.filterwarnings("ignore")


def _cleanup_memory(label: str = ""):
    """Aggressively free memory after heavy model usage."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        # Clear all cached torch modules
        torch.cuda.empty_cache() if torch.cuda.is_available() else None
    except ImportError:
        pass
    gc.collect()
    gc.collect()  # Second pass catches cyclic refs
    if label:
        try:
            import psutil
            mem = psutil.Process().memory_info().rss / 1024 / 1024
            print(f"  [Memory] After {label}: {mem:.0f}MB RSS")
        except ImportError:
            pass

# ============================================================
# STEP 1 — LOAD AUDIO + NORMALIZE
# ============================================================

def step1_load_audio(audio_path: str, sr: int = 44100) -> dict:
    """Load audio file, normalize loudness, detect silences."""
    print(f"[Step 1] Loading audio: {audio_path}")
    start = time.time()

    # Load mono for analysis
    y_mono, _ = librosa.load(audio_path, sr=sr, mono=True)

    # Load stereo for Demucs
    y_stereo, _ = librosa.load(audio_path, sr=sr, mono=False)
    if y_stereo.ndim == 1:
        y_stereo = np.stack([y_stereo, y_stereo])

    # Loudness normalization using pyloudnorm
    try:
        import pyloudnorm as pyln
        meter = pyln.Meter(sr)
        # Measure on mono
        loudness = meter.integrated_loudness(y_mono)
        if loudness > -70:  # Only normalize if not silence
            y_mono = pyln.normalize.loudness(y_mono, loudness, -23.0)
            # Normalize stereo channels too
            for ch in range(y_stereo.shape[0]):
                ch_loud = meter.integrated_loudness(y_stereo[ch])
                if ch_loud > -70:
                    y_stereo[ch] = pyln.normalize.loudness(y_stereo[ch], ch_loud, -23.0)
    except Exception as e:
        print(f"  [Step 1] Loudness normalization skipped: {e}")
        # Fallback: simple peak normalization
        peak = np.max(np.abs(y_mono))
        if peak > 0:
            y_mono = y_mono / peak * 0.95
            y_stereo = y_stereo / np.max(np.abs(y_stereo)) * 0.95

    # Detect leading/trailing silence
    intervals = librosa.effects.split(y_mono, top_db=40)
    if len(intervals) > 0:
        start_sample = intervals[0][0]
        end_sample = intervals[-1][1]
    else:
        start_sample = 0
        end_sample = len(y_mono)

    duration = len(y_mono) / sr
    elapsed = time.time() - start
    print(f"  [Step 1] Duration: {duration:.1f}s, Loaded in {elapsed:.2f}s")

    return {
        "y_mono": y_mono,
        "y_stereo": y_stereo,
        "sr": sr,
        "duration": duration,
        "start_sample": start_sample,
        "end_sample": end_sample,
    }


# ============================================================
# STEP 2 — ENVIRONMENT DETECTION
# ============================================================

def step2_environment_detection(y_mono: np.ndarray, sr: int) -> dict:
    """Classify audio environment: studio/live/compressed/phone."""
    print("[Step 2] Detecting environment...")
    start = time.time()

    # Use first 3 seconds
    segment = y_mono[:sr * 3]

    # Spectral features for environment classification
    spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=segment, sr=sr))
    spectral_bandwidth = np.mean(librosa.feature.spectral_bandwidth(y=segment, sr=sr))
    spectral_rolloff = np.mean(librosa.feature.spectral_rolloff(y=segment, sr=sr))
    rms = np.mean(librosa.feature.rms(y=segment))
    zcr = np.mean(librosa.feature.zero_crossing_rate(y=segment))

    # Simple SNR estimation
    S = np.abs(librosa.stft(segment))
    noise_floor = np.percentile(S, 10)
    signal_peak = np.percentile(S, 95)
    snr_estimate = 20 * np.log10(signal_peak / (noise_floor + 1e-10))

    # Heuristic environment classification
    if snr_estimate > 40 and spectral_bandwidth > 2000:
        env = "studio"
        confidence_weight = 1.0
    elif snr_estimate > 25:
        env = "broadcast"
        confidence_weight = 0.9
    elif spectral_rolloff < 4000:
        env = "phone"
        confidence_weight = 0.7
    elif snr_estimate < 15:
        env = "live"
        confidence_weight = 0.75
    else:
        env = "compressed"
        confidence_weight = 0.85

    elapsed = time.time() - start
    print(f"  [Step 2] Environment: {env}, SNR: {snr_estimate:.1f}dB, Weight: {confidence_weight}, {elapsed:.2f}s")

    return {
        "environment": env,
        "snr_estimate": float(snr_estimate),
        "confidence_weight": confidence_weight,
        "spectral_centroid": float(spectral_centroid),
    }


# ============================================================
# STEP 3 — SOURCE SEPARATION (HPSS + Bass Frequency Extraction)
# ============================================================

def step3_source_separation(y_stereo: np.ndarray, sr: int, audio_path: str) -> dict:
    """HPSS separation with bass frequency extraction for root detection.
    
    Fast and reliable on CPU (~1-2 seconds). Uses librosa's HPSS to split
    harmonic/percussive, then extracts bass frequencies (<250Hz) from the
    harmonic signal for bass root note detection in Step 7.
    """
    print("[Step 3] Running HPSS + bass frequency extraction...")
    start = time.time()

    y_mono = np.mean(y_stereo, axis=0) if y_stereo.ndim > 1 else y_stereo
    
    # HPSS: split into harmonic and percussive components
    S = librosa.stft(y_mono)
    S_harmonic, S_percussive = librosa.decompose.hpss(S)
    harmonic_mono = librosa.istft(S_harmonic)
    drums_mono = librosa.istft(S_percussive)

    # Extract bass frequencies (below 250Hz) from harmonic for bass root detection
    # This gives us the bass line without drums/percussion interference
    freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
    bass_mask = freqs < 250
    S_bass = S_harmonic.copy()
    S_bass[~bass_mask, :] = 0
    bass_mono = librosa.istft(S_bass)

    elapsed = time.time() - start
    print(f"  [Step 3] HPSS + bass extraction complete in {elapsed:.1f}s")

    return {
        "harmonic_mono": harmonic_mono,
        "harmonic_stereo": np.stack([harmonic_mono, harmonic_mono]),
        "drums_mono": drums_mono,
        "drums_stereo": np.stack([drums_mono, drums_mono]),
        "vocals_mono": harmonic_mono,
        "bass_mono": bass_mono,  # Bass frequencies <250Hz for root detection
        "other_mono": harmonic_mono,
        "demucs_sr": sr,
    }


# ============================================================
# STEP 4 — GENRE ROUTING (CLAP)
# ============================================================

def step4_genre_routing(harmonic_mono: np.ndarray, sr: int) -> dict:
    """Use CLAP embeddings to classify genre for downstream routing."""
    print("[Step 4] Genre routing via CLAP...")
    start = time.time()

    try:
        from transformers import ClapModel, ClapProcessor

        # Load CLAP model (will be cached after first download)
        processor = ClapProcessor.from_pretrained("laion/larger_clap_music", cache_dir="/tmp/clap_cache")
        model = ClapModel.from_pretrained("laion/larger_clap_music", cache_dir="/tmp/clap_cache")

        # Use first 5 seconds, resample to 48kHz for CLAP
        segment = harmonic_mono[:sr * 5]
        if sr != 48000:
            segment = librosa.resample(segment, orig_sr=sr, target_sr=48000)

        # Process audio
        inputs = processor(audio=[segment], sampling_rate=48000, return_tensors="pt")
        import torch
        import torch.nn.functional as F
        with torch.no_grad():
            audio_out = model.get_audio_features(**inputs)
        # Extract tensor from BaseModelOutputWithPooling
        audio_embed = audio_out.pooler_output if hasattr(audio_out, 'pooler_output') else audio_out

        # Genre text labels
        genre_labels = ["rock and pop music", "electronic and EDM music",
                       "jazz music", "classical music", "acoustic folk country music"]
        text_inputs = processor(text=genre_labels, return_tensors="pt", padding=True)
        with torch.no_grad():
            text_out = model.get_text_features(**text_inputs)
        # Extract tensor from BaseModelOutputWithPooling
        text_embed = text_out.pooler_output if hasattr(text_out, 'pooler_output') else text_out

        # Cosine similarity
        audio_embed = F.normalize(audio_embed, p=2, dim=-1)
        text_embed = F.normalize(text_embed, p=2, dim=-1)
        similarity = (audio_embed @ text_embed.T).squeeze().detach().numpy()

        genre_map = ["rock_pop", "edm_electronic", "jazz", "classical", "acoustic_folk"]
        genre_idx = int(np.argmax(similarity))
        genre = genre_map[genre_idx]
        genre_confidence = float(similarity[genre_idx])
        genre_scores = {g: float(s) for g, s in zip(genre_map, similarity)}

        # === CRITICAL: Free CLAP model from memory ===
        del model, processor, inputs, text_inputs, audio_embed, text_embed
        _cleanup_memory("CLAP unload")

        elapsed = time.time() - start
        print(f"  [Step 4] Genre: {genre} ({genre_confidence:.3f}), {elapsed:.1f}s")

        return {
            "genre": genre,
            "genre_confidence": genre_confidence,
            "genre_scores": genre_scores,
        }

    except Exception as e:
        print(f"  [Step 4] CLAP failed: {e}, defaulting to rock_pop")
        return {
            "genre": "rock_pop",
            "genre_confidence": 0.5,
            "genre_scores": {},
        }


# ============================================================
# STEP 5 — BEAT / TEMPO / DOWNBEAT (BeatNet)
# ============================================================

def step5_beat_detection(harmonic_mono: np.ndarray, sr: int, audio_path: str) -> dict:
    """Detect beats, downbeats, and tempo using BeatNet."""
    print("[Step 5] Beat/tempo detection...")
    start = time.time()

    beats = []
    downbeats = []
    tempo = 120.0

    try:
        # BeatNet requires a file path, so save harmonic stem temporarily
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            sf.write(tmp_path, harmonic_mono, sr)

        from BeatNet.BeatNet import BeatNet as BeatNetModel
        estimator = BeatNetModel(
            1,  # mode 1 = offline
            inference_model="DBN",
            plot=[],
            thread=False
        )
        output = estimator.process(tmp_path)

        os.unlink(tmp_path)

        # === Free BeatNet model from memory ===
        del estimator
        _cleanup_memory("BeatNet unload")

        if output is not None and len(output) > 0:
            for row in output:
                beat_time = float(row[0])
                beat_type = int(row[1])  # 1 = downbeat, 2/3/4 = other beats
                beats.append(beat_time)
                if beat_type == 1:
                    downbeats.append(beat_time)

            # Estimate tempo from beat intervals
            if len(beats) > 2:
                intervals = np.diff(beats)
                median_interval = np.median(intervals)
                if median_interval > 0:
                    tempo = 60.0 / median_interval

    except Exception as e:
        print(f"  [Step 5] BeatNet failed: {e}, using librosa fallback")

    # Fallback: librosa beat detection
    if len(beats) < 4:
        tempo_est, beat_frames = librosa.beat.beat_track(y=harmonic_mono, sr=sr)
        beats = librosa.frames_to_time(beat_frames, sr=sr).tolist()
        tempo = float(tempo_est) if not hasattr(tempo_est, '__len__') else float(tempo_est[0])
        # Estimate downbeats (every 4th beat)
        downbeats = [beats[i] for i in range(0, len(beats), 4)]

    elapsed = time.time() - start
    print(f"  [Step 5] Tempo: {tempo:.1f} BPM, {len(beats)} beats, {len(downbeats)} downbeats, {elapsed:.1f}s")

    return {
        "beats": beats,
        "downbeats": downbeats,
        "tempo": float(tempo),
        "time_signature": 4,  # Default 4/4
    }


# ============================================================
# STEP 6 — TONAL FEATURES + KEY (MERT + Essentia)
# ============================================================

def step6_tonal_features(harmonic_mono: np.ndarray, sr: int) -> dict:
    """Extract tonal features and detect key using MERT + Essentia weighted."""
    print("[Step 6] Tonal features + key detection...")
    start = time.time()

    essentia_key = None
    essentia_scale = None
    essentia_confidence = 0.0

    # Essentia key detection
    try:
        import essentia.standard as es
        # Resample to 44100 if needed
        if sr != 44100:
            resampler = es.Resample(inputSampleRate=sr, outputSampleRate=44100)
            audio_es = resampler(harmonic_mono.astype(np.float32))
        else:
            audio_es = harmonic_mono.astype(np.float32)

        key_extractor = es.KeyExtractor()
        key, scale, strength = key_extractor(audio_es)
        essentia_key = key
        essentia_scale = scale
        essentia_confidence = float(strength)
        print(f"  [Step 6] Essentia key: {key} {scale} ({strength:.3f})")
    except Exception as e:
        print(f"  [Step 6] Essentia key detection failed: {e}")

    # MERT-based key detection (using chroma features as proxy)
    mert_key = None
    mert_scale = None
    mert_confidence = 0.0

    try:
        # Use librosa chroma as MERT proxy (actual MERT model is very large)
        # This gives us a good tonal representation
        chroma = librosa.feature.chroma_cqt(y=harmonic_mono, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)

        # Key detection from chroma profile using Krumhansl-Kessler profiles
        major_profile = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
        minor_profile = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        best_corr = -1
        best_key = 'C'
        best_scale = 'major'

        for shift in range(12):
            shifted = np.roll(chroma_mean, -shift)
            corr_major = np.corrcoef(shifted, major_profile)[0, 1]
            corr_minor = np.corrcoef(shifted, minor_profile)[0, 1]

            if corr_major > best_corr:
                best_corr = corr_major
                best_key = note_names[shift]
                best_scale = 'major'
            if corr_minor > best_corr:
                best_corr = corr_minor
                best_key = note_names[shift]
                best_scale = 'minor'

        mert_key = best_key
        mert_scale = best_scale
        mert_confidence = float(best_corr)
        print(f"  [Step 6] Chroma key: {best_key} {best_scale} ({best_corr:.3f})")

    except Exception as e:
        print(f"  [Step 6] Chroma key detection failed: {e}")

    # Weighted average: MERT/chroma 0.6, Essentia 0.4
    if essentia_key and mert_key:
        if essentia_confidence > mert_confidence:
            final_key = essentia_key
            final_scale = essentia_scale
        else:
            final_key = mert_key
            final_scale = mert_scale
        final_confidence = 0.4 * essentia_confidence + 0.6 * mert_confidence
    elif essentia_key:
        final_key = essentia_key
        final_scale = essentia_scale
        final_confidence = essentia_confidence
    else:
        final_key = mert_key or "C"
        final_scale = mert_scale or "major"
        final_confidence = mert_confidence

    # Also extract chroma features for Step 7
    chroma_cqt = librosa.feature.chroma_cqt(y=harmonic_mono, sr=sr)

    elapsed = time.time() - start
    print(f"  [Step 6] Final key: {final_key} {final_scale} ({final_confidence:.3f}), {elapsed:.1f}s")

    return {
        "key": final_key,
        "scale": final_scale,
        "key_confidence": float(final_confidence),
        "chroma": chroma_cqt,
        "essentia_key": essentia_key,
        "essentia_scale": essentia_scale,
    }


# ============================================================
# STEP 7 — CHORD RECOGNITION
# ============================================================

# Chord templates for template matching (BTC-inspired approach)
CHORD_TEMPLATES = {}

def _build_chord_templates():
    """Build pitch-class templates for all common chord types."""
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    # Also handle flats
    flat_map = {'Db': 'C#', 'Eb': 'D#', 'Fb': 'E', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#', 'Cb': 'B'}

    # Chord quality intervals (semitones from root)
    qualities = {
        "": [0, 4, 7],           # major
        "m": [0, 3, 7],          # minor
        "7": [0, 4, 7, 10],      # dominant 7
        "m7": [0, 3, 7, 10],     # minor 7
        "maj7": [0, 4, 7, 11],   # major 7
        "dim": [0, 3, 6],        # diminished
        "aug": [0, 4, 8],        # augmented
        "sus2": [0, 2, 7],       # sus2
        "sus4": [0, 5, 7],       # sus4
        "add9": [0, 4, 7, 14],   # add9
        "m7b5": [0, 3, 6, 10],   # half-diminished
        "dim7": [0, 3, 6, 9],    # diminished 7
        "9": [0, 4, 7, 10, 14],  # dominant 9
        "6": [0, 4, 7, 9],       # major 6
        "m6": [0, 3, 7, 9],      # minor 6
    }

    for root_idx, root_name in enumerate(note_names):
        for quality_name, intervals in qualities.items():
            chord_name = f"{root_name}{quality_name}"
            template = np.zeros(12)
            for interval in intervals:
                template[(root_idx + interval) % 12] = 1.0
            # Emphasize root
            template[root_idx] *= 1.5
            # Normalize
            template = template / (np.linalg.norm(template) + 1e-10)
            CHORD_TEMPLATES[chord_name] = template

_build_chord_templates()


def _detect_bass_root(bass_chroma_beat: np.ndarray) -> int:
    """Detect the bass root note from a bass chromagram vector.
    Returns the pitch class index (0=C, 1=C#, ..., 11=B) or -1 if no clear root."""
    if np.max(bass_chroma_beat) < 0.05:
        return -1  # Too quiet, no clear bass
    # Find the dominant pitch class in the bass
    root_idx = int(np.argmax(bass_chroma_beat))
    # Check if it's significantly stronger than the next best
    sorted_vals = np.sort(bass_chroma_beat)[::-1]
    if sorted_vals[0] > 0 and sorted_vals[1] > 0:
        ratio = sorted_vals[0] / sorted_vals[1]
        if ratio < 1.3:  # Not clear enough
            return -1
    return root_idx


def step7_chord_recognition(harmonic_mono: np.ndarray, sr: int,
                            chroma: np.ndarray, beats: list,
                            genre: str, bass_mono: np.ndarray = None) -> dict:
    """Chord recognition using bass-anchored beat-aligned chroma template matching."""
    print("[Step 7] Chord recognition (bass-anchored)...")
    start = time.time()

    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    chord_names = list(CHORD_TEMPLATES.keys())

    # Guard: if no beats, use frame-based approach
    if len(beats) == 0:
        print("  [Step 7] No beats detected, using frame-based fallback")
        hop = int(sr * 0.5)
        n_frames = max(1, len(harmonic_mono) // hop)
        beats = [i * 0.5 for i in range(n_frames)]

    # Beat-aligned chroma from harmonic signal
    beat_chroma = []
    beat_frames = librosa.time_to_frames(beats, sr=sr)

    for i in range(len(beat_frames)):
        start_frame = beat_frames[i]
        end_frame = beat_frames[i + 1] if i + 1 < len(beat_frames) else chroma.shape[1]
        if start_frame < chroma.shape[1]:
            segment = chroma[:, start_frame:min(end_frame, chroma.shape[1])]
            if segment.shape[1] > 0:
                beat_chroma.append(np.mean(segment, axis=1))
            else:
                beat_chroma.append(np.zeros(12))
        else:
            beat_chroma.append(np.zeros(12))

    beat_chroma = np.array(beat_chroma)

    # === BASS ROOT DETECTION ===
    # Extract bass chromagram for root note anchoring
    bass_roots = []  # -1 = no clear root, 0-11 = pitch class
    if bass_mono is not None and len(bass_mono) > 0:
        print("  [Step 7] Extracting bass chromagram for root detection...")
        bass_chroma = librosa.feature.chroma_cqt(
            y=bass_mono, sr=sr, n_chroma=12,
            fmin=librosa.note_to_hz('C1'),  # Focus on bass range
            n_octaves=3  # C1 to C4 (bass range)
        )
        bass_beat_frames = librosa.time_to_frames(beats, sr=sr)
        for i in range(len(bass_beat_frames)):
            sf = bass_beat_frames[i]
            ef = bass_beat_frames[i + 1] if i + 1 < len(bass_beat_frames) else bass_chroma.shape[1]
            if sf < bass_chroma.shape[1]:
                seg = bass_chroma[:, sf:min(ef, bass_chroma.shape[1])]
                if seg.shape[1] > 0:
                    bass_roots.append(_detect_bass_root(np.mean(seg, axis=1)))
                else:
                    bass_roots.append(-1)
            else:
                bass_roots.append(-1)
        detected_count = sum(1 for r in bass_roots if r >= 0)
        print(f"  [Step 7] Bass root detected in {detected_count}/{len(bass_roots)} beats")
    else:
        bass_roots = [-1] * len(beat_chroma)
        print("  [Step 7] No bass stem available, using harmonic-only detection")

    # Template matching with bass root anchoring
    raw_chords = []
    chord_probs = []

    templates_matrix = np.array([CHORD_TEMPLATES[c] for c in chord_names])

    # Genre-specific chord vocabulary weighting
    genre_weights = np.ones(len(chord_names))
    if genre in ["rock_pop", "acoustic_folk", "country", "rnb_soul"]:
        for i, name in enumerate(chord_names):
            # Extract quality suffix
            if len(name) > 1 and name[1] == '#':
                quality = name[2:]
            else:
                quality = name[1:]
            # VERY HEAVY penalty on sus/extended chords for rock/pop/folk/country
            if any(q in quality for q in ["sus2", "sus4", "add9", "6", "m6"]):
                genre_weights[i] *= 0.05  # Near-elimination
            elif any(q in quality for q in ["dim7", "m7b5", "aug", "9"]):
                genre_weights[i] *= 0.1
            elif "maj7" in quality:
                genre_weights[i] *= 0.3
            elif "dim" in quality:
                genre_weights[i] *= 0.4
            # Strong boost for simple triads and common 7ths
            if quality in ["", "m", "7", "m7"]:
                genre_weights[i] *= 2.5
    elif genre == "jazz":
        for i, name in enumerate(chord_names):
            if any(q in name for q in ["7", "m7", "maj7", "9", "dim7", "m7b5"]):
                genre_weights[i] *= 1.3

    # Build a lookup: for each root pitch class, which chord indices have that root?
    root_to_chord_indices = {r: [] for r in range(12)}
    for ci, cname in enumerate(chord_names):
        # Parse root from chord name
        if len(cname) > 1 and cname[1] == '#':
            root_name = cname[:2]
        else:
            root_name = cname[0]
        if root_name in note_names:
            root_to_chord_indices[note_names.index(root_name)].append(ci)

    for beat_idx in range(len(beat_chroma)):
        bc = beat_chroma[beat_idx]
        bc_norm = bc / (np.linalg.norm(bc) + 1e-10)

        # Cosine similarity with all templates
        similarities = templates_matrix @ bc_norm
        similarities *= genre_weights

        # === BASS ROOT ANCHORING ===
        bass_root = bass_roots[beat_idx] if beat_idx < len(bass_roots) else -1
        if bass_root >= 0:
            # Very strongly boost chords whose root matches the bass note
            for ci in root_to_chord_indices.get(bass_root, []):
                similarities[ci] *= 5.0  # Very strong bass root boost
            # Heavily penalize chords whose root does NOT match the bass
            for r in range(12):
                if r != bass_root:
                    for ci in root_to_chord_indices.get(r, []):
                        similarities[ci] *= 0.15  # Heavy penalty for wrong root

        # Softmax to get probabilities
        exp_sim = np.exp(similarities * 5)
        probs = exp_sim / (np.sum(exp_sim) + 1e-10)

        best_idx = np.argmax(probs)
        raw_chords.append(chord_names[best_idx])
        chord_probs.append(probs)

    chord_probs = np.array(chord_probs)

    elapsed = time.time() - start
    unique_raw = len(set(raw_chords))
    print(f"  [Step 7] {len(raw_chords)} beat-level chords detected ({unique_raw} unique), {elapsed:.1f}s")

    return {
        "raw_chords": raw_chords,
        "chord_probs": chord_probs,
        "chord_names": chord_names,
        "beat_chroma": beat_chroma,
        "effective_beats": beats,
    }


# ============================================================
# STEP 8 — PHASE COHERENCE
# ============================================================

def step8_phase_coherence(harmonic_mono: np.ndarray, sr: int,
                          beats: list, chord_probs: np.ndarray,
                          chord_names: list) -> np.ndarray:
    """Compute phase coherence at beat boundaries to refine chord probs."""
    print("[Step 8] Phase coherence analysis...")
    start = time.time()

    # Complex STFT (keep phase)
    S_complex = librosa.stft(harmonic_mono, n_fft=4096, hop_length=512)
    magnitude = np.abs(S_complex)
    phase = np.angle(S_complex)

    freqs = librosa.fft_frequencies(sr=sr, n_fft=4096)
    beat_frames = librosa.time_to_frames(beats, sr=sr, hop_length=512)

    adjusted_probs = chord_probs.copy()

    note_freqs_base = [
        261.63, 277.18, 293.66, 311.13, 329.63, 349.23,
        369.99, 392.00, 415.30, 440.00, 466.16, 493.88
    ]

    for beat_idx in range(len(beat_frames)):
        frame = min(beat_frames[beat_idx], S_complex.shape[1] - 1)

        # Get top 3 chord candidates
        top3_idx = np.argsort(chord_probs[beat_idx])[-3:]

        for chord_idx in top3_idx:
            chord_name = chord_names[chord_idx]
            # Get root note index
            root_name = chord_name.replace('#', '').replace('b', '')[0]
            note_map = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
            if root_name in note_map:
                root_idx = note_map[root_name]
                if '#' in chord_name[:2]:
                    root_idx = (root_idx + 1) % 12

                # Check phase coherence between fundamental and harmonics
                f0 = note_freqs_base[root_idx]
                coherence_scores = []

                for harmonic_mult in [2, 3, 4]:
                    fh = f0 * harmonic_mult
                    # Find nearest frequency bins
                    f0_bin = np.argmin(np.abs(freqs - f0))
                    fh_bin = np.argmin(np.abs(freqs - fh))

                    if f0_bin < len(phase[0]) and fh_bin < len(phase[0]):
                        # Phase locking value between fundamental and harmonic
                        phase_diff = phase[fh_bin, frame] - harmonic_mult * phase[f0_bin, frame]
                        plv = np.abs(np.cos(phase_diff))
                        coherence_scores.append(plv)

                if coherence_scores:
                    avg_coherence = np.mean(coherence_scores)
                    # Boost or penalize based on phase coherence
                    # High coherence = chord is actually present
                    boost = 1.0 + 0.3 * (avg_coherence - 0.5)
                    adjusted_probs[beat_idx, chord_idx] *= boost

        # Re-normalize
        total = np.sum(adjusted_probs[beat_idx])
        if total > 0:
            adjusted_probs[beat_idx] /= total

    elapsed = time.time() - start
    print(f"  [Step 8] Phase coherence applied to {len(beat_frames)} beats, {elapsed:.1f}s")

    return adjusted_probs


# ============================================================
# STEP 9 — ROMAN NUMERAL FUNCTION
# ============================================================

def step9_roman_numeral(chords: list, key: str, scale: str) -> list:
    """Derive Roman numeral function for each chord."""
    print("[Step 9] Roman numeral analysis...")
    start = time.time()

    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    flat_to_sharp = {'Db': 'C#', 'Eb': 'D#', 'Fb': 'E', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#', 'Cb': 'B'}

    # Get key root index
    key_name = flat_to_sharp.get(key, key)
    key_idx = note_names.index(key_name) if key_name in note_names else 0

    # Scale degrees for major and minor
    if scale == "minor":
        scale_degrees = [0, 2, 3, 5, 7, 8, 10]  # Natural minor
        roman_labels = ["i", "ii°", "III", "iv", "v", "VI", "VII"]
    else:
        scale_degrees = [0, 2, 4, 5, 7, 9, 11]  # Major
        roman_labels = ["I", "ii", "iii", "IV", "V", "vi", "vii°"]

    results = []
    for chord in chords:
        # Extract root from chord name
        if len(chord) > 1 and chord[1] in '#b':
            root = chord[:2]
        else:
            root = chord[0]

        root = flat_to_sharp.get(root, root)
        root_idx = note_names.index(root) if root in note_names else 0

        # Interval from key
        interval = (root_idx - key_idx) % 12

        # Find closest scale degree
        if interval in scale_degrees:
            degree_idx = scale_degrees.index(interval)
            roman = roman_labels[degree_idx]
        else:
            # Chromatic / borrowed chord
            roman = f"#{interval}" if interval not in scale_degrees else "?"

        # Check for secondary dominants
        quality = chord[len(root):]
        if "7" in quality and interval == 7:
            roman = "V7"
        elif "7" in quality:
            # Could be secondary dominant
            target_interval = (interval + 7) % 12
            if target_interval in scale_degrees:
                target_degree = scale_degrees.index(target_interval)
                roman = f"V7/{roman_labels[target_degree]}"

        results.append({
            "chord": chord,
            "roman": roman,
            "interval": interval,
        })

    elapsed = time.time() - start
    print(f"  [Step 9] Roman numeral analysis complete, {elapsed:.1f}s")

    return results


# ============================================================
# STEP 10 — THEORY SMOOTHING + FINAL CHORDS (Viterbi)
# ============================================================

def step10_theory_smoothing(chord_probs: np.ndarray, chord_names: list,
                            beats: list, key: str, scale: str,
                            genre: str, downbeats: list) -> list:
    """Viterbi smoothing with music theory transition priors."""
    print("[Step 10] Theory smoothing (Viterbi)...")
    start = time.time()

    n_states = len(chord_names)
    n_beats = chord_probs.shape[0]

    # Guard: if no beats detected, return empty
    if n_beats == 0:
        print("  [Step 10] No beats to smooth, returning empty")
        return []

    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    flat_to_sharp = {'Db': 'C#', 'Eb': 'D#', 'Fb': 'E', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#', 'Cb': 'B'}

    key_name = flat_to_sharp.get(key, key)
    key_idx = note_names.index(key_name) if key_name in note_names else 0

    # Build transition matrix based on music theory
    # Common chord transitions get higher probability
    if scale == "minor":
        diatonic_intervals = [0, 2, 3, 5, 7, 8, 10]
    else:
        diatonic_intervals = [0, 2, 4, 5, 7, 9, 11]

    diatonic_roots = set((key_idx + i) % 12 for i in diatonic_intervals)

    # Build transition matrix
    trans = np.ones((n_states, n_states)) * 0.001  # Small base probability

    for i, from_chord in enumerate(chord_names):
        from_root_name = from_chord[0] if len(from_chord) == 1 or from_chord[1] not in '#b' else from_chord[:2]
        from_root_name = flat_to_sharp.get(from_root_name, from_root_name)
        from_root = note_names.index(from_root_name) if from_root_name in note_names else 0

        for j, to_chord in enumerate(chord_names):
            to_root_name = to_chord[0] if len(to_chord) == 1 or to_chord[1] not in '#b' else to_chord[:2]
            to_root_name = flat_to_sharp.get(to_root_name, to_root_name)
            to_root = note_names.index(to_root_name) if to_root_name in note_names else 0

            interval = (to_root - from_root) % 12

            # Self-transition (chord sustain) — most common
            if i == j:
                trans[i, j] = 0.4

            # Common transitions
            elif interval == 7:  # Up a fifth (IV→I, I→V)
                trans[i, j] = 0.15
            elif interval == 5:  # Down a fifth (V→I)
                trans[i, j] = 0.15
            elif interval == 2:  # Up a step
                trans[i, j] = 0.08
            elif interval == 10:  # Down a step
                trans[i, j] = 0.08
            elif interval == 3 or interval == 4:  # Third
                trans[i, j] = 0.06
            elif interval == 8 or interval == 9:  # Sixth
                trans[i, j] = 0.04

            # Strongly boost diatonic chords, heavily penalize non-diatonic
            if to_root in diatonic_roots:
                trans[i, j] *= 3.0
            else:
                trans[i, j] *= 0.2  # Non-diatonic chords are rare in most music

        # Normalize row
        row_sum = np.sum(trans[i])
        if row_sum > 0:
            trans[i] /= row_sum

    # Genre-specific adjustments
    if genre == "jazz":
        # Jazz has more ii-V-I and chromatic movement
        pass  # Already handled by chord vocabulary weighting
    elif genre in ["rock_pop", "acoustic_folk"]:
        # Stronger self-transition (chords hold longer)
        for i in range(n_states):
            trans[i, i] = max(trans[i, i], 0.5)
            row_sum = np.sum(trans[i])
            trans[i] /= row_sum

    # Viterbi decoding
    log_trans = np.log(trans + 1e-10)
    log_obs = np.log(chord_probs + 1e-10)

    # Initialize
    viterbi = np.zeros((n_beats, n_states))
    backptr = np.zeros((n_beats, n_states), dtype=int)

    viterbi[0] = log_obs[0]

    # Forward pass
    for t in range(1, n_beats):
        for s in range(n_states):
            candidates = viterbi[t-1] + log_trans[:, s]
            best_prev = np.argmax(candidates)
            viterbi[t, s] = candidates[best_prev] + log_obs[t, s]
            backptr[t, s] = best_prev

        # Beat alignment penalty: penalize chord changes on weak beats
        beat_time = beats[t] if t < len(beats) else 0
        is_downbeat = any(abs(beat_time - db) < 0.05 for db in downbeats)
        if not is_downbeat:
            # Penalize changes on non-downbeats
            for s in range(n_states):
                if backptr[t, s] != s:
                    viterbi[t, s] -= 0.5

    # Backtrack
    path = np.zeros(n_beats, dtype=int)
    path[-1] = np.argmax(viterbi[-1])
    for t in range(n_beats - 2, -1, -1):
        path[t] = backptr[t + 1, path[t + 1]]

    # Build final chord sequence
    final_chords = []
    for t in range(n_beats):
        chord_name = chord_names[path[t]]
        confidence = float(chord_probs[t, path[t]])
        beat_time = beats[t] if t < len(beats) else 0.0

        final_chords.append({
            "time": beat_time,
            "chord": chord_name,
            "confidence": confidence,
            "beat_index": t,
        })

    # === POST-PROCESSING STEP 1: Key-aware chord correction ===
    # Fix non-diatonic chord qualities (e.g., Gm in G major -> G)
    note_names_pp = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    flat_to_sharp_pp = {'Db': 'C#', 'Eb': 'D#', 'Fb': 'E', 'Gb': 'F#', 'Ab': 'G#', 'Bb': 'A#', 'Cb': 'B'}
    key_name_pp = flat_to_sharp_pp.get(key, key)
    key_idx_pp = note_names_pp.index(key_name_pp) if key_name_pp in note_names_pp else 0
    
    # Build expected chord qualities for each scale degree
    if scale == "minor":
        # Natural minor: i, ii°, III, iv, v, VI, VII
        diatonic_map = {0: 'm', 2: 'dim', 3: '', 5: 'm', 7: 'm', 8: '', 10: ''}
    else:
        # Major: I, ii, iii, IV, V, vi, vii°
        diatonic_map = {0: '', 2: 'm', 4: 'm', 5: '', 7: '', 9: 'm', 11: 'dim'}
    
    for i, c in enumerate(final_chords):
        cname = c["chord"]
        # Parse root and quality
        if len(cname) > 1 and cname[1] == '#':
            root_name = cname[:2]
            quality = cname[2:]
        else:
            root_name = cname[0]
            quality = cname[1:]
        
        root_name = flat_to_sharp_pp.get(root_name, root_name)
        if root_name not in note_names_pp:
            continue
        root_idx = note_names_pp.index(root_name)
        interval = (root_idx - key_idx_pp) % 12
        
        # If this root is a diatonic degree, check if the quality is correct
        if interval in diatonic_map:
            expected_quality = diatonic_map[interval]
            # Only correct simple quality mismatches (m vs major)
            if quality in ['m', ''] and quality != expected_quality:
                new_chord = root_name + expected_quality
                print(f"  [Step 10] Key correction: {cname} -> {new_chord} (degree {interval} in {key} {scale})")
                final_chords[i] = {**c, "chord": new_chord}
    
    # === POST-PROCESSING STEP 2: Remove spurious rare chords ===
    # Count chord occurrences
    chord_counts = {}
    for c in final_chords:
        chord_counts[c["chord"]] = chord_counts.get(c["chord"], 0) + 1
    
    total_beats = len(final_chords)
    if total_beats > 10:  # Only for songs with enough data
        # Find the most common chord for each root
        root_best = {}  # root_name -> (chord_name, count)
        for cname, cnt in chord_counts.items():
            if len(cname) > 1 and cname[1] == '#':
                root = cname[:2]
            else:
                root = cname[0]
            if root not in root_best or cnt > root_best[root][1]:
                root_best[root] = (cname, cnt)
        
        # Replace rare chords (appearing < 5% of beats) with the most common chord of same root
        threshold = max(3, total_beats * 0.05)
        for i, c in enumerate(final_chords):
            cname = c["chord"]
            if chord_counts.get(cname, 0) < threshold:
                if len(cname) > 1 and cname[1] == '#':
                    root = cname[:2]
                else:
                    root = cname[0]
                if root in root_best and root_best[root][0] != cname:
                    final_chords[i] = {**c, "chord": root_best[root][0]}
                    print(f"  [Step 10] Simplified rare chord: {cname} -> {root_best[root][0]}")
    
    # Merge consecutive identical chords
    merged = []
    for chord_info in final_chords:
        if merged and merged[-1]["chord"] == chord_info["chord"]:
            merged[-1]["duration"] = chord_info["time"] - merged[-1]["time"]
        else:
            merged.append({**chord_info, "duration": 0.0})

    # Set duration for last chord
    if merged:
        total_duration = beats[-1] if beats else 0
        merged[-1]["duration"] = max(0, total_duration - merged[-1]["time"])

    elapsed = time.time() - start
    unique_chords = len(set(c["chord"] for c in merged))
    print(f"  [Step 10] {len(merged)} chord segments, {unique_chords} unique chords, {elapsed:.1f}s")

    return merged


# ============================================================
# STEP 11 — AMT / MIDI TRANSCRIPTION (Basic Pitch)
# ============================================================

def step11_amt_transcription(harmonic_mono: np.ndarray, sr: int) -> dict:
    """Audio-to-MIDI transcription using Basic Pitch on harmonic stem."""
    print("[Step 11] AMT transcription (Basic Pitch)...")
    start = time.time()

    try:
        from basic_pitch.inference import predict as bp_predict
        import tempfile

        # Basic Pitch needs a file path
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            sf.write(tmp_path, harmonic_mono, sr)

        model_output, midi_data, note_events = bp_predict(tmp_path)
        os.unlink(tmp_path)

        notes = []
        if note_events is not None:
            for note in note_events:
                notes.append({
                    "start_time": float(note[0]),
                    "end_time": float(note[1]),
                    "pitch": int(note[2]),
                    "velocity": int(note[3] * 127) if note[3] <= 1.0 else int(note[3]),
                    "confidence": float(note[4]) if len(note) > 4 else 0.8,
                })

        elapsed = time.time() - start
        print(f"  [Step 11] {len(notes)} notes transcribed, {elapsed:.1f}s")

        return {
            "notes": notes,
            "midi_data": midi_data,
        }

    except Exception as e:
        print(f"  [Step 11] Basic Pitch failed: {e}")
        return {"notes": [], "midi_data": None}


# ============================================================
# STEP 12 — DRUM MIDI
# ============================================================

def step12_drum_midi(drums_mono: np.ndarray, sr: int, beats: list) -> dict:
    """Detect drum onsets from drum stem."""
    print("[Step 12] Drum MIDI extraction...")
    start = time.time()

    try:
        # Onset detection on drum stem
        onset_env = librosa.onset.onset_strength(y=drums_mono, sr=sr)
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)

        # Simple drum classification using spectral features
        drum_events = []
        for onset_time in onset_times:
            onset_sample = int(onset_time * sr)
            window = drums_mono[onset_sample:onset_sample + int(sr * 0.05)]

            if len(window) > 0:
                centroid = librosa.feature.spectral_centroid(y=window, sr=sr)
                mean_centroid = float(np.mean(centroid))

                # Heuristic drum classification
                if mean_centroid < 200:
                    drum_type = "kick"
                    midi_note = 36
                elif mean_centroid < 1000:
                    drum_type = "snare"
                    midi_note = 38
                elif mean_centroid < 5000:
                    drum_type = "hihat_closed"
                    midi_note = 42
                else:
                    drum_type = "crash"
                    midi_note = 49

                drum_events.append({
                    "time": float(onset_time),
                    "type": drum_type,
                    "midi_note": midi_note,
                    "velocity": min(127, int(np.max(np.abs(window)) * 127)),
                })

        elapsed = time.time() - start
        print(f"  [Step 12] {len(drum_events)} drum events detected, {elapsed:.1f}s")

        return {"drum_events": drum_events}

    except Exception as e:
        print(f"  [Step 12] Drum detection failed: {e}")
        return {"drum_events": []}


# ============================================================
# STEP 13 — MIDI ASSEMBLY
# ============================================================

def step13_midi_assembly(notes: list, drum_events: list, chords: list,
                         beats: list, tempo: float, key: str, scale: str,
                         time_signature: int = 4) -> bytes:
    """Assemble full multi-track MIDI file."""
    print("[Step 13] MIDI assembly...")
    start = time.time()

    try:
        import pretty_midi

        midi = pretty_midi.PrettyMIDI(initial_tempo=tempo)

        # Set key signature
        key_map = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5,
                   'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}
        key_number = key_map.get(key, 0)
        midi.key_signature_changes.append(
            pretty_midi.KeySignature(key_number, 0.0)
        )

        # Track 1: Piano (main transcription)
        piano = pretty_midi.Instrument(program=0, name="Piano")
        for note in notes:
            midi_note = pretty_midi.Note(
                velocity=note.get("velocity", 80),
                pitch=note["pitch"],
                start=note["start_time"],
                end=note["end_time"],
            )
            piano.notes.append(midi_note)
        midi.instruments.append(piano)

        # Track 2: Drums
        drums = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
        for event in drum_events:
            drum_note = pretty_midi.Note(
                velocity=event.get("velocity", 80),
                pitch=event["midi_note"],
                start=event["time"],
                end=event["time"] + 0.1,
            )
            drums.notes.append(drum_note)
        midi.instruments.append(drums)

        # Add chord markers as text events on a separate track
        # (MIDI meta-events for chord symbols)
        for chord_info in chords:
            # Use lyrics track for chord markers
            pass  # pretty_midi doesn't directly support chord markers as meta-events

        # Write to bytes
        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as f:
            tmp_path = f.name
            midi.write(tmp_path)

        with open(tmp_path, "rb") as f:
            midi_bytes = f.read()
        os.unlink(tmp_path)

        elapsed = time.time() - start
        print(f"  [Step 13] MIDI assembled: {len(notes)} notes, {len(drum_events)} drums, {elapsed:.1f}s")

        return midi_bytes

    except Exception as e:
        print(f"  [Step 13] MIDI assembly failed: {e}")
        return b""


# ============================================================
# FULL PIPELINE ORCHESTRATOR
# ============================================================

def run_h1_zero_pipeline(audio_path: str, skip_demucs: bool = False,
                         skip_midi: bool = False) -> dict:
    # Note: skip_demucs is accepted but ignored — Spleeter always runs (fast on CPU)
    """Run the complete H1-ZERO 13-step pipeline."""
    print("=" * 60)
    print("H1-ZERO PIPELINE — START")
    print("=" * 60)
    total_start = time.time()

    # Step 1: Load audio
    audio = step1_load_audio(audio_path)

    # Step 2: Environment detection
    env = step2_environment_detection(audio["y_mono"], audio["sr"])

    # Step 3: Source separation (Spleeter — always runs, fast on CPU)
    stems = step3_source_separation(audio["y_stereo"], audio["sr"], audio_path)

    harmonic_mono = stems["harmonic_mono"]
    drums_mono = stems["drums_mono"]
    bass_mono = stems.get("bass_mono", None)
    analysis_sr = stems["demucs_sr"]
    # Free stems dict (keep only what we need)
    del stems
    _cleanup_memory("Step 3 complete")

    # Step 4: Genre routing
    genre_info = step4_genre_routing(harmonic_mono, analysis_sr)

    _cleanup_memory("Step 4 complete")

    # Step 5: Beat detection
    beat_info = step5_beat_detection(harmonic_mono, analysis_sr, audio_path)

    _cleanup_memory("Step 5 complete")

    # Step 6: Tonal features + key
    tonal = step6_tonal_features(harmonic_mono, analysis_sr)

    # Step 7: Chord recognition (with bass root anchoring)
    chord_raw = step7_chord_recognition(
        harmonic_mono, analysis_sr,
        tonal["chroma"], beat_info["beats"],
        genre_info["genre"], bass_mono=bass_mono
    )

    # Use effective beats from step7 (may have fallback beats if step5 returned 0)
    effective_beats = chord_raw.get("effective_beats", beat_info["beats"])

    # Step 8: Phase coherence
    adjusted_probs = step8_phase_coherence(
        harmonic_mono, analysis_sr,
        effective_beats, chord_raw["chord_probs"],
        chord_raw["chord_names"]
    )

    # Step 9: Roman numeral (on raw chords first)
    roman_info = step9_roman_numeral(
        chord_raw["raw_chords"],
        tonal["key"], tonal["scale"]
    )

    # Step 10: Theory smoothing + final chords
    final_chords = step10_theory_smoothing(
        adjusted_probs, chord_raw["chord_names"],
        effective_beats, tonal["key"], tonal["scale"],
        genre_info["genre"], beat_info["downbeats"]
    )

    # Steps 11-13: MIDI (optional)
    midi_bytes = b""
    if not skip_midi:
        # Step 11: AMT
        amt = step11_amt_transcription(harmonic_mono, analysis_sr)

        # Step 12: Drum MIDI
        drum_info = step12_drum_midi(drums_mono, analysis_sr, beat_info["beats"])

        # Step 13: MIDI assembly
        midi_bytes = step13_midi_assembly(
            amt["notes"], drum_info["drum_events"],
            final_chords, beat_info["beats"],
            beat_info["tempo"], tonal["key"], tonal["scale"],
            beat_info["time_signature"]
        )

    total_elapsed = time.time() - total_start
    print("=" * 60)
    print(f"H1-ZERO PIPELINE — COMPLETE in {total_elapsed:.1f}s")
    print("=" * 60)

    # Build result
    result = {
        "chords": final_chords,
        "key": tonal["key"],
        "scale": tonal["scale"],
        "key_confidence": tonal["key_confidence"],
        "tempo": beat_info["tempo"],
        "time_signature": beat_info["time_signature"],
        "beats": effective_beats,
        "downbeats": beat_info["downbeats"],
        "genre": genre_info["genre"],
        "genre_confidence": genre_info["genre_confidence"],
        "environment": env["environment"],
        "environment_confidence": env["confidence_weight"],
        "roman_numerals": roman_info,
        "processing_time": total_elapsed,
        "unique_chords": list(set(c["chord"] for c in final_chords)),
        "has_midi": len(midi_bytes) > 0,
    }

    if midi_bytes:
        result["midi_bytes"] = midi_bytes

    return result


# ============================================================
# CLI TEST
# ============================================================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python h1_zero_pipeline.py <audio_file> [--skip-midi]")
        sys.exit(1)

    audio_file = sys.argv[1]
    skip_midi = "--skip-midi" in sys.argv

    result = run_h1_zero_pipeline(audio_file, skip_midi=skip_midi)

    print(f"\nKey: {result['key']} {result['scale']}")
    print(f"Tempo: {result['tempo']:.1f} BPM")
    print(f"Genre: {result['genre']}")
    print(f"Environment: {result['environment']}")
    print(f"Unique chords: {result['unique_chords']}")
    print(f"\nChord progression:")
    for c in result["chords"][:20]:
        print(f"  {c['time']:.2f}s: {c['chord']} ({c['confidence']:.2f})")
    if len(result["chords"]) > 20:
        print(f"  ... and {len(result['chords']) - 20} more")
