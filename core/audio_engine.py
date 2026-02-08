"""
Audio Engine (Phase 8L + EQ Upgrade + Loop Upgrade)
====================================================
Updates:
- EQ Upgrade: 3-stage DX8 ParamEQ cascade for DJ-grade kill EQ (-45dB max)
- Loop Upgrade: Improved beat-snapped looping with floor() snap and enhanced first_beat detection
- Added BASS_SYNC definitions and Ctypes callback (SYNCPROC)
- Implemented set_loop/clear_loop/set_loop_snapped in Deck class
- Enables seamless looping using BASS_SYNC_POS | BASS_SYNC_MIXTIME
"""

import logging
import ctypes
import os
import platform
import math
from typing import Optional, Dict, Any
from dataclasses import dataclass

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

logger = logging.getLogger(__name__)

# --- BASS Constants ---
BASS_ATTRIB_FREQ = 1
BASS_ATTRIB_VOL = 2
BASS_ATTRIB_PAN = 3
BASS_ATTRIB_TEMPO = 0x10000
BASS_ATTRIB_TEMPO_PITCH = 0x10004
BASS_UNICODE = 0x80000000

BASS_STREAM_DECODE = 0x200000
BASS_STREAM_PRESCAN = 0x20000 
BASS_SAMPLE_FLOAT = 256
BASS_FX_FREESOURCE = 0x10000

BASS_POS_BYTE = 0

# Sync Constants (For Looping)
BASS_SYNC_POS = 0
BASS_SYNC_MIXTIME = 0x40000000

# FX Constants
BASS_FX_DX8_PARAMEQ = 7
BASS_FX_BFX_BQF    = 0x1000F

BASS_BFX_BQF_LOWPASS  = 0
BASS_BFX_BQF_HIGHPASS = 1

# Library Loading
if platform.system() == 'Windows':
    lib_ext = '.dll'
    DLL_LOADER = ctypes.WinDLL 
elif platform.system() == 'Darwin':
    lib_ext = '.dylib'
    DLL_LOADER = ctypes.CDLL
else:
    lib_ext = '.so'
    DLL_LOADER = ctypes.CDLL

BASS_LIB = None
BASS_FX_LIB = None
BASS_AVAILABLE = False
BASS_FX_AVAILABLE = False

# --- Ctypes Structures & Callbacks ---
class BASS_DX8_PARAMEQ(ctypes.Structure):
    _fields_ = [
        ("fCenter", ctypes.c_float),
        ("fBandwidth", ctypes.c_float),
        ("fGain", ctypes.c_float),
    ]

class BASS_BFX_BQF(ctypes.Structure):
    _fields_ = [
        ("lFilter", ctypes.c_int),
        ("fCenter", ctypes.c_float),
        ("fGain", ctypes.c_float),
        ("fBandwidth", ctypes.c_float),
        ("fQ", ctypes.c_float),
        ("fS", ctypes.c_float),
        ("lChannel", ctypes.c_int)
    ]

# Callback type for Sync (Looping)
SYNCPROC = ctypes.CFUNCTYPE(None, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)

# --- BASS Library Initialization ---
try:
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    if platform.system() == 'Windows' and hasattr(os, 'add_dll_directory'):
        try: os.add_dll_directory(base_path)
        except: pass

    bass_path = os.path.join(base_path, f'bass{lib_ext}')
    bass_fx_path = os.path.join(base_path, f'bass_fx{lib_ext}')
    
    if os.path.exists(bass_path):
        BASS_LIB = DLL_LOADER(bass_path)
        
        # Argtypes
        BASS_LIB.BASS_Init.argtypes = [ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
        BASS_LIB.BASS_Init.restype = ctypes.c_bool
        BASS_LIB.BASS_Free.restype = ctypes.c_bool
        BASS_LIB.BASS_StreamCreateFile.argtypes = [ctypes.c_bool, ctypes.c_wchar_p, ctypes.c_uint64, ctypes.c_uint64, ctypes.c_uint32]
        BASS_LIB.BASS_StreamCreateFile.restype = ctypes.c_uint32
        BASS_LIB.BASS_StreamFree.argtypes = [ctypes.c_uint32]
        BASS_LIB.BASS_ChannelPlay.argtypes = [ctypes.c_uint32, ctypes.c_bool]
        BASS_LIB.BASS_ChannelPause.argtypes = [ctypes.c_uint32]
        BASS_LIB.BASS_ChannelSetAttribute.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float]
        BASS_LIB.BASS_ChannelSetPosition.argtypes = [ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint32]
        BASS_LIB.BASS_ChannelGetLength.restype = ctypes.c_uint64
        BASS_LIB.BASS_ChannelGetPosition.restype = ctypes.c_uint64
        BASS_LIB.BASS_ChannelBytes2Seconds.restype = ctypes.c_double
        BASS_LIB.BASS_ChannelIsActive.restype = ctypes.c_uint32
        
        # FX & Sync
        BASS_LIB.BASS_ChannelSetFX.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int]
        BASS_LIB.BASS_ChannelSetFX.restype = ctypes.c_uint32
        BASS_LIB.BASS_FXSetParameters.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
        BASS_LIB.BASS_FXSetParameters.restype = ctypes.c_bool
        
        # Sync (for Looping)
        BASS_LIB.BASS_ChannelSetSync.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint64, SYNCPROC, ctypes.c_void_p]
        BASS_LIB.BASS_ChannelSetSync.restype = ctypes.c_uint32
        BASS_LIB.BASS_ChannelRemoveSync.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        BASS_LIB.BASS_ChannelRemoveSync.restype = ctypes.c_bool

        BASS_LIB.BASS_ChannelSeconds2Bytes.argtypes = [ctypes.c_uint32, ctypes.c_double]
        BASS_LIB.BASS_ChannelSeconds2Bytes.restype = ctypes.c_uint64

        BASS_LIB.BASS_ErrorGetCode.restype = ctypes.c_int
        
        # PluginLoad
        BASS_LIB.BASS_PluginLoad.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
        BASS_LIB.BASS_PluginLoad.restype = ctypes.c_uint32

        BASS_LIB.BASS_ChannelGetData.argtypes = [ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
        BASS_LIB.BASS_ChannelGetData.restype = ctypes.c_int

        if BASS_LIB.BASS_Init(-1, 48000, 0, 0, 0):
            BASS_AVAILABLE = True
            logger.info("BASS Output Driver Initialized.")
        else:
            logger.error(f"BASS_Init failed: Error {BASS_LIB.BASS_ErrorGetCode()}")
    
    # BASS_FX
    if os.path.exists(bass_fx_path) and BASS_AVAILABLE:
        try:
            BASS_FX_LIB = DLL_LOADER(bass_fx_path)
            BASS_FX_LIB.BASS_FX_GetVersion.restype = ctypes.c_uint32
            BASS_FX_LIB.BASS_FX_TempoCreate.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
            BASS_FX_LIB.BASS_FX_TempoCreate.restype = ctypes.c_uint32
            BASS_FX_LIB.BASS_FX_TempoGetRateRatio.argtypes = [ctypes.c_uint32]
            BASS_FX_LIB.BASS_FX_TempoGetRateRatio.restype = ctypes.c_float
            
            version = BASS_FX_LIB.BASS_FX_GetVersion()
            BASS_FX_AVAILABLE = True
            logger.info(f"BASS_FX Loaded Successfully (Version: {hex(version)}, Tempo Support Active)")
            
        except Exception as e:
            logger.warning(f"BASS_FX Load Exception: {e}")
            BASS_FX_AVAILABLE = False
    
except Exception as e:
    logger.error(f"BASS Critical Load Error: {e}")


@dataclass
class AudioConfig:
    sample_rate: int = 48000
    channels: int = 2
    block_size: int = 2048


class Deck:
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
        self.fx_eq_low = []   # 3-stage cascade handles
        self.fx_eq_mid = []   # 3-stage cascade handles
        self.fx_eq_high = []  # 3-stage cascade handles
        self.fx_filter = 0
        
        # Loop State + Loop Upgrade
        self.loop_active = False
        self.loop_sync_handle = 0
        self.loop_start_bytes = 0
        self.loop_cb_ref = None
        self.loop_start_sec = 0.0     # Loop Upgrade: スナップ済みループ開始位置(秒)
        self.loop_duration_sec = 0.0  # Loop Upgrade: ループ長(秒)
        
        # HOT CUE State
        self.hot_cues: list[Optional[float]] = [None] * 4
        
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
        BASS_LIB.BASS_ChannelSetPosition(self.stream_decode, 0, BASS_POS_BYTE)

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

        logger.info(f"Deck {self.name} Ready: {os.path.basename(filepath)}")
        if self.on_load_complete: self.on_load_complete(self.name, True)
        return True

    def unload(self):
        self.clear_loop()
        self.clear_all_hot_cues()
        if self.stream_fx and self.stream_fx != self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_fx)
        if self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_decode)
        self.stream_decode = 0; self.stream_fx = 0
        self.duration = 0.0; self.waveform_cache = None
        # EQ Upgrade: リスト型に対応
        self.fx_eq_low = []; self.fx_eq_mid = []; self.fx_eq_high = []

    def _setup_dsp(self):
        if not self.stream_fx: return
        
        # EQ Upgrade: 3-Stage Cascade DX8 EQ (DJ-grade kill EQ)
        # 各バンド3段重ね: -15dB × 3 = -45dB max attenuation
        EQ_CASCADE_STAGES = 3
        
        self.fx_eq_low = []
        self.fx_eq_mid = []
        self.fx_eq_high = []
        
        for _ in range(EQ_CASCADE_STAGES):
            h_low = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
            h_mid = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
            h_high = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
            if h_low: self.fx_eq_low.append(h_low)
            if h_mid: self.fx_eq_mid.append(h_mid)
            if h_high: self.fx_eq_high.append(h_high)
        
        # Initialize all stages with DJ-standard crossover frequencies
        # (based on Mixxx's default EQ settings)
        for h in self.fx_eq_low:
            self._update_dx8_eq(h, 246.0, 8.0, self.eq_low)  # Low: 246Hz (DJ standard)
        for h in self.fx_eq_mid:
            self._update_dx8_eq(h, 2500.0, 12.0, self.eq_mid)  # Mid: 2.5kHz (DJ standard)
        for h in self.fx_eq_high:
            self._update_dx8_eq(h, 10000.0, 8.0, self.eq_high)  # High: 10kHz (same)

        if BASS_FX_AVAILABLE:
            self.fx_filter = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_BFX_BQF, 0)
        
        logger.debug(f"Deck {self.name}: EQ Setup - {len(self.fx_eq_low)}x3 cascade stages")

    def _update_dx8_eq(self, handle, center, bw, gain):
        if not handle: return
        # カスケードでゲインが3倍になるため、1段あたりは控えめに
        safe_gain = max(-15.0, min(15.0, gain))
        p = BASS_DX8_PARAMEQ(center, bw, safe_gain)
        BASS_LIB.BASS_FXSetParameters(handle, ctypes.byref(p))

    def set_eq_low(self, db: float):
        self.eq_low = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} Low: {db:.1f}dB (x{len(self.fx_eq_low)} cascade)") 
        for h in self.fx_eq_low:
            self._update_dx8_eq(h, 246.0, 8.0, db)  # 246Hz (DJ standard)

    def set_eq_mid(self, db: float):
        self.eq_mid = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} Mid: {db:.1f}dB (x{len(self.fx_eq_mid)} cascade)")
        for h in self.fx_eq_mid:
            self._update_dx8_eq(h, 2500.0, 12.0, db)  # 2.5kHz (DJ standard)

    def set_eq_high(self, db: float):
        self.eq_high = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} High: {db:.1f}dB (x{len(self.fx_eq_high)} cascade)")
        for h in self.fx_eq_high:
            self._update_dx8_eq(h, 10000.0, 8.0, db)  # 10kHz

    def set_filter(self, val: float):
        self.filter_val = val
        if not self.fx_filter: return
        p = BASS_BFX_BQF(lChannel=-1, fGain=0.0, fBandwidth=1.0, fQ=1.0, fS=0.0)
        
        if abs(val) < 0.05:
            p.lFilter = BASS_BFX_BQF_LOWPASS; p.fCenter = 20000.0; p.fQ = 0.707
        elif val < 0: # LPF
            p.lFilter = BASS_BFX_BQF_LOWPASS
            p.fCenter = max(100.0, 20000.0 + val * 19800.0)
            p.fQ = 0.707
        else: # HPF
            p.lFilter = BASS_BFX_BQF_HIGHPASS
            p.fCenter = min(10000.0, 20.0 + val * 9980.0)
            p.fQ = 0.707
        
        BASS_LIB.BASS_FXSetParameters(self.fx_filter, ctypes.byref(p))

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

    def _update_volume(self):
        if not self.stream_fx: return
        trim_linear = 10.0 ** (self.trim_db / 20.0)
        final_vol = self.channel_volume * trim_linear * self.mix_volume
        BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_VOL, final_vol)

    def play(self):
        if self.stream_fx: BASS_LIB.BASS_ChannelPlay(self.stream_fx, False)

    def pause(self):
        if self.stream_fx: BASS_LIB.BASS_ChannelPause(self.stream_fx)

    def stop(self):
        if self.stream_fx:
            BASS_LIB.BASS_ChannelPause(self.stream_fx)
            BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, 0, BASS_POS_BYTE)

    def cue(self):
        if self.stream_fx:
            BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, 0, BASS_POS_BYTE)
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
        pos_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, seconds)
        BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, pos_bytes, BASS_POS_BYTE)

    def sync_bpm(self, target_bpm: float) -> bool:
        if not BASS_FX_AVAILABLE or self.original_bpm <= 0:
            return False
        tempo_adjust = ((target_bpm / self.original_bpm) - 1.0) * 100.0
        tempo_adjust = max(-50.0, min(50.0, tempo_adjust))
        self.set_tempo(tempo_adjust)
        logger.info(f"Deck {self.name}: Synced to {target_bpm:.1f} BPM "
                   f"(Original: {self.original_bpm:.1f}, Adjust: {tempo_adjust:+.1f}%)")
        return True

    # --- Loop Implementation ---
    def set_loop(self, start_pos: float, duration: float):
        """Set a seamless loop using BASS_ChannelSetSync"""
        if not self.stream_fx:
            logger.warning(f"Deck {self.name}: No stream loaded")
            return
        
        self.clear_loop()
        
        # ループ終了位置（調整なし - BASS_SYNC_MIXTIMEが正確に動作）
        end_pos = start_pos + duration
        
        start_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, ctypes.c_double(start_pos))
        end_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, ctypes.c_double(end_pos))
        
        self.loop_start_bytes = start_bytes
        
        def loop_callback(handle, channel, data, user):
            BASS_LIB.BASS_ChannelSetPosition(channel, self.loop_start_bytes, BASS_POS_BYTE)
        
        self.loop_cb_ref = SYNCPROC(loop_callback)
        self.loop_sync_handle = BASS_LIB.BASS_ChannelSetSync(
            self.stream_fx,
            BASS_SYNC_POS | BASS_SYNC_MIXTIME,
            end_bytes,
            self.loop_cb_ref,
            None
        )
        
        if self.loop_sync_handle:
            self.loop_active = True
            logger.info(f"Deck {self.name}: Loop set {start_pos:.2f}s - {end_pos:.2f}s (duration: {duration:.2f}s)")
        else:
            logger.error(f"Deck {self.name}: Loop sync failed, Error: {BASS_LIB.BASS_ErrorGetCode()}")

    def clear_loop(self):
        if self.loop_sync_handle:
            BASS_LIB.BASS_ChannelRemoveSync(self.stream_fx, self.loop_sync_handle)
            self.loop_sync_handle = 0
            self.loop_active = False
            self.loop_cb_ref = None
            logger.info(f"Deck {self.name}: Loop cleared")

    def set_loop_snapped(self, bpm: float, first_beat: float = 0.0, bars: int = 4):
        """
        Loop Upgrade: ビートグリッドにスナップした4小節ループを設定
        
        改善点:
        - floor() で「今鳴っている小節」の頭にスナップ (round→floor)
        - ループ開始/長さを属性に保存し外部から参照可能に
        - first_beatが不正な場合のフォールバック強化
        - ビートグリッド位置のバリデーション追加
        """
        if not self.stream_fx:
            return
        
        # BPMフォールバック
        if bpm <= 0:
            logger.warning(f"Deck {self.name}: Invalid BPM ({bpm}), using 120.0")
            bpm = 120.0
        
        beat_duration = 60.0 / bpm
        bar_duration = beat_duration * 4  # 4/4拍子前提
        loop_duration = bar_duration * bars
        
        current = self.get_position()
        
        # first_beatバリデーション: 負値や曲尺超えは無効
        if first_beat < 0 or first_beat > self.duration:
            logger.warning(f"Deck {self.name}: Invalid first_beat ({first_beat:.3f}s), resetting to 0.0")
            first_beat = 0.0
        
        # ビートグリッドからの経過を計算
        if current >= first_beat:
            elapsed = current - first_beat
            # floor: 「今いる小節」の頭にスナップ (roundだと次の小節に飛ぶ場合がある)
            bar_index = int(elapsed / bar_duration)  # int() = floor for positive values
            snap_start = first_beat + (bar_index * bar_duration)
            
            # デバッグ情報
            logger.info(f"Deck {self.name} Loop Snap Debug:")
            logger.info(f"  Current position: {current:.3f}s")
            logger.info(f"  First beat: {first_beat:.3f}s")
            logger.info(f"  Elapsed from first beat: {elapsed:.3f}s")
            logger.info(f"  Bar duration: {bar_duration:.3f}s ({beat_duration:.3f}s × 4)")
            logger.info(f"  Bar index (floor): {bar_index}")
            logger.info(f"  Snap start: {snap_start:.3f}s")
            logger.info(f"  Expected bars in loop: 0={first_beat:.3f}s, 1={first_beat + bar_duration:.3f}s, 2={first_beat + bar_duration*2:.3f}s, 3={first_beat + bar_duration*3:.3f}s")
        else:
            # 再生位置がfirst_beatより前 (イントロ等)
            # first_beatからのループにする
            snap_start = first_beat
        
        # スナップ位置のバリデーション
        snap_start = max(0.0, snap_start)
        
        # ループ終了が曲尾を超える場合、開始位置を手前にずらす
        if self.duration > 0 and (snap_start + loop_duration) > self.duration:
            # 曲末から逆算して最後の完全なN小節区間を取る
            total_bars = int((self.duration - first_beat) / bar_duration)
            if total_bars >= bars:
                snap_start = first_beat + ((total_bars - bars) * bar_duration)
            else:
                # 曲が短すぎる場合、曲頭から
                snap_start = first_beat
        
        # Loop Upgrade: ループ開始/長さを属性に保存 (外部参照用)
        self.loop_start_sec = snap_start
        self.loop_duration_sec = loop_duration
        
        # ループ設定
        self.set_loop(snap_start, loop_duration)
        
        logger.info(f"Deck {self.name}: Loop SNAPPED to bar {int((snap_start - first_beat) / bar_duration):.0f} "
                   f"(Start: {snap_start:.3f}s, Duration: {loop_duration:.3f}s, "
                   f"BPM: {bpm:.1f}, FirstBeat: {first_beat:.3f}s)")

    # --- HOT CUE Implementation ---
    def set_hot_cue(self, slot: int, position: float):
        if 0 <= slot < 4:
            self.hot_cues[slot] = position
            logger.info(f"Deck {self.name}: HOT CUE {slot+1} set at {position:.2f}s")

    def jump_to_hot_cue(self, slot: int):
        if 0 <= slot < 4 and self.hot_cues[slot] is not None:
            self.set_position(self.hot_cues[slot])
            logger.info(f"Deck {self.name}: Jumped to HOT CUE {slot+1}")

    def clear_hot_cue(self, slot: int):
        if 0 <= slot < 4:
            self.hot_cues[slot] = None
            logger.info(f"Deck {self.name}: HOT CUE {slot+1} cleared")

    def clear_all_hot_cues(self):
        self.hot_cues = [None] * 4
        logger.debug(f"Deck {self.name}: All HOT CUEs cleared")

    def get_dsp_settings(self):
        stages = len(self.fx_eq_low) if self.fx_eq_low else 1
        return {
            'type': f"DX8(x{stages} Cascade)",
            'eq_high': f"{self.eq_high:.1f}dB (eff: {self.eq_high * stages:.0f}dB)",
            'eq_mid': f"{self.eq_mid:.1f}dB (eff: {self.eq_mid * stages:.0f}dB)",
            'eq_low': f"{self.eq_low:.1f}dB (eff: {self.eq_low * stages:.0f}dB)",
        }

    def apply_track_analysis(self, analysis: dict):
        """トラック解析結果を適用"""
        if 'auto_gain' in analysis:
            self.set_trim(analysis['auto_gain'])
        if 'bpm' in analysis:
            self.original_bpm = analysis['bpm']
            logger.debug(f"Deck {self.name}: Original BPM set to {self.original_bpm}")

    def _generate_waveform(self, decode_stream, points=800):
        if not NUMPY_AVAILABLE or not decode_stream: return None
        try:
            len_bytes = BASS_LIB.BASS_ChannelGetLength(decode_stream, BASS_POS_BYTE)
            if len_bytes <= 0: return None
            chunk = max(8, int(len_bytes // points // 8) * 8)
            buf = (ctypes.c_float * (4096 // 4))()
            vals = []
            for i in range(points):
                BASS_LIB.BASS_ChannelSetPosition(decode_stream, i * chunk, BASS_POS_BYTE)
                read = BASS_LIB.BASS_ChannelGetData(decode_stream, buf, min(chunk, 4096))
                if read > 0:
                    arr = np.ctypeslib.as_array(buf)[:read//4]
                    vals.append(min(1.0, np.sqrt(np.mean(arr**2)) * 1.5))
                else: vals.append(0.0)
            return np.convolve(np.array(vals), np.ones(3)/3, mode='same')
        except: return None


class AudioEngine:
    def __init__(self, config: AudioConfig):
        self.config = config
        self.deck_a = Deck("A", config)
        self.deck_b = Deck("B", config)
        self.master_volume = 1.0
        self.crossfader = 0.5
        self.running = False

    def start(self) -> bool:
        if not BASS_AVAILABLE: return False
        self.running = True
        return True

    def stop(self):
        self.running = False
        self.deck_a.unload(); self.deck_b.unload()
        if BASS_AVAILABLE: BASS_LIB.BASS_Free()

    def set_crossfader(self, v: float):
        self.crossfader = max(0.0, min(1.0, v))
        self._update_mix()

    def set_master_volume(self, v: float):
        self.master_volume = max(0.0, min(1.0, v))
        self._update_mix()

    def _update_mix(self):
        theta = self.crossfader * (math.pi / 2)
        self.deck_a.set_master_volume_coeff(math.cos(theta) * self.master_volume)
        self.deck_b.set_master_volume_coeff(math.sin(theta) * self.master_volume)


class VCI100_MIDI:
    CROSSFADER = 8; MASTER_VOLUME = 24
    CH1_VOLUME = 12; CH1_TRIM = 28; CH1_EQ_HIGH = 20; CH1_EQ_MID = 21; CH1_EQ_LOW = 22; CH1_FILTER = 23; CH1_TEMPO = 14
    CH2_VOLUME = 13; CH2_TRIM = 29; CH2_EQ_HIGH = 24; CH2_EQ_MID = 25; CH2_EQ_LOW = 26; CH2_FILTER = 27; CH2_TEMPO = 15
    CH1_LOOP = 66
    CH2_LOOP = 67
