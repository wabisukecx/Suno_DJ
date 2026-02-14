"""
Track Analyzer Module (Phase 8C V6: HOT CUE + Beatgrid + Librosa Key)
======================================================================
Version 6 Features:
- HOT CUE persistence (4 slots per track)
- First beat detection (beatgrid anchor)
- Librosa-only key detection (Essentia removed)
- Explosive energy dynamics (Power 2.5)
- Auto cache invalidation on version change
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

from core.audio_constants import (
    BASS_AVAILABLE, 
    BASS_FX_AVAILABLE, 
    BASS_LIB, 
    BASS_FX_LIB, 
    BASS_STREAM_DECODE, 
    BASS_SAMPLE_FLOAT, 
    BASS_STREAM_PRESCAN
)

logger = logging.getLogger(__name__)

# Phase 8C Week 3: Version 6 - HOT CUE persistence, Beatgrid, Librosa key only
ANALYZER_VERSION = 6

class TrackAnalyzer:
    def __init__(self, cache_file: str = "analysis_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self._setup_bass_functions()
        
    def _setup_bass_functions(self):
        """BASS_FXé–¢æ•°ã®ã‚»ãƒƒãƒˆã‚¢ãƒƒãƒ—"""
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
        """ã‚­ãƒ£ãƒƒã‚·ãƒ¥ãƒ•ã‚¡ã‚¤ãƒ«ã‚’èª­ã¿è¾¼ã¿"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data
            except Exception:
                pass
        return {}

    def _save_cache(self):
        """ã‚­ãƒ£ãƒƒã‚·ãƒ¥ã‚’ãƒ•ã‚¡ã‚¤ãƒ«ã«ä¿å­˜"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _get_file_hash(self, filepath: str) -> str:
        """ãƒ•ã‚¡ã‚¤ãƒ«ã®MD5ãƒãƒƒã‚·ãƒ¥ã‚’è¨ˆç®—"""
        hasher = hashlib.md5()
        try:
            with open(filepath, 'rb') as f:
                buf = f.read(65536)
                while len(buf) > 0:
                    hasher.update(buf)
                    buf = f.read(65536)
            return hasher.hexdigest()
        except FileNotFoundError:
            return "missing"

    def analyze_track(self, filepath: str, force_reanalyze: bool = False) -> dict:
        """
        ãƒˆãƒ©ãƒƒã‚¯ã‚’è§£æžã—ã¦BPMã€ã‚­ãƒ¼ã€ã‚¨ãƒãƒ«ã‚®ãƒ¼ãªã©ã‚’å–å¾—
        
        Args:
            filepath: è§£æžã™ã‚‹ãƒ•ã‚¡ã‚¤ãƒ«ãƒ‘ã‚¹
            force_reanalyze: ã‚­ãƒ£ãƒƒã‚·ãƒ¥ã‚’ç„¡è¦–ã—ã¦å†è§£æž
            
        Returns:
            è§£æžçµæžœã®è¾žæ›¸
        """
        if not os.path.exists(filepath):
            return {}
            
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
        if final_bpm == 0:
            final_bpm = 120.0
        
        # Energy Analysis (Aggressive Mode)
        energy_data, auto_gain = self._analyze_energy(filepath)
        
        genre = metadata.get('genre', 'Unknown')
        if genre == 'Unknown':
            genre = self._estimate_genre_from_bpm(final_bpm)

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
            'hot_cues': [None, None, None, None],  # Phase 8C Week 3: HOT CUEåˆæœŸå€¤
            'last_analyzed': int(time.time())
        }
        
        self.cache[file_hash] = result
        self._save_cache()
        return result

    def _get_metadata(self, filepath: str) -> dict:
        """ID3ã‚¿ã‚°ã‹ã‚‰ãƒ¡ã‚¿ãƒ‡ãƒ¼ã‚¿ã‚’å–å¾—"""
        meta = {'artist': '', 'title': '', 'genre': 'Unknown'}
        if not MUTAGEN_AVAILABLE:
            return meta
            
        try:
            audio = EasyID3(filepath)
            if 'artist' in audio:
                meta['artist'] = audio['artist'][0]
            if 'title' in audio:
                meta['title'] = audio['title'][0]
            if 'genre' in audio:
                meta['genre'] = audio['genre'][0]
        except Exception:
            pass
        return meta

    def _get_bpm_bass(self, filepath: str) -> float:
        """BASS_FXã‚’ä½¿ç”¨ã—ã¦BPMã‚’æ¤œå‡º"""
        if not BASS_AVAILABLE or not BASS_FX_AVAILABLE:
            return 0.0
            
        stream = 0
        try:
            path_bytes = filepath.encode('utf-8')
            stream = BASS_LIB.BASS_StreamCreateFile(
                False, path_bytes, 0, 0, 
                BASS_STREAM_DECODE | BASS_SAMPLE_FLOAT | BASS_STREAM_PRESCAN
            )
            if not stream:
                return 0.0
            
            # BPM range: 45-230
            min_max = (230 << 16) | 45 
            bpm = BASS_FX_LIB.BASS_FX_BPM_DecodeGet(
                stream, 
                ctypes.c_double(0.0), 
                ctypes.c_double(-1.0), 
                min_max, 
                0, 
                None, 
                None
            )
            return float(bpm)
        except Exception:
            return 0.0
        finally:
            if stream:
                BASS_LIB.BASS_StreamFree(stream)

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

    def _to_camelot_key(self, key: str, scale: str) -> str:
        """
        éŸ³æ¥½ã‚­ãƒ¼ã‚’Camelotè¡¨è¨˜ã«å¤‰æ›
        
        Args:
            key: 'C', 'C#', 'D', etc.
            scale: 'major' or 'minor'
        
        Returns:
            Camelotè¡¨è¨˜ï¼ˆä¾‹: '8B', '8A'ï¼‰
        """
        # Camelotãƒ›ã‚¤ãƒ¼ãƒ«é †åºè¡¨
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
            return key_map_major.get(key, '8B')  # ãƒ‡ãƒ•ã‚©ãƒ«ãƒˆã¯C Major
        else:
            return key_map_minor.get(key, '8A')  # ãƒ‡ãƒ•ã‚©ãƒ«ãƒˆã¯A Minor

    def _analyze_energy(self, filepath: str) -> tuple:
        """
        ã‚¨ãƒãƒ«ã‚®ãƒ¼è§£æžï¼ˆExplosive Dynamics - Power 2.5ï¼‰
        
        Returns:
            (energy_data, auto_gain): ã‚¨ãƒãƒ«ã‚®ãƒ¼ãƒ‡ãƒ¼ã‚¿ã¨æŽ¨å¥¨ã‚²ã‚¤ãƒ³
        """
        try:
            # 1. Load Audio
            y, sr = librosa.load(filepath, sr=22050)
            
            # Shorter frame length for sharper transient detection
            rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=512)[0]
            
            if len(rms) == 0:
                return {}, 0.0

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
            if p_max < 0.001:
                p_max = 1.0

            profile = []
            for t, val in enumerate(raw_points):
                # Ratio against the track's peak (0.0 to 1.0)
                ratio = val / p_max
                
                # Apply Power 2.5 for explosive curve
                # 0.0 stays 0.0, but 0.5 becomes 0.177, 0.8 becomes 0.574
                explosive_val = ratio ** 2.5
                
                profile.append({
                    'time': float(t),
                    'level': float(explosive_val)
                })
            
            # 4. Calculate Stats
            levels = [p['level'] for p in profile]
            mean_energy = float(np.mean(levels)) if levels else 0.0
            max_energy = float(np.max(levels)) if levels else 0.0
            
            # Auto-gain: normalize to peak RMS
            auto_gain = -20.0 * np.log10(p_max) if p_max > 0.001 else 0.0
            auto_gain = max(-12.0, min(12.0, auto_gain))
            
            energy_data = {
                'mean': mean_energy,
                'max': max_energy,
                'numeric': mean_energy * 5.0,  # 0.0-5.0 scale
                'profile': profile
            }
            
            return energy_data, auto_gain
            
        except Exception as e:
            logger.warning(f"Energy analysis failed: {e}")
            return {}, 0.0

    def _estimate_genre_from_bpm(self, bpm: float) -> str:
        """BPMã‹ã‚‰å¤§ã¾ã‹ãªã‚¸ãƒ£ãƒ³ãƒ«ã‚’æŽ¨å®š"""
        if bpm < 100:
            return "Hip Hop / Trip Hop"
        elif bpm < 115:
            return "Downtempo / Chill"
        elif bpm < 125:
            return "House / Deep House"
        elif bpm < 135:
            return "Techno / Tech House"
        elif bpm < 145:
            return "Trance / Progressive"
        elif bpm < 160:
            return "Hardstyle / Hard Trance"
        else:
            return "Drum & Bass / Jungle"

    def update_bpm(self, filepath: str, new_bpm: float) -> bool:
        """
        BPMã‚’æ‰‹å‹•ã§æ›´æ–°ï¼ˆGUIã‹ã‚‰ã®è£œæ­£ç”¨ï¼‰
        
        Args:
            filepath: ãƒ•ã‚¡ã‚¤ãƒ«ãƒ‘ã‚¹
            new_bpm: æ–°ã—ã„BPMå€¤
            
        Returns:
            æ›´æ–°æˆåŠŸã—ãŸã‚‰True
        """
        file_hash = self._get_file_hash(filepath)
        if file_hash in self.cache:
            self.cache[file_hash]['bpm'] = float(new_bpm)
            self._save_cache()
            logger.info(f"BPM updated: {os.path.basename(filepath)} -> {new_bpm}")
            return True
        return False

    def recalculate_relative_energy(self, all_tracks: list) -> dict:
        """
        å…¨ãƒˆãƒ©ãƒƒã‚¯ã®ç›¸å¯¾ã‚¨ãƒãƒ«ã‚®ãƒ¼ã‚’å†è¨ˆç®—ï¼ˆZ-scoreæ–¹å¼ï¼‰
        
        Args:
            all_tracks: ãƒˆãƒ©ãƒƒã‚¯ãƒªã‚¹ãƒˆ
            
        Returns:
            ãƒ•ã‚¡ã‚¤ãƒ«ãƒ‘ã‚¹ â†’ ç›¸å¯¾ã‚¨ãƒãƒ«ã‚®ãƒ¼ (1.0-5.0) ã®ãƒžãƒƒãƒ—
        """
        # å…¨ãƒˆãƒ©ãƒƒã‚¯ã®mean energyã‚’åŽé›†
        energies = []
        filepath_to_mean = {}
        
        for track in all_tracks:
            energy = track.get('energy', {})
            mean = energy.get('mean', 0.0)
            if mean > 0:
                energies.append(mean)
                filepath_to_mean[track['filepath']] = mean
        
        if len(energies) < 2:
            # ãƒˆãƒ©ãƒƒã‚¯ãŒå°‘ãªã™ãŽã‚‹å ´åˆã¯ãƒ‡ãƒ•ã‚©ãƒ«ãƒˆå€¤
            return {fp: 3.0 for fp in filepath_to_mean.keys()}
        
        # Z-scoreã§æ­£è¦åŒ–
        mean_val = np.mean(energies)
        std_val = np.std(energies)
        
        if std_val < 0.01:
            # æ¨™æº–åå·®ãŒã»ã¼ã‚¼ãƒ­ã®å ´åˆã¯å…¨ã¦3.0
            return {fp: 3.0 for fp in filepath_to_mean.keys()}
        
        relative_map = {}
        for filepath, mean in filepath_to_mean.items():
            # Z-scoreè¨ˆç®—
            z_score = (mean - mean_val) / std_val
            
            # 1.0-5.0ã®ã‚¹ã‚±ãƒ¼ãƒ«ã«ãƒžãƒƒãƒ”ãƒ³ã‚°ï¼ˆÂ±3Ïƒã§ç¯„å›²ã«åŽã‚ã‚‹ï¼‰
            # z=-3 -> 1.0, z=0 -> 3.0, z=+3 -> 5.0
            relative = 3.0 + (z_score * (2.0 / 3.0))
            relative = max(1.0, min(5.0, relative))
            
            relative_map[filepath] = float(relative)
        
        return relative_map

    def update_hot_cue(self, filepath: str, slot: int, position: float) -> bool:
        """
        HOT CUEãƒã‚¤ãƒ³ãƒˆã‚’æ›´æ–°
        
        Args:
            filepath: ãƒ•ã‚¡ã‚¤ãƒ«ãƒ‘ã‚¹
            slot: CUEã‚¹ãƒ­ãƒƒãƒˆ (0-3)
            position: ä½ç½®ï¼ˆç§’ï¼‰
            
        Returns:
            æ›´æ–°æˆåŠŸã—ãŸã‚‰True
        """
        if slot < 0 or slot > 3:
            return False
            
        file_hash = self._get_file_hash(filepath)
        if file_hash in self.cache:
            if 'hot_cues' not in self.cache[file_hash]:
                self.cache[file_hash]['hot_cues'] = [None, None, None, None]
            
            self.cache[file_hash]['hot_cues'][slot] = float(position)
            self._save_cache()
            logger.info(f"HOT CUE {slot+1} updated: {os.path.basename(filepath)} @ {position:.2f}s")
            return True
        return False

    def clear_hot_cue(self, filepath: str, slot: int) -> bool:
        """
        HOT CUEãƒã‚¤ãƒ³ãƒˆã‚’ã‚¯ãƒªã‚¢
        
        Args:
            filepath: ãƒ•ã‚¡ã‚¤ãƒ«ãƒ‘ã‚¹
            slot: CUEã‚¹ãƒ­ãƒƒãƒˆ (0-3)
            
        Returns:
            ã‚¯ãƒªã‚¢æˆåŠŸã—ãŸã‚‰True
        """
        if slot < 0 or slot > 3:
            return False
            
        file_hash = self._get_file_hash(filepath)
        if file_hash in self.cache:
            if 'hot_cues' in self.cache[file_hash]:
                self.cache[file_hash]['hot_cues'][slot] = None
                self._save_cache()
                logger.info(f"HOT CUE {slot+1} cleared: {os.path.basename(filepath)}")
                return True
        return False
