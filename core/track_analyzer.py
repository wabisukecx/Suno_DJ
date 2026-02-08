"""
Track Analyzer Module (Phase 8C V4: Explosive Dynamics)
=======================================================
Fixes:
- Energy Flow: Changed from Linear to Exponential (Power of 2.5).
- Anchored "Silence" to 0.0 (Removed min-max floor lifting).
- Result: Quiet parts stick to 0, drops spike aggressively.
- Auto Cache Invalidation: Version 4
"""

import os
import hashlib
import json
import logging
import time
import numpy as np
import librosa
from pathlib import Path
import ctypes

try:
    from mutagen.easyid3 import EasyID3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

from core.audio_engine import BASS_AVAILABLE, BASS_FX_AVAILABLE, BASS_LIB, BASS_FX_LIB, BASS_STREAM_DECODE, BASS_SAMPLE_FLOAT, BASS_STREAM_PRESCAN

logger = logging.getLogger(__name__)

# Phase 8C Week 3: Version 6 - HOT CUE persistence, Beatgrid, Librosa key only
ANALYZER_VERSION = 6

class TrackAnalyzer:
    def __init__(self, cache_file: str = "analysis_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self._setup_bass_functions()
        
    def _setup_bass_functions(self):
        if BASS_FX_AVAILABLE and BASS_FX_LIB:
            try:
                if not getattr(BASS_FX_LIB.BASS_FX_BPM_DecodeGet, 'argtypes', None):
                    BASS_FX_LIB.BASS_FX_BPM_DecodeGet.argtypes = [
                        ctypes.c_uint32, ctypes.c_double, ctypes.c_double,
                        ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p
                    ]
                    BASS_FX_LIB.BASS_FX_BPM_DecodeGet.restype = ctypes.c_float
            except Exception as e:
                logger.warning(f"Failed to setup BASS_FX types: {e}")

    def _load_cache(self) -> dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data
            except Exception: pass
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception: pass

    def _get_file_hash(self, filepath: str) -> str:
        hasher = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                buf = f.read(65536)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(65536)
            return hasher.hexdigest()
        except FileNotFoundError: return "missing"

    def analyze_track(self, filepath: str, force_reanalyze: bool = False) -> dict:
        if not os.path.exists(filepath): return {}
        file_hash = self._get_file_hash(filepath)
        
        # Check cache version
        cached_data = self.cache.get(file_hash)
        if not force_reanalyze and cached_data:
            if cached_data.get('version', 0) == ANALYZER_VERSION:
                return cached_data
            else:
                logger.info(f"Updating analysis format (V{ANALYZER_VERSION}) for: {os.path.basename(filepath)}")

        logger.info(f"Analyzing track: {os.path.basename(filepath)}")
        
        metadata = self._get_metadata(filepath)
        
        # Hybrid BPM with optimized librosa (single audio load)
        bpm_bass = self._get_bpm_bass(filepath)
        
        # librosaã«ã‚ˆã‚‹çµ±åˆåˆ†æžï¼ˆBPMã€Keyã€First Beatã‚’1å›žã®ãƒ­ãƒ¼ãƒ‰ã§å–å¾—ï¼‰
        librosa_result = self._analyze_with_librosa(filepath, 120.0)
        bpm_librosa = librosa_result['bpm']
        key = librosa_result['key']
        first_beat = librosa_result['first_beat']
        
        # BPMã®æœ€çµ‚æ±ºå®š
        final_bpm = bpm_bass if bpm_bass > 0 else bpm_librosa
        if bpm_bass > 0 and bpm_librosa > 0 and abs(bpm_bass - bpm_librosa) > 5.0:
            final_bpm = bpm_bass
        if final_bpm == 0: final_bpm = 120.0
        
        # Energy Analysis (Aggressive Mode)
        energy_data, auto_gain = self._analyze_energy(filepath)
        
        genre = metadata.get('genre', 'Unknown')
        if genre == 'Unknown': genre = self._estimate_genre_from_bpm(final_bpm)

        result = {
            'version': ANALYZER_VERSION,
            'filename': os.path.basename(filepath),
            'filepath': filepath,
            'bpm': float(final_bpm),
            'key': key,
            'genre': genre,
            'energy': energy_data,
            'auto_gain': float(auto_gain),
            'first_beat': float(first_beat),  # Phase 8C Week 3
            'hot_cues': [None, None, None, None],  # Phase 8C Week 3: HOT CUEÃ¦Â°Â¸Ã§Â¶Å¡Ã¥Å’â€“
            'last_analyzed': int(time.time())
        }
        
        self.cache[file_hash] = result
        self._save_cache()
        return result

    def _get_metadata(self, filepath: str) -> dict:
        meta = {'artist': '', 'title': '', 'genre': 'Unknown'}
        if not MUTAGEN_AVAILABLE: return meta
        try:
            audio = EasyID3(filepath)
            if 'artist' in audio: meta['artist'] = audio['artist'][0]
            if 'title' in audio: meta['title'] = audio['title'][0]
            if 'genre' in audio: meta['genre'] = audio['genre'][0]
        except Exception: pass
        return meta

    def _get_bpm_bass(self, filepath: str) -> float:
        if not BASS_AVAILABLE or not BASS_FX_AVAILABLE: return 0.0
        stream = 0
        try:
            path_bytes = filepath.encode('utf-8')
            stream = BASS_LIB.BASS_StreamCreateFile(False, path_bytes, 0, 0, BASS_STREAM_DECODE | BASS_SAMPLE_FLOAT | BASS_STREAM_PRESCAN)
            if not stream: return 0.0
            
            min_max = (230 << 16) | 45 
            bpm = BASS_FX_LIB.BASS_FX_BPM_DecodeGet(stream, ctypes.c_double(0.0), ctypes.c_double(-1.0), min_max, 0, None, None)
            return float(bpm)
        except Exception: return 0.0
        finally:
            if stream: BASS_LIB.BASS_StreamFree(stream)

    # TODO: Performance optimization - librosa.load() is called 3 times for same file
    # Should load audio once and share between _get_bpm_librosa, _get_key_librosa, _detect_first_beat

    def _analyze_with_librosa(self, filepath: str, target_bpm: float) -> dict:
        """
        librosaã‚’ä½¿ã£ãŸçµ±åˆåˆ†æžï¼ˆ1å›žã®ã‚ªãƒ¼ãƒ‡ã‚£ã‚ªãƒ­ãƒ¼ãƒ‰ã§è¤‡æ•°ã®è§£æžã‚’å®Ÿè¡Œï¼‰
        
        Returns:
            dict: {
                'bpm': float,
                'key': str,
                'first_beat': float
            }
        """
        try:
            # ã‚ªãƒ¼ãƒ‡ã‚£ã‚ªã‚’1å›žã ã‘ãƒ­ãƒ¼ãƒ‰
            y, sr = librosa.load(filepath, sr=22050, duration=60)
            
            # BPMæ¤œå‡º
            bpm = 0.0
            try:
                onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
                bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
            except Exception as e:
                logger.debug(f"librosa BPM detection failed: {e}")
            
            # ã‚­ãƒ¼æ¤œå‡º
            key = ""
            try:
                chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
                key_idx = np.argmax(np.mean(chroma, axis=1))
                keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
                
                # Major/Minoråˆ¤å®šï¼ˆç°¡æ˜“ç‰ˆï¼‰
                chroma_mean = np.mean(chroma, axis=1)
                major_profile = np.array([1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1])
                minor_profile = np.array([1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0])
                
                major_corr = np.correlate(chroma_mean, np.roll(major_profile, key_idx))[0]
                minor_corr = np.correlate(chroma_mean, np.roll(minor_profile, key_idx))[0]
                
                scale = 'Maj' if major_corr > minor_corr else 'Min'
                camelot = self._to_camelot_key(keys[key_idx], 'major' if scale == 'Maj' else 'minor')
                key = f"{keys[key_idx]} {scale} ({camelot})"
            except Exception as e:
                logger.debug(f"librosa key detection failed: {e}")
            
            # First Beatæ¤œå‡º
            first_beat = 0.0
            try:
                onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units='time')[1]
                if len(beats) > 0:
                    first_beat = float(beats[0])
            except Exception as e:
                logger.debug(f"librosa first beat detection failed: {e}")
            
            return {
                'bpm': bpm,
                'key': key,
                'first_beat': first_beat
            }
            
        except Exception as e:
            logger.warning(f"librosa analysis failed: {e}")
            return {'bpm': 0.0, 'key': '', 'first_beat': 0.0}


    def _get_bpm_librosa(self, filepath: str) -> float:
        try:
            y, sr = librosa.load(filepath, sr=22050, duration=60)
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            return float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
        except Exception: return 0.0

    def _get_key_librosa(self, filepath: str) -> str:
        """
        Ã£â€šÂ­Ã£Æ’Â¼Ã¦Â¤Å“Ã¥â€¡ÂºÃ¯Â¼Ë†EssentiaÃ¥â€žÂªÃ¥â€¦Ë†Ã£â‚¬ÂlibosaÃ£Æ’â€¢Ã£â€šÂ©Ã£Æ’Â¼Ã£Æ’Â«Ã£Æ’ÂÃ£Æ’Æ’Ã£â€šÂ¯Ã¯Â¼â€°
        Phase 8C Week 3: EssentiaÃ§ÂµÂ±Ã¥ÂË†
        """
        # Essentia KeyExtractorÃ£â€šâ€™Ã¨Â©Â¦Ã¨Â¡Å’
        essentia_key = self._get_key_essentia(filepath)
        if essentia_key and essentia_key != "Unknown":
            return essentia_key
        
        # EssentiaÃ£ÂÅ’Ã¤Â½Â¿Ã£ÂË†Ã£ÂÂªÃ£Ââ€žÃ¥Â Â´Ã¥ÂË†Ã£ÂÂ¯libosaÃ£Æ’â€¢Ã£â€šÂ©Ã£Æ’Â¼Ã£Æ’Â«Ã£Æ’ÂÃ£Æ’Æ’Ã£â€šÂ¯
        try:
            y, sr = librosa.load(filepath, sr=22050, duration=60)
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            key_idx = np.argmax(np.mean(chroma, axis=1))
            keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            
            # CamelotÃ¨Â¡Â¨Ã¨Â¨ËœÃ£â€šâ€™Ã¨Â¿Â½Ã¥Å Â Ã¯Â¼Ë†Ã§Â°Â¡Ã¦Ëœâ€œÃ§Å¡â€žÃ£ÂÂªÃ¦Å½Â¨Ã¥Â®Å¡Ã¯Â¼â€°
            camelot = self._to_camelot_key(keys[key_idx], 'major')  # Ã¤Â»Â®Ã£ÂÂ§Major
            return f"{keys[key_idx]} ({camelot})"
        except Exception:
            return "Unknown"
    

    def _to_camelot_key(self, key: str, scale: str) -> str:
        """
        Ã©Å¸Â³Ã¦Â¥Â½Ã£â€šÂ­Ã£Æ’Â¼Ã£â€šâ€™CamelotÃ¨Â¡Â¨Ã¨Â¨ËœÃ£ÂÂ«Ã¥Â¤â€°Ã¦Ââ€º
        
        Args:
            key: 'C', 'C#', 'D', etc.
            scale: 'major' or 'minor'
        
        Returns:
            CamelotÃ¨Â¡Â¨Ã¨Â¨ËœÃ¯Â¼Ë†Ã¤Â¾â€¹: '8B', '8A'Ã¯Â¼â€°
        """
        # CamelotÃ£Æ’â€ºÃ£â€šÂ¤Ã£Æ’Â¼Ã£Æ’Â«Ã©â‚¬â€ Ã¥Â¼â€¢Ã£ÂÂ
        key_map_major = {
            'B': '1B', 'F#': '2B', 'Db': '3B', 'Ab': '4B', 'Eb': '5B',
            'Bb': '6B', 'F': '7B', 'C': '8B', 'G': '9B', 'D': '10B',
            'A': '11B', 'E': '12B'
        }
        key_map_minor = {
            'Ab': '1A', 'Eb': '2A', 'Bb': '3A', 'F': '4A', 'C': '5A',
            'G': '6A', 'D': '7A', 'A': '8A', 'E': '9A', 'B': '10A',
            'F#': '11A', 'Db': '12A', 'C#': '12A'  # C# = Db
        }
        
        scale_lower = scale.lower()
        
        if scale_lower == 'major':
            return key_map_major.get(key, '8B')  # Ã£Æ’â€¡Ã£Æ’â€¢Ã£â€šÂ©Ã£Æ’Â«Ã£Æ’Ë†C Major
        else:
            return key_map_minor.get(key, '8A')  # Ã£Æ’â€¡Ã£Æ’â€¢Ã£â€šÂ©Ã£Æ’Â«Ã£Æ’Ë†A Minor
    
    def _detect_first_beat(self, filepath: str, bpm: float) -> float:
        """
        Ã¦Å“â‚¬Ã¥Ë†ÂÃ£ÂÂ®Ã£Æ’â€œÃ£Æ’Â¼Ã£Æ’Ë†Ã¤Â½ÂÃ§Â½Â®Ã£â€šâ€™Ã¦Â¤Å“Ã¥â€¡ÂºÃ¯Â¼Ë†Phase 8C Week 3Ã¯Â¼â€°
        
        SunoÃ§â€Å¸Ã¦Ë†ÂÃ¦â€ºÂ²Ã£ÂÂ¯Ã©â‚¬Å¡Ã¥Â¸Â¸BPMÃ£ÂÅ’Ã¤Â¸â‚¬Ã¥Â®Å¡Ã£ÂÂªÃ£ÂÂ®Ã£ÂÂ§Ã£â‚¬ÂÃ§Â°Â¡Ã¦Ëœâ€œÃ§Å¡â€žÃ£ÂÂªÃ¦Â¤Å“Ã¥â€¡ÂºÃ£ÂÂ§OK
        Ã¦Å“â‚¬Ã¥Ë†ÂÃ£ÂÂ®60Ã§Â§â€™Ã£ÂÂ Ã£Ââ€˜Ã£â€šâ€™Ã¨Â§Â£Ã¦Å¾ÂÃ£Ââ€”Ã£ÂÂ¦Ã¨Â¨Ë†Ã§Â®â€”Ã©â€¡ÂÃ£â€šâ€™Ã¥â€°Å Ã¦Â¸â€º
        
        Args:
            filepath: Ã©Å¸Â³Ã¥Â£Â°Ã£Æ’â€¢Ã£â€šÂ¡Ã£â€šÂ¤Ã£Æ’Â«Ã£Æ’â€˜Ã£â€šÂ¹
            bpm: Ã¦Â¤Å“Ã¥â€¡ÂºÃ¦Â¸Ë†Ã£ÂÂ¿BPM
        
        Returns:
            Ã¦Å“â‚¬Ã¥Ë†ÂÃ£ÂÂ®Ã£Æ’â€œÃ£Æ’Â¼Ã£Æ’Ë†Ã¤Â½ÂÃ§Â½Â®Ã¯Â¼Ë†Ã§Â§â€™Ã¯Â¼â€°
        """
        try:
            # Ã¦Å“â‚¬Ã¥Ë†ÂÃ£ÂÂ®60Ã§Â§â€™Ã£ÂÂ Ã£Ââ€˜Ã£Æ’Â­Ã£Æ’Â¼Ã£Æ’â€°Ã¯Â¼Ë†Ã¨Â¨Ë†Ã§Â®â€”Ã©â€¡ÂÃ¥â€°Å Ã¦Â¸â€ºÃ¯Â¼â€°
            y, sr = librosa.load(filepath, sr=22050, duration=60)
            
            # Onset DetectionÃ¯Â¼Ë†Ã£â€šÂ¢Ã£â€šÂ¿Ã£Æ’Æ’Ã£â€šÂ¯Ã¦Â¤Å“Ã¥â€¡ÂºÃ¯Â¼â€°
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            onset_frames = librosa.onset.onset_detect(
                onset_envelope=onset_env,
                sr=sr,
                units='frames'
            )
            
            if len(onset_frames) == 0:
                # OnsetÃ¦Â¤Å“Ã¥â€¡ÂºÃ¥Â¤Â±Ã¦â€¢â€”Ã¦â„¢â€šÃ£ÂÂ¯0.0Ã£â€šâ€™Ã¨Â¿â€Ã£Ââ„¢
                logger.warning(f"No onsets detected in {os.path.basename(filepath)}")
                return 0.0
            
            # Ã¦Å“â‚¬Ã¥Ë†ÂÃ£ÂÂ®OnsetÃ£â€šâ€™Ã§Â§â€™Ã£ÂÂ«Ã¥Â¤â€°Ã¦Ââ€º
            first_onset_sec = librosa.frames_to_time(onset_frames[0], sr=sr)
            
            # BPMÃ£Ââ€¹Ã£â€šâ€°1Ã¦â€¹ÂÃ£ÂÂ®Ã©â€¢Â·Ã£Ââ€¢Ã£â€šâ€™Ã¨Â¨Ë†Ã§Â®â€”
            beat_duration = 60.0 / bpm
            
            # Ã¦Å“â‚¬Ã¥Ë†ÂÃ£ÂÂ®OnsetÃ£â€šâ€™Ã¦Å“â‚¬Ã¥Â¯â€žÃ£â€šÅ Ã£ÂÂ®Ã£Æ’â€œÃ£Æ’Â¼Ã£Æ’Ë†Ã£â€šÂ°Ã£Æ’ÂªÃ£Æ’Æ’Ã£Æ’â€°Ã£ÂÂ«Ã¤Â¸Â¸Ã£â€šÂÃ£â€šâ€¹
            first_beat = round(first_onset_sec / beat_duration) * beat_duration
            
            logger.debug(f"First beat detected: {first_beat:.3f}s (onset: {first_onset_sec:.3f}s, BPM: {bpm:.1f})")
            return float(first_beat)
            
        except Exception as e:
            logger.warning(f"Beat detection failed for {os.path.basename(filepath)}: {e}")
            return 0.0

    def _analyze_energy(self, filepath: str) -> tuple:
        try:
            # 1. Load Audio
            y, sr = librosa.load(filepath, sr=22050)
            
            # Shorter frame length for sharper transient detection
            rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=512)[0]
            
            if len(rms) == 0: return {}, 0.0

            # 2. Collect Raw Points
            frames_per_sec = sr / 512
            total_sec = len(rms) / frames_per_sec
            raw_points = []
            
            for i in range(int(total_sec)):
                start = int(i * frames_per_sec)
                end = int((i + 1) * frames_per_sec)
                segment = rms[start:end]
                
                if len(segment) > 0:
                    # Use 98th percentile to capture only the loudest kicks in that second
                    val = float(np.percentile(segment, 98))
                    raw_points.append(val)
                else:
                    raw_points.append(0.0)
            
            # 3. Explosive Scaling (Exponential Curve)
            p_max = np.max(raw_points) if raw_points else 1.0
            if p_max < 0.001: p_max = 1.0

            profile = []
            for t, val in enumerate(raw_points):
                # Ratio against the track's peak (0.0 to 1.0)
                # NOT using p_min here. We anchor silence to 0.
                ratio = val / p_max
                
                # Apply Threshold / Noise Gate
                # If signal is less than 5% of peak, crush it to 0 (Silence)
                if ratio < 0.05:
                    ratio = 0.0
                
                # Exponential Curve (Power of 2.5)
                # 0.2 -> 0.01 (Very Low)
                # 0.5 -> 0.17 (Low)
                # 0.8 -> 0.57 (Medium-High)
                # 1.0 -> 1.00 (Max)
                curve = np.power(ratio, 2.5)
                
                # Map to visual range 0.0 - 5.0
                level = curve * 5.0
                
                profile.append({'time': float(t), 'level': float(level)})

            # 4. Global Stats
            mean_rms = float(np.mean(rms))
            max_rms = float(np.max(rms))
            
            # 5. Auto Gain
            target_linear = 0.25 
            if max_rms > 0:
                gain_linear = target_linear / max_rms
                auto_gain_db = 20 * np.log10(gain_linear)
                auto_gain_db = max(-12.0, min(12.0, auto_gain_db))
            else: auto_gain_db = 0.0

            energy_data = {
                'mean': mean_rms,
                'max': max_rms,
                'profile': profile,
                'numeric': min(5.0, 1.0 + (mean_rms * 15.0)) 
            }
            return energy_data, auto_gain_db
            
        except Exception as e:
            logger.error(f"Energy analysis failed: {e}")
            return {}, 0.0

    def _estimate_genre_from_bpm(self, bpm: float) -> str:
        if 60 <= bpm < 90: return "Dubstep / Trap"
        if 90 <= bpm < 110: return "Hip Hop / Glitch"
        if 110 <= bpm < 128: return "House / Deep House"
        if 128 <= bpm < 140: return "Techno / Trance"
        if 140 <= bpm < 160: return "Dubstep / Hardstyle"
        if 160 <= bpm < 180: return "Drum & Bass"
        if bpm >= 180: return "Hardcore"
        return "Electronic"

    def update_bpm(self, filepath: str, new_bpm: float) -> bool:
        file_hash = self._get_file_hash(filepath)
        if file_hash in self.cache:
            self.cache[file_hash]['bpm'] = float(new_bpm)
            self._save_cache()
            return True
        return False

    def recalculate_relative_energy(self, all_tracks: list) -> list:
        if len(all_tracks) < 2: return all_tracks
        
        means = [t.get('energy', {}).get('mean', 0.0) for t in all_tracks]
        valid_means = [m for m in means if m > 0]
        if not valid_means: return all_tracks
        
        global_mean = np.mean(valid_means)
        global_std = np.std(valid_means)
        if global_std == 0: global_std = 0.001
        
        updated = []
        for track in all_tracks:
            energy = track.get('energy', {})
            raw_mean = energy.get('mean', 0.0)
            
            z = (raw_mean - global_mean) / global_std
            new_level = 3.0 + z
            new_level = max(1.0, min(5.0, new_level))
            
            energy['numeric'] = float(new_level)
            track['energy'] = energy
            
            fhash = self._get_file_hash(track['filepath'])
            if fhash in self.cache:
                self.cache[fhash]['energy'] = energy
            updated.append(track)
                
        self._save_cache()
        return updated
    
    # --- HOT CUE Persistence (Phase 8C Week 3) ---
    
    def save_hot_cues(self, filepath: str, hot_cues: list):
        """
        HOT CUEÃ£Æ’ÂÃ£â€šÂ¤Ã£Æ’Â³Ã£Æ’Ë†Ã£â€šâ€™Ã£â€šÂ­Ã£Æ’Â£Ã£Æ’Æ’Ã£â€šÂ·Ã£Æ’Â¥Ã£ÂÂ«Ã¤Â¿ÂÃ¥Â­Ëœ
        
        Args:
            filepath: Ã£Æ’Ë†Ã£Æ’Â©Ã£Æ’Æ’Ã£â€šÂ¯Ã£Æ’â€¢Ã£â€šÂ¡Ã£â€šÂ¤Ã£Æ’Â«Ã£Æ’â€˜Ã£â€šÂ¹
            hot_cues: HOT CUEÃ£Æ’ÂÃ£â€šÂ¤Ã£Æ’Â³Ã£Æ’Ë†Ã£Æ’ÂªÃ£â€šÂ¹Ã£Æ’Ë† [pos1, pos2, pos3, pos4]
        """
        file_hash = self._get_file_hash(filepath)
        
        if file_hash in self.cache:
            self.cache[file_hash]['hot_cues'] = hot_cues
            self._save_cache()
            logger.debug(f"HOT CUEs saved for {os.path.basename(filepath)}")
        else:
            logger.warning(f"Cannot save HOT CUEs: track not in cache: {filepath}")
    
    def load_hot_cues(self, filepath: str) -> list:
        """
        Ã£â€šÂ­Ã£Æ’Â£Ã£Æ’Æ’Ã£â€šÂ·Ã£Æ’Â¥Ã£Ââ€¹Ã£â€šâ€°HOT CUEÃ£Æ’ÂÃ£â€šÂ¤Ã£Æ’Â³Ã£Æ’Ë†Ã£â€šâ€™Ã¨ÂªÂ­Ã£ÂÂ¿Ã¨Â¾Â¼Ã£ÂÂ¿
        
        Args:
            filepath: Ã£Æ’Ë†Ã£Æ’Â©Ã£Æ’Æ’Ã£â€šÂ¯Ã£Æ’â€¢Ã£â€šÂ¡Ã£â€šÂ¤Ã£Æ’Â«Ã£Æ’â€˜Ã£â€šÂ¹
        
        Returns:
            HOT CUEÃ£Æ’ÂÃ£â€šÂ¤Ã£Æ’Â³Ã£Æ’Ë†Ã£Æ’ÂªÃ£â€šÂ¹Ã£Æ’Ë† [pos1, pos2, pos3, pos4]Ã£â‚¬ÂÃ¥Â­ËœÃ¥Å“Â¨Ã£Ââ€”Ã£ÂÂªÃ£Ââ€žÃ¥Â Â´Ã¥ÂË†Ã£ÂÂ¯[None]*4
        """
        file_hash = self._get_file_hash(filepath)
        
        if file_hash in self.cache:
            hot_cues = self.cache[file_hash].get('hot_cues', [None] * 4)
            logger.debug(f"HOT CUEs loaded for {os.path.basename(filepath)}: {hot_cues}")
            return hot_cues
        
        return [None] * 4


# --- Camelot Wheel & Key Matching (Phase 8C Week 2) ---

# CamelotÃ£Æ’â€ºÃ£â€šÂ¤Ã£Æ’Â¼Ã£Æ’Â«Ã¥Â®Å¡Ã§Â¾Â©
CAMELOT_WHEEL = {
    '1A': 'Ab Min', '1B': 'B Maj',  '2A': 'Eb Min', '2B': 'F# Maj',
    '3A': 'Bb Min', '3B': 'Db Maj', '4A': 'F Min',  '4B': 'Ab Maj',
    '5A': 'C Min',  '5B': 'Eb Maj', '6A': 'G Min',  '6B': 'Bb Maj',
    '7A': 'D Min',  '7B': 'F Maj',  '8A': 'A Min',  '8B': 'C Maj',
    '9A': 'E Min',  '9B': 'G Maj',  '10A':'B Min',  '10B':'D Maj',
    '11A':'F# Min', '11B':'A Maj',  '12A':'Db Min', '12B':'E Maj',
}

def get_compatible_keys(camelot: str) -> list[str]:
    """
    CamelotÃ£â€šÂ­Ã£Æ’Â¼Ã£Ââ€¹Ã£â€šâ€°Ã¤Âºâ€™Ã¦Ââ€ºÃ£â€šÂ­Ã£Æ’Â¼Ã£Æ’ÂªÃ£â€šÂ¹Ã£Æ’Ë†Ã£â€šâ€™Ã¨Â¿â€Ã£Ââ„¢
    
    Ã¤Âºâ€™Ã¦Ââ€ºÃ¦â‚¬Â§Ã£Æ’Â«Ã£Æ’Â¼Ã£Æ’Â«:
    1. Ã¥ÂÅ’Ã¤Â¸â‚¬Ã£â€šÂ­Ã£Æ’Â¼Ã¯Â¼Ë†8A Ã¢â€ â€™ 8AÃ¯Â¼â€°
    2. Ã©Å¡Â£Ã¦Å½Â¥Ã£â€šÂ­Ã£Æ’Â¼Ã¯Â¼Ë†8A Ã¢â€ â€™ 7A, 9AÃ¯Â¼â€°
    3. Ã¥Â¯Â¾Ã£â€šÂ­Ã£Æ’Â¼Ã¯Â¼Ë†8A Ã¢â€ â€™ 8BÃ¯Â¼â€°
    
    Args:
        camelot: CamelotÃ£â€šÂ­Ã£Æ’Â¼Ã¯Â¼Ë†Ã¤Â¾â€¹: "8A", "8B"Ã¯Â¼â€°
    
    Returns:
        Ã¤Âºâ€™Ã¦Ââ€ºÃ£â€šÂ­Ã£Æ’Â¼Ã£ÂÂ®Ã£Æ’ÂªÃ£â€šÂ¹Ã£Æ’Ë†Ã¯Â¼Ë†Ã¨â€¡ÂªÃ¨ÂºÂ«Ã£â€šâ€™Ã¥ÂÂ«Ã£â€šâ‚¬4Ã£ÂÂ¤Ã¯Â¼â€°
    
    Example:
        >>> get_compatible_keys("8A")
        ['8A', '7A', '9A', '8B']
    """
    if not camelot or len(camelot) < 2:
        return []
    
    try:
        num = int(camelot[:-1])  # "8A" Ã¢â€ â€™ 8
        letter = camelot[-1]     # "8A" Ã¢â€ â€™ "A"
    except (ValueError, IndexError):
        return []
    
    compatible = [camelot]  # Ã¥ÂÅ’Ã¤Â¸â‚¬Ã£â€šÂ­Ã£Æ’Â¼
    
    # Ã©Å¡Â£Ã¦Å½Â¥Ã£â€šÂ­Ã£Æ’Â¼ (Ã‚Â±1Ã£â‚¬ÂÃ£Æ’â€ºÃ£â€šÂ¤Ã£Æ’Â¼Ã£Æ’Â«Ã£ÂÂ¯12Ã¦Â®ÂµÃ©Å¡Å½Ã£ÂÂ§Ã¥Â¾ÂªÃ§â€™Â°)
    for delta in [-1, 1]:
        adj_num = ((num - 1 + delta) % 12) + 1  # 1-12Ã£ÂÂ®Ã§Â¯â€žÃ¥â€ºÂ²Ã£ÂÂ§Ã¥Â¾ÂªÃ§â€™Â°
        compatible.append(f"{adj_num}{letter}")
    
    # Ã¥Â¯Â¾Ã£â€šÂ­Ã£Æ’Â¼ (AÃ¢â€ â€B)
    opposite = 'B' if letter == 'A' else 'A'
    compatible.append(f"{num}{opposite}")
    
    return compatible


def extract_camelot_from_key(key_string: str) -> str:
    """
    Ã£â€šÂ­Ã£Æ’Â¼Ã¦â€“â€¡Ã¥Â­â€”Ã¥Ë†â€”Ã£Ââ€¹Ã£â€šâ€°CamelotÃ¨Â¡Â¨Ã¨Â¨ËœÃ£â€šâ€™Ã¦Å Â½Ã¥â€¡Âº
    
    Args:
        key_string: "A Min (8A)" Ã£ÂÂ¾Ã£ÂÅ¸Ã£ÂÂ¯ "8A" Ã¥Â½Â¢Ã¥Â¼Â
    
    Returns:
        CamelotÃ¨Â¡Â¨Ã¨Â¨ËœÃ¯Â¼Ë†Ã¤Â¾â€¹: "8A"Ã¯Â¼â€°Ã£â‚¬ÂÃ¨Â¦â€¹Ã£ÂÂ¤Ã£Ââ€¹Ã£â€šâ€°Ã£ÂÂªÃ£Ââ€žÃ¥Â Â´Ã¥ÂË†Ã£ÂÂ¯Ã§Â©ÂºÃ¦â€“â€¡Ã¥Â­â€”Ã¥Ë†â€”
    
    Example:
        >>> extract_camelot_from_key("A Min (8A)")
        '8A'
        >>> extract_camelot_from_key("8A")
        '8A'
    """
    import re
    match = re.search(r'(\d{1,2}[AB])', key_string)
    return match.group(1) if match else ""