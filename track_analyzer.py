"""
Track Analyzer Module (Phase R6 V7: Downbeat + beat_times + Auto-Cue)
======================================================================
Version 7 Features (Phase R6):
- beat_times: 全ビートの絶対秒数配列を保存（Beatgrid精度向上）
- downbeat_indices: 小節先頭ビートのインデックス配列
- auto_cue: Energy Flow変化点からの自動Cue候補（秒）
- HOT CUE 8スロットに拡張（HotCueManager対応）
- キャッシュv6→v7 自動マイグレーション

Version 6 Features (Phase 8C):
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
    BASS_STREAM_PRESCAN,
    BASS_UNICODE
)

logger = logging.getLogger(__name__)

# Phase R6: Version 7 - beat_times, downbeat, auto_cue, 8-slot HOT CUE
# Phase R6 fix: Version 8 - beat_timesを先頭60秒のみでなく曲全体分で生成
# Phase R6 fix: Version 9 - profile.levelを 0、1.0 → 1.0、5.0 に統一（numericとスケール一致）
ANALYZER_VERSION = 10


class TrackAnalyzer:
    # ─── 解析パラメータ定数 ─────────────────────────────────────────
    # Step 3: Magic Numbers の定数化
    LIBROSA_ANALYSIS_DURATION_SEC: float = 60.0
    """librosa に渡す先頭解析秒数（先頭60秒で BPM/Key/Beat を検出）"""

    ENERGY_POWER_CURVE: float = 2.5
    """Explosive Dynamics べき乗値（0.5^2.5=0.177, 0.8^2.5=0.574 と急峻な立ち上がり）"""

    AUTO_GAIN_CLIP_DB: float = 12.0
    """Auto-gain クリップ値 (±dB)。人間の聴覚的に±12dB が実用上限"""

    def __init__(self, cache_file: str = "analysis_cache.json"):
        self.cache_file = cache_file
        self.cache = self._load_cache()
        self._setup_bass_functions()
        
    def _setup_bass_functions(self):
        """BASS_FX関数のセットアップ"""
        if BASS_FX_AVAILABLE and BASS_FX_LIB:
            try:
                # 常に上書き設定（既存のargtypesが不正な場合でも修正される）
                BASS_FX_LIB.BASS_FX_BPM_DecodeGet.argtypes = [
                    ctypes.c_uint32,   # handle
                    ctypes.c_double,   # startSec
                    ctypes.c_double,   # endSec (-1.0 = 全体)
                    ctypes.c_uint32,   # minMaxBPM (high16=max, low16=min)
                    ctypes.c_uint32,   # flags
                    ctypes.c_void_p,   # callback (NULL)
                    ctypes.c_void_p,   # user (NULL)
                ]
                BASS_FX_LIB.BASS_FX_BPM_DecodeGet.restype = ctypes.c_float
            except Exception as e:
                logger.warning(f"Failed to setup BASS_FX types: {e}")

    def _load_cache(self) -> dict:
        """キャッシュファイルを読み込み"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data
            except Exception as e:
                logger.warning(f"Cache load failed ({self.cache_file}): {e}")
        return {}

    def _save_cache(self):
        """キャッシュをファイルに保存"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Cache save failed ({self.cache_file}): {e}")

    def _get_file_hash(self, filepath: str) -> str:
        """ファイルのMD5ハッシュを計算"""
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
        トラックを解析してBPM、キー、エネルギーなどを取得
        
        Args:
            filepath: 解析するファイルパス
            force_reanalyze: キャッシュを無視して再解析
            
        Returns:
            解析結果の辞書
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
        
        # librosaによる統合分析（BPM、Key、First Beat、beat_times、downbeatを1回のロードで取得）
        librosa_result = self._analyze_with_librosa(filepath, 120.0)
        bpm_librosa = librosa_result['bpm']
        key = librosa_result['key']
        first_beat = librosa_result['first_beat']
        beat_times = librosa_result['beat_times']        # Phase R6: 全ビート秒数配列
        downbeat_indices = librosa_result['downbeat_indices']  # Phase R6: 小節先頭インデックス
        
        # BPMの最終決定
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

        # Phase R6: Energy FlowからAuto-Cue候補を検出
        auto_cue_points = self._detect_auto_cue(energy_data)

        result = {
            'version': ANALYZER_VERSION,
            'filename': os.path.basename(filepath),
            'filepath': filepath,
            'bpm': float(final_bpm),
            'key': key,
            'genre': genre,
            'energy': energy_data,
            'auto_gain': float(auto_gain),
            'first_beat': float(first_beat),
            'beat_times': beat_times,               # Phase R6: 全ビート秒数配列
            'downbeat_indices': downbeat_indices,   # Phase R6: 小節先頭インデックス
            'auto_cue': auto_cue_points,            # Phase R6: Auto-Cue候補（秒）
            'hot_cues': [None] * 8,                 # Phase R6: 8スロットに拡張
            'last_analyzed': int(time.time())
        }
        
        self.cache[file_hash] = result
        self._save_cache()
        return result

    def _get_metadata(self, filepath: str) -> dict:
        """ID3タグからメタデータを取得"""
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
        except Exception as e:
            logger.debug(f"ID3 metadata read failed ({os.path.basename(filepath)}): {e}")
        return meta

    def _get_bpm_bass(self, filepath: str) -> float:
        """BASS_FXを使用してBPMを検出"""
        if not BASS_AVAILABLE or not BASS_FX_AVAILABLE:
            return 0.0
            
        stream = 0
        try:
            stream = BASS_LIB.BASS_StreamCreateFile(
                False, filepath, 0, 0,
                BASS_STREAM_DECODE | BASS_SAMPLE_FLOAT | BASS_STREAM_PRESCAN | BASS_UNICODE
            )
            if not stream:
                err = BASS_LIB.BASS_ErrorGetCode()
                logger.debug(f"BASS_FX BPM: stream open failed for {os.path.basename(filepath)} (err={err})")
                return 0.0
            
            # BPM range: 45-230
            min_max = (230 << 16) | 45 
            bpm = BASS_FX_LIB.BASS_FX_BPM_DecodeGet(
                stream,
                0.0,
                -1.0,
                min_max,
                0,
                None,
                None
            )
            return float(bpm)
        except Exception as e:
            logger.warning(f"BASS_FX BPM detection failed ({os.path.basename(filepath)}): {e}")
            return 0.0
        finally:
            if stream:
                BASS_LIB.BASS_StreamFree(stream)

    def _analyze_with_librosa(self, filepath: str, target_bpm: float) -> dict:
        """
        librosaを使った統合分析（1回のオーディオロードで複数の解析を実行）

        Phase R6 追加:
        - beat_times: 全ビートの絶対秒数リスト
        - downbeat_indices: 4拍ごとの小節先頭ビートインデックスリスト

        修正:
        - BPM/Key/first_beat検出は先頭60秒のみ（高速化のため維持）
        - beat_timesは検出したBPM+first_beatから曲全体分を生成
          （librosaのduration=60秒制限で60秒以降のビートグリッドが消える問題を解消）
        - 曲の実際のdurationはmutagen/BASSで取得

        Returns:
            dict: {
                'bpm': float,
                'key': str,
                'first_beat': float,
                'beat_times': list[float],
                'downbeat_indices': list[int]
            }
        """
        try:
            # オーディオを1回だけロード（BPM/Key/beat検出用、先頭60秒のみ）
            y, sr = librosa.load(filepath, sr=22050, duration=self.LIBROSA_ANALYSIS_DURATION_SEC)
            
            # BPM検出
            bpm = 0.0
            try:
                onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                tempo, _ = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr)
                bpm = float(tempo[0]) if isinstance(tempo, np.ndarray) else float(tempo)
            except Exception as e:
                logger.debug(f"librosa BPM detection failed: {e}")
            
            # キー検出
            key = ""
            try:
                chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
                key_idx = np.argmax(np.mean(chroma, axis=1))
                keys = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
                
                # Major/Minor判定（簡易版）
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
            
            # First Beat検出（先頭60秒のデータから）
            first_beat = 0.0
            try:
                onset_env = librosa.onset.onset_strength(y=y, sr=sr)
                _, raw_beats = librosa.beat.beat_track(
                    onset_envelope=onset_env, sr=sr, units='time'
                )
                if len(raw_beats) > 0:
                    first_beat = float(raw_beats[0])
            except Exception as e:
                logger.debug(f"librosa beat detection failed: {e}")

            # 曲全体のdurationをmutagenまたはBASSで取得
            full_duration = self._get_duration(filepath)

            # beat_timesをハイブリッド方式で生成
            # 先頭60秒: librosa実測値をそのまま使用（BPMの揺れに追従）
            # 60秒以降: 最後の実測ビートからBPM固定で補完
            beat_times = []
            downbeat_indices = []
            if bpm > 0 and full_duration > 0:
                # librosa実測beat_timesを取得（先頭60秒分）
                try:
                    onset_env_full = librosa.onset.onset_strength(y=y, sr=sr)
                    _, raw_beats_full = librosa.beat.beat_track(
                        onset_envelope=onset_env_full, sr=sr, units='time'
                    )
                    measured_beats = [float(t) for t in raw_beats_full]
                except Exception:
                    measured_beats = []

                if measured_beats:
                    # 先頭60秒は実測値をそのまま使用
                    beat_times = measured_beats
                    # 60秒以降をBPM固定で補完
                    beat_dur = 60.0 / bpm
                    last_t = beat_times[-1]
                    t = last_t + beat_dur
                    while t < full_duration:
                        beat_times.append(float(t))
                        t += beat_dur
                    logger.debug(
                        f"beat_times hybrid: {len(measured_beats)} measured + "
                        f"{len(beat_times) - len(measured_beats)} extrapolated "
                        f"(BPM={bpm:.1f}, dur={full_duration:.1f}s)"
                    )
                else:
                    # 実測失敗時はBPM固定グリッドにフォールバック
                    beat_dur = 60.0 / bpm
                    t = first_beat
                    while t < full_duration:
                        beat_times.append(float(t))
                        t += beat_dur
                    logger.debug(
                        f"beat_times fallback (fixed grid): {len(beat_times)} beats "
                        f"(BPM={bpm:.1f}, dur={full_duration:.1f}s)"
                    )

                downbeat_indices = list(range(0, len(beat_times), 4))

            return {
                'bpm': bpm,
                'key': key,
                'first_beat': first_beat,
                'beat_times': beat_times,
                'downbeat_indices': downbeat_indices
            }
            
        except Exception as e:
            logger.warning(f"librosa analysis failed: {e}")
            return {'bpm': 0.0, 'key': '', 'first_beat': 0.0,
                    'beat_times': [], 'downbeat_indices': []}

    def _to_camelot_key(self, key: str, scale: str) -> str:
        """
        音楽キーをCamelot表記に変換
        
        Args:
            key: 'C', 'C#', 'D', etc.
            scale: 'major' or 'minor'
        
        Returns:
            Camelot表記（例: '8B', '8A'）
        """
        # Camelotホイール順序表
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
            return key_map_major.get(key, '8B')  # デフォルトはC Major
        else:
            return key_map_minor.get(key, '8A')  # デフォルトはA Minor

    def _get_duration(self, filepath: str) -> float:
        """
        曲の実際の再生時間（秒）を取得する。
        mutagen → BASS → librosa の順でフォールバック。
        """
        # 1. mutagen (高速、フォールバック不要なら最優先)
        try:
            from mutagen import File as MutagenFile
            audio = MutagenFile(filepath)
            if audio is not None and audio.info is not None:
                dur = float(audio.info.length)
                if dur > 0:
                    return dur
        except Exception:
            pass

        # 2. BASS (既にロード済みライブラリで正確な値)
        if BASS_AVAILABLE:
            try:
                from core.audio_constants import BASS_POS_BYTE
                stream = BASS_LIB.BASS_StreamCreateFile(
                    False, filepath, 0, 0,
                    BASS_STREAM_DECODE | BASS_SAMPLE_FLOAT | BASS_STREAM_PRESCAN | BASS_UNICODE
                )
                if stream:
                    len_bytes = BASS_LIB.BASS_ChannelGetLength(stream, BASS_POS_BYTE)
                    dur = BASS_LIB.BASS_ChannelBytes2Seconds(stream, len_bytes)
                    BASS_LIB.BASS_StreamFree(stream)
                    if dur > 0:
                        return float(dur)
            except Exception:
                pass

        # 3. librosa (低速だが確実)
        try:
            dur = librosa.get_duration(path=filepath)
            return float(dur)
        except Exception:
            return 0.0

    def _detect_auto_cue(self, energy_data: dict) -> list[float]:
        """
        Phase R6: Energy Flow の変化点からAuto-Cue候補（秒）を検出する。

        アルゴリズム:
        1. 秒単位の Energy profile から1階差分を計算
        2. 差分が threshold を超えた秒をセクション境界として検出
        3. 前後 MIN_INTERVAL 秒以内の重複は除外
        4. 最大 MAX_CUES 個を返す

        Args:
            energy_data: _analyze_energy() の戻り値

        Returns:
            Auto-Cue 候補の秒数リスト（昇順）
        """
        CHANGE_THRESHOLD = 0.6   # level 変化量の閾値（1.0〜5.0 スケール、旧0.15×4.0）
        MIN_INTERVAL     = 8.0   # 候補間の最小間隔（秒）
        MAX_CUES         = 8     # 最大候補数

        profile = energy_data.get('profile', [])
        if len(profile) < 4:
            return []

        levels = [p['level'] for p in profile]
        times  = [p['time']  for p in profile]

        candidates: list[float] = []
        prev_time = -MIN_INTERVAL  # 最初の候補を t=0 付近でも拾えるよう初期化

        for i in range(1, len(levels)):
            delta = abs(levels[i] - levels[i - 1])
            t     = times[i]
            if delta >= CHANGE_THRESHOLD and (t - prev_time) >= MIN_INTERVAL:
                # 4小節境界に丸める（4拍 × 4/4拍子 の概算 = BPM 依存なので秒固定で近似）
                candidates.append(float(t))
                prev_time = t
                if len(candidates) >= MAX_CUES:
                    break

        return candidates

    # _analyze_energy 内部定数
    # ダウンサンプリング後のサンプルレート。エネルギープロファイルの分解能とメモリのトレードオフ。
    # 11025Hz = 22050の半分。RMS計算に十分な精度。
    ENERGY_ANALYSIS_SR: int = 11025

    def _analyze_energy(self, filepath: str) -> tuple:
        """
        エネルギー解析（Explosive Dynamics - Power 2.5）

        修正点 (メモリ圧迫解消):
        - 旧実装は 22050Hz で全曲をロードしていたが、6分曲で当時
          sr=22050 なら 7,938,000 サンプル x 4byte = 約 30MB 占有。
        - 現在は sr=11025 (半分) でロードする。同じ曲が約 15MB。
        - RMS分解能(秒単位) に影響はない。

        Returns:
            (energy_data, auto_gain): エネルギーデータと推奨ゲイン
        """
        try:
            # 1. Load Audio (ダウンサンプリングでロード - メモリ圧迫解消)
            # hop_length のスケーリング: 22050→ 11025 に伴い 512→ 256 に変更。
            # 秒当たりのフレーム数 (sr/hop) をほぼ维持するため。1秒分難能は変わらない。
            ENERGY_HOP = 256
            y, sr = librosa.load(filepath, sr=self.ENERGY_ANALYSIS_SR)

            # Shorter frame length for sharper transient detection
            rms = librosa.feature.rms(y=y, frame_length=512, hop_length=ENERGY_HOP)[0]

            if len(rms) == 0:
                return {}, 0.0

            # 2. Collect Raw Points
            frames_per_sec = sr / ENERGY_HOP   # ≈ 43 (11025/256)
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

                # Apply power curve for explosive dynamics
                # 0.0 stays 0.0, but 0.5 becomes 0.177, 0.8 becomes 0.574
                explosive_val = ratio ** self.ENERGY_POWER_CURVE

                # levelは1.0、5.0スケールで保存（numericと統一）
                # explosive_val(0、1.0) → 1.0 + explosive_val * 4.0 → 1.0、5.0
                level_1to5 = 1.0 + explosive_val * 4.0

                profile.append({
                    'time': float(t),
                    'level': float(level_1to5)
                })

            # 4. Calculate Stats
            levels = [p['level'] for p in profile]  # 1.0、5.0スケール
            mean_energy = float(np.mean(levels)) if levels else 3.0
            max_energy = float(np.max(levels)) if levels else 5.0

            # Auto-gain: normalize to peak RMS
            auto_gain = -20.0 * np.log10(p_max) if p_max > 0.001 else 0.0
            auto_gain = max(-self.AUTO_GAIN_CLIP_DB, min(self.AUTO_GAIN_CLIP_DB, auto_gain))

            energy_data = {
                'mean': mean_energy,       # 1.0、5.0
                'max': max_energy,         # 1.0、5.0
                'numeric': mean_energy,    # profile.levelと同じスケールに統一
                'profile': profile
            }

            return energy_data, auto_gain

        except Exception as e:
            logger.warning(f"Energy analysis failed: {e}")
            return {}, 0.0

    def _estimate_genre_from_bpm(self, bpm: float) -> str:
        """BPMから大まかなジャンルを推定"""
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
        BPMを手動で更新（GUIからの補正用）
        
        Args:
            filepath: ファイルパス
            new_bpm: 新しいBPM値
            
        Returns:
            更新成功したらTrue
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
        全トラックの相対エネルギーを再計算（Z-score方式）
        
        Args:
            all_tracks: トラックリスト
            
        Returns:
            ファイルパス → 相対エネルギー (1.0-5.0) のマップ
        """
        # 全トラックのmean energyを収集
        energies = []
        filepath_to_mean = {}
        
        for track in all_tracks:
            energy = track.get('energy', {})
            mean = energy.get('mean', 0.0)
            if mean > 0:
                energies.append(mean)
                filepath_to_mean[track['filepath']] = mean
        
        # 修正: 最小サンプル数を 2 → 5 に引き上げ。
        # 2　2トラックでは外れ値 1つでZ-scoreが大きく振れる。
        # 5トラック以上で概ね安定する。
        if len(energies) < 5:
            # トラックが少ない時は絶対エネルギーを直接 1　5.0 にベタ線形スケーリング
            # （2トラックでライブラリ全体の平均が定まらないのでデフォルト値にしない）
            global_min = min(energies) if energies else 0.0
            global_max = max(energies) if energies else 1.0
            span = global_max - global_min
            if span < 0.001:
                return {fp: 3.0 for fp in filepath_to_mean.keys()}
            relative_map = {}
            for fp, mean in filepath_to_mean.items():
                scaled = 1.0 + (mean - global_min) / span * 4.0  # 1.0〘5.0
                relative_map[fp] = round(max(1.0, min(5.0, scaled)), 3)
            return relative_map

        # Z-scoreで正規化
        mean_val = np.mean(energies)
        std_val = np.std(energies)

        if std_val < 0.01:
            # 標準偏差がほぼゼロの場合は全て 3.0
            return {fp: 3.0 for fp in filepath_to_mean.keys()}
        
        relative_map = {}
        for filepath, mean in filepath_to_mean.items():
            # Z-score計算
            z_score = (mean - mean_val) / std_val
            
            # 1.0-5.0のスケールにマッピング（±3σで範囲に収める）
            # z=-3 -> 1.0, z=0 -> 3.0, z=+3 -> 5.0
            relative = 3.0 + (z_score * (2.0 / 3.0))
            relative = max(1.0, min(5.0, relative))
            
            relative_map[filepath] = float(relative)
        
        return relative_map

    # ─────────────────────────────────────────────────────────────
    # Phase R6: キャッシュ v6 → v7 マイグレーション
    # ─────────────────────────────────────────────────────────────

    def migrate_cache(self) -> int:
        """
        キャッシュ内の旧バージョンエントリを v7 形式に一括マイグレーションする。

        追加フィールドのデフォルト値を補完し、hot_cues を 8 スロットに拡張。
        バージョンフィールドは ANALYZER_VERSION に更新する。

        Returns:
            マイグレーションした件数
        """
        migrated = 0
        for file_hash, entry in self.cache.items():
            if entry.get('version', 0) >= ANALYZER_VERSION:
                continue

            # beat_times / downbeat_indices / auto_cue を補完
            entry.setdefault('beat_times', [])
            entry.setdefault('downbeat_indices', [])
            entry.setdefault('auto_cue', [])

            # hot_cues を 8 スロットに拡張（旧 4 スロットを先頭に保持）
            old_hc = entry.get('hot_cues') or []
            if len(old_hc) < 8:
                old_hc = list(old_hc) + [None] * (8 - len(old_hc))
            entry['hot_cues'] = old_hc[:8]

            entry['version'] = ANALYZER_VERSION
            migrated += 1

        if migrated:
            self._save_cache()
            logger.info(f"Cache migrated: {migrated} entries → v{ANALYZER_VERSION}")

        return migrated

    # ─────────────────────────────────────────────────────────────
    # HOT CUE キャッシュ操作（8スロット対応）
    # ─────────────────────────────────────────────────────────────

    def update_hot_cue(self, filepath: str, slot: int, position: float) -> bool:
        """
        HOT CUE ポイントを更新（Phase R6: 8スロット対応）

        Args:
            filepath: ファイルパス
            slot:     CUE スロット (0-7)
            position: 位置（秒）

        Returns:
            更新成功したら True
        """
        if slot < 0 or slot >= 8:
            return False

        file_hash = self._get_file_hash(filepath)
        if file_hash in self.cache:
            hc = self.cache[file_hash].get('hot_cues') or [None] * 8
            if len(hc) < 8:
                hc = list(hc) + [None] * (8 - len(hc))
            hc[slot] = float(position)
            self.cache[file_hash]['hot_cues'] = hc
            self._save_cache()
            logger.info(f"HOT CUE {slot+1} updated: {os.path.basename(filepath)} @ {position:.2f}s")
            return True
        return False

    def clear_hot_cue(self, filepath: str, slot: int) -> bool:
        """
        HOT CUE ポイントをクリア（Phase R6: 8スロット対応）

        Args:
            filepath: ファイルパス
            slot:     CUE スロット (0-7)

        Returns:
            クリア成功したら True
        """
        if slot < 0 or slot >= 8:
            return False

        file_hash = self._get_file_hash(filepath)
        if file_hash in self.cache:
            hc = self.cache[file_hash].get('hot_cues') or [None] * 8
            if len(hc) < 8:
                hc = list(hc) + [None] * (8 - len(hc))
            hc[slot] = None
            self.cache[file_hash]['hot_cues'] = hc
            self._save_cache()
            logger.info(f"HOT CUE {slot+1} cleared: {os.path.basename(filepath)}")
            return True
        return False

    def get_auto_cue(self, filepath: str) -> list[float]:
        """
        Phase R6: 保存済みの Auto-Cue 候補を返す。

        キャッシュに存在しない場合は空リストを返す（再解析は不要）。

        Args:
            filepath: ファイルパス

        Returns:
            Auto-Cue 候補の秒数リスト
        """
        file_hash = self._get_file_hash(filepath)
        entry = self.cache.get(file_hash, {})
        return entry.get('auto_cue', [])

    def get_beat_times(self, filepath: str) -> list[float]:
        """
        Phase R6: 保存済みのビート秒数配列を返す。

        Args:
            filepath: ファイルパス

        Returns:
            ビート秒数のリスト
        """
        file_hash = self._get_file_hash(filepath)
        entry = self.cache.get(file_hash, {})
        return entry.get('beat_times', [])

    def get_downbeat_times(self, filepath: str) -> list[float]:
        """
        Phase R6: downbeat_indices と beat_times から小節先頭の秒数リストを返す。

        Args:
            filepath: ファイルパス

        Returns:
            小節先頭秒数のリスト
        """
        file_hash = self._get_file_hash(filepath)
        entry = self.cache.get(file_hash, {})
        beat_times      = entry.get('beat_times', [])
        downbeat_idx    = entry.get('downbeat_indices', [])
        if not beat_times or not downbeat_idx:
            return []
        return [
            beat_times[i]
            for i in downbeat_idx
            if i < len(beat_times)
        ]