"""
Prompt Generation Base Module
==============================

Phase 9G/8L: 基盤クラス・共通定数・データクラス定義

このモジュールは以下を提供します:
1. Enum定義（GenerationMode, EnergyStrategy, ErrorType）
2. データクラス（TokenUsage, DailyQuota, DJStyleProfile, EnergyHistoryEntry, SunoPrompt）
3. 共通定数
4. ヘルパー関数
"""

import time
import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Dict, Any

# ロギング設定
logger = logging.getLogger(__name__)


# ============================================================
# Enum定義
# ============================================================

class GenerationMode(Enum):
    """プロンプト生成モード"""
    GEMINI = "gemini"           # Gemini API使用
    RULE_BASED = "rule_based"   # ルールベース生成
    FALLBACK = "fallback"       # フォールバック（エラー時）


class EnergyStrategy(Enum):
    """エネルギー戦略（Phase 9G）"""
    STORY = "story"          # EDM的（ビルドアップ→ドロップ→ブレイク）- エネルギー変動大
    HYPNOTIC = "hypnotic"    # ミニマル的（ループ維持、テクスチャ変化、没入感）- エネルギー維持


class ErrorType(Enum):
    """APIエラータイプ（Phase 9G）"""
    RESOURCE_EXHAUSTED = "resource_exhausted"  # クォータ超過
    OVERLOADED = "overloaded"                  # API過負荷
    TIMEOUT = "timeout"                        # タイムアウト
    UNKNOWN = "unknown"                        # 不明なエラー


# ============================================================
# データクラス定義
# ============================================================

@dataclass
class TokenUsage:
    """
    トークン使用量追跡（Phase 9G）
    
    Gemini APIのトークン使用量を追跡します。
    
    Attributes:
        input_tokens (int): 入力トークン数
        output_tokens (int): 出力トークン数
        total_tokens (int): 合計トークン数
    
    Example:
        >>> usage = TokenUsage()
        >>> usage.add(100, 50)
        >>> print(f"Total: {usage.total_tokens}")
        Total: 150
    """
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    def add(self, input_t: int, output_t: int):
        """
        トークン使用量を追加
        
        Args:
            input_t (int): 入力トークン数
            output_t (int): 出力トークン数
        """
        self.input_tokens += input_t
        self.output_tokens += output_t
        self.total_tokens += input_t + output_t


@dataclass
class DailyQuota:
    """
    日次クォータ管理（Phase 9G）
    
    Gemini API無料枠（1日1500リクエスト）を管理します。
    日付が変わると自動的にリセットされます。
    
    Attributes:
        date (str): 最終使用日（ISO形式）
        request_count (int): 現在のリクエスト数
        max_requests (int): 最大リクエスト数（デフォルト1500）
        exhausted (bool): クォータ枯渇フラグ
    
    Example:
        >>> quota = DailyQuota()
        >>> if quota.check_and_increment():
        ...     print("API call allowed")
        API call allowed
        >>> print(f"Remaining: {quota.remaining}")
        Remaining: 1499
    """
    date: str = ""
    request_count: int = 0
    max_requests: int = 1500
    exhausted: bool = False
    
    def check_and_increment(self) -> bool:
        """
        クォータをチェックし、使用可能ならインクリメント
        
        日付が変わった場合は自動的にリセットします。
        
        Returns:
            bool: API使用可能ならTrue
        """
        today = date.today().isoformat()
        if self.date != today:
            # 日付が変わったのでリセット
            self.date = today
            self.request_count = 0
            self.exhausted = False
        
        if self.exhausted:
            return False
        
        if self.request_count >= self.max_requests:
            return False
        
        self.request_count += 1
        return True
    
    def mark_exhausted(self):
        """
        クォータを枯渇状態にマーク
        
        RESOURCE_EXHAUSTEDエラー発生時に呼び出されます。
        """
        self.exhausted = True
        self.request_count = self.max_requests
        logger.warning(f"Daily quota exhausted! Switching to rule-based mode.")
    
    @property
    def remaining(self) -> int:
        """
        残りリクエスト数を取得
        
        Returns:
            int: 残りリクエスト数
        """
        return max(0, self.max_requests - self.request_count)


@dataclass
class DJStyleProfile:
    """
    DJスタイルプロファイル（Phase 9G）
    
    EQ/Filter操作履歴を追跡し、DJの操作傾向を分析します。
    Context Aware AIでの戦略判定に使用されます。
    
    Attributes:
        eq_high_cuts (int): High EQカット回数
        eq_high_boosts (int): High EQブースト回数
        eq_mid_cuts (int): Mid EQカット回数
        eq_mid_boosts (int): Mid EQブースト回数
        eq_low_cuts (int): Low EQカット回数
        eq_low_boosts (int): Low EQブースト回数
        filter_hpf_uses (int): HPF使用回数
        filter_lpf_uses (int): LPF使用回数
    
    Example:
        >>> profile = DJStyleProfile()
        >>> profile.record_eq_high(0.8)  # Boost
        >>> profile.record_filter(0.7)    # LPF
        >>> style = profile.analyze_tendencies()
        >>> print(style['build_preference'])
        subtle
    """
    eq_high_cuts: int = 0
    eq_high_boosts: int = 0
    eq_mid_cuts: int = 0
    eq_mid_boosts: int = 0
    eq_low_cuts: int = 0
    eq_low_boosts: int = 0
    filter_hpf_uses: int = 0
    filter_lpf_uses: int = 0
    
    _prev_eq_high: float = 0.5
    _prev_eq_mid: float = 0.5
    _prev_eq_low: float = 0.5
    _prev_filter: float = 0.5
    
    def record_eq_high(self, value: float):
        """
        High EQ操作を記録
        
        Args:
            value (float): EQ値（0.0-1.0）
                - < 0.3: カット
                - > 0.7: ブースト
        """
        if value < 0.3 and self._prev_eq_high >= 0.3:
            self.eq_high_cuts += 1
        elif value > 0.7 and self._prev_eq_high <= 0.7:
            self.eq_high_boosts += 1
        self._prev_eq_high = value
    
    def record_eq_mid(self, value: float):
        """
        Mid EQ操作を記録
        
        Args:
            value (float): EQ値（0.0-1.0）
        """
        if value < 0.3 and self._prev_eq_mid >= 0.3:
            self.eq_mid_cuts += 1
        elif value > 0.7 and self._prev_eq_mid <= 0.7:
            self.eq_mid_boosts += 1
        self._prev_eq_mid = value
    
    def record_eq_low(self, value: float):
        """
        Low EQ操作を記録
        
        Args:
            value (float): EQ値（0.0-1.0）
        """
        if value < 0.3 and self._prev_eq_low >= 0.3:
            self.eq_low_cuts += 1
        elif value > 0.7 and self._prev_eq_low <= 0.7:
            self.eq_low_boosts += 1
        self._prev_eq_low = value
    
    def record_filter(self, value: float):
        """
        Filter操作を記録
        
        Args:
            value (float): Filter値（0.0-1.0）
                - < 0.4: HPF（ハイパスフィルター）
                - > 0.6: LPF（ローパスフィルター）
        """
        if value < 0.4 and self._prev_filter >= 0.4:
            self.filter_hpf_uses += 1
        elif value > 0.6 and self._prev_filter <= 0.6:
            self.filter_lpf_uses += 1
        self._prev_filter = value
    
    def analyze_tendencies(self) -> Dict[str, Any]:
        """
        DJ操作傾向を分析
        
        EQ/Filter操作履歴から以下を判定:
        - atmosphere: 雰囲気（'bright', 'dark', 'balanced'）
        - build_preference: 展開の派手さ（'dynamic', 'subtle'）
        - total_operations: 総操作回数
        
        Returns:
            Dict[str, Any]: 操作傾向
                - overall (str): 全体傾向
                - atmosphere (str): 雰囲気
                - build_preference (str): 展開スタイル
                - total_operations (int): 総操作回数
        
        Example:
            >>> profile = DJStyleProfile()
            >>> profile.eq_high_boosts = 5
            >>> profile.filter_lpf_uses = 10
            >>> style = profile.analyze_tendencies()
            >>> style['atmosphere']
            'bright'
            >>> style['build_preference']
            'dynamic'
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
        
        # 雰囲気判定（High EQのバランス）
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
    
    トラックのエネルギー情報を履歴として保存します。
    Context Aware AIでのエネルギーフロー分析に使用されます。
    
    Attributes:
        track_name (str): トラック名
        energy_level (float): エネルギーレベル（1.0-5.0 連続値）
            旧実装では int に丸めていたが、3.4 と 3.6 が同一視される
            精度劣化を防ぐため float に変更。
        genre (str): ジャンル
        bpm (float): BPM
        key (str): キー
        timestamp (float): タイムスタンプ（UNIX時間）
    
    Example:
        >>> entry = EnergyHistoryEntry(
        ...     track_name="track1.mp3",
        ...     energy_level=3.7,
        ...     genre="Techno",
        ...     bpm=130.0,
        ...     key="Am"
        ... )
        >>> print(entry.energy_level)
        3.7
    """
    track_name: str
    energy_level: float   # 修正: int → float（精度劣化を防止）
    genre: str
    bpm: float
    key: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SunoPrompt:
    """
    Suno UI形式のプロンプト（Phase 8L）
    
    Suno UIで使用する3つのフィールド（lyrics, styles, title）と
    メタデータを格納します。
    
    Attributes:
        lyrics (str): 楽曲構造の設計図（Instrumental/Vocal対応）
        styles (str): ジャンル、キーワード、スタイルタグ
        title (str): 曲タイトル
        genre (str): ジャンル（メタデータ）
        bpm (float): BPM（メタデータ）
        key (str): キー（メタデータ）
        energy_level (int): エネルギーレベル（メタデータ）
    
    Example:
        >>> prompt = SunoPrompt(
        ...     lyrics="[Intro][Build][Drop][Outro]",
        ...     styles="Techno, Dark, 130 BPM",
        ...     title="Midnight Drive"
        ... )
        >>> prompt.to_dict()
        {'lyrics': '[Intro][Build][Drop][Outro]', 'styles': 'Techno, Dark, 130 BPM', ...}
    """
    lyrics: str = ""
    styles: str = ""
    title: str = ""
    genre: str = ""
    bpm: float = 0.0
    key: str = ""
    energy_level: int = 3
    
    def to_dict(self) -> Dict:
        """
        辞書形式に変換
        
        Returns:
            Dict: プロンプト情報
        """
        return {
            'lyrics': self.lyrics,
            'styles': self.styles,
            'title': self.title,
            'genre': self.genre,
            'bpm': self.bpm,
            'key': self.key,
            'energy_level': self.energy_level
        }


# ============================================================
# 共通定数
# ============================================================

# Gemini API設定
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.9
DEFAULT_TOP_K = 40

# エネルギーレベル閾値
ENERGY_FLAT_THRESHOLD = 0.3  # 分散0.3未満はフラット


# ============================================================
# ヘルパー関数
# ============================================================

def classify_error(error_message: str) -> ErrorType:
    """
    エラーメッセージからエラータイプを分類
    
    Args:
        error_message (str): エラーメッセージ
    
    Returns:
        ErrorType: エラータイプ
    
    Example:
        >>> error_type = classify_error("RESOURCE_EXHAUSTED")
        >>> error_type == ErrorType.RESOURCE_EXHAUSTED
        True
    """
    msg_lower = error_message.lower()
    
    if "resource" in msg_lower and "exhaust" in msg_lower:
        return ErrorType.RESOURCE_EXHAUSTED
    elif "overload" in msg_lower or "quota" in msg_lower:
        return ErrorType.OVERLOADED
    elif "timeout" in msg_lower or "deadline" in msg_lower:
        return ErrorType.TIMEOUT
    else:
        return ErrorType.UNKNOWN
