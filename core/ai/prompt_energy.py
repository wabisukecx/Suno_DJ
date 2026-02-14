"""
Energy Flow Analysis Module
============================

Phase 9G: Context Aware AI - エネルギーフロー解析とコンテキスト判定
Phase R1: エネルギー推移解析（暫定実装のみ）

このモジュールは以下の機能を提供します:
1. エネルギーフロー分析（Phase 9G）
2. DJ操作スタイル分析（Phase 9G）
3. ジャンル一貫性分析（Phase 9G）
4. 戦略自動判定（Hypnotic/Story）（Phase 9G）
5. エネルギー履歴管理（Phase 9G）
6. エネルギー推移解析（Phase R1 - 暫定実装）
"""

from typing import List, Dict, Tuple, Optional
from threading import Lock
from .prompt_base import EnergyStrategy, DJStyleProfile, EnergyHistoryEntry


class EnergyFlowAnalyzer:
    """
    Energy Flow解析・Context Aware AI（Phase 9G完全版）
    
    トラックのエネルギーフロー、DJ操作スタイル、ジャンル一貫性を分析し、
    最適な生成戦略（Hypnotic/Story）を自動判定します。
    
    Phase 9G機能:
    - エネルギーフロー分析（分散計算）
    - DJ操作スタイル分析（EQ/Filter操作）
    - ジャンル一貫性分析（Minimal系検出）
    - 戦略自動判定ロジック
    - エネルギー履歴管理（最大20件）
    
    Phase R1機能（暫定実装）:
    - エネルギー推移解析（基本的な実装のみ）
    - Z-score正規化（簡易変換のみ）
    - セクション構造推定（NotImplementedError）
    - フローパターン検出（NotImplementedError）
    
    Attributes:
        energy_history (List[EnergyHistoryEntry]): エネルギー履歴（最大20件）
        max_history (int): 履歴の最大保持数
        dj_style (DJStyleProfile): DJ操作スタイルプロファイル
        _lock (Lock): スレッドセーフ用ロック
    
    Example:
        >>> analyzer = EnergyFlowAnalyzer()
        >>> 
        >>> # EQ操作を記録
        >>> analyzer.record_eq_operation('high', 0.8)
        >>> analyzer.record_filter_operation(0.6)
        >>> 
        >>> # トラック情報を分析に追加
        >>> current_track = {
        ...     'filename': 'track1.mp3',
        ...     'genre': 'Minimal Techno',
        ...     'energy': {'numeric': 3},
        ...     'bpm': 125.0,
        ...     'key': 'Am'
        ... }
        >>> 
        >>> # コンテキスト分析と戦略判定
        >>> strategy, reason = analyzer.analyze_context(current_track)
        >>> print(f"Strategy: {strategy}, Reason: {reason}")
        Strategy: EnergyStrategy.HYPNOTIC, Reason: Minimal genre detected (Minimal Techno)
    """
    
    def __init__(self):
        """EnergyFlowAnalyzerを初期化"""
        self.energy_history: List[EnergyHistoryEntry] = []
        self.max_history: int = 20
        self.dj_style = DJStyleProfile()
        self._lock = Lock()
    
    # ============================================================
    # Phase 9G: Context Aware AI - メインメソッド
    # ============================================================
    
    def analyze_context(self, current: Dict) -> Tuple[EnergyStrategy, str]:
        """
        コンテキスト（履歴、エナジーフロー、DJ操作）を分析して戦略を決定する
        
        Phase 9G完全実装:
        - エネルギーフロー分析（分散計算）
        - DJ操作スタイル分析（dynamic/subtle判定）
        - ジャンル一貫性分析（Minimal系キーワード検出）
        - 4つの判定ロジック（優先順位順）
        
        判定ロジックの優先順位:
        1. Minimal系ジャンル + 安定操作 → Hypnotic
        2. フラットエネルギー + 安定操作 → Hypnotic
        3. エネルギー上昇中 → Story
        4. ダイナミック操作 → Story
        5. デフォルト → Story
        
        Args:
            current (Dict): 現在のトラック情報
                - filename (str): ファイル名
                - genre (str): ジャンル
                - energy (Dict): エネルギー情報
                    - numeric (int): 数値エネルギー（1-5）
                - bpm (float): BPM
                - key (str): キー
        
        Returns:
            Tuple[EnergyStrategy, str]: (戦略, 理由)
                - EnergyStrategy.HYPNOTIC: ミニマル継続戦略
                - EnergyStrategy.STORY: ストーリー展開戦略
        
        Example:
            >>> analyzer = EnergyFlowAnalyzer()
            >>> track = {
            ...     'filename': 'minimal_track.mp3',
            ...     'genre': 'Minimal Techno',
            ...     'energy': {'numeric': 3},
            ...     'bpm': 125.0,
            ...     'key': 'Am'
            ... }
            >>> strategy, reason = analyzer.analyze_context(track)
            >>> print(f"{strategy}: {reason}")
            EnergyStrategy.HYPNOTIC: Minimal genre detected (Minimal Techno)
        """
        # 初期トラックの場合はStory戦略
        if len(self.energy_history) < 2:
            return EnergyStrategy.STORY, "Initial track"
        
        reasoning_parts = []
        
        # --- A. エナジーフロー分析 ---
        recent = self.energy_history[-3:]  # 最新3トラック
        energies = [e.energy_level for e in recent]
        variance = 1.0
        if len(energies) > 1:
            mean = sum(energies) / len(energies)
            variance = sum((x - mean) ** 2 for x in energies) / len(energies)
        
        is_flat_energy = variance < 0.3  # 分散0.3未満はフラット
        is_rising = energies[-1] > energies[0]  # エネルギー上昇中
        
        # --- B. DJ操作スタイル分析 ---
        style = self.dj_style.analyze_tendencies()
        is_dynamic_ops = style.get('build_preference') == 'dynamic'
        
        # --- C. ジャンルの一貫性 ---
        current_genre = current.get('genre', '')
        minimal_keywords = ['Minimal', 'Dub', 'Deep', 'Tech', 'Ambient']
        is_minimal_genre = any(k in current_genre for k in minimal_keywords)
        
        # === 判定ロジック（優先順位順） ===
        
        # 1. Minimal系ジャンル + 安定操作 → Hypnotic
        if is_minimal_genre and not is_dynamic_ops:
            reasoning_parts.append(f"Minimal genre detected ({current_genre})")
            if is_flat_energy:
                reasoning_parts.append("Maintaining steady groove")
            return EnergyStrategy.HYPNOTIC, " / ".join(reasoning_parts)
        
        # 2. フラットエネルギー + 安定操作 → Hypnotic
        if is_flat_energy and not is_dynamic_ops:
            reasoning_parts.append("Flat energy flow detected")
            reasoning_parts.append("Subtle mixing style")
            return EnergyStrategy.HYPNOTIC, " / ".join(reasoning_parts)
        
        # 3. エネルギー上昇中 → Story
        if is_rising:
            reasoning_parts.append("Energy is rising")
            return EnergyStrategy.STORY, " / ".join(reasoning_parts)
        
        # 4. ダイナミック操作 → Story
        if is_dynamic_ops:
            reasoning_parts.append("Dynamic filtering detected")
            return EnergyStrategy.STORY, " / ".join(reasoning_parts)
        
        # 5. デフォルト → Story
        return EnergyStrategy.STORY, "Standard progression"
    
    # ============================================================
    # Phase 9G: エネルギー履歴管理
    # ============================================================
    
    def _add_to_energy_history(self, analysis: Dict):
        """
        エネルギー履歴にトラック情報を追加
        
        スレッドセーフな履歴管理を実装。最大20件を超えた場合は
        古いエントリから削除します。
        
        Args:
            analysis (Dict): トラック分析結果
                - filename (str): ファイル名
                - energy (Dict): エネルギー情報
                    - numeric (int): 数値エネルギー（1-5）
                - genre (str): ジャンル
                - bpm (float): BPM
                - key (str): キー
        
        Example:
            >>> analyzer = EnergyFlowAnalyzer()
            >>> track = {
            ...     'filename': 'track1.mp3',
            ...     'energy': {'numeric': 4},
            ...     'genre': 'House',
            ...     'bpm': 128.0,
            ...     'key': 'Cm'
            ... }
            >>> analyzer._add_to_energy_history(track)
            >>> len(analyzer.energy_history)
            1
        """
        entry = EnergyHistoryEntry(
            track_name=analysis.get('filename', 'Unknown'),
            energy_level=analysis.get('energy', {}).get('numeric', 3),
            genre=analysis.get('genre', 'House'),
            bpm=analysis.get('bpm', 120.0),
            key=analysis.get('key', 'C')
        )
        with self._lock:
            self.energy_history.append(entry)
            if len(self.energy_history) > self.max_history:
                self.energy_history.pop(0)
    
    # ============================================================
    # Phase 9G: DJ操作記録
    # ============================================================
    
    def record_eq_operation(self, band: str, value: float):
        """
        EQ操作を記録（Phase 9G）
        
        DJ操作スタイルプロファイルにEQ操作を記録します。
        これにより、analyze_context()でのスタイル分析が可能になります。
        
        Args:
            band (str): EQバンド ('high', 'mid', 'low')
            value (float): EQ値（0.0-1.0）
        
        Example:
            >>> analyzer = EnergyFlowAnalyzer()
            >>> analyzer.record_eq_operation('high', 0.8)
            >>> analyzer.record_eq_operation('mid', 0.5)
            >>> analyzer.record_eq_operation('low', 0.3)
        """
        if band == 'high':
            self.dj_style.record_eq_high(value)
        elif band == 'mid':
            self.dj_style.record_eq_mid(value)
        elif band == 'low':
            self.dj_style.record_eq_low(value)
    
    def record_filter_operation(self, value: float):
        """
        Filter操作を記録（Phase 9G）
        
        DJ操作スタイルプロファイルにFilter操作を記録します。
        これにより、analyze_context()でのスタイル分析が可能になります。
        
        Args:
            value (float): Filter値（0.0-1.0）
        
        Example:
            >>> analyzer = EnergyFlowAnalyzer()
            >>> analyzer.record_filter_operation(0.6)
            >>> analyzer.record_filter_operation(0.7)
        """
        self.dj_style.record_filter(value)
    
    # ============================================================
    # Phase R1: エネルギー推移解析（暫定実装）
    # ============================================================
    
    def analyze_energy_flow(self, track_info: dict) -> Dict:
        """
        トラックのエネルギー推移を解析（Phase R1 - 暫定実装）
        
        [Phase R1で完全実装予定]
        現在は基本的な情報のみを返す暫定実装です。
        
        将来実装予定:
        - セクション構造の詳細推定
        - フローパターンの高度な検出
        - Z-score正規化による精密なエネルギー分析
        
        Args:
            track_info (dict): トラック情報
                - energy (Dict): エネルギー情報
                    - numeric (int): 数値エネルギー（1-5）
        
        Returns:
            Dict: エネルギーフロー情報
                - energy_level (int): エネルギーレベル
                - sections (List): セクション情報（空リスト）
                - flow_pattern (str): フローパターン（'standard'固定）
        
        Note:
            Phase R1で以下を実装予定:
            - セクション構造推定（_estimate_sections）
            - フローパターン検出（_detect_flow_pattern）
            - Z-score正規化（_normalize_energy）
        """
        # [Phase R1で実装]
        return {
            'energy_level': track_info.get('energy', {}).get('numeric', 3),
            'sections': [],
            'flow_pattern': 'standard'
        }
    
    def _normalize_energy(self, energy: float) -> str:
        """
        Z-score正規化（Phase R1 - 暫定実装）
        
        [Phase R1で完全実装予定]
        現在は簡易的な3段階変換のみを実装しています。
        
        将来実装予定:
        - 履歴全体の平均・標準偏差を使用したZ-score計算
        - より精密なエネルギーレベル分類
        
        Args:
            energy (float): エネルギー値（0.0-1.0）
        
        Returns:
            str: 正規化後のエネルギーレベル
                - "low": 0.0-0.3
                - "medium": 0.3-0.6
                - "high": 0.6-1.0
        
        Note:
            Phase R1で完全なZ-score正規化を実装予定
        """
        # [Phase R1で実装]
        if energy < 0.3:
            return "low"
        elif energy < 0.6:
            return "medium"
        else:
            return "high"
    
    def _estimate_sections(self, energy: float, duration: int) -> List[Dict]:
        """
        セクション構造推定（Phase R1で実装予定）
        
        トラックのエネルギー値と長さから、セクション構造を推定します。
        
        Args:
            energy (float): エネルギー値
            duration (int): トラック長（秒）
        
        Returns:
            List[Dict]: セクション情報リスト
        
        Raises:
            NotImplementedError: Phase R1で実装予定
        
        Note:
            Phase R1で以下を実装予定:
            - Intro/Build/Drop/Outro等のセクション検出
            - セクション境界の推定
            - セクション毎のエネルギー特性分析
        """
        raise NotImplementedError("Phase R1で実装予定")
    
    def _detect_flow_pattern(self, sections: List[Dict]) -> str:
        """
        フローパターン検出（Phase R1で実装予定）
        
        セクション情報からトラック全体のフローパターンを検出します。
        
        Args:
            sections (List[Dict]): セクション情報リスト
        
        Returns:
            str: フローパターン（例: 'progressive', 'peak-time', 'minimal'）
        
        Raises:
            NotImplementedError: Phase R1で実装予定
        
        Note:
            Phase R1で以下を実装予定:
            - Progressive系のパターン検出
            - Peak-time系のパターン検出
            - Minimal系のパターン検出
            - その他のフローパターン分類
        """
        raise NotImplementedError("Phase R1で実装予定")
