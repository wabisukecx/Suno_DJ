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

import os
import time
import logging
from typing import Dict, Optional

from .prompt_base import (
    GenerationMode, EnergyStrategy, DailyQuota, TokenUsage,
    ErrorType, classify_error
)
from .prompt_genre import GenreKnowledgeManager
from .prompt_energy import EnergyFlowAnalyzer
from .prompt_suno import SunoPromptBuilder
from core.camelot_wheel import CamelotWheel

# Gemini SDK（google.genai 優先、旧 google.generativeai はフォールバック）
try:
    import google.genai as genai
    from google.genai import types as genai_types
    _GENAI_NEW = True
    GEMINI_AVAILABLE = True
except ImportError:
    try:
        import google.generativeai as genai  # 旧 SDK （非推奨）
        _GENAI_NEW = False
        GEMINI_AVAILABLE = True
    except ImportError:
        GEMINI_AVAILABLE = False
        _GENAI_NEW = False

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
    - セッション統計（エラーログ含む）

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

        # Camelot Wheel
        self.camelot_wheel = CamelotWheel()

        # セッション統計
        self.session_stats = {
            'rule_based_calls': 0,
            'fallback_calls': 0,
            'errors': [],          # エラー情報を実際に追記する
            'start_time': time.time()
        }

        # Gemini API 初期化
        self.gemini_model = None
        self._init_gemini()

        mode_str = "Gemini API" if self.gemini_model else "Rule-based mode only"
        logger.info(f"PromptCoordinator initialized ({mode_str})")

    def _init_gemini(self):
        """Gemini API を初期化。APIキーがなければスキップ。"""
        if not GEMINI_AVAILABLE:
            logger.warning("google-genai not installed. Run: pip install google-genai")
            return

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set. Running in rule-based mode.")
            return

        try:
            if _GENAI_NEW:
                # 新 SDK: google.genai
                self._genai_client = genai.Client(api_key=api_key)
                self.gemini_model = "gemini-2.0-flash"  # モデル名を文字列で保持
                logger.info("Gemini API initialized (google.genai / gemini-2.0-flash)")
            else:
                # 旧 SDK フォールバック: google.generativeai
                genai.configure(api_key=api_key)
                self._genai_client = None
                self.gemini_model = genai.GenerativeModel("gemini-2.0-flash")
                logger.warning("Gemini API initialized via deprecated google.generativeai. "
                               "Run: pip install google-genai")
        except Exception as e:
            logger.error(f"Gemini API init failed: {e}")
            self.gemini_model = None
            self._genai_client = None

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
                - source (str): 生成ソース（'rule_based', 'gemini', 'fallback'等）
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

            # 3. Gemini API / ルールベースで生成
            if self.gemini_model and self.quota.check_and_increment():
                result = self._generate_gemini(
                    current_track_analysis,
                    energy_target,
                    preferred_genre,
                    vocal,
                    strategy,
                    strategy_reasoning
                )
                result['mode'] = GenerationMode.GEMINI.value
            else:
                result = self._generate_rule_based(
                    current_track_analysis,
                    energy_target,
                    preferred_genre,
                    vocal,
                    strategy,
                    strategy_reasoning,
                    is_fallback=False
                )
                result['mode'] = GenerationMode.RULE_BASED.value

            # 4. メタデータ追加
            result['generation_time'] = time.time() - start_time
            result['strategy'] = strategy.value
            result['quota_remaining'] = self.quota.remaining

            return result

        except Exception as e:
            logger.error(f"Prompt generation failed: {e}", exc_info=True)
            self.session_stats['errors'].append({
                'type': 'generation_error',
                'message': str(e),
                'timestamp': time.time()
            })
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
    # Gemini API生成
    # ============================================================

    @staticmethod
    def _summarize_energy_profile(profile: list) -> str:
        """energy profile リストを簡潔な文字列に変換（トークン節約）"""
        if not profile:
            return "unknown"
        # 先頭・中間・末尾の3点サンプル
        n = len(profile)
        samples = [profile[0], profile[n // 2], profile[-1]]
        labels = ['start', 'mid', 'end']
        parts = []
        for label, p in zip(labels, samples):
            lvl = p.get('level', 0)
            t   = p.get('time', 0)
            parts.append(f"{label}@{t:.0f}s={lvl:.2f}")
        return ', '.join(parts)

    def _build_gemini_prompt(self, current: Dict, strategy: 'EnergyStrategy',
                              strategy_reasoning: str, next_genre: str,
                              next_bpm: float, next_energy: int,
                              compatible_keys: list, vocal: bool,
                              base_lyrics: str) -> str:
        """Gemini に送るプロンプトを構築（track_analyzer の全情報を活用）"""
        energy_map = {1: "Very Low", 2: "Low", 3: "Medium", 4: "High", 5: "Very High"}
        vocal_str = "Vocal" if vocal else "Instrumental (no singing, no vocals)"
        compatible_str = ', '.join(compatible_keys[:4]) if compatible_keys else 'any'

        # --- 現在曲の詳細情報を整形 ---
        energy_data   = current.get('energy', {})
        energy_num    = max(1, min(5, round(float(energy_data.get('numeric', 3)))))
        energy_mean   = energy_data.get('mean', 0.0)
        energy_max    = energy_data.get('max', 0.0)
        energy_profile_str = self._summarize_energy_profile(energy_data.get('profile', []))

        raw_key       = current.get('key', 'C')          # 例: "A Min (8A)"
        current_camelot = self.camelot_wheel.to_camelot(raw_key)
        auto_gain     = current.get('auto_gain', 0.0)
        first_beat    = current.get('first_beat', 0.0)
        auto_cue      = current.get('auto_cue', [])       # セクション変化点（秒）
        auto_cue_str  = ', '.join(f"{t:.1f}s" for t in auto_cue[:6]) if auto_cue else 'none detected'

        # ★拍ズレ対策として、## LYRICS field と ## STYLES field にリズム固定の指示を追加
        return f"""You are a Suno V5 dance music prompt expert.
Generate the 3 fields (LYRICS / STYLES / TITLE) for the next track in a DJ set.

## Currently playing track (full analysis)
- File      : {current.get('filename', 'Unknown')}
- Genre     : {current.get('genre', 'House')}
- BPM       : {current.get('bpm', 120.0):.1f}
- Key       : {raw_key}  (Camelot: {current_camelot})
- Energy    : {energy_num}/5  (mean={energy_mean:.3f}, peak={energy_max:.3f})
- Profile   : {energy_profile_str}
- Auto-cue  : {auto_cue_str}   ← detected section change points
- Auto-gain : {auto_gain:+.1f} dB
- First beat: {first_beat:.2f}s
- DJ strategy: {strategy.value} — {strategy_reasoning}

## Next track design parameters
- Genre     : {next_genre}
- BPM       : {next_bpm:.0f}
- Energy    : {next_energy}/5 ({energy_map.get(next_energy, 'Medium')})
- Key options (Camelot-compatible): {compatible_str}
- Vocal     : {vocal_str}

## How to use the analysis
- "Profile" shows energy arc: use it to decide if the next track should contrast or continue.
- "Auto-cue" points are likely drop/breakdown times in the current track — use them to
  inform phrasing and section lengths in the LYRICS field.
- "DJ strategy" drives the overall arc: hypnotic = maintain groove, story = build and release.

## LYRICS field — strict rules
{'VOCAL MODE: Write actual song lyrics with section tags.' if vocal else 'INSTRUMENTAL MODE: performance-direction tags only, NO words, NO lyrics.'}

{'Vocal structure rules:' if vocal else 'Instrumental structure rules:'}
{'- Keep every section tag from the base structure exactly as-is.' if vocal else '- Keep every section tag from the base structure exactly as-is.'}
{'- Under each section tag, write actual singable lyrics (2-8 lines per section).' if vocal else '- After each section tag, add 2-3 short performance-direction tags on separate lines.'}
{'- [Intro] and [Outro]: minimal or no lyrics, mood-setting.' if vocal else '- Tags must describe sound/texture/filter/mix feel.'}
{'- CRITICAL: Maintain a strict 4/4 time signature. Do NOT write lines that break the rhythm.' if vocal else '- CRITICAL: Maintain a strict 4/4 time signature. Do NOT add tags for complex drum fills, polyrhythms, or tempo shifts.'}

Base structure:
{base_lyrics}

{'Example (Vocal):' if vocal else 'Example (Instrumental):'}
[Intro 16 bars]
{'Lost in the light' if vocal else '[sparse kick, low-pass filter almost closed]'}
{'Drifting through the night' if vocal else '[sub bass pulse entering slowly]'}
[Groove A 32 bars]
{'Feel the beat inside' if vocal else '[rolling bassline locked with kick]'}
{'Let it take you higher' if vocal else '[clicky hats adding texture]'}

## STYLES field — strict rules
- First token must be the genre name
- Add sound-design keywords specific to {next_genre}
- Must include: {next_bpm:.0f} BPM, "Steady 4/4 beat", "Four on the floor"
- If Instrumental: must include "Instrumental"
- Max 200 characters, comma-separated English only
- FORBIDDEN: "Medium Energy", "High Energy", "Dark" alone, "Minimal Tech"
- Example (Tech House): Tech House, Driving Bassline, Clicky Hats, Acid Elements, Steady 4/4 beat, Four on the floor, Instrumental, {next_bpm:.0f} BPM
- Example (Techno)    : Techno, Hard Kick, Distorted Bass, Industrial Noise, Underground Berlin, Steady 4/4 beat, Four on the floor, Instrumental, {next_bpm:.0f} BPM

## TITLE field
- 2-4 English words, evocative and genre-appropriate

## Output (EXACTLY this format, nothing else)
LYRICS:
[section tag]
[performance direction]
...

STYLES:
[comma-separated keywords]

TITLE:
[title]"""

    def _parse_gemini_response(self, text: str, fallback_suno: dict) -> dict:
        """
        Gemini レスポンスを parse して suno dict を返す

        修正: LYRICS・STYLES の結合を ' '.join から '\\n'.join に変更し、
        改行構造を保持する。STYLES は複数行をカンマ結合して正規化する。
        """
        result = dict(fallback_suno)  # フォールバックで初期化
        try:
            lines = text.strip().splitlines()
            current_field = None
            buf = []
            for line in lines:
                stripped = line.strip()
                if stripped.upper().startswith("LYRICS:"):
                    current_field = 'lyrics'
                    rest = stripped[7:].strip()
                    buf = [rest] if rest else []
                elif stripped.upper().startswith("STYLES:"):
                    if current_field == 'lyrics':
                        # LYRICS は改行を保持して結合
                        result['lyrics'] = '\n'.join(buf).strip()
                    current_field = 'styles'
                    rest = stripped[7:].strip()
                    buf = [rest] if rest else []
                elif stripped.upper().startswith("TITLE:"):
                    if current_field == 'styles':
                        # STYLES は複数行をカンマで結合し、重複カンマを整理
                        styles_raw = ', '.join(buf).strip()
                        result['styles'] = self._normalize_styles(styles_raw)
                    current_field = 'title'
                    rest = stripped[6:].strip()
                    buf = [rest] if rest else []
                elif stripped:
                    buf.append(stripped)

            # 最後のフィールドをフラッシュ
            if current_field == 'title':
                result['title'] = ' '.join(buf).strip()
            elif current_field == 'styles':
                styles_raw = ', '.join(buf).strip()
                result['styles'] = self._normalize_styles(styles_raw)
            elif current_field == 'lyrics':
                result['lyrics'] = '\n'.join(buf).strip()

        except Exception as e:
            logger.warning(f"Gemini response parse error: {e}")
        return result

    @staticmethod
    def _normalize_styles(styles_raw: str) -> str:
        """
        Stylesテキストを正規化する。

        - 重複カンマ・余分なスペースを除去
        - 200文字を超えた場合は末尾を切り捨て

        Args:
            styles_raw (str): 未整形のStyles文字列

        Returns:
            str: 正規化後のStyles文字列（最大200文字）
        """
        tokens = [t.strip() for t in styles_raw.split(',') if t.strip()]
        result = ', '.join(tokens)
        if len(result) > 200:
            result = result[:200]
            logger.warning("Gemini Styles hard-truncated to 200 chars")
        return result

    def _generate_gemini(self, current: Dict, energy_target: Optional[int],
                          preferred_genre: Optional[str], vocal: bool,
                          strategy: 'EnergyStrategy', strategy_reasoning: str) -> Dict:
        """
        Gemini API でプロンプトを生成。失敗時はルールベースにフォールバック。

        修正: _generate_rule_based() の戻り値から Camelot 情報を再利用し、
        重複計算を排除。
        """
        # まずルールベースで骨格を作る（フォールバック兼ねる）
        rule_result = self._generate_rule_based(
            current, energy_target, preferred_genre, vocal,
            strategy, strategy_reasoning, is_fallback=False
        )

        # ルールベース結果から Camelot 情報を再利用（重複計算を排除）
        camelot_info = rule_result.get('camelot', {})
        compatible_keys = camelot_info.get('compatible', [])

        prompt_text = self._build_gemini_prompt(
            current=current,
            strategy=strategy,
            strategy_reasoning=strategy_reasoning,
            next_genre=rule_result['parameters']['genre'],
            next_bpm=rule_result['parameters']['bpm'],
            next_energy=rule_result['parameters']['energy_numeric'],
            compatible_keys=compatible_keys,
            vocal=vocal,
            base_lyrics=rule_result['suno']['lyrics']
        )

        try:
            # 新 SDK (google.genai) と旧 SDK (google.generativeai) で API 呼び出し方が異なる
            if _GENAI_NEW:
                response = self._genai_client.models.generate_content(
                    model=self.gemini_model,
                    contents=prompt_text
                )
                raw_text = response.text
                # 新 SDK のトークン情報
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    m = response.usage_metadata
                    self.token_usage.add(
                        getattr(m, 'prompt_token_count', 0),
                        getattr(m, 'candidates_token_count', 0)
                    )
            else:
                # 旧 SDK フォールバック
                response = self.gemini_model.generate_content(prompt_text)
                raw_text = response.text
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    m = response.usage_metadata
                    self.token_usage.add(
                        getattr(m, 'prompt_token_count', 0),
                        getattr(m, 'candidates_token_count', 0)
                    )

            logger.debug(f"Gemini raw response:\n{raw_text}")

            # parse して suno フィールドを上書き
            suno_dict = self._parse_gemini_response(raw_text, rule_result['suno'])
            rule_result['suno'] = suno_dict
            rule_result['prompt'] = suno_dict.get('styles', rule_result['prompt'])
            rule_result['source'] = 'gemini'
            logger.info(f"Gemini generation OK: '{suno_dict.get('title', '')}' | quota remaining: {self.quota.remaining}")

        except Exception as e:
            err_str = str(e)
            err_type = classify_error(err_str)
            if err_type == ErrorType.RESOURCE_EXHAUSTED:
                self.quota.mark_exhausted()
                logger.warning("Gemini quota exhausted, switching to rule-based")
            else:
                logger.warning(f"Gemini API error ({err_type.value}): {e}")
            # エラーをセッション統計に記録
            self.session_stats['errors'].append({
                'type': err_type.value,
                'message': err_str,
                'timestamp': time.time()
            })
            rule_result['source'] = 'rule_based_fallback'
            self.session_stats['fallback_calls'] += 1

        return rule_result

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
        3. BPM調整（整数丸め）
        4. Camelot相性を考慮したキー選択
        5. Sunoプロンプト構築
        6. 統計更新
        7. 結果構築

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

        # Camelot変換（現在のトラック）
        current_camelot = self.camelot_wheel.to_camelot(current_key)

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

        # 3. BPM調整（整数丸め: Suno UIに貼り付ける値を一致させる）
        next_bpm = self._adjust_bpm(current_bpm, strategy)

        # 4. Camelot相性を考慮したキー選択
        compatible_keys = self.camelot_wheel.get_compatible_keys(current_camelot)

        # 5. Sunoプロンプト構築
        suno_prompt = self.suno_builder.build_suno_prompt(
            genre=next_genre,
            bpm=next_bpm,
            key=current_key,
            energy_level=next_energy_numeric,
            strategy=strategy,
            vocal=vocal
        )

        # 6. 統計更新
        if is_fallback:
            self.session_stats['fallback_calls'] += 1
        else:
            self.session_stats['rule_based_calls'] += 1

        # 7. 結果構築
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
            'reasoning': self._build_reasoning_ja(
                current_genre, next_genre, current_bpm, next_bpm,
                current_energy, next_energy_numeric, strategy, strategy_reasoning,
                current_camelot, compatible_keys
            ),
            'source': 'fallback' if is_fallback else 'rule_based',
            'detected_strategy': strategy.value,
            'camelot': {
                'current': current_camelot,
                'compatible': compatible_keys,
            }
        }

    # ============================================================
    # 説明文生成（日本語）
    # ============================================================

    def _build_reasoning_ja(
        self,
        current_genre: str, next_genre: str,
        current_bpm: float, next_bpm: float,
        current_energy: int, next_energy: int,
        strategy: 'EnergyStrategy', strategy_reasoning: str,
        current_camelot: str, compatible_keys: list
    ) -> dict:
        """日本語でプロンプト生成理由を構築"""
        from .prompt_base import EnergyStrategy

        # エネルギーを整数に正規化（float が来ても安全に処理）
        current_energy = max(1, min(5, round(float(current_energy))))
        next_energy    = max(1, min(5, round(float(next_energy))))

        # ジャンル遷移の説明
        if current_genre == next_genre:
            genre_text = f"現在の「{current_genre}」を維持してグルーブを継続"
        else:
            genre_text = f"「{current_genre}」から「{next_genre}」へのジャンルトランジション"

        # BPM差の説明
        bpm_diff = next_bpm - current_bpm
        if abs(bpm_diff) < 1.0:
            bpm_text = f"BPM {next_bpm:.0f}（変化なし）"
        elif bpm_diff > 0:
            bpm_text = f"BPM {current_bpm:.0f} → {next_bpm:.0f}（+{bpm_diff:.0f}）"
        else:
            bpm_text = f"BPM {current_bpm:.0f} → {next_bpm:.0f}（{bpm_diff:.0f}）"

        # エネルギー変化の説明
        energy_labels = {1: "非常に弱", 2: "弱", 3: "中程度", 4: "強", 5: "最高潮"}
        e_cur = energy_labels.get(current_energy, str(current_energy))
        e_nxt = energy_labels.get(next_energy, str(next_energy))
        if current_energy == next_energy:
            energy_text = f"エネルギー {e_nxt}を維持"
        elif next_energy > current_energy:
            energy_text = f"エネルギー {e_cur} → {e_nxt}（ビルドアップ）"
        else:
            energy_text = f"エネルギー {e_cur} → {e_nxt}（ブレイク）"

        # 戦略の説明
        if strategy == EnergyStrategy.HYPNOTIC:
            strategy_text = "ミニマル/ヒプノティック・グルーブを維持"
        else:
            strategy_text = "EDM的・ビルドアップ→ドロップのエネルギー展開"

        # Camelotの説明
        if compatible_keys and len(compatible_keys) >= 3:
            camelot_text = (
                f"現在のキー: {current_camelot} / "
                f"推奨キー: {compatible_keys[0]}(同一)・"
                f"{compatible_keys[2]}(-1半音)・"
                f"{compatible_keys[3] if len(compatible_keys) > 3 else ''}"
            )
        else:
            camelot_text = f"現在のキー: {current_camelot}"

        return {
            'genre_transition': genre_text,
            'bpm': bpm_text,
            'energy': energy_text,
            'strategy': f"{strategy_text}（{strategy_reasoning}）",
            'camelot': camelot_text,
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
        BPMを調整し整数に丸めて返す

        Suno UIへの貼り付け値と parameters['bpm'] を一致させるため、
        round() で整数値（float型）に丸める。

        Hypnotic戦略: ±1の微調整
        Story戦略: ±3の範囲で変動

        Args:
            current_bpm (float): 現在のBPM
            strategy (EnergyStrategy): 戦略

        Returns:
            float: 調整後のBPM（整数丸め）
        """
        import random

        if strategy == EnergyStrategy.HYPNOTIC:
            delta = random.uniform(-1, 1)
        else:
            delta = random.uniform(-3, 3)

        # 整数丸め: Stylesの "{bpm:.0f} BPM" トークンと値を一致させる
        return float(round(current_bpm + delta))

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
                - errors (List[Dict]): エラーリスト（type/message/timestamp）
                - session_duration (float): セッション経過時間
                - quota_remaining (int): 残りクォータ
                - token_usage (Dict): トークン使用量
        """
        return {
            'rule_based_calls': self.session_stats['rule_based_calls'],
            'fallback_calls': self.session_stats['fallback_calls'],
            'errors': list(self.session_stats['errors']),  # コピーを返す
            'session_duration': time.time() - self.session_stats['start_time'],
            'quota_remaining': self.quota.remaining,
            'token_usage': {
                'input': self.token_usage.input_tokens,
                'output': self.token_usage.output_tokens,
                'total': self.token_usage.total_tokens,
            }
        }
