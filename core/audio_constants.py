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
BASS_ATTRIB_TEMPO_PITCH = 0x10001  # bass_fx.h: enum { BASS_ATTRIB_TEMPO=0x10000, BASS_ATTRIB_TEMPO_PITCH, BASS_ATTRIB_TEMPO_FREQ }
# 修正: 旧値 0x10004 は誤り（存在しない属性ID）。0x10001 が正しい BASS_FX の PITCH 属性

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
# BASS_FX_BFX_BQF: bass_fx.h enum ( ROTATE=0x10000始まり ) から数えて第19番目(0基準) = 0x10000+19 = 0x10013
# enum順: ROTATE(0),ECHO(1),FLANGER(2),VOLUME(3),PEAKEQ(4),REVERB(5),LPF(6),
#        MIX(7),DAMP(8),AUTOWAH(9),ECHO2(10),PHASER(11),ECHO3(12),CHORUS(13),
#        APF(14),COMPRESSOR(15),DISTORTION(16),COMPRESSOR2(17),VOLUME_ENV(18),BQF(19)
BASS_FX_BFX_BQF = 0x10013  # = 0x10000 + 19

# BQF Filter Types (bass_fx.h準拠)
BASS_BFX_BQF_LOWPASS    = 0
BASS_BFX_BQF_HIGHPASS   = 1
BASS_BFX_BQF_BANDPASS   = 2
BASS_BFX_BQF_BANDPASS_Q = 3  # constant skirt gain
BASS_BFX_BQF_NOTCH      = 4
BASS_BFX_BQF_ALLPASS    = 5
BASS_BFX_BQF_PEAKINGEQ  = 6  # Bell型イコライザー（D-02 BQF EQ移行用）
BASS_BFX_BQF_LOWSHELF   = 7
BASS_BFX_BQF_HIGHSHELF  = 8

# BQF Channel Flags (bass_fx.h準拠)
BASS_BFX_CHANALL  = -1  # 全チャンネル（デフォルト）
BASS_BFX_CHANNONE =  0  # 全チャンネル無効

# BASS_ChannelGetLevelEx flags (bass.h準拠)
BASS_LEVEL_MONO   = 1  # モノレベル取得
BASS_LEVEL_STEREO = 2  # ステレオレベル取得
BASS_LEVEL_RMS    = 4  # RMSレベル（ピークでなく真のRMS）
BASS_LEVEL_VOLPAN = 8  # VOL/PAN属性をレベルに適用

# BASS_FX Tempo Options (bass_fx.h準拠)
# BASS_ChannelSetAttribute(stream_fx, BASS_ATTRIB_TEMPO_OPTION_xxx, value) で設定
# enum順(bass_fx.h): USE_AA_FILTER(0x10010), AA_FILTER_LENGTH, USE_QUICKALGO,
#                   SEQUENCE_MS, SEEKWINDOW_MS, OVERLAP_MS, PREVENT_CLICK
# PREVENT_CLICK = 0x10010 + 6 = 0x10016
BASS_ATTRIB_TEMPO_OPTION_USE_AA_FILTER      = 0x10010  # TRUE(default)/FALSE
BASS_ATTRIB_TEMPO_OPTION_AA_FILTER_LENGTH   = 0x10011  # 32(default), 8..128 taps
BASS_ATTRIB_TEMPO_OPTION_USE_QUICKALGO      = 0x10012  # TRUE/FALSE(default)
BASS_ATTRIB_TEMPO_OPTION_SEQUENCE_MS        = 0x10013  # 82(default), 0=auto
BASS_ATTRIB_TEMPO_OPTION_SEEKWINDOW_MS      = 0x10014  # 28(default), 0=auto
BASS_ATTRIB_TEMPO_OPTION_OVERLAP_MS         = 0x10015  # 8(default)
BASS_ATTRIB_TEMPO_OPTION_PREVENT_CLICK      = 0x10016  # TRUE/FALSE(default): クリックノイズ防止

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
# Windows BASS.dll は stdcall 規約。WINFUNCTYPE を使わないと
# スタック破壊が起き "Don't know how to convert parameter" エラーになる。
if platform.system() == 'Windows':
    SYNCPROC = ctypes.WINFUNCTYPE(
        None,
        ctypes.c_uint32,  # handle
        ctypes.c_uint32,  # channel
        ctypes.c_uint32,  # data
        ctypes.c_void_p,  # user
    )
else:
    SYNCPROC = ctypes.CFUNCTYPE(
        None,
        ctypes.c_uint32,  # handle
        ctypes.c_uint32,  # channel
        ctypes.c_uint32,  # data
        ctypes.c_void_p,  # user
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
        BASS_LIB.BASS_ChannelSetAttribute.restype = ctypes.c_bool
        BASS_LIB.BASS_ChannelGetAttribute.argtypes = [
            ctypes.c_uint32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_float)
        ]
        BASS_LIB.BASS_ChannelGetAttribute.restype = ctypes.c_bool
        BASS_LIB.BASS_ChannelSetPosition.argtypes = [
            ctypes.c_uint32, ctypes.c_uint64, ctypes.c_uint32
        ]
        
        # --- チャンネル情報取得 ---
        BASS_LIB.BASS_ChannelGetLength.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        BASS_LIB.BASS_ChannelGetLength.restype = ctypes.c_uint64
        BASS_LIB.BASS_ChannelGetPosition.argtypes = [ctypes.c_uint32, ctypes.c_uint32]
        BASS_LIB.BASS_ChannelGetPosition.restype = ctypes.c_uint64
        # BASS_ChannelBytes2Seconds(DWORD handle, QWORD pos) -> double
        # argtypes 未定義だと Python int を QWORD に変換できずエラーになる
        BASS_LIB.BASS_ChannelBytes2Seconds.argtypes = [ctypes.c_uint32, ctypes.c_uint64]
        BASS_LIB.BASS_ChannelBytes2Seconds.restype = ctypes.c_double
        BASS_LIB.BASS_ChannelSeconds2Bytes.argtypes = [
            ctypes.c_uint32, ctypes.c_double
        ]
        BASS_LIB.BASS_ChannelSeconds2Bytes.restype = ctypes.c_uint64
        BASS_LIB.BASS_ChannelIsActive.argtypes = [ctypes.c_uint32]
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
        # BASS_ChannelSetSync(DWORD handle, DWORD type, QWORD param, SYNCPROC *proc, void *user)
        # Windows stdcall: QWORD(param) は 64bit 整数。WinDLL では c_uint64 必須。
        BASS_LIB.BASS_ChannelSetSync.argtypes = [
            ctypes.c_uint32,   # handle
            ctypes.c_uint32,   # type  (DWORD)
            ctypes.c_uint64,   # param (QWORD)
            SYNCPROC,          # proc
            ctypes.c_void_p,   # user
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
        
        # --- レベル取得 ---
        BASS_LIB.BASS_ChannelGetLevel.argtypes = [ctypes.c_uint32]
        BASS_LIB.BASS_ChannelGetLevel.restype = ctypes.c_uint32
        
        # BASS_ChannelGetLevelEx: float精度のRMSレベル取得 (bass.h準拠)
        # flags: BASS_LEVEL_STEREO=2, BASS_LEVEL_RMS=4
        BASS_LIB.BASS_ChannelGetLevelEx.argtypes = [
            ctypes.c_uint32,   # handle
            ctypes.POINTER(ctypes.c_float),  # levels (float配列)
            ctypes.c_float,    # length (秒)
            ctypes.c_uint32    # flags
        ]
        BASS_LIB.BASS_ChannelGetLevelEx.restype = ctypes.c_bool
        
        # BASS_ChannelSlideAttribute: スムーズな属性変化（クリックノイズ防止）
        BASS_LIB.BASS_ChannelSlideAttribute.argtypes = [
            ctypes.c_uint32,  # handle
            ctypes.c_uint32,  # attrib
            ctypes.c_float,   # value
            ctypes.c_uint32   # time (ms)
        ]
        BASS_LIB.BASS_ChannelSlideAttribute.restype = ctypes.c_bool
        
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
