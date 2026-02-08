"""
Core logic modules for VCI-100 AI DJ Mixer.

This package contains the main business logic components:
- mixer_core: Main integration controller (AIVCIMixer)
- audio_engine: BASS-based audio playback and processing
- track_analyzer: Music analysis (BPM, key, energy detection)
- prompt_generator: AI-powered prompt generation using Gemini API
"""

from .mixer_core import AIVCIMixer
from .audio_engine import AudioEngine, AudioConfig
from .track_analyzer import TrackAnalyzer
from .prompt_generator import PromptGenerator

__all__ = [
    'AIVCIMixer',
    'AudioEngine',
    'AudioConfig',
    'TrackAnalyzer',
    'PromptGenerator',
]
