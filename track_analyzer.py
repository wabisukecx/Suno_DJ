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
import numpy as np
import librosa
from pathlib import Path
import ctypes

try:
    from mutagen.easyid3 import EasyID3
    MUTAGEN_AVAILABLE = True
except ImportError:
    MUTAGEN_AVAILABLE = False

try:
    from essentia.standard import MonoLoader, KeyExtractor
    ESSENTIA_AVAILABLE = True
except ImportError:
    ESSENTIA_AVAILABLE = False
    # Pylance警告回避用のダミー定義
    MonoLoader = None
    KeyExtractor = None

from audio_engine import BASS_AVAILABLE, BASS_FX_AVAILABLE, BASS_LIB, BASS_FX_LIB, BASS_STREAM_DECODE, BASS_SAMPLE_FLOAT, BASS_STREAM_PRESCAN

logger = logging.getLogger(__name__)

# Phase 8C Week 3: Version 5 - HOT CUE persistence, Beatgrid, Essentia key
ANALYZER_VERSION = 5

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
        
        # Hybrid BPM
        bpm_bass = self._get_bpm_bass(filepath)
        bpm_librosa = self._get_bpm_librosa(filepath)
        final_bpm = bpm_bass if bpm_bass > 0 else bpm_librosa
        if bpm_bass > 0 and bpm_librosa > 0 and abs(bpm_bass - bpm_librosa) > 5.0:
            final_bpm = bpm_bass
        if final_bpm == 0: final_bpm = 120.0

        key = self._get_key_librosa(filepath)
        
        # Beat Grid Detection (Phase 8C Week 3)
        first_beat = self._detect_first_beat(filepath, final_bpm)
        
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
            'hot_cues': [None, None, None, None],  # Phase 8C Week 3: HOT CUE永続化
            'last_analyzed': 0
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

    def _get_bpm_librosa(self, filepath: str) -> float:
        try:
            y, sr = librosa.load(filepath, sr=22050, duration=60)
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
            return float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
        except Exception: return 0.0

    def _get_key_librosa(self, filepath: str) -> str:
        """
        キー検出（Essentia優先、libosaフォールバック）
        Phase 8C Week 3: Essentia統合
        """
        # Essentia KeyExtractorを試行
        essentia_key = self._get_key_essentia(filepath)
        if essentia_key and essentia_key != "Unknown":
            return essentia_key
        
        # Essentiaが使えない場合はlibosaフォールバック
        try:
            y, sr = librosa.load(filepath, sr=22050, duration=60)
            chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
            key_idx = np.argmax(np.mean(chroma, axis=1))
            keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            
            # Camelot表記を追加（簡易的な推定）
            camelot = self._to_camelot_key(keys[key_idx], 'major')  # 仮でMajor
            return f"{keys[key_idx]} ({camelot})"
        except Exception:
            return "Unknown"
    
    def _get_key_essentia(self, filepath: str) -> str:
        """
        Essentia KeyExtractorによる高精度キー検出
        Phase 8C Week 3
        
        Returns:
            "C Maj (8B)" 形式のキー文字列、失敗時は空文字列
        """
        if not ESSENTIA_AVAILABLE:
            logger.debug("Essentia not available, skipping")
            return ""
        
        try:
            # オーディオロード（最初の60秒）
            audio = MonoLoader(filename=filepath, sampleRate=44100)()
            if len(audio) > 44100 * 60:
                audio = audio[:44100 * 60]
            
            # キー検出
            key_extractor = KeyExtractor()
            key, scale, strength = key_extractor(audio)
            
            # Camelot表記に変換
            camelot = self._to_camelot_key(key, scale)
            
            # 出力形式: "C Maj (8B)"
            scale_str = 'Maj' if scale == 'major' else 'Min'
            result = f"{key} {scale_str} ({camelot})"
            
            logger.info(f"Essentia key detection: {result} (strength: {strength:.2f})")
            return result
            
        except Exception as e:
            logger.warning(f"Essentia key detection failed: {e}, falling back to librosa")
            return ""
    
    def _to_camelot_key(self, key: str, scale: str) -> str:
        """
        音楽キーをCamelot表記に変換
        
        Args:
            key: 'C', 'C#', 'D', etc.
            scale: 'major' or 'minor'
        
        Returns:
            Camelot表記（例: '8B', '8A'）
        """
        # Camelotホイール逆引き
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
            return key_map_major.get(key, '8B')  # デフォルトC Major
        else:
            return key_map_minor.get(key, '8A')  # デフォルトA Minor
    
    def _detect_first_beat(self, filepath: str, bpm: float) -> float:
        """
        最初のビート位置を検出（Phase 8C Week 3）
        
        Suno生成曲は通常BPMが一定なので、簡易的な検出でOK
        最初の60秒だけを解析して計算量を削減
        
        Args:
            filepath: 音声ファイルパス
            bpm: 検出済みBPM
        
        Returns:
            最初のビート位置（秒）
        """
        try:
            # 最初の60秒だけロード（計算量削減）
            y, sr = librosa.load(filepath, sr=22050, duration=60)
            
            # Onset Detection（アタック検出）
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            onset_frames = librosa.onset.onset_detect(
                onset_envelope=onset_env,
                sr=sr,
                units='frames'
            )
            
            if len(onset_frames) == 0:
                # Onset検出失敗時は0.0を返す
                logger.warning(f"No onsets detected in {os.path.basename(filepath)}")
                return 0.0
            
            # 最初のOnsetを秒に変換
            first_onset_sec = librosa.frames_to_time(onset_frames[0], sr=sr)
            
            # BPMから1拍の長さを計算
            beat_duration = 60.0 / bpm
            
            # 最初のOnsetを最寄りのビートグリッドに丸める
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
        HOT CUEポイントをキャッシュに保存
        
        Args:
            filepath: トラックファイルパス
            hot_cues: HOT CUEポイントリスト [pos1, pos2, pos3, pos4]
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
        キャッシュからHOT CUEポイントを読み込み
        
        Args:
            filepath: トラックファイルパス
        
        Returns:
            HOT CUEポイントリスト [pos1, pos2, pos3, pos4]、存在しない場合は[None]*4
        """
        file_hash = self._get_file_hash(filepath)
        
        if file_hash in self.cache:
            hot_cues = self.cache[file_hash].get('hot_cues', [None] * 4)
            logger.debug(f"HOT CUEs loaded for {os.path.basename(filepath)}: {hot_cues}")
            return hot_cues
        
        return [None] * 4


# --- Camelot Wheel & Key Matching (Phase 8C Week 2) ---

# Camelotホイール定義
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
    Camelotキーから互換キーリストを返す
    
    互換性ルール:
    1. 同一キー（8A → 8A）
    2. 隣接キー（8A → 7A, 9A）
    3. 対キー（8A → 8B）
    
    Args:
        camelot: Camelotキー（例: "8A", "8B"）
    
    Returns:
        互換キーのリスト（自身を含む4つ）
    
    Example:
        >>> get_compatible_keys("8A")
        ['8A', '7A', '9A', '8B']
    """
    if not camelot or len(camelot) < 2:
        return []
    
    try:
        num = int(camelot[:-1])  # "8A" → 8
        letter = camelot[-1]     # "8A" → "A"
    except (ValueError, IndexError):
        return []
    
    compatible = [camelot]  # 同一キー
    
    # 隣接キー (±1、ホイールは12段階で循環)
    for delta in [-1, 1]:
        adj_num = ((num - 1 + delta) % 12) + 1  # 1-12の範囲で循環
        compatible.append(f"{adj_num}{letter}")
    
    # 対キー (A↔B)
    opposite = 'B' if letter == 'A' else 'A'
    compatible.append(f"{num}{opposite}")
    
    return compatible


def extract_camelot_from_key(key_string: str) -> str:
    """
    キー文字列からCamelot表記を抽出
    
    Args:
        key_string: "A Min (8A)" または "8A" 形式
    
    Returns:
        Camelot表記（例: "8A"）、見つからない場合は空文字列
    
    Example:
        >>> extract_camelot_from_key("A Min (8A)")
        '8A'
        >>> extract_camelot_from_key("8A")
        '8A'
    """
    import re
    match = re.search(r'(\d{1,2}[AB])', key_string)
    return match.group(1) if match else ""