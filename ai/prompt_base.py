"""
AI Prompt Generation - Base Module
====================================

Phase 9G/8L対応:
- Enum定義（GenerationMode, EnergyStrategy, ErrorType）
- データクラス（TokenUsage, DailyQuota, DJStyleProfile, EnergyHistoryEntry, SunoPrompt）
- 共通定数

このモジュールは他のAIモジュールの基盤となる。
"""

import logging
import time
from datetime import date
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any

# ロギング設定
logger = logging.getLogger(__name__)


# ===================================================================
# Enum定義（Phase 9G）
# ===================================================================

class GenerationMode(Enum):
    """プロンプト生成モード"""
    GEMINI = "gemini"
    RULE_BASED = "rule_based"
    FALLBACK = "fallback"


class EnergyStrategy(Enum):
    """
    エネルギー戦略（Phase 9G: Context Aware AI）
    
    - STORY: EDM的（ビルドアップ→ドロップ→ブレイク）- エネルギー変動大
    - HYPNOTIC: ミニマル的（ループ維持、テクスチャ変化、没入感）- エネルギー維持
    """
    STORY = "story"
    HYPNOTIC = "hypnotic"


class ErrorType(Enum):
    """APIエラータイプ（Phase 9G）"""
    RESOURCE_EXHAUSTED = "resource_exhausted"
    OVERLOADED = "overloaded"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


# ===================================================================
# 共通定数
# ===================================================================

DEFAULT_BPM_RANGE = (120, 140)
ENERGY_LEVELS = ['low', 'medium', 'high', 'peak']
SECTION_TYPES = ['intro', 'buildup', 'drop', 'break', 'outro']


# ===================================================================
# データクラス（Phase 9G/8L）
# ===================================================================

@dataclass
class TokenUsage:
    """
    トークン使用量追跡（Phase 9G）
    
    Gemini APIのトークン使用量を記録し、セッション統計を提供する。
    """
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    def add(self, input_t: int, output_t: int):
        """トークン使用量を追加"""
        self.input_tokens += input_t
        self.output_tokens += output_t
        self.total_tokens += input_t + output_t


@dataclass
class DailyQuota:
    """
    日次クォータ管理（Phase 9G）
    
    Gemini API無料枠（1500リクエスト/日）を管理し、
    超過時に自動的にルールベース生成へフォールバックする。
    """
    date: str = ""
    request_count: int = 0
    max_requests: int = 1500
    exhausted: bool = False
    
    def check_and_increment(self) -> bool:
        """
        クォータチェックと増分
        
        Returns:
            bool: クォータ内ならTrue、超過ならFalse
        """
        today = date.today().isoformat()
        
        # 日付が変わったらリセット
        if self.date != today:
            self.date = today
            self.request_count = 0
            self.exhausted = False
        
        # クォータチェック
        if self.exhausted:
            return False
        
        if self.request_count >= self.max_requests:
            return False
        
        # 増分
        self.request_count += 1
        return True
    
    def mark_exhausted(self):
        """クォータを使い果たしたとマーク"""
        self.exhausted = True
        self.request_count = self.max_requests
        logger.warning(f"Daily quota exhausted! Switching to rule-based mode.")
    
    @property
    def remaining(self) -> int:
        """残りリクエスト数"""
        return max(0, self.max_requests - self.request_count)


@dataclass
class DJStyleProfile:
    """
    DJスタイルプロファイル（Phase 9G）
    
    EQ/Filter操作履歴を追跡し、DJの操作傾向を学習する。
    Context Aware AIの入力データとして使用される。
    """
    eq_high_cuts: int = 0
    eq_high_boosts: int = 0
    eq_mid_cuts: int = 0
    eq_mid_boosts: int = 0
    eq_low_cuts: int = 0
    eq_low_boosts: int = 0
    filter_hpf_uses: int = 0
    filter_lpf_uses: int = 0
    
    # 前回値（内部状態）
    _prev_eq_high: float = 0.5
    _prev_eq_mid: float = 0.5
    _prev_eq_low: float = 0.5
    _prev_filter: float = 0.5
    
    def record_eq_high(self, value: float):
        """High EQ操作を記録"""
        if value < 0.3 and self._prev_eq_high >= 0.3:
            self.eq_high_cuts += 1
        elif value > 0.7 and self._prev_eq_high <= 0.7:
            self.eq_high_boosts += 1
        self._prev_eq_high = value
    
    def record_eq_mid(self, value: float):
        """Mid EQ操作を記録"""
        if value < 0.3 and self._prev_eq_mid >= 0.3:
            self.eq_mid_cuts += 1
        elif value > 0.7 and self._prev_eq_mid <= 0.7:
            self.eq_mid_boosts += 1
        self._prev_eq_mid = value
    
    def record_eq_low(self, value: float):
        """Low EQ操作を記録"""
        if value < 0.3 and self._prev_eq_low >= 0.3:
            self.eq_low_cuts += 1
        elif value > 0.7 and self._prev_eq_low <= 0.7:
            self.eq_low_boosts += 1
        self._prev_eq_low = value
    
    def record_filter(self, value: float):
        """Filter操作を記録"""
        if value < 0.4 and self._prev_filter >= 0.4:
            self.filter_hpf_uses += 1
        elif value > 0.6 and self._prev_filter <= 0.6:
            self.filter_lpf_uses += 1
        self._prev_filter = value
    
    def analyze_tendencies(self) -> Dict[str, Any]:
        """
        操作傾向を分析（Phase 9G）
        
        Returns:
            dict: {
                'total_operations': int,
                'atmosphere': str (bright/dark/balanced),
                'build_preference': str (dynamic/subtle)
            }
        """
        total_eq_ops = sum([
            self.eq_high_cuts, self.eq_high_boosts,
            self.eq_mid_cuts, self.eq_mid_boosts,
            self.eq_low_cuts, self.eq_low_boosts
        ])
        
        style = {'total_operations': total_eq_ops}
        
        if total_eq_ops == 0:
            style['overall'] = 'neutral'
            style['build_preference'] = 'subtle'
            return style
        
        # 雰囲気判定
        high_balance = self.eq_high_boosts - self.eq_high_cuts
        if high_balance > 2:
            style['atmosphere'] = 'bright'
        elif high_balance < -2:
            style['atmosphere'] = 'dark'
        else:
            style['atmosphere'] = 'balanced'
        
        # 展開の派手さ判定（Filter多用 = Dynamic）
        total_filter = self.filter_hpf_uses + self.filter_lpf_uses
        if total_filter > 8 or (total_eq_ops > 0 and (total_filter / total_eq_ops) > 0.5):
            style['build_preference'] = 'dynamic'
        else:
            style['build_preference'] = 'subtle'
        
        return style


@dataclass
class EnergyHistoryEntry:
    """
    エネルギー履歴エントリ（Phase 9G）
    
    Context Aware AIのエネルギーフロー分析用。
    """
    track_name: str
    energy_level: int
    genre: str
    bpm: float
    key: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SunoPrompt:
    """
    Suno UI形式のプロンプト（Phase 8L）
    
    Suno v5の新UI形式（lyrics/styles/title）に対応。
    """
    lyrics: str = ""      # 楽曲構造の設計図
    styles: str = ""      # ジャンル、キーワード、BPM、Key
    title: str = ""       # 曲タイトル
    genre: str = ""
    bpm: float = 0.0
    key: str = ""
    energy_level: int = 3
    
    def to_dict(self) -> Dict:
        """辞書形式に変換"""
        return {
            'lyrics': self.lyrics,
            'styles': self.styles,
            'title': self.title,
            'genre': self.genre,
            'bpm': self.bpm,
            'key': self.key,
            'energy_level': self.energy_level
        }


# ===================================================================
# ヘルパー関数
# ===================================================================

def validate_track_info(track_info: dict) -> bool:
    """
    トラック情報の妥当性検証
    
    Args:
        track_info: トラック情報辞書
    
    Returns:
        bool: 有効ならTrue
    """
    required_keys = ['bpm', 'genre', 'energy']
    return all(key in track_info for key in required_keys)


def clamp(value: float, min_val: float, max_val: float) -> float:
    """値を範囲内にクランプ"""
    return max(min_val, min(max_val, value))


# ===================================================================
# モジュール情報
# ===================================================================

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
]
