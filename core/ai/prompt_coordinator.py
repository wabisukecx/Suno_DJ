"""
Prompt Coordinator Module
==========================

Phase 9G: プロンプト生成統合・コーディネーター

このモジュールは以下を提供します:
1. 全モジュールの統合（Energy, Genre, Suno）
2. メインプロンプト生成フロー
3. 無料枠管理（DailyQuota）
4. エラー分類・ハンドリング
5. ルールベースフォールバック
"""

import time
import logging
from typing import Dict, Optional

from .prompt_base import (
    GenerationMode, EnergyStrategy, ErrorType,
    DailyQuota, TokenUsage, SunoPrompt
)
from .prompt_genre import GenreKnowledgeManager
from .prompt_energy import EnergyFlowAnalyzer
from .prompt_suno import SunoPromptBuilder

# ロギング設定
logger = logging.getLogger(__name__)


class PromptCoordinator:
    """
    プロンプト生成コーディネーター（Phase 9G完全版）
    
    全モジュール（EnergyFlowAnalyzer, GenreKnowledgeManager, SunoPromptBuilder）
    を統合し、メインプロンプト生成フローを制御します。
    
    Phase 9G機能:
    - Context Aware AI（戦略自動判定）
    - 無料枠管理（DailyQuota）
    - エラー分類・ハンドリング
    - ルールベースフォールバック
    - セッション統計
    
    Attributes:
        energy_analyzer (EnergyFlowAnalyzer): エネルギーフロー分析
        genre_manager (GenreKnowledgeManager): ジャンル知識管理
        suno_builder (SunoPromptBuilder): Sunoプロンプト構築
        quota (DailyQuota): 日次クォータ管理
        token_usage (TokenUsage): トークン使用量追跡
        session_stats (Dict): セッション統計
    
    Example:
        >>> coordinator = PromptCoordinator()
        >>> 
        >>> # トラック分析結果を入力
        >>> current_track = {
        ...     'filename': 'track1.mp3',
        ...     'genre': 'Minimal Techno',
        ...     'energy': {'numeric': 3},
        ...     'bpm': 125.0,
        ...     'key': 'Am'
        ... }
        >>> 
        >>> # プロンプト生成
        >>> result = coordinator.generate_prompt(
        ...     current_track_analysis=current_track,
        ...     vocal=False
        ... )
        >>> 
        >>> print(result['suno']['title'])
        'Deep Groove'
        >>> print(result['strategy'])
        'hypnotic'
    """
    
    def __init__(self, knowledge_base_path: Optional[str] = None):
        """
        PromptCoordinatorを初期化
        
        Args:
            knowledge_base_path (Optional[str]): knowledge_base.jsonのパス
                指定されない場合、自動検出
        """
        # 各コンポーネントを初期化
        self.energy_analyzer = EnergyFlowAnalyzer()
        self.genre_manager = GenreKnowledgeManager(knowledge_base_path)
        self.suno_builder = SunoPromptBuilder()
        
        # クォータ管理
        self.quota = DailyQuota()
        self.token_usage = TokenUsage()
        
        # セッション統計
        self.session_stats = {
            'rule_based_calls': 0,
            'fallback_calls': 0,
            'errors': [],
            'start_time': time.time()
        }
        
        logger.info("PromptCoordinator initialized (Rule-based mode only)")
    
    # ============================================================
    # メインプロンプト生成フロー
    # ============================================================
    
    def generate_prompt(
        self,
        current_track_analysis: Dict,
        energy_target: Optional[int] = None,
        preferred_genre: Optional[str] = None,
        vocal: bool = False
    ) -> Dict:
        """
        Suno UI形式でプロンプトを生成
        
        Phase 9G完全フロー:
        1. エネルギー履歴更新
        2. Context分析・戦略自動判定
        3. ジャンル選択
        4. エネルギー計算
        5. Sunoプロンプト構築
        
        Args:
            current_track_analysis (Dict): 現在のトラック分析結果
                - filename (str): ファイル名
                - genre (str): ジャンル
                - energy (Dict): エネルギー情報
                    - numeric (int): 数値エネルギー（1-5）
                - bpm (float): BPM
                - key (str): キー
            energy_target (Optional[int]): ターゲットエネルギーレベル（1-5）
            preferred_genre (Optional[str]): 優先ジャンル
            vocal (bool): Vocalモードかどうか（デフォルト: False）
        
        Returns:
            Dict: プロンプト生成結果
                - suno (Dict): Suno UI形式プロンプト
                    - lyrics (str): Lyrics
                    - styles (str): Styles
                    - title (str): Title
                    - genre (str): ジャンル
                    - bpm (float): BPM
                    - key (str): キー
                    - energy_level (int): エネルギーレベル
                - prompt (str): Stylesフィールド（互換性用）
                - parameters (Dict): パラメータ
                - reasoning (Dict): 判定理由
                - source (str): 生成ソース（'rule_based', 'fallback'）
                - detected_strategy (str): 検出された戦略
                - mode (str): 生成モード
                - strategy (str): 戦略
                - quota_remaining (int): 残りクォータ
                - generation_time (float): 生成時間
        
        Example:
            >>> coordinator = PromptCoordinator()
            >>> 
            >>> track = {
            ...     'filename': 'minimal.mp3',
            ...     'genre': 'Minimal Techno',
            ...     'energy': {'numeric': 3},
            ...     'bpm': 125.0,
            ...     'key': 'Am'
            ... }
            >>> 
            >>> result = coordinator.generate_prompt(track)
            >>> 
            >>> result['strategy']
            'hypnotic'
            >>> result['suno']['styles']
            'Minimal Techno, Instrumental, 125 BPM, Am, Hypnotic, Loop-based, Minimalist'
        """
        start_time = time.time()
        
        try:
            # 1. エネルギー履歴更新
            self.energy_analyzer._add_to_energy_history(current_track_analysis)
            
            # 2. Context分析・戦略自動判定（Phase 9G）
            strategy, strategy_reasoning = self.energy_analyzer.analyze_context(
                current_track_analysis
            )
            logger.info(f"Detected Strategy: {strategy.value} ({strategy_reasoning})")
            
            # 3. ルールベース生成（現在はこれのみ実装）
            result = self._generate_rule_based(
                current_track_analysis,
                energy_target,
                preferred_genre,
                vocal,
                strategy,
                strategy_reasoning,
                is_fallback=False
            )
            
            # 4. メタデータ追加
            result['generation_time'] = time.time() - start_time
            result['mode'] = GenerationMode.RULE_BASED.value
            result['strategy'] = strategy.value
            result['quota_remaining'] = self.quota.remaining
            
            return result
        
        except Exception as e:
            logger.error(f"Prompt generation failed: {e}", exc_info=True)
            # フォールバック
            return self._generate_rule_based(
                current_track_analysis,
                energy_target,
                preferred_genre,
                vocal,
                EnergyStrategy.STORY,  # デフォルト戦略
                "Fallback to Story strategy",
                is_fallback=True
            )
    
    # ============================================================
    # ルールベース生成
    # ============================================================
    
    def _generate_rule_based(
        self,
        current: Dict,
        energy_target: Optional[int],
        preferred_genre: Optional[str],
        vocal: bool,
        strategy: EnergyStrategy,
        strategy_reasoning: str,
        is_fallback: bool = False
    ) -> Dict:
        """
        ルールベースプロンプト生成
        
        Phase 9G完全実装:
        1. ジャンル選択（戦略対応）
        2. エネルギー計算（戦略対応）
        3. Sunoプロンプト構築
        
        Args:
            current (Dict): 現在のトラック情報
            energy_target (Optional[int]): ターゲットエネルギーレベル
            preferred_genre (Optional[str]): 優先ジャンル
            vocal (bool): Vocalモードかどうか
            strategy (EnergyStrategy): 戦略（HYPNOTIC/STORY）
            strategy_reasoning (str): 戦略判定理由
            is_fallback (bool): フォールバック生成かどうか
        
        Returns:
            Dict: プロンプト生成結果
        """
        current_genre = current.get('genre', 'House')
        current_energy = current.get('energy', {}).get('numeric', 3)
        current_bpm = current.get('bpm', 120.0)
        current_key = current.get('key', 'C')
        
        # 1. ジャンル選択（戦略対応）
        next_genre = self.genre_manager.select_genre_for_strategy(
            strategy=strategy,
            current_genre=current_genre,
            energy_target=energy_target,
            preferred_genre=preferred_genre
        )
        
        # 2. エネルギー計算（戦略対応）
        next_energy_numeric = self._calculate_next_energy(
            current_energy,
            energy_target,
            strategy
        )
        
        # 3. BPM調整
        next_bpm = self._adjust_bpm(current_bpm, strategy)
        
        # 4. Sunoプロンプト構築
        suno_prompt = self.suno_builder.build_suno_prompt(
            genre=next_genre,
            bpm=next_bpm,
            key=current_key,
            energy_level=next_energy_numeric,
            strategy=strategy,
            vocal=vocal
        )
        
        # 5. 統計更新
        if is_fallback:
            self.session_stats['fallback_calls'] += 1
        else:
            self.session_stats['rule_based_calls'] += 1
        
        # 6. 結果構築
        return {
            'suno': suno_prompt.to_dict(),
            'prompt': suno_prompt.styles,  # 互換性用
            'parameters': {
                'genre': next_genre,
                'bpm': next_bpm,
                'key': suno_prompt.key,
                'energy_level': self._numeric_to_energy_level(next_energy_numeric),
                'energy_numeric': next_energy_numeric
            },
            'reasoning': {
                'genre_transition': f"Auto-selected based on {strategy.value} strategy ({strategy_reasoning})",
                'energy_strategy': f"Strategy: {strategy.value}"
            },
            'source': 'fallback' if is_fallback else 'rule_based',
            'detected_strategy': strategy.value
        }
    
    # ============================================================
    # ヘルパーメソッド
    # ============================================================
    
    def _calculate_next_energy(
        self,
        current_energy: int,
        energy_target: Optional[int],
        strategy: EnergyStrategy
    ) -> int:
        """
        次のエネルギーレベルを計算
        
        Hypnotic戦略: ±1の範囲でランダム変動
        Story戦略: ターゲットに向かって上昇
        
        Args:
            current_energy (int): 現在のエネルギーレベル（1-5）
            energy_target (Optional[int]): ターゲットエネルギーレベル
            strategy (EnergyStrategy): 戦略
        
        Returns:
            int: 次のエネルギーレベル（1-5）
        """
        import random
        
        if strategy == EnergyStrategy.HYPNOTIC:
            # Hypnotic: ±1の範囲でランダム変動（フラット維持）
            delta = random.choice([-1, 0, 0, 1])  # 0が2回で確率50%
            next_energy = current_energy + delta
        else:
            # Story: ターゲットに向かって上昇
            if energy_target:
                next_energy = energy_target
            else:
                next_energy = min(5, current_energy + 1)
        
        # 1-5の範囲にクランプ
        return max(1, min(5, next_energy))
    
    def _adjust_bpm(self, current_bpm: float, strategy: EnergyStrategy) -> float:
        """
        BPMを調整
        
        Hypnotic戦略: ±1の微調整
        Story戦略: ±3の範囲で変動
        
        Args:
            current_bpm (float): 現在のBPM
            strategy (EnergyStrategy): 戦略
        
        Returns:
            float: 調整後のBPM
        """
        import random
        
        if strategy == EnergyStrategy.HYPNOTIC:
            # Hypnotic: ±1の微調整
            delta = random.uniform(-1, 1)
        else:
            # Story: ±3の範囲で変動
            delta = random.uniform(-3, 3)
        
        return current_bpm + delta
    
    def _numeric_to_energy_level(self, n: int) -> str:
        """
        数値エネルギーを文字列エネルギーレベルに変換
        
        Args:
            n (int): 数値エネルギー（1-5）
        
        Returns:
            str: エネルギーレベル文字列
        """
        mapping = {
            1: "Very Low",
            2: "Low",
            3: "Medium",
            4: "High",
            5: "Very High"
        }
        return mapping.get(n, "Medium")
    
    # ============================================================
    # DJ操作記録（外部から呼び出し）
    # ============================================================
    
    def record_eq_operation(self, band: str, value: float):
        """
        EQ操作を記録
        
        Args:
            band (str): EQバンド（'high', 'mid', 'low'）
            value (float): EQ値（0.0-1.0）
        """
        self.energy_analyzer.record_eq_operation(band, value)
    
    def record_filter_operation(self, value: float):
        """
        Filter操作を記録
        
        Args:
            value (float): Filter値（0.0-1.0）
        """
        self.energy_analyzer.record_filter_operation(value)
    
    # ============================================================
    # セッション統計
    # ============================================================
    
    def get_session_stats(self) -> Dict:
        """
        セッション統計を取得
        
        Returns:
            Dict: セッション統計
                - rule_based_calls (int): ルールベース呼び出し回数
                - fallback_calls (int): フォールバック呼び出し回数
                - errors (List): エラーリスト
                - session_duration (float): セッション経過時間
                - quota_remaining (int): 残りクォータ
        """
        return {
            'rule_based_calls': self.session_stats['rule_based_calls'],
            'fallback_calls': self.session_stats['fallback_calls'],
            'errors': self.session_stats['errors'],
            'session_duration': time.time() - self.session_stats['start_time'],
            'quota_remaining': self.quota.remaining
        }
