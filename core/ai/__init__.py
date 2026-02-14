"""
<<<<<<< HEAD
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
=======
AI-powered Prompt Generation Package
=====================================

Phase 9G/8L完全版:
- Context Aware AI（Hypnotic/Story Mode戦略自動判定）
- DJスタイルプロファイリング
- Suno v5 UI対応（lyrics/styles/title形式）
- 無料枠管理とフォールバック制御

モジュール構成:
- prompt_base: 基盤クラス・定数・データクラス
- prompt_genre: ジャンル知識管理
- prompt_energy: Energy Flow解析（Phase R1以降で追加予定）
- prompt_suno: Sunoプロンプト生成（Phase R1以降で追加予定）
- prompt_coordinator: 統合コーディネーター（Phase R1以降で追加予定）
"""

from .prompt_base import (
    # Enums
    GenerationMode,
    EnergyStrategy,
    ErrorType,
    # Data Classes
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09
    TokenUsage,
    DailyQuota,
    DJStyleProfile,
    EnergyHistoryEntry,
    SunoPrompt,
<<<<<<< HEAD
    classify_error,
=======
    # Constants
    DEFAULT_BPM_RANGE,
    ENERGY_LEVELS,
    SECTION_TYPES,
    # Helper Functions
    validate_track_info,
    clamp,
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09
)

from .prompt_genre import (
    GenreKnowledgeManager,
)

<<<<<<< HEAD
from .prompt_energy import (
    EnergyFlowAnalyzer,
)

from .prompt_suno import (
    SunoPromptBuilder,
)

from .prompt_coordinator import (
    PromptCoordinator,
)
=======
# 後方互換性: Phase R1以降でPromptCoordinatorが作成されたら
# PromptGenerator = PromptCoordinator として設定
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09

__all__ = [
    # Enums
    'GenerationMode',
    'EnergyStrategy',
    'ErrorType',
<<<<<<< HEAD
    
=======
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09
    # Data Classes
    'TokenUsage',
    'DailyQuota',
    'DJStyleProfile',
    'EnergyHistoryEntry',
    'SunoPrompt',
<<<<<<< HEAD
    
    # Managers
    'GenreKnowledgeManager',
    'EnergyFlowAnalyzer',
    'SunoPromptBuilder',
    'PromptCoordinator',
    
    # Helper Functions
    'classify_error',
=======
    # Constants
    'DEFAULT_BPM_RANGE',
    'ENERGY_LEVELS',
    'SECTION_TYPES',
    # Helper Functions
    'validate_track_info',
    'clamp',
    # Classes
    'GenreKnowledgeManager',
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09
]
