"""
AI Module - Prompt Generation Components
=========================================

This module provides AI-powered prompt generation functionality for the VCI-100 AI DJ Mixer.

Components:
-----------
1. prompt_base.py - Core data structures and enums
2. prompt_genre.py - Genre knowledge management and selection
3. prompt_energy.py - Energy flow analysis and context aware AI
4. prompt_suno.py - Suno API prompt generation (TBD)
5. prompt_coordinator.py - Main coordinator (TBD)

Phase Implementation Status:
----------------------------
- Phase 9G/8L: ✅ Implemented (Data classes, Genre selection, Energy analysis)
- Phase R1-R7: ⏳ Planned (Future phases)

Example Usage:
-------------
>>> from core.ai import (
...     GenerationMode, EnergyStrategy, 
...     GenreKnowledgeManager, EnergyFlowAnalyzer
... )
>>> 
>>> # Energy flow analysis
>>> analyzer = EnergyFlowAnalyzer()
>>> analyzer.record_eq_operation('high', 0.8)
>>> strategy, reason = analyzer.analyze_context({
...     'genre': 'Minimal Techno',
...     'energy': {'numeric': 3}
... })
>>> print(f"{strategy}: {reason}")
EnergyStrategy.HYPNOTIC: Minimal genre detected (Minimal Techno)
>>> 
>>> # Genre selection
>>> genre_mgr = GenreKnowledgeManager()
>>> genre = genre_mgr.select_genre_for_strategy(
...     strategy=EnergyStrategy.HYPNOTIC,
...     current_genre="Deep House"
... )
>>> print(genre)
'Minimal Techno'
"""

from .prompt_base import (
    GenerationMode,
    EnergyStrategy,
    ErrorType,
    TokenUsage,
    DailyQuota,
    DJStyleProfile,
    EnergyHistoryEntry,
    SunoPrompt,
    classify_error,
)

from .prompt_genre import (
    GenreKnowledgeManager,
)

from .prompt_energy import (
    EnergyFlowAnalyzer,
)

from .prompt_suno import (
    SunoPromptBuilder,
)

from .prompt_coordinator import (
    PromptCoordinator,
)

__all__ = [
    # Enums
    'GenerationMode',
    'EnergyStrategy',
    'ErrorType',
    
    # Data Classes
    'TokenUsage',
    'DailyQuota',
    'DJStyleProfile',
    'EnergyHistoryEntry',
    'SunoPrompt',
    
    # Managers
    'GenreKnowledgeManager',
    'EnergyFlowAnalyzer',
    'SunoPromptBuilder',
    'PromptCoordinator',
    
    # Helper Functions
    'classify_error',
]
