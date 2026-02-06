"""
Audio Engine (Phase 8L: 4-Bar Loop Implementation)
==================================================
Updates:
- Added BASS_SYNC definitions and Ctypes callback (SYNCPROC).
- Implemented set_loop/clear_loop in Deck class.
- Enables seamless looping using BASS_SYNC_POS | BASS_SYNC_MIXTIME.
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
BASS_POS_SEC = 0 

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
# void CALLBACK SyncProc(HSYNC handle, DWORD channel, DWORD data, void *user);
SYNCPROC = ctypes.CFUNCTYPE(None, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p)

try:
    base_path = os.path.dirname(os.path.abspath(__file__))
    
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

        if BASS_LIB.BASS_Init(-1, 48000, 0, 0, 0):
            BASS_AVAILABLE = True
            logger.info("BASS Output Driver Initialized.")
        else:
            logger.error(f"BASS Init Failed: {BASS_LIB.BASS_ErrorGetCode()}")

    # Load BASS_FX (Phase 9.1: ÃƒÂ¦Ã‚Â­Ã‚Â£ÃƒÂ£Ã‚ÂÃ¢â‚¬â€ÃƒÂ£Ã‚ÂÃ¢â‚¬Å¾LoadLibraryÃƒÂ¦Ã¢â‚¬â€œÃ‚Â¹ÃƒÂ¥Ã‚Â¼Ã‚Â)
    if BASS_AVAILABLE and os.path.exists(bass_fx_path):
        try:
            # BASS_FXÃƒÂ£Ã‚ÂÃ‚Â¯ÃƒÂ§Ã¢â‚¬Â¹Ã‚Â¬ÃƒÂ§Ã‚Â«Ã¢â‚¬Â¹ÃƒÂ£Ã‚ÂÃ¢â‚¬â€ÃƒÂ£Ã‚ÂÃ…Â¸DLLÃƒÂ£Ã‚ÂÃ‚Â¨ÃƒÂ£Ã‚ÂÃ¢â‚¬â€ÃƒÂ£Ã‚ÂÃ‚Â¦ÃƒÂ§Ã¢â‚¬ÂºÃ‚Â´ÃƒÂ¦Ã…Â½Ã‚Â¥ÃƒÂ£Ã†â€™Ã‚Â­ÃƒÂ£Ã†â€™Ã‚Â¼ÃƒÂ£Ã†â€™Ã¢â‚¬Â°(BASS_PluginLoadÃƒÂ£Ã‚ÂÃ‚Â¯ÃƒÂ¤Ã‚Â½Ã‚Â¿ÃƒÂ£Ã¢â‚¬Å¡Ã‚ÂÃƒÂ£Ã‚ÂÃ‚ÂªÃƒÂ£Ã‚ÂÃ¢â‚¬Å¾)
            BASS_FX_LIB = DLL_LOADER(bass_fx_path)
            
            # BASS_FXÃƒÂ©Ã¢â‚¬â€œÃ‚Â¢ÃƒÂ¦Ã¢â‚¬Â¢Ã‚Â°ÃƒÂ£Ã‚ÂÃ‚Â®ÃƒÂ¥Ã…Â¾Ã¢â‚¬Â¹ÃƒÂ¥Ã‚Â®Ã…Â¡ÃƒÂ§Ã‚Â¾Ã‚Â©
            BASS_FX_LIB.BASS_FX_GetVersion.restype = ctypes.c_uint32
            BASS_FX_LIB.BASS_FX_TempoCreate.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
            BASS_FX_LIB.BASS_FX_TempoCreate.restype = ctypes.c_uint32
            BASS_FX_LIB.BASS_FX_TempoGetRateRatio.argtypes = [ctypes.c_uint32]
            BASS_FX_LIB.BASS_FX_TempoGetRateRatio.restype = ctypes.c_float
            
            # ÃƒÂ£Ã†â€™Ã‚ÂÃƒÂ£Ã†â€™Ã‚Â¼ÃƒÂ£Ã¢â‚¬Å¡Ã‚Â¸ÃƒÂ£Ã†â€™Ã‚Â§ÃƒÂ£Ã†â€™Ã‚Â³ÃƒÂ§Ã‚Â¢Ã‚ÂºÃƒÂ¨Ã‚ÂªÃ‚Â
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
        self.original_bpm = 0.0  # 解析時のBPM（Sync計算用）
        
        self.channel_volume = 1.0
        self.mix_volume = 1.0
        self.trim_db = 0.0
        
        self.eq_high = 0.0
        self.eq_mid = 0.0
        self.eq_low = 0.0
        self.filter_val = 0.0
        self.tempo_percent = 0.0
        self.pitch_semitones = 0.0
        
        self.fx_eq_low = 0
        self.fx_eq_mid = 0
        self.fx_eq_high = 0
        self.fx_filter = 0
        
        # Loop State
        self.loop_active = False
        self.loop_sync_handle = 0
        self.loop_start_bytes = 0
        self.loop_cb_ref = None # Keep reference to callback to prevent GC
        
        # HOT CUE State (Phase 8C)
        self.hot_cues: list[Optional[float]] = [None] * 4  # 4 slots, in seconds
        
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
        self.clear_all_hot_cues()  # HOT CUEもクリア
        if self.stream_fx and self.stream_fx != self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_fx)
        if self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_decode)
        self.stream_decode = 0; self.stream_fx = 0
        self.duration = 0.0; self.waveform_cache = None

    def _setup_dsp(self):
        if not self.stream_fx: return
        
        # Single DX8 EQ (Clean Audio)
        self.fx_eq_low = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
        self.fx_eq_mid = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
        self.fx_eq_high = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
        
        self._update_dx8_eq(self.fx_eq_low, 100.0, 18.0, self.eq_low)
        self._update_dx8_eq(self.fx_eq_mid, 1000.0, 18.0, self.eq_mid)
        self._update_dx8_eq(self.fx_eq_high, 8000.0, 18.0, self.eq_high)

        if BASS_FX_AVAILABLE:
            self.fx_filter = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_BFX_BQF, 0)

    def _update_dx8_eq(self, handle, center, bw, gain):
        if not handle: return
        safe_gain = max(-15.0, min(15.0, gain))
        p = BASS_DX8_PARAMEQ(center, bw, safe_gain)
        BASS_LIB.BASS_FXSetParameters(handle, ctypes.byref(p))

    def set_eq_low(self, db: float):
        self.eq_low = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} Low: {db:.1f}dB") 
        self._update_dx8_eq(self.fx_eq_low, 100.0, 18.0, db)

    def set_eq_mid(self, db: float):
        self.eq_mid = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} Mid: {db:.1f}dB")
        self._update_dx8_eq(self.fx_eq_mid, 1000.0, 18.0, db)

    def set_eq_high(self, db: float):
        self.eq_high = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} High: {db:.1f}dB")
        self._update_dx8_eq(self.fx_eq_high, 8000.0, 18.0, db)

    def set_filter(self, val: float):
        self.filter_val = val
        if not self.fx_filter: return
        p = BASS_BFX_BQF(lChannel=-1, fGain=0.0, fBandwidth=1.0, fQ=1.0, fS=0.0)
        
        if abs(val) < 0.05:
            p.lFilter = BASS_BFX_BQF_LOWPASS; p.fCenter = 20000.0; p.fQ = 0.707
        elif val < 0: # LPF
            p.lFilter = BASS_BFX_BQF_LOWPASS
            p.fCenter = max(100.0, 20000.0 * (0.01 ** abs(val)))
        else: # HPF
            p.lFilter = BASS_BFX_BQF_HIGHPASS
            p.fCenter = min(15000.0, 20.0 * (500.0 ** val))
            
        BASS_LIB.BASS_FXSetParameters(self.fx_filter, ctypes.byref(p))

    def set_volume(self, v: float):
        self.channel_volume = max(0.0, min(1.0, v))
        self._update_volume()
    
    def set_master_volume_coeff(self, v: float):
        self.mix_volume = v
        self._update_volume()

    def _update_volume(self):
        if not self.stream_fx: return
        trim_linear = 10 ** (self.trim_db / 20.0)
        final_vol = trim_linear * self.channel_volume * self.mix_volume
        BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_VOL, ctypes.c_float(final_vol))
    
    def set_trim(self, db: float): self.trim_db = db; self._update_volume()
    
    def set_tempo(self, percent: float):
        if self.stream_fx and BASS_FX_AVAILABLE:
            BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_TEMPO, ctypes.c_float(percent))
            self.tempo_percent = percent
    
    def set_pitch(self, semitones: float):
        if self.stream_fx and BASS_FX_AVAILABLE:
            BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_TEMPO_PITCH, ctypes.c_float(semitones))
            self.pitch_semitones = semitones
    
    def sync_tempo_to(self, target_bpm: float) -> bool:
        """
        対向デッキのBPMに同期（BPM Sync）
        Args:
            target_bpm: 目標BPM（対向デッキのBPM）
        Returns:
            成功時True、失敗時False
        """
        if not self.stream_fx or not BASS_FX_AVAILABLE:
            logger.warning(f"Deck {self.name}: Cannot sync - BASS_FX not available")
            return False
        
        if self.original_bpm <= 0:
            logger.warning(f"Deck {self.name}: Cannot sync - original BPM not set")
            return False
        
        if target_bpm <= 0:
            logger.warning(f"Deck {self.name}: Cannot sync - invalid target BPM: {target_bpm}")
            return False
        
        # テンポ調整量を計算: ((target / source) - 1.0) * 100
        tempo_adjust = ((target_bpm / self.original_bpm) - 1.0) * 100.0
        
        # BASSの制限: -50%〜+50%
        tempo_adjust = max(-50.0, min(50.0, tempo_adjust))
        
        self.set_tempo(tempo_adjust)
        
        logger.info(f"Deck {self.name}: Synced to {target_bpm:.1f} BPM "
                   f"(Original: {self.original_bpm:.1f}, Adjust: {tempo_adjust:+.1f}%)")
        return True

    def get_position(self) -> float:
        if not self.stream_fx: return 0.0
        pos = BASS_LIB.BASS_ChannelGetPosition(self.stream_fx, BASS_POS_BYTE)
        return BASS_LIB.BASS_ChannelBytes2Seconds(self.stream_fx, pos) if pos != -1 else 0.0
    
    def get_duration(self) -> float: return self.duration
    def get_waveform_data(self, num_points=100) -> Optional[np.ndarray]: return self.waveform_cache
    def get_dsp_settings(self):
        return {
            'type': "DX8(Single)",
            'eq_high': f"{self.eq_high:.1f}dB",
            'eq_mid': f"{self.eq_mid:.1f}dB",
            'eq_low': f"{self.eq_low:.1f}dB",
        }
    
    def apply_track_analysis(self, analysis: dict):
        """トラック解析結果を適用"""
        if 'auto_gain' in analysis:
            self.set_trim(analysis['auto_gain'])
        if 'bpm' in analysis:
            self.original_bpm = analysis['bpm']
            logger.debug(f"Deck {self.name}: Original BPM set to {self.original_bpm}")

    # --- Loop Implementation ---
    def set_loop(self, start_pos: float, duration: float):
        """Set a seamless loop using BASS_ChannelSetSync"""
        if not self.stream_fx: return
        
        # Clear existing loop
        self.clear_loop()
        
        # Calculate bytes
        end_pos = start_pos + duration
        start_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, ctypes.c_double(start_pos))
        end_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, ctypes.c_double(end_pos))
        
        self.loop_start_bytes = start_bytes
        
        # Define callback logic
        # IMPORTANT: We must keep a reference to the SYNCPROC object (self.loop_cb_ref)
        # otherwise garbage collector kills it and BASS crashes.
        def loop_sync_proc(handle, channel, data, user):
            BASS_LIB.BASS_ChannelSetPosition(channel, self.loop_start_bytes, BASS_POS_BYTE)

        self.loop_cb_ref = SYNCPROC(loop_sync_proc)
        
        # Set Sync: BASS_SYNC_POS | BASS_SYNC_MIXTIME (Mixtime ensures gapless loop)
        self.loop_sync_handle = BASS_LIB.BASS_ChannelSetSync(
            self.stream_fx,
            BASS_SYNC_POS | BASS_SYNC_MIXTIME,
            end_bytes,
            self.loop_cb_ref,
            None
        )
        
        if self.loop_sync_handle:
            self.loop_active = True
            logger.info(f"Deck {self.name}: Loop SET (Start: {start_pos:.1f}s, Dur: {duration:.1f}s)")
        else:
            logger.error(f"Deck {self.name}: Loop Set Failed (Error {BASS_LIB.BASS_ErrorGetCode()})")

    def clear_loop(self):
        """Disable loop"""
        if self.loop_sync_handle and self.stream_fx:
            BASS_LIB.BASS_ChannelRemoveSync(self.stream_fx, self.loop_sync_handle)
            self.loop_sync_handle = 0
            self.loop_active = False
            self.loop_cb_ref = None
            logger.info(f"Deck {self.name}: Loop CLEARED")
    
    def set_loop_snapped(self, bpm: float, first_beat: float = 0.0, bars: int = 4):
        """
        現在位置を最寄りの小節頭にスナップしてループ設定（Phase 8C Week 3）
        
        Args:
            bpm: トラックのBPM
            first_beat: 最初のビート位置（秒）
            bars: ループの小節数（デフォルト4）
        """
        if not self.stream_fx:
            return
        
        if bpm <= 0:
            logger.warning(f"Deck {self.name}: Cannot snap loop - invalid BPM: {bpm}")
            # フォールバック: 通常のループ設定
            loop_duration = 960.0 / 120.0  # 4小節@120BPM
            current = self.get_position()
            self.set_loop(current, loop_duration)
            return
        
        # 1小節 = 4拍 = (60 / BPM) * 4 秒
        bar_duration = (60.0 / bpm) * 4
        
        # 現在位置を取得
        current = self.get_position()
        
        # 現在位置がfirst_beatからどれだけ経過しているか
        elapsed_from_first = current - first_beat
        
        # 経過時間を小節数に変換
        bars_elapsed = elapsed_from_first / bar_duration
        
        # 最寄りの小節頭に丸める
        nearest_bar = round(bars_elapsed)
        
        # スナップ位置を計算
        snap_pos = first_beat + (nearest_bar * bar_duration)
        snap_pos = max(0.0, snap_pos)  # 負の値にならないように
        
        # ループ長さ = 指定小節数分
        loop_duration = bar_duration * bars
        
        # ループ設定
        self.set_loop(snap_pos, loop_duration)
        
        logger.info(f"Deck {self.name}: Loop SNAPPED to bar {nearest_bar:.0f} "
                   f"(Position: {snap_pos:.2f}s, Duration: {loop_duration:.2f}s, BPM: {bpm:.1f})")

    # --- HOT CUE Functions (Phase 8C) ---
    
    def set_hot_cue(self, slot: int, position: Optional[float] = None):
        """
        Set HOT CUE point
        Args:
            slot: CUE slot number (0-3)
            position: Position in seconds (None = current position)
        """
        if slot < 0 or slot >= 4:
            logger.warning(f"Deck {self.name}: Invalid HOT CUE slot {slot}")
            return
        
        if not self.stream_fx:
            logger.warning(f"Deck {self.name}: Cannot set HOT CUE - no track loaded")
            return
        
        pos = position if position is not None else self.get_position()
        self.hot_cues[slot] = pos
        logger.info(f"Deck {self.name}: HOT CUE {slot+1} set at {pos:.2f}s")
    
    def trigger_hot_cue(self, slot: int):
        """
        Trigger HOT CUE (jump to position and play)
        Args:
            slot: CUE slot number (0-3)
        """
        if slot < 0 or slot >= 4:
            logger.warning(f"Deck {self.name}: Invalid HOT CUE slot {slot}")
            return
        
        if self.hot_cues[slot] is None:
            logger.debug(f"Deck {self.name}: HOT CUE {slot+1} not set")
            return
        
        cue_pos = self.hot_cues[slot]
        self.seek(cue_pos)
        self.play()
        logger.info(f"Deck {self.name}: HOT CUE {slot+1} triggered at {cue_pos:.2f}s")
    
    def clear_hot_cue(self, slot: int):
        """
        Clear HOT CUE point
        Args:
            slot: CUE slot number (0-3)
        """
        if slot < 0 or slot >= 4:
            logger.warning(f"Deck {self.name}: Invalid HOT CUE slot {slot}")
            return
        
        if self.hot_cues[slot] is not None:
            logger.info(f"Deck {self.name}: HOT CUE {slot+1} cleared (was at {self.hot_cues[slot]:.2f}s)")
            self.hot_cues[slot] = None
    
    def clear_all_hot_cues(self):
        """Clear all HOT CUE points"""
        self.hot_cues = [None] * 4
        logger.info(f"Deck {self.name}: All HOT CUEs cleared")
    
    def get_hot_cue(self, slot: int) -> Optional[float]:
        """Get HOT CUE position (None if not set)"""
        if slot < 0 or slot >= 4:
            return None
        return self.hot_cues[slot]

    # --- Playback Control ---
    
    def play(self): 
        if self.stream_fx: BASS_LIB.BASS_ChannelPlay(self.stream_fx, False)
    def pause(self): 
        if self.stream_fx: BASS_LIB.BASS_ChannelPause(self.stream_fx)
    def cue(self):
        if self.stream_fx:
            BASS_LIB.BASS_ChannelPause(self.stream_fx)
            BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, 0, BASS_POS_BYTE)
    def seek(self, seconds: float):
        if self.stream_fx:
            pos = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, ctypes.c_double(seconds))
            BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, pos, BASS_POS_BYTE)

    def _generate_waveform(self, decode_stream, points=800):
        if not NUMPY_AVAILABLE: return None
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
    # Loop Controls (Added)
    CH1_LOOP = 66
    CH2_LOOP = 67