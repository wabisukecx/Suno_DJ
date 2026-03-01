"""
Core Module - VCI-100 AI DJ Mixer
==================================

コアモジュール

このパッケージは以下を提供します:
1. オーディオエンジン（audio_engine, deck, audio_constants）
2. AIプロンプト生成（ai/）
3. ミキサーコア（mixer_core）
4. トラック分析（track_analyzer）
"""

# Audio Engine
from .audio_constants import (
    BASS_AVAILABLE, BASS_FX_AVAILABLE, NUMPY_AVAILABLE,
    BASS_LIB, BASS_FX_LIB
)
from .deck import Deck, AudioConfig
from .audio_engine import AudioEngine, VCI100_MIDI

# AI Module (already exists)
# from .ai import PromptCoordinator, ...

# Phase R4
from .mix_advisor import MixAdvisor
from .style_logger import StyleLogger
from .hotcue_manager import HotCueManager, CueMode, CueStatus, LedCommand

__all__ = [
    # Audio Constants
    'BASS_AVAILABLE',
    'BASS_FX_AVAILABLE',
    'NUMPY_AVAILABLE',
    'BASS_LIB',
    'BASS_FX_LIB',
    
    # Deck & Engine
    'AudioConfig',
    'Deck',
    'AudioEngine',
    'VCI100_MIDI',

    # Phase R4
    'MixAdvisor',
    'StyleLogger',
    'HotCueManager',
    'CueMode',
    'CueStatus',
    'LedCommand',
]
