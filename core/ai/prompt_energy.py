"""
Energy Flow Analysis Module
============================

Phase 9G: Context Aware AI - エネルギーフロー解析とコンテキスト判定
Phase R1: エネルギー推移解析（実装完了）

このモジュールは以下の機能を提供します:
1. エネルギーフロー分析（Phase 9G）
2. DJ操作スタイル分析（Phase 9G）
3. ジャンル一貫性分析（Phase 9G）
4. 戦略自動判定（Hypnotic/Story）（Phase 9G）
5. エネルギー履歴管理（Phase 9G）
6. セクション分割・フローパターン分類（Phase R1）
"""

from typing import List, Dict, Tuple
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
        # IQR動的閾値: 全履歴から間四分範囲を計算し、その円内に収まる場合を「フラット」と判定する。
        # 固定値 < 0.3 はライブラリ構成次第で常に共通または常に非共通になる。
        recent = self.energy_history[-3:]  # 最新3トラック
        recent_energies = [e.energy_level for e in recent]

        # IQR閾値を全履歴から算出（履歴が少ない時は固定値にフォールバック）
        all_energies = [e.energy_level for e in self.energy_history]
        if len(all_energies) >= 4:
            all_sorted = sorted(all_energies)
            n = len(all_sorted)
            q1 = all_sorted[n // 4]
            q3 = all_sorted[(n * 3) // 4]
            iqr = q3 - q1
            # IQRの50%を閾値とする（全履歴のバラツきに応じて脱却判定が変化）
            flat_threshold = iqr * 0.5 + 0.05  # 最小値は0.05（履歴が全全同一の時でも機能）
        else:
            flat_threshold = 0.3  # 履歴不足時のフォールバック

        variance = 0.0
        if len(recent_energies) > 1:
            mean = sum(recent_energies) / len(recent_energies)
            variance = sum((x - mean) ** 2 for x in recent_energies) / len(recent_energies)

        energies = recent_energies  # 以降の判定で使用する変数を統一
        is_flat_energy = variance < flat_threshold
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
        raw_energy = analysis.get('energy', {}).get('numeric', 3.0)
        entry = EnergyHistoryEntry(
            track_name=analysis.get('filename', 'Unknown'),
            # 修正: round()による整数化を廃止し、floatのまま格納する
            energy_level=max(1.0, min(5.0, float(raw_energy))),
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
    # Phase R1: エネルギー推移解析
    # ============================================================

    def analyze_energy_flow(self, track_info: dict) -> Dict:
        """
        トラックのエネルギー推移を解析する。

        track_analyzer._analyze_energy() が生成する energy_data['profile']
        （1秒ごとの {'time': float, 'level': float} リスト）を入力として
        セクション分割とフローパターン分類を行う。

        Args:
            track_info (dict): analyze_track() の戻り値
                - energy (Dict):
                    - numeric (float): 相対エネルギー（1.0-5.0）
                    - profile (List[Dict]): 1秒ごとの level 配列

        Returns:
            Dict:
                - energy_level (float): 相対エネルギー（1.0-5.0）
                - energy_label (str): 'low' / 'medium' / 'high'
                - sections (List[Dict]): セクション情報
                - flow_pattern (str): フローパターン
        """
        energy = track_info.get('energy', {})
        numeric = float(energy.get('numeric', 3.0))
        profile = energy.get('profile', [])

        energy_label = self._normalize_energy(numeric)
        sections     = self._estimate_sections(profile)
        flow_pattern = self._detect_flow_pattern(sections)

        return {
            'energy_level':  numeric,
            'energy_label':  energy_label,
            'sections':      sections,
            'flow_pattern':  flow_pattern,
        }

    def _normalize_energy(self, numeric: float) -> str:
        """
        相対エネルギー値（1.0-5.0）を履歴の分布に基づいてラベル化する。

        履歴が4件以上ある場合は IQR を使って low/medium/high を動的に決定する。
        履歴が少ない場合はスケールを3等分した固定境界にフォールバックする。

        Args:
            numeric (float): recalculate_relative_energy() が出力する 1.0-5.0 の値

        Returns:
            str: 'low' | 'medium' | 'high'
        """
        all_levels = [e.energy_level for e in self.energy_history]

        if len(all_levels) >= 4:
            sorted_levels = sorted(all_levels)
            n = len(sorted_levels)
            q1 = sorted_levels[n // 4]
            q3 = sorted_levels[(n * 3) // 4]
            if numeric <= q1:
                return 'low'
            elif numeric >= q3:
                return 'high'
            else:
                return 'medium'

        # 履歴不足: 1-5 スケールを3等分
        if numeric < 2.33:
            return 'low'
        elif numeric < 3.67:
            return 'medium'
        else:
            return 'high'

    def _estimate_sections(self, profile: List[Dict]) -> List[Dict]:
        """
        1秒ごとの energy profile からセクション境界を推定する。

        アルゴリズム:
        1. プロファイルを8秒ウィンドウで移動平均して平滑化する
        2. 隣接ウィンドウ間の差分が THRESHOLD を超えた秒をセクション境界とする
        3. 各セクションに label（'intro'/'build'/'drop'/'breakdown'/'outro'）を割り当てる

        label の割当ルール:
        - 先頭セクション: 'intro'
        - 末尾セクション: 'outro'
        - 中間でレベルが直前セクションより +0.15 以上上昇: 'drop'
        - 中間でレベルが直前セクションより -0.15 以上低下: 'breakdown'
        - それ以外の中間: 'build'

        Args:
            profile (List[Dict]): [{'time': float, 'level': float}, ...]

        Returns:
            List[Dict]: [
                {
                    'start':  float,   # セクション開始秒
                    'end':    float,   # セクション終了秒
                    'level':  float,   # セクション内 level の平均値
                    'label':  str,     # 'intro'/'build'/'drop'/'breakdown'/'outro'
                },
                ...
            ]
        """
        SMOOTH_WIN  = 8    # 移動平均ウィンドウ幅（秒）
        THRESHOLD   = 0.12 # セクション境界と判定する level 差分
        MIN_SEC     = 8    # セクションの最短秒数

        if len(profile) < SMOOTH_WIN * 2:
            # プロファイルが短すぎる場合はトラック全体を1セクションとして返す
            if not profile:
                return []
            level = sum(p['level'] for p in profile) / len(profile)
            return [{'start': profile[0]['time'], 'end': profile[-1]['time'],
                     'level': level, 'label': 'intro'}]

        levels = [p['level'] for p in profile]
        times  = [p['time']  for p in profile]

        # 移動平均で平滑化
        smoothed = []
        half = SMOOTH_WIN // 2
        for i in range(len(levels)):
            lo = max(0, i - half)
            hi = min(len(levels), i + half + 1)
            smoothed.append(sum(levels[lo:hi]) / (hi - lo))

        # セクション境界の検出
        boundaries = [0]  # 先頭は常に境界
        last_boundary = 0
        for i in range(1, len(smoothed)):
            if (times[i] - times[last_boundary]) >= MIN_SEC:
                delta = abs(smoothed[i] - smoothed[i - 1])
                if delta >= THRESHOLD:
                    boundaries.append(i)
                    last_boundary = i
        boundaries.append(len(profile))  # 末尾

        # セクションオブジェクトの生成
        sections = []
        for k in range(len(boundaries) - 1):
            lo = boundaries[k]
            hi = boundaries[k + 1]
            seg = levels[lo:hi]
            sec_level = sum(seg) / len(seg) if seg else 0.0
            sections.append({
                'start': times[lo],
                'end':   times[hi - 1] if hi - 1 < len(times) else times[-1],
                'level': round(sec_level, 4),
                'label': '',  # 後続ステップで設定
            })

        # label の割当
        for i, sec in enumerate(sections):
            if i == 0:
                sec['label'] = 'intro'
            elif i == len(sections) - 1:
                sec['label'] = 'outro'
            else:
                prev_level = sections[i - 1]['level']
                if sec['level'] - prev_level >= 0.15:
                    sec['label'] = 'drop'
                elif prev_level - sec['level'] >= 0.15:
                    sec['label'] = 'breakdown'
                else:
                    sec['label'] = 'build'

        return sections

    def _detect_flow_pattern(self, sections: List[Dict]) -> str:
        """
        セクション列からトラック全体のフローパターンを分類する。

        分類ルール（優先順位順）:
        1. 'drop' を含む         → 'peak-time'  （EDM的なクライマックス構造）
        2. 'breakdown' を含む    → 'progressive' （起伏のある展開）
        3. セクション数が2以下   → 'minimal'     （単調・ミニマル）
        4. level が単調増加      → 'progressive'
        5. その他                → 'standard'

        Args:
            sections (List[Dict]): _estimate_sections() の戻り値

        Returns:
            str: 'peak-time' | 'progressive' | 'minimal' | 'standard'
        """
        if not sections:
            return 'standard'

        labels = [s['label'] for s in sections]

        if 'drop' in labels:
            return 'peak-time'

        if 'breakdown' in labels:
            return 'progressive'

        if len(sections) <= 2:
            return 'minimal'

        # level が全体を通じて単調増加しているか確認
        levels = [s['level'] for s in sections]
        is_monotone_rising = all(levels[i] <= levels[i + 1] for i in range(len(levels) - 1))
        if is_monotone_rising:
            return 'progressive'

        return 'standard'
