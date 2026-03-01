"""
Deck Control Module
===================

デッキ制御クラス

このモジュールは以下を提供します:
1. Deckクラス（トラック再生制御）
2. AudioConfigデータクラス
3. EQ/Filter/CUE機能

ループ関連ロジックは DeckLoopMixin (deck_loop_mixin.py) に分離済み。
DSP/EQ/Filter/Volume ロジックは DeckDspMixin (deck_dsp_mixin.py) に分離済み。
"""

import logging
import ctypes
import os
from dataclasses import dataclass

from .audio_constants import (
    BASS_LIB, BASS_FX_LIB, BASS_AVAILABLE, BASS_FX_AVAILABLE,
    NUMPY_AVAILABLE,
    BASS_ATTRIB_TEMPO, BASS_ATTRIB_TEMPO_PITCH,
    BASS_STREAM_DECODE, BASS_STREAM_PRESCAN, BASS_SAMPLE_FLOAT, BASS_UNICODE,
    BASS_FX_FREESOURCE, BASS_POS_BYTE,
    BASS_LEVEL_STEREO, BASS_LEVEL_RMS,
)
from .deck_loop_mixin import DeckLoopMixin
from .deck_dsp_mixin import DeckDspMixin

if NUMPY_AVAILABLE:
    import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """
    オーディオ設定
    
    Attributes:
        sample_rate (int): サンプルレート (Hz)
        channels (int): チャンネル数
        block_size (int): ブロックサイズ
    """
    sample_rate: int = 48000
    channels: int = 2
    block_size: int = 2048


class Deck(DeckLoopMixin, DeckDspMixin):
    def __init__(self, name: str, config: AudioConfig):
        self.name = name
        self.config = config
        
        self.stream_decode = 0
        self.stream_fx = 0
        self.duration = 0.0
        self.waveform_cache = None
        
        # Track Analysis Data
        self.original_bpm = 0.0
        
        self.channel_volume = 1.0
        self.mix_volume = 1.0
        self.trim_db = 0.0
        
        self.eq_high = 0.0
        self.eq_mid = 0.0
        self.eq_low = 0.0
        self.filter_val = 0.0
        self.tempo_percent = 0.0
        self.pitch_semitones = 0.0
        
        # EQ Upgrade: 3-stage cascade handles
        self.fx_eq_low = []   # 3段階カスケード・ハンドル
        self.fx_eq_mid = []   # 3段階カスケード・ハンドル
        self.fx_eq_high = []  # 3段階カスケード・ハンドル
        self.fx_filter = 0
        
        # Loop State + Loop Upgrade
        self.loop_active = False
        self.loop_sync_handle = 0
        self.loop_start_bytes = 0
        self.loop_cb_ref = None
        self.loop_start_sec = 0.0     # Loop Upgrade: スナップ済みループ開始位置(秒)
        self.loop_duration_sec = 0.0  # Loop Upgrade: ループ長(秒)
        
        # HOT CUE State は HotCueManager (mixer_core) が管理する
        # deck.py では保持しない
        
        # P-02 Beatgrid: トラックロード時に設定されるビート位置配列
        # first_beat_pos + beat_times で beatgrid を表現
        self.beat_times: list[float] = []  # 各ビートの絶対秒数
        
        self.on_load_complete = None

    def load(self, filepath: str):
        if not BASS_AVAILABLE: return False
        self.unload()
        if not os.path.exists(filepath):
            if self.on_load_complete: self.on_load_complete(self.name, False)
            return False

        self.stream_decode = BASS_LIB.BASS_StreamCreateFile(False, filepath, 0, 0, BASS_STREAM_DECODE | BASS_SAMPLE_FLOAT | BASS_STREAM_PRESCAN | BASS_UNICODE)
        if self.stream_decode == 0:
            if self.on_load_complete: self.on_load_complete(self.name, False)
            return False

        len_bytes = BASS_LIB.BASS_ChannelGetLength(self.stream_decode, BASS_POS_BYTE)
        self.duration = BASS_LIB.BASS_ChannelBytes2Seconds(self.stream_decode, len_bytes) if len_bytes > 0 else 0.0
        self.waveform_cache = self._generate_waveform(self.stream_decode)
        BASS_LIB.BASS_ChannelSetPosition(self.stream_decode, ctypes.c_uint64(0), BASS_POS_BYTE)

        success = False
        if BASS_FX_AVAILABLE:
            self.stream_fx = BASS_FX_LIB.BASS_FX_TempoCreate(self.stream_decode, BASS_FX_FREESOURCE)
            if self.stream_fx != 0: success = True

        if not success:
            if self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_decode); self.stream_decode = 0
            self.stream_fx = BASS_LIB.BASS_StreamCreateFile(False, filepath, 0, 0, BASS_SAMPLE_FLOAT | BASS_STREAM_PRESCAN | BASS_UNICODE)
            if self.stream_fx == 0:
                if self.on_load_complete: self.on_load_complete(self.name, False)
                return False
            logger.info(f"Deck {self.name}: Fallback stream (No Tempo)")
        
        self._setup_dsp()
        self._update_volume()
        self.set_tempo(self.tempo_percent)
        self.set_pitch(self.pitch_semitones)
        self._setup_tempo_options()

        logger.info(f"Deck {self.name} Ready: {os.path.basename(filepath)}")
        if self.on_load_complete: self.on_load_complete(self.name, True)
        return True

    def unload(self):
        self.clear_loop()
        if self.stream_fx and self.stream_fx != self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_fx)
        if self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_decode)
        self.stream_decode = 0; self.stream_fx = 0
        self.duration = 0.0; self.waveform_cache = None
        # EQ Upgrade: リスト型に対応
        self.fx_eq_low = []; self.fx_eq_mid = []; self.fx_eq_high = []

    # EQ定数・DSPメソッド・Filterは DeckDspMixin (deck_dsp_mixin.py) に分離済み

    def set_tempo(self, percent: float):
        self.tempo_percent = max(-50.0, min(50.0, percent))
        if self.stream_fx and BASS_FX_AVAILABLE:
            BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_TEMPO, self.tempo_percent)

    def set_pitch(self, semitones: float):
        self.pitch_semitones = max(-12.0, min(12.0, semitones))
        if self.stream_fx and BASS_FX_AVAILABLE:
            BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_TEMPO_PITCH, self.pitch_semitones)

    def set_volume(self, v: float):
        self.channel_volume = max(0.0, min(1.0, v))
        self._update_volume()

    def set_trim(self, db: float):
        self.trim_db = max(-10.0, min(10.0, db))
        self._update_volume()

    def set_master_volume_coeff(self, coeff: float):
        self.mix_volume = coeff
        self._update_volume()

    # _update_volume / VOLUME_SLIDE_* 定数は DeckDspMixin (deck_dsp_mixin.py) に分離済み

    def play(self):
        if self.stream_fx: BASS_LIB.BASS_ChannelPlay(self.stream_fx, False)

    def pause(self):
        if self.stream_fx: BASS_LIB.BASS_ChannelPause(self.stream_fx)

    def stop(self):
        if self.stream_fx:
            BASS_LIB.BASS_ChannelPause(self.stream_fx)
            BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, ctypes.c_uint64(0), BASS_POS_BYTE)

    def cue(self):
        if self.stream_fx:
            BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, ctypes.c_uint64(0), BASS_POS_BYTE)
            BASS_LIB.BASS_ChannelPause(self.stream_fx)

    def is_playing(self) -> bool:
        if not self.stream_fx: return False
        return BASS_LIB.BASS_ChannelIsActive(self.stream_fx) == 1

    def get_position(self) -> float:
        if not self.stream_fx: return 0.0
        pos_bytes = BASS_LIB.BASS_ChannelGetPosition(self.stream_fx, BASS_POS_BYTE)
        return BASS_LIB.BASS_ChannelBytes2Seconds(self.stream_fx, pos_bytes)

    def get_duration(self) -> float:
        return self.duration

    def get_waveform_data(self, num_points=800):
        return self.waveform_cache

    def set_position(self, seconds: float):
        if not self.stream_fx: return
        # get_position() と同じ stream_fx 座標系でバイト計算する
        # stream_decode と stream_fx は座標系が異なるため混在させてはならない
        pos_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, seconds)
        BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, ctypes.c_uint64(int(pos_bytes)), BASS_POS_BYTE)

    def sync_bpm(self, target_bpm: float) -> bool:
        if not BASS_FX_AVAILABLE or self.original_bpm <= 0:
            return False
        tempo_adjust = ((target_bpm / self.original_bpm) - 1.0) * 100.0
        tempo_adjust = max(-50.0, min(50.0, tempo_adjust))
        self.set_tempo(tempo_adjust)
        logger.info(f"Deck {self.name}: Synced to {target_bpm:.1f} BPM "
                   f"(Original: {self.original_bpm:.1f}, Adjust: {tempo_adjust:+.1f}%)")
        return True

    def get_level(self) -> tuple[float, float]:
        """VUメーター用 L/R RMSレベル取得

        P4: BASS_ChannelGetLevelEx + BASS_LEVEL_RMSで真のRMS値をfloat精度で取得。
        旧API (BASS_ChannelGetLevel) は Hi/Lo WordのUINT16分割で精度が低かった。
        フォールバックとして旧APIも残す（BASSバージョン互換性のため）。

        BASS_ChannelGetLevel は BASS_ERROR_NOTPLAYING (err=24) を返す場合がある。
        停止中は呼び出さず (0.0, 0.0) を返す。

        Returns:
            (left, right): 0.0≤1.0のRMSレベル。停止中・エラー時は(0.0, 0.0)
        """
        if not BASS_AVAILABLE or not self.stream_fx:
            return (0.0, 0.0)
        if not self.is_playing():
            return (0.0, 0.0)
        try:
            # P4: GetLevelEx で L/R RMSをfloat精度で取得
            # BASS_LEVEL_STEREO(2) | BASS_LEVEL_RMS(4) = 6
            # length=0.02秒: 20ms RMSウィンドウ（VUメーターの時定整理に最適）
            levels = (ctypes.c_float * 2)(0.0, 0.0)
            ok = BASS_LIB.BASS_ChannelGetLevelEx(
                self.stream_fx,
                levels,
                ctypes.c_float(0.02),
                BASS_LEVEL_STEREO | BASS_LEVEL_RMS
            )
            if ok:
                left  = max(0.0, min(1.0, float(levels[0])))
                right = max(0.0, min(1.0, float(levels[1])))
                return (left, right)

            # フォールバック: 旧API (BASS_ChannelGetLevel)
            # BASS 2.4未満の環境やGetLevelEx非対応時の互換性のため残す
            level = BASS_LIB.BASS_ChannelGetLevel(self.stream_fx)
            if level == 0xFFFFFFFF:
                err = BASS_LIB.BASS_ErrorGetCode()
                if err == 24:
                    logger.debug(f"Deck {self.name}: GetLevel NOTPLAYING (race condition)")
                else:
                    logger.warning(f"Deck {self.name}: GetLevel failed (err={err})")
                return (0.0, 0.0)
            left  = (level & 0xFFFF) / 32768.0
            right = (level >> 16)   / 32768.0
            return (min(left, 1.0), min(right, 1.0))
        except Exception as e:
            logger.warning(f"Deck {self.name}: get_level exception: {e}")
            return (0.0, 0.0)

    def get_dsp_settings(self):
        stages = len(self.fx_eq_low) if self.fx_eq_low else 1
        return {
            'type': f"BQF LowShelf/PeakEQ/HighShelf (x{stages} Cascade)",
            'eq_high': self.eq_high,
            'eq_mid':  self.eq_mid,
            'eq_low':  self.eq_low,
            'filter':  self.filter_val,
        }

    def apply_track_analysis(self, analysis: dict):
        """トラック解析結果を適用"""
        if 'auto_gain' in analysis:
            self.set_trim(analysis['auto_gain'])
        if 'bpm' in analysis:
            self.original_bpm = analysis['bpm']
            logger.debug(f"Deck {self.name}: Original BPM set to {self.original_bpm}")
        # P-02 Beatgrid: beat_timesをキャッシュから設定
        beat_times = analysis.get('beat_times', [])
        if beat_times:
            self.beat_times = list(beat_times)
            logger.debug(f"Deck {self.name}: Beatgrid loaded ({len(self.beat_times)} beats)")
        else:
            # beat_timesがない場合、BPMと first_beat から生成
            bpm = analysis.get('bpm', 0.0)
            first_beat = analysis.get('first_beat', 0.0)
            duration = self.duration
            if bpm > 0 and duration > 0:
                beat_dur = 60.0 / bpm
                self.beat_times = []
                t = first_beat
                while t < duration:
                    self.beat_times.append(t)
                    t += beat_dur
                logger.debug(f"Deck {self.name}: Beatgrid generated from BPM {bpm:.1f} "
                            f"({len(self.beat_times)} beats)")

    def _generate_waveform(self, decode_stream, points=800):
        if not NUMPY_AVAILABLE or not decode_stream: return None
        try:
            len_bytes = BASS_LIB.BASS_ChannelGetLength(decode_stream, BASS_POS_BYTE)
            if len_bytes <= 0: return None
            chunk = max(8, int(len_bytes // points // 8) * 8)
            buf = (ctypes.c_float * (4096 // 4))()
            vals = []
            for i in range(points):
                BASS_LIB.BASS_ChannelSetPosition(decode_stream, ctypes.c_uint64(i * chunk), BASS_POS_BYTE)
                read = BASS_LIB.BASS_ChannelGetData(decode_stream, buf, min(chunk, 4096))
                if read > 0:
                    arr = np.ctypeslib.as_array(buf)[:read//4]
                    vals.append(min(1.0, np.sqrt(np.mean(arr**2)) * 1.5))
                else: vals.append(0.0)
            return np.convolve(np.array(vals), np.ones(3)/3, mode='same')
        except Exception as e:
            logger.warning(f"Deck {self.name}: _generate_waveform failed: {e}")
            return None