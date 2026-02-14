"""
Audio Constants and BASS Library Initialization
===============================================

BASS Audio Library定数定義とライブラリ初期化処理

このモジュールは以下を提供します:
1. BASS API定数
2. BASS_FX定数
3. Ctypes構造体定義
4. BASSライブラリ初期化
"""

import logging
import ctypes
import os
import platform

logger = logging.getLogger(__name__)

# ============================================================
# BASS Constants
# ============================================================

# Attribute Constants
BASS_ATTRIB_FREQ = 1
BASS_ATTRIB_VOL = 2
BASS_ATTRIB_PAN = 3
BASS_ATTRIB_TEMPO = 0x10000
BASS_ATTRIB_TEMPO_PITCH = 0x10004

# Stream Flags
BASS_UNICODE = 0x80000000
BASS_STREAM_DECODE = 0x200000
BASS_STREAM_PRESCAN = 0x20000
BASS_SAMPLE_FLOAT = 256
BASS_FX_FREESOURCE = 0x10000

# Position Mode
BASS_POS_BYTE = 0

# Sync Constants (For Looping)
BASS_SYNC_POS = 0
BASS_SYNC_MIXTIME = 0x40000000

# FX Constants
BASS_FX_DX8_PARAMEQ = 7
BASS_FX_BFX_BQF = 0x1000F

# BQF Filter Types
BASS_BFX_BQF_LOWPASS = 0
BASS_BFX_BQF_HIGHPASS = 1

# ============================================================
# Platform-Specific Library Configuration
# ============================================================

if platform.system() == 'Windows':
    lib_ext = '.dll'
    DLL_LOADER = ctypes.WinDLL
elif platform.system() == 'Darwin':
    lib_ext = '.dylib'
    DLL_LOADER = ctypes.CDLL
else:
    lib_ext = '.so'
    DLL_LOADER = ctypes.CDLL

# ============================================================
# Ctypes Structures
# ============================================================

class BASS_DX8_PARAMEQ(ctypes.Structure):
    """
    BASS DX8 Parametric EQ構造体
    
    Attributes:
        fCenter (float): 中心周波数 (Hz)
        fBandwidth (float): 帯域幅 (semitones)
        fGain (float): ゲイン (dB)
    """
    _fields_ = [
        ("fCenter", ctypes.c_float),
        ("fBandwidth", ctypes.c_float),
        ("fGain", ctypes.c_float),
    ]


class BASS_BFX_BQF(ctypes.Structure):
    """
    BASS BQF (Biquad Filter)構造体
    
    Attributes:
        lFilter (int): フィルタータイプ
        fCenter (float): 中心周波数 (Hz)
        fGain (float): ゲイン (dB)
        fBandwidth (float): 帯域幅
        fQ (float): Qファクター
        fS (float): シェルフスロープ
        lChannel (int): チャンネル
    """
    _fields_ = [
        ("lFilter", ctypes.c_int),
        ("fCenter", ctypes.c_float),
        ("fGain", ctypes.c_float),
        ("fBandwidth", ctypes.c_float),
        ("fQ", ctypes.c_float),
        ("fS", ctypes.c_float),
        ("lChannel", ctypes.c_int)
    ]


# ============================================================
# Callback Types
# ============================================================

# Sync Callback (For Looping)
SYNCPROC = ctypes.CFUNCTYPE(
    None,
    ctypes.c_uint32,  # handle
    ctypes.c_uint32,  # channel
    ctypes.c_uint32,  # data
    ctypes.c_void_p   # user
)

# ============================================================
# BASS Library Initialization
# ============================================================

BASS_LIB = None
BASS_FX_LIB = None
BASS_AVAILABLE = False
BASS_FX_AVAILABLE = False

try:
    # ベースパスを取得（プロジェクトルート）
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Windows: DLLディレクトリを追加
    if platform.system() == 'Windows' and hasattr(os, 'add_dll_directory'):
        try:
            os.add_dll_directory(base_path)
        except:
            pass
    
    bass_path = os.path.join(base_path, f'bass{lib_ext}')
    bass_fx_path = os.path.join(base_path, f'bass_fx{lib_ext}')
    
    # ============================================================
    # BASS Library
    # ============================================================
    
    if os.path.exists(bass_path):
        BASS_LIB = DLL_LOADER(bass_path)
        
        # --- 基本関数 ---
        BASS_LIB.BASS_Init.argtypes = [
            ctypes.c_int, ctypes.c_uint32, ctypes.c_uint32,
            ctypes.c_void_p, ctypes.c_void_p
        ]
        BASS_LIB.BASS_Init.restype = ctypes.c_bool
        BASS_LIB.BASS_Free.restype = ctypes.c_bool
        
        # --- ストリーム関数 ---
        BASS_LIB.BASS_StreamCreateFile.argtypes = [
            ctypes.c_bool, ctypes.c_wchar_p, ctypes.c_uint64,
            ctypes.c_uint64, ctypes.c_uint32
        ]
        BASS_LIB.BASS_StreamCreateFile.restype = ctypes.c_uint32
        BASS_LIB.BASS_StreamFree.argtypes = [ctypes.c_uint32]
        
        # --- チャンネル制御 ---
        BASS_LIB.BASS_ChannelPlay.argtypes = [ctypes.c_uint32, ctypes.c_bool]
        BASS_LIB.BASS_ChannelPause.argtypes = [ctypes.c_uint32]
        BASS_LIB.BASS_ChannelSetAttribute.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_float
        ]
        BASS_LIB.BASS_ChannelSetPosition.argtypes = [
            ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint32
        ]
        
        # --- チャンネル情報取得 ---
        BASS_LIB.BASS_ChannelGetLength.restype = ctypes.c_uint64
        BASS_LIB.BASS_ChannelGetPosition.restype = ctypes.c_uint64
        BASS_LIB.BASS_ChannelBytes2Seconds.restype = ctypes.c_double
        BASS_LIB.BASS_ChannelSeconds2Bytes.argtypes = [
            ctypes.c_uint32, ctypes.c_double
        ]
        BASS_LIB.BASS_ChannelSeconds2Bytes.restype = ctypes.c_uint64
        BASS_LIB.BASS_ChannelIsActive.restype = ctypes.c_uint32
        
        # --- FX & Sync ---
        BASS_LIB.BASS_ChannelSetFX.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_int
        ]
        BASS_LIB.BASS_ChannelSetFX.restype = ctypes.c_uint32
        BASS_LIB.BASS_FXSetParameters.argtypes = [
            ctypes.c_uint32, ctypes.c_void_p
        ]
        BASS_LIB.BASS_FXSetParameters.restype = ctypes.c_bool
        
        # --- Sync (ループ用) ---
        BASS_LIB.BASS_ChannelSetSync.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint64,
            SYNCPROC, ctypes.c_void_p
        ]
        BASS_LIB.BASS_ChannelSetSync.restype = ctypes.c_uint32
        BASS_LIB.BASS_ChannelRemoveSync.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32
        ]
        BASS_LIB.BASS_ChannelRemoveSync.restype = ctypes.c_bool
        
        # --- データ取得 ---
        BASS_LIB.BASS_ChannelGetData.argtypes = [
            ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32
        ]
        BASS_LIB.BASS_ChannelGetData.restype = ctypes.c_int
        
        # --- プラグイン ---
        BASS_LIB.BASS_PluginLoad.argtypes = [
            ctypes.c_wchar_p, ctypes.c_uint32
        ]
        BASS_LIB.BASS_PluginLoad.restype = ctypes.c_uint32
        
        # --- エラー処理 ---
        BASS_LIB.BASS_ErrorGetCode.restype = ctypes.c_int
        
        # BASS初期化（デバイス-1: no sound, 48kHz）
        if BASS_LIB.BASS_Init(-1, 48000, 0, 0, 0):
            BASS_AVAILABLE = True
            logger.info("BASS Output Driver Initialized (48kHz)")
        else:
            error_code = BASS_LIB.BASS_ErrorGetCode()
            logger.error(f"BASS_Init failed: Error {error_code}")
    else:
        logger.warning(f"BASS library not found: {bass_path}")
    
    # ============================================================
    # BASS_FX Library
    # ============================================================
    
    if os.path.exists(bass_fx_path) and BASS_AVAILABLE:
        try:
            BASS_FX_LIB = DLL_LOADER(bass_fx_path)
            
            # --- BASS_FX関数 ---
            BASS_FX_LIB.BASS_FX_GetVersion.restype = ctypes.c_uint32
            BASS_FX_LIB.BASS_FX_TempoCreate.argtypes = [
                ctypes.c_uint32, ctypes.c_uint32
            ]
            BASS_FX_LIB.BASS_FX_TempoCreate.restype = ctypes.c_uint32
            BASS_FX_LIB.BASS_FX_TempoGetRateRatio.argtypes = [ctypes.c_uint32]
            BASS_FX_LIB.BASS_FX_TempoGetRateRatio.restype = ctypes.c_float
            
            version = BASS_FX_LIB.BASS_FX_GetVersion()
            BASS_FX_AVAILABLE = True
            logger.info(
                f"BASS_FX Loaded Successfully "
                f"(Version: {hex(version)}, Tempo Support Active)"
            )
        except Exception as e:
            logger.warning(f"BASS_FX Load Exception: {e}")
            BASS_FX_AVAILABLE = False
    else:
        if not os.path.exists(bass_fx_path):
            logger.warning(f"BASS_FX library not found: {bass_fx_path}")

except Exception as e:
    logger.error(f"BASS Critical Load Error: {e}")

# ============================================================
# Numpy Availability Check
# ============================================================

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    logger.warning("NumPy not available - waveform generation disabled")
