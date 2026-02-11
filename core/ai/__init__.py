"""
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
    TokenUsage,
    DailyQuota,
    DJStyleProfile,
    EnergyHistoryEntry,
    SunoPrompt,
    # Constants
    DEFAULT_BPM_RANGE,
    ENERGY_LEVELS,
    SECTION_TYPES,
    # Helper Functions
    validate_track_info,
    clamp,
)

from .prompt_genre import (
    GenreKnowledgeManager,
)

# 後方互換性: Phase R1以降でPromptCoordinatorが作成されたら
# PromptGenerator = PromptCoordinator として設定

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
    # Constants
    'DEFAULT_BPM_RANGE',
    'ENERGY_LEVELS',
    'SECTION_TYPES',
    # Helper Functions
    'validate_track_info',
    'clamp',
    # Classes
    'GenreKnowledgeManager',
]
