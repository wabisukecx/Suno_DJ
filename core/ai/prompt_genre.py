"""
Genre Knowledge Management Module
==================================

ジャンル知識ベース管理とジャンル選択ロジック

このモジュールは以下を提供します:
1. knowledge_base.json読み込み
2. ジャンル選択（Hypnotic/Story戦略対応）
3. ジャンル知識検索
"""

import json
import os
import random
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .prompt_base import EnergyStrategy

# ロギング設定
logger = logging.getLogger(__name__)


class GenreKnowledgeManager:
    """
    ジャンル知識ベース管理クラス
    
    knowledge_base.jsonからジャンル情報を読み込み、
    戦略（Hypnotic/Story）に応じたジャンル選択を行います。
    
    Attributes:
        kb (Dict): 知識ベースデータ
        available_genres (List[str]): 利用可能なジャンルリスト
    
    Example:
        >>> mgr = GenreKnowledgeManager()
        >>> genre = mgr.select_genre_for_strategy(
        ...     strategy=EnergyStrategy.HYPNOTIC,
        ...     current_genre="Deep House"
        ... )
        >>> print(genre)
        'Minimal Techno'
    """
    
    def __init__(self, knowledge_base_path: Optional[str] = None):
        """
        GenreKnowledgeManagerを初期化
        
        Args:
            knowledge_base_path (Optional[str]): knowledge_base.jsonのパス
                指定されない場合、プロジェクトルートから自動検出
        """
        # 知識ベース読み込み
        if knowledge_base_path is None:
            # プロジェクトルート（coreの親の親ディレクトリ）を基準にする
            current_dir = Path(__file__).parent.parent.parent
            knowledge_base_path = current_dir / "knowledge_base.json"
        
        if os.path.exists(knowledge_base_path):
            with open(knowledge_base_path, 'r', encoding='utf-8') as f:
                self.kb = json.load(f)
            logger.info(f"Loaded knowledge_base.json from {knowledge_base_path}")
        else:
            logger.warning("knowledge_base.json not found. Using internal fallback.")
            self.kb = {
                'genres': {},
                'transitions': {
                    'energy_progression': {
                        'building': ['Tech House', 'Progressive House'],
                        'peak': ['Techno', 'Trance']
                    }
                }
            }
        
        # 利用可能なジャンルリストを抽出
        self.available_genres = list(self.kb.get('genres', {}).keys())
        
        if self.available_genres:
            logger.info(f"Available genres: {len(self.available_genres)} genres loaded")
        else:
            logger.warning("No genres found in knowledge_base.json")
    
    def select_genre_for_strategy(
        self,
        strategy: EnergyStrategy,
        current_genre: str,
        energy_target: Optional[int] = None,
        preferred_genre: Optional[str] = None
    ) -> str:
        """
        戦略に応じたジャンル選択
        
        Hypnotic戦略の場合:
        - 現在のジャンルがMinimal系なら70%で継続
        - それ以外はMinimal系プールからランダム選択
        
        Story戦略の場合:
        - energy_target >= 4: Peak系ジャンル（Techno, Trance）
        - それ以外: Building系ジャンル（Tech House, Progressive House）
        
        Args:
            strategy (EnergyStrategy): 戦略（HYPNOTIC/STORY）
            current_genre (str): 現在のジャンル
            energy_target (Optional[int]): ターゲットエネルギーレベル（1-5）
            preferred_genre (Optional[str]): 優先ジャンル（指定時は優先）
        
        Returns:
            str: 選択されたジャンル
        
        Example:
            >>> mgr = GenreKnowledgeManager()
            >>> 
            >>> # Hypnotic戦略: Minimal系を選択
            >>> genre = mgr.select_genre_for_strategy(
            ...     strategy=EnergyStrategy.HYPNOTIC,
            ...     current_genre="Minimal Techno"
            ... )
            >>> genre in ["Minimal Techno", "Dub Techno", "Deep Tech", "Deep House"]
            True
            >>> 
            >>> # Story戦略: Peak系を選択
            >>> genre = mgr.select_genre_for_strategy(
            ...     strategy=EnergyStrategy.STORY,
            ...     current_genre="House",
            ...     energy_target=5
            ... )
            >>> genre in ["Techno", "Trance"]
            True
        """
        # 優先ジャンルが指定されている場合は優先
        if preferred_genre:
            return preferred_genre
        
        # Hypnotic戦略: Minimal系ジャンルを選択
        if strategy == EnergyStrategy.HYPNOTIC:
            return self._select_hypnotic_genre(current_genre)
        
        # Story戦略: エネルギーターゲットに応じて選択
        else:
            return self._select_story_genre(energy_target)
    
    def _select_hypnotic_genre(self, current_genre: str) -> str:
        """
        Hypnotic戦略用ジャンル選択
        
        Minimal系ジャンルプールから選択。
        現在のジャンルがMinimal系の場合は70%で継続。
        
        Args:
            current_genre (str): 現在のジャンル
        
        Returns:
            str: 選択されたジャンル
        """
        # Minimal系ジャンルプール
        hypnotic_pool = [
            "Minimal Techno",
            "Dub Techno",
            "Deep Tech",
            "Deep House"
        ]
        
        # 現在のジャンルがMinimal系なら70%で継続
        if current_genre in hypnotic_pool and random.random() < 0.7:
            return current_genre
        
        # それ以外はランダム選択
        return random.choice(hypnotic_pool)
    
    def _select_story_genre(self, energy_target: Optional[int]) -> str:
        """
        Story戦略用ジャンル選択
        
        エネルギーターゲットに応じてPeak系/Building系を選択。
        
        Args:
            energy_target (Optional[int]): ターゲットエネルギーレベル（1-5）
        
        Returns:
            str: 選択されたジャンル
        """
        transitions = self.kb.get('transitions', {}).get('energy_progression', {})
        
        # エネルギーターゲットが4以上の場合はPeak系
        if energy_target and energy_target >= 4:
            peak_genres = transitions.get('peak', ['Techno', 'Trance'])
            return random.choice(peak_genres)
        
        # それ以外はBuilding系
        else:
            building_genres = transitions.get('building', ['Tech House', 'Progressive House'])
            return random.choice(building_genres)
    
    def get_genre_info(self, genre: str) -> Optional[Dict]:
        """
        ジャンル情報を取得
        
        Args:
            genre (str): ジャンル名
        
        Returns:
            Optional[Dict]: ジャンル情報（存在しない場合はNone）
        
        Example:
            >>> mgr = GenreKnowledgeManager()
            >>> info = mgr.get_genre_info("Techno")
            >>> if info:
            ...     print(info.get('bpm_range'))
            [125, 135]
        """
        return self.kb.get('genres', {}).get(genre)
    
    def get_all_genres(self) -> List[str]:
        """
        全ジャンルリストを取得
        
        Returns:
            List[str]: ジャンルリスト
        
        Example:
            >>> mgr = GenreKnowledgeManager()
            >>> genres = mgr.get_all_genres()
            >>> len(genres) > 0
            True
        """
        return self.available_genres.copy()
    
    def is_minimal_genre(self, genre: str) -> bool:
        """
        Minimal系ジャンルかどうかを判定
        
        Args:
            genre (str): ジャンル名
        
        Returns:
            bool: Minimal系ジャンルならTrue
        
        Example:
            >>> mgr = GenreKnowledgeManager()
            >>> mgr.is_minimal_genre("Minimal Techno")
            True
            >>> mgr.is_minimal_genre("House")
            False
        """
        minimal_keywords = ['Minimal', 'Dub', 'Deep', 'Tech', 'Ambient']
        return any(keyword in genre for keyword in minimal_keywords)
