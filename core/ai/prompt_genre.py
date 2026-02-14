"""
<<<<<<< HEAD
Genre Knowledge Management Module
==================================

ジャンル知識ベース管理とジャンル選択ロジック

このモジュールは以下を提供します:
1. knowledge_base.json読み込み
2. ジャンル選択（Hypnotic/Story戦略対応）
3. ジャンル知識検索
=======
AI Prompt Generation - Genre Knowledge Module
==============================================

ジャンル知識管理:
- knowledge_base.json の読み込み
- ジャンル情報の取得
- ジャンル選択ロジック

Phase R1で詳細メソッドを拡張予定。
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09
"""

import json
import os
<<<<<<< HEAD
import random
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .prompt_base import EnergyStrategy
=======
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .prompt_base import DEFAULT_BPM_RANGE, EnergyStrategy
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09

# ロギング設定
logger = logging.getLogger(__name__)


class GenreKnowledgeManager:
    """
<<<<<<< HEAD
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
=======
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
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09
    
    def get_genre_info(self, genre: str) -> Optional[Dict]:
        """
        ジャンル情報を取得
        
        Args:
<<<<<<< HEAD
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
=======
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
>>>>>>> 5c8ea206127779140fcfd111b922886419977f09
