"""
Audio energy field analyzer — extracts E/W/D (Energy, Warmth, Density)
signatures from audio files using numpy + pydub + ffmpeg.

Layer 3 time-of-day offsets also live here since they operate on the
same E/W/D axes.
"""

import os
import math
import struct
import logging
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

logger = logging.getLogger(__name__)

# ── Time-of-day offset table ────────────────────────────────────

# Hour ranges: [start, end) → (energy_offset, warmth_offset, density_offset)
TIME_OFFSET_TABLE = [
    # (hour_start, hour_end, e_off, w_off, d_off)
    (5,  8,  +0.10, +0.05,  0.00),   # morning: slight brightening
    (8,  12,  0.00,  0.00,  0.00),   # late morning: baseline
    (12, 18, +0.05, +0.10,  0.00),   # afternoon: warm
    (18, 21,  0.00, +0.05, -0.05),   # evening: gentle wind-down
    (21, 24, -0.10, -0.05, -0.05),   # night: lower energy
    (0,  5,  -0.15,  0.00, -0.10),   # late night: darkest
]


def get_time_offset(hour: int | None = None) -> dict:
    """
    Return {energy_offset, warmth_offset, density_offset} for the given hour.

    All offsets are in [-0.15, +0.15]. Never persisted — applied ephemerally
    at playback time.
    """
    if hour is None:
        hour = datetime.now().hour
    for h_start, h_end, e, w, d in TIME_OFFSET_TABLE:
        if h_start <= hour < h_end:
            return {"energy_offset": e, "warmth_offset": w, "density_offset": d}
    return {"energy_offset": 0.0, "warmth_offset": 0.0, "density_offset": 0.0}


def apply_offset(base_value: float, offset: float) -> float:
    """Clamp base + offset to [0.0, 1.0]."""
    return round(max(0.0, min(1.0, base_value + offset)), 4)


def get_effective_ewd(energy: float, warmth: float, density: float,
                      hour: int | None = None) -> dict:
    """Return effective E/W/D after time-of-day offset."""
    offsets = get_time_offset(hour)
    return {
        "energy": apply_offset(energy, offsets["energy_offset"]),
        "warmth": apply_offset(warmth, offsets["warmth_offset"]),
        "density": apply_offset(density, offsets["density_offset"]),
    }


# ── Audio analysis ─────────────────────────────────────────────

def analyze_audio_file(filepath: str) -> dict:
    """
    Analyze a single audio file and return {energy, warmth, density}.

    Attempts real FFT-based extraction via numpy/pydub first.
    Falls back to metadata estimation if audio loading fails.
    Returns None for any dimension that cannot be computed.
    """
    result = {"energy": None, "warmth": None, "density": None}
    fpath = Path(filepath)
    if not fpath.exists():
        logger.warning(f"Audio file not found: {filepath}")
        return result
    try:
        return _analyze_with_pydub(str(fpath))
    except Exception as e:
        logger.warning(f"Audio analysis failed for {filepath}: {e}")
        return _estimate_from_metadata(str(fpath))


def _load_audio_pydub(filepath: str) -> tuple[np.ndarray, int] | None:
    """Load audio file as mono float32 numpy array via pydub+ffmpeg."""
    try:
        from pydub import AudioSegment
    except ImportError:
        return None

    ext = Path(filepath).suffix.lower()
    fmt_map = {".mp3": "mp3", ".flac": "flac", ".wav": "wav",
               ".m4a": "mp4", ".ogg": "ogg", ".wma": "wma"}
    fmt = fmt_map.get(ext)
    if fmt is None:
        return None

    seg = AudioSegment.from_file(filepath, format=fmt)
    seg = seg.set_channels(1)

    # Load first 60 seconds
    if len(seg) > 60000:
        seg = seg[:60000]

    sr = seg.frame_rate
    samples = np.array(seg.get_array_of_samples(), dtype=np.float32)
    # Normalize to [-1, 1]
    max_val = float(np.iinfo(np.int16).max) if seg.sample_width == 2 else float(2 ** (seg.sample_width * 8 - 1))
    samples /= max_val
    return samples, sr


def _analyze_with_pydub(filepath: str) -> dict:
    """Real FFT-based E/W/D extraction."""
    loaded = _load_audio_pydub(filepath)
    if loaded is None:
        return {"energy": None, "warmth": None, "density": None}

    samples, sr = loaded
    if len(samples) == 0:
        return {"energy": None, "warmth": None, "density": None}

    # ── Energy: RMS + rough BPM ──
    frame_size = 2048
    hop = 1024
    frames = [samples[i:i+frame_size] for i in range(0, len(samples) - frame_size, hop)]
    if not frames:
        return {"energy": None, "warmth": None, "density": None}

    rms_vals = np.array([np.sqrt(np.mean(f**2)) for f in frames])
    rms_mean = float(np.mean(rms_vals))
    rms_norm = min(rms_mean / 0.25, 1.0)  # 0.25 as reference RMS

    # Rough BPM via autocorrelation of energy envelope
    bpm = _estimate_bpm(rms_vals, sr, hop)
    bpm_norm = min(bpm / 180.0, 1.0) if bpm else 0.5

    energy = round(bpm_norm * 0.5 + rms_norm * 0.5, 4)

    # ── Warmth: 1 - spectral centroid ratio ──
    centroid_hz = _spectral_centroid(samples, sr)
    if centroid_hz is not None:
        warmth = round(1.0 - min(centroid_hz / 5000.0, 1.0), 4)
    else:
        warmth = None

    # ── Density: spectral bandwidth + onset rate ──
    bandwidth_hz = _spectral_bandwidth(samples, sr)
    onset_rate = _onset_rate(rms_vals, sr, hop)

    if bandwidth_hz is not None and onset_rate is not None:
        bw_norm = min(bandwidth_hz / 4000.0, 1.0)
        onset_norm = min(onset_rate / 8.0, 1.0)
        density = round(bw_norm * 0.6 + onset_norm * 0.4, 4)
    elif bandwidth_hz is not None:
        density = round(min(bandwidth_hz / 4000.0, 1.0), 4)
    else:
        density = None

    return {"energy": energy, "warmth": warmth, "density": density}


def _estimate_bpm(rms_vals: np.ndarray, sr: int, hop: int) -> float | None:
    """Estimate BPM from RMS energy autocorrelation."""
    try:
        # Downsample energy envelope
        rms_smooth = np.convolve(rms_vals, np.ones(4) / 4, mode='valid')
        rms_centered = rms_smooth - np.mean(rms_smooth)
        corr = np.correlate(rms_centered, rms_centered, mode='full')
        corr = corr[len(corr)//2:]
        # Look for peaks in 60-200 BPM range
        bpm_min_idx = int((60.0 / 200.0) * sr / hop)
        bpm_max_idx = int((60.0 / 60.0) * sr / hop)
        if bpm_max_idx >= len(corr):
            bpm_max_idx = len(corr) - 1
        if bpm_min_idx >= bpm_max_idx:
            return None
        search = corr[bpm_min_idx:bpm_max_idx]
        if len(search) == 0:
            return None
        peak_idx = np.argmax(search) + bpm_min_idx
        if peak_idx == 0:
            return None
        bpm = 60.0 * sr / hop / peak_idx
        return float(np.clip(bpm, 60, 200))
    except Exception:
        return None


def _spectral_centroid(samples: np.ndarray, sr: int) -> float | None:
    """Mean spectral centroid in Hz from FFT frames."""
    try:
        frame_size = 2048
        hop = 1024
        centroids = []
        for i in range(0, len(samples) - frame_size, hop):
            frame = samples[i:i+frame_size] * np.hanning(frame_size)
            fft = np.abs(np.fft.rfft(frame))
            freqs = np.fft.rfftfreq(frame_size, 1.0 / sr)
            if np.sum(fft) > 0:
                centroid = np.sum(freqs * fft) / np.sum(fft)
                centroids.append(centroid)
        return float(np.mean(centroids)) if centroids else None
    except Exception:
        return None


def _spectral_bandwidth(samples: np.ndarray, sr: int) -> float | None:
    """Mean spectral bandwidth in Hz."""
    try:
        frame_size = 2048
        hop = 1024
        bandwidths = []
        for i in range(0, len(samples) - frame_size, hop):
            frame = samples[i:i+frame_size] * np.hanning(frame_size)
            fft = np.abs(np.fft.rfft(frame))
            freqs = np.fft.rfftfreq(frame_size, 1.0 / sr)
            if np.sum(fft) > 0:
                centroid = np.sum(freqs * fft) / np.sum(fft)
                variance = np.sum(((freqs - centroid) ** 2) * fft) / np.sum(fft)
                bandwidths.append(np.sqrt(variance) if variance > 0 else 0)
        return float(np.mean(bandwidths)) if bandwidths else None
    except Exception:
        return None


def _onset_rate(rms_vals: np.ndarray, sr: int, hop: int) -> float | None:
    """Onsets per second based on RMS energy delta."""
    try:
        if len(rms_vals) < 2:
            return None
        diff = np.diff(rms_vals)
        diff[diff < 0] = 0
        threshold = np.mean(diff) + 0.5 * np.std(diff)
        onsets = np.sum(diff > threshold)
        duration_sec = len(rms_vals) * hop / sr
        return float(onsets / duration_sec) if duration_sec > 0 else None
    except Exception:
        return None


def _estimate_from_metadata(filepath: str) -> dict:
    """Fallback: rough estimates from format and duration heuristics."""
    result = {"energy": 0.50, "warmth": 0.50, "density": 0.50}
    ext = Path(filepath).suffix.lower()

    # Format hints
    if ext == ".flac":
        result["density"] = 0.55   # lossless preserves more spectral detail
        result["warmth"] = 0.55
    elif ext == ".mp3":
        result["warmth"] = 0.50

    # Duration hints via mutagen
    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(filepath)
        if audio and hasattr(audio.info, 'length'):
            dur = audio.info.length
            if dur < 120:
                result["energy"] = 0.42
                result["density"] = 0.45
            elif dur > 300:
                result["energy"] = 0.55
                result["density"] = 0.55
    except Exception:
        pass

    return result


# ── Batch analysis ──────────────────────────────────────────────

def batch_analyze_library(session) -> int:
    """
    Analyze all songs in the library that lack E/W/D values.
    Returns count of songs updated.
    """
    from models.music import Song

    songs = session.query(Song).filter(
        (Song.energy.is_(None)) |
        (Song.warmth.is_(None)) |
        (Song.density.is_(None))
    ).all()

    audio_dir = Path(os.path.dirname(__file__)) / ".." / "data" / "audio" / "songs"
    updated = 0

    for song in songs:
        # Resolve audio path
        if song.audio_path:
            fpath = Path(song.audio_path)
            if not fpath.is_absolute():
                fpath = audio_dir / fpath.name
        else:
            # Try matching by title + artist
            fpath = _find_audio_file(audio_dir, song.title, song.artist)

        if not fpath or not fpath.exists():
            logger.warning(f"No audio file for song {song.id}: {song.title}")
            continue

        result = analyze_audio_file(str(fpath))

        if result["energy"] is not None:
            song.energy = result["energy"]
        if result["warmth"] is not None:
            song.warmth = result["warmth"]
        if result["density"] is not None:
            song.density = result["density"]

        if any(v is not None for v in result.values()):
            song.energy_updated_at = datetime.now(timezone.utc)
            updated += 1

    session.commit()
    return updated


def _find_audio_file(audio_dir: Path, title: str, artist: list) -> Path | None:
    """Try to find an audio file by song title/artist in the audio directory."""
    if not audio_dir.exists():
        return None
    for f in audio_dir.iterdir():
        if f.is_file() and f.suffix.lower() in (".mp3", ".flac", ".wav", ".m4a", ".ogg"):
            fname = f.stem.lower()
            title_lower = title.lower()
            if title_lower in fname:
                return f
            if artist and len(artist) > 0:
                artist_lower = artist[0].lower()
                if artist_lower in fname:
                    return f
    return None
