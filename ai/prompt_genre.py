"""
AI Prompt Generation - Genre Knowledge Module
==============================================

ジャンル知識管理:
- knowledge_base.json の読み込み
- ジャンル情報の取得
- ジャンル選択ロジック

Phase R1で詳細メソッドを拡張予定。
"""

import json
import os
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .prompt_base import DEFAULT_BPM_RANGE, EnergyStrategy

# ロギング設定
logger = logging.getLogger(__name__)


class GenreKnowledgeManager:
    """
    ジャンル知識データベース管理
    
    knowledge_base.jsonを読み込み、ジャンル情報の取得および
    エネルギー戦略に基づくジャンル選択を提供する。
    """
    
    def __init__(self, knowledge_base_path: str = None):
        """
        Args:
            knowledge_base_path: knowledge_base.jsonのパス（Noneの場合はプロジェクトルートから検索）
        """
        if knowledge_base_path is None:
            # プロジェクトルート（core/aiの親の親ディレクトリ）を基準にする
            current_dir = Path(__file__).parent.parent.parent
            knowledge_base_path = current_dir / "knowledge_base.json"
        
        self.knowledge_base_path = Path(knowledge_base_path)
        self.kb: Dict = {}
        self._load_knowledge_base()
    
    def _load_knowledge_base(self) -> None:
        """
        knowledge_base.jsonを読み込む
        
        ファイルが存在しない場合は警告を出して空の知識ベースを使用。
        """
        if not self.knowledge_base_path.exists():
            logger.warning(f"{self.knowledge_base_path} not found. Using empty knowledge base.")
            self.kb = {
                'genres': {},
                'transitions': {'energy_progression': {}}
            }
            return
        
        try:
            with open(self.knowledge_base_path, 'r', encoding='utf-8') as f:
                self.kb = json.load(f)
            logger.info(f"Loaded knowledge base from {self.knowledge_base_path}")
        except Exception as e:
            logger.error(f"Failed to load knowledge_base.json: {e}")
            self.kb = {
                'genres': {},
                'transitions': {'energy_progression': {}}
            }
    
    # ===================================================================
    # 基本的な情報取得（実装済み）
    # ===================================================================
    
    def get_genre_info(self, genre: str) -> Optional[Dict]:
        """
        ジャンル情報を取得
        
        Args:
            genre: ジャンル名
        
        Returns:
            dict: ジャンル情報（存在しない場合はNone）
        """
        return self.kb.get('genres', {}).get(genre)
    
    # ===================================================================
    # 詳細メソッド（Phase R1で拡張予定、現在は暫定実装）
    # ===================================================================
    
    def get_bpm_range(self, genre: str) -> Tuple[int, int]:
        """
        ジャンルのBPM範囲を取得
        
        [Phase R1で詳細実装予定]
        現在は基本的な取得のみ。
        
        Args:
            genre: ジャンル名
        
        Returns:
            tuple: (min_bpm, max_bpm)
        """
        genre_info = self.get_genre_info(genre)
        if not genre_info:
            return DEFAULT_BPM_RANGE
        
        bpm_range = genre_info.get('bpm_range', [120, 140])
        return tuple(bpm_range)
    
    def get_instruments(self, genre: str) -> List[str]:
        """
        ジャンルの楽器リストを取得
        
        [Phase R1で詳細実装予定]
        現在はkeywordsをinstrumentsとして返す簡易版。
        
        Args:
            genre: ジャンル名
        
        Returns:
            list: 楽器リスト
        """
        genre_info = self.get_genre_info(genre)
        if not genre_info:
            return []
        
        # 暫定: keywordsを楽器リストとして返す
        return genre_info.get('keywords', [])
    
    def get_genre_characteristics(self, genre: str) -> Dict:
        """
        ジャンルの特性を取得（BPM/楽器/エネルギーレベル）
        
        [Phase R1で詳細実装予定]
        現在は基本情報のみ。
        
        Args:
            genre: ジャンル名
        
        Returns:
            dict: ジャンル特性
        """
        genre_info = self.get_genre_info(genre)
        if not genre_info:
            return self._get_default_characteristics()
        
        return {
            'bpm_range': self.get_bpm_range(genre),
            'instruments': self.get_instruments(genre),
            'energy_level': genre_info.get('energy_level', 'medium')
        }
    
    def _get_default_characteristics(self) -> Dict:
        """デフォルト特性"""
        return {
            'bpm_range': DEFAULT_BPM_RANGE,
            'instruments': ['synth', 'bass', 'drums'],
            'energy_level': 'medium'
        }
    
    # ===================================================================
    # ジャンル選択ロジック（実装済み、Phase 9G対応）
    # ===================================================================
    
    def select_genre_for_energy(
        self,
        current_genre: str,
        energy_target: Optional[int],
        strategy: EnergyStrategy,
        preferred_genre: Optional[str] = None
    ) -> str:
        """
        エネルギーターゲットと戦略に基づいてジャンルを選択
        
        Phase 9G: Context Aware AI対応
        - Hypnotic Mode: Minimal系ジャンルプールから選択（連続性重視）
        - Story Mode: エネルギープログレッションに基づく選択
        
        Args:
            current_genre: 現在のジャンル
            energy_target: 目標エネルギーレベル（1-5）
            strategy: エネルギー戦略（HYPNOTIC/STORY）
            preferred_genre: 優先ジャンル（指定時はこれを返す）
        
        Returns:
            str: 次のジャンル名
        """
        # 優先ジャンル指定時
        if preferred_genre:
            return preferred_genre
        
        # Hypnotic Mode: Minimal系プールから選択
        if strategy == EnergyStrategy.HYPNOTIC:
            hypnotic_pool = ["Minimal Techno", "Dub Techno", "Deep Tech", "Deep House"]
            
            # 現在がMinimal系なら70%の確率で継続
            if current_genre in hypnotic_pool and random.random() < 0.7:
                return current_genre
            else:
                return random.choice(hypnotic_pool)
        
        # Story Mode: エネルギープログレッションに基づく選択
        transitions = self.kb.get('transitions', {}).get('energy_progression', {})
        
        if energy_target and energy_target >= 4:
            # ピークエネルギー: Techno, Trance
            return random.choice(transitions.get('peak', ['Techno', 'Trance']))
        else:
            # ビルドアップ: Tech House, Progressive House
            return random.choice(transitions.get('building', ['Tech House', 'Progressive House']))
    
    # ===================================================================
    # ユーティリティ
    # ===================================================================
    
    def list_available_genres(self) -> List[str]:
        """利用可能なジャンル一覧を取得"""
        return list(self.kb.get('genres', {}).keys())
    
    def get_transition_info(self) -> Dict:
        """トランジション情報を取得"""
        return self.kb.get('transitions', {})


# ===================================================================
# モジュール情報
# ===================================================================

__all__ = [
    'GenreKnowledgeManager',
]
