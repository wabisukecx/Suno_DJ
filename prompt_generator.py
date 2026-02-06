"""
プロンプト生成エンジン（Phase 9: Suno UI対応 & Context Aware AI完全版）
===================================================================

Suno UIフォーマット対応:
- lyrics: 楽曲構造の設計図（Instrumental/Vocal対応）
- styles: ジャンル、キーワード、スタイルタグ
- title: 曲タイトル

機能:
- Gemini 2.0 Flash API連携
- Context Aware Logic (文脈認識による戦略自動切り替え)
- Hypnotic Mode (ミニマル戦略) / Story Mode (ストーリー戦略)
- Instrumental生成時の強制ブラケット処理（歌唱防止）
- 無料枠管理 & 自動フォールバック
"""

import json
import os
import time
import logging
import re
import math
import statistics
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
import random
import threading

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Google Generative AI
GEMINI_AVAILABLE = False
genai = None

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
    import warnings
    warnings.filterwarnings('ignore', category=FutureWarning, module='google.generativeai')
except ImportError:
    logger.warning("google-generativeai not installed. Using rule-based mode.")


class GenerationMode(Enum):
    """プロンプト生成モード"""
    GEMINI = "gemini"
    RULE_BASED = "rule_based"
    FALLBACK = "fallback"


class EnergyStrategy(Enum):
    """エネルギー戦略"""
    STORY = "story"      # EDM的（ビルドアップ→ドロップ→ブレイク）- エネルギー変動大
    HYPNOTIC = "hypnotic" # ミニマル的（ループ維持、テクスチャ変化、没入感）- エネルギー維持


class ErrorType(Enum):
    """APIエラータイプ"""
    RESOURCE_EXHAUSTED = "resource_exhausted"
    OVERLOADED = "overloaded"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass
class TokenUsage:
    """トークン使用量追跡"""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    
    def add(self, input_t: int, output_t: int):
        self.input_tokens += input_t
        self.output_tokens += output_t
        self.total_tokens += input_t + output_t


@dataclass
class DailyQuota:
    """日次クォータ管理"""
    date: str = ""
    request_count: int = 0
    max_requests: int = 1500
    exhausted: bool = False
    
    def check_and_increment(self) -> bool:
        today = date.today().isoformat()
        if self.date != today:
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
        self.exhausted = True
        self.request_count = self.max_requests
        logger.warning(f"Daily quota exhausted! Switching to rule-based mode.")
    
    @property
    def remaining(self) -> int:
        return max(0, self.max_requests - self.request_count)


@dataclass
class DJStyleProfile:
    """DJスタイルプロファイル（EQ/Filter操作履歴）"""
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
        if value < 0.3 and self._prev_eq_high >= 0.3: self.eq_high_cuts += 1
        elif value > 0.7 and self._prev_eq_high <= 0.7: self.eq_high_boosts += 1
        self._prev_eq_high = value
    
    def record_eq_mid(self, value: float):
        if value < 0.3 and self._prev_eq_mid >= 0.3: self.eq_mid_cuts += 1
        elif value > 0.7 and self._prev_eq_mid <= 0.7: self.eq_mid_boosts += 1
        self._prev_eq_mid = value
    
    def record_eq_low(self, value: float):
        if value < 0.3 and self._prev_eq_low >= 0.3: self.eq_low_cuts += 1
        elif value > 0.7 and self._prev_eq_low <= 0.7: self.eq_low_boosts += 1
        self._prev_eq_low = value
    
    def record_filter(self, value: float):
        if value < 0.4 and self._prev_filter >= 0.4: self.filter_hpf_uses += 1
        elif value > 0.6 and self._prev_filter <= 0.6: self.filter_lpf_uses += 1
        self._prev_filter = value
    
    def analyze_tendencies(self) -> Dict[str, Any]:
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
        if high_balance > 2: style['atmosphere'] = 'bright'
        elif high_balance < -2: style['atmosphere'] = 'dark'
        else: style['atmosphere'] = 'balanced'
        
        # 展開の派手さ判定 (Filter多用 = Dynamic)
        total_filter = self.filter_hpf_uses + self.filter_lpf_uses
        if total_filter > 8 or (total_eq_ops > 0 and (total_filter / total_eq_ops) > 0.5):
            style['build_preference'] = 'dynamic'
        else:
            style['build_preference'] = 'subtle'
        
        return style


@dataclass
class EnergyHistoryEntry:
    """エネルギー履歴エントリ"""
    track_name: str
    energy_level: int
    genre: str
    bpm: float
    key: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class SunoPrompt:
    """Suno UI形式のプロンプト"""
    lyrics: str = ""
    styles: str = ""
    title: str = ""
    genre: str = ""
    bpm: float = 0.0
    key: str = ""
    energy_level: int = 3
    
    def to_dict(self) -> Dict:
        return {
            'lyrics': self.lyrics, 'styles': self.styles, 'title': self.title,
            'genre': self.genre, 'bpm': self.bpm, 'key': self.key, 'energy_level': self.energy_level
        }


class PromptGenerator:
    """
    プロンプト生成クラス（Suno UI対応版 + Context Logic）
    """
    
    SUNO_SECTION_BLUEPRINTS = {
        # --- Hypnotic / Minimal Styles (歌唱防止のため全て[]で囲む) ---
        "Minimal Techno": [
            "[Intro - 64bars - Stripped]",
            "[Deep pulsing bassline enters]",
            "[Main Groove - Layer 1]",
            "[Filtered synth melody begins]",
            "[Main Groove - Layer 2]",
            "[Add Percussion: Shaker and Ride]",
            "[Subtle Modulation Phase]",
            "[Filter adjustments and delay changes]",
            "[Main Groove - Hypnotic]",
            "[Continuous bassline and drum groove]",
            "[Minimal Breakdown]",
            "[Bassline drops out momentarily]",
            "[Atmospheric textures only]",
            "[Main Groove - Re-entry]",
            "[Bassline returns with force]",
            "[Outro - 64bars]",
            "[Synth melody fades out gradually]",
            "[Reverb increases]",
        ],
        "Dub Techno": [
            "[Intro - Atmosphere]",
            "[Tape Hiss and Static Noise]",
            "[Chord Stab - Entry]",
            "[Deep Echoes and Delay]",
            "[Main Groove - Deep]",
            "[Sub Bass focus]",
            "[Modulation Phase]",
            "[Space Expanding with Reverb]",
            "[Breakdown]",
            "[Delay Feedback Loop]",
            "[Main Groove - Return]",
            "[Full Texture]",
            "[Outro - Fade]",
            "[Fade into Noise]",
        ],
        "Deep Tech": [
            "[Intro - 32bars]",
            "[Minimal texture]",
            "[Groove A - Minimal]",
            "[Tight Kick and Bass]",
            "[Groove B - Rolling Bass]",
            "[Add Closed Hats]",
            "[Transition]",
            "[Texture Change and Filter Open]",
            "[Groove C - Full]",
            "[Driving Rhythm]",
            "[Outro - Loop Friendly]",
            "[Remove elements one by one]"
        ],
        
        # --- Standard / Story Styles ---
        "Progressive House": [
            "[Intro - Extended]",
            "[Main Groove - Hypnotic]",
            "[Layering Phase - Gradual]",
            "[Middle Section - Breath]",
            "[Breakdown - Long Journey]",
            "[Build - Emotional Rise]",
            "[True Climax - Euphoric Drop]",
            "[Outro - DJ Friendly]",
        ],
        "Trance": [
            "[Intro - Atmospheric]",
            "[Main Theme - Driving]",
            "[The Breakdown - Extended 64 bars]",
            "[Build - Tension Rising]",
            "[True Climax - Hands Up Drop]",
            "[Outro - Floating]",
        ],
        "Techno": [
            "[Intro - Industrial Atmosphere]",
            "[Main Loop - Pounding]",
            "[Break - Mechanical Silence]",
            "[Build - Rising Tension]",
            "[Drop - Harder]",
            "[Outro - Utility DJ Tool]",
        ],
        "House": [
            "[Intro - Four on the Floor]",
            "[Main Groove - Classic]",
            "[Vocal Hook - Catchy]",
            "[Breakdown - Piano Chords]",
            "[Build - Uplifting]",
            "[Drop - Feel Good]",
            "[Outro - DJ Tool]",
        ],
    }
    
    def __init__(self, knowledge_base_path: str = None, api_key: str = None):
        # 知識ベース読み込み
        if knowledge_base_path is None:
            current_dir = Path(__file__).parent
            knowledge_base_path = current_dir / "knowledge_base.json"
        
        if os.path.exists(knowledge_base_path):
            with open(knowledge_base_path, 'r', encoding='utf-8') as f:
                self.kb = json.load(f)
        else:
            logger.warning("knowledge_base.json not found. Using internal fallback.")
            self.kb = {'genres': {}, 'transitions': {'energy_progression': {}}}
        
        # Gemini API設定
        self.api_key = api_key or os.environ.get('GEMINI_API_KEY', '')
        self.model = None
        self._init_gemini()
        
        # クォータ管理
        self.quota = DailyQuota()
        self.token_usage = TokenUsage()
        
        # 状態管理
        self.energy_history: List[EnergyHistoryEntry] = []
        self.max_history = 20
        self.dj_style = DJStyleProfile()
        
        # 現在の戦略（自動判定）
        self.strategy = EnergyStrategy.STORY
        self.strategy_reasoning = ""
        
        self._lock = threading.Lock()
        
        self.session_stats = {
            'gemini_calls': 0, 'rule_based_calls': 0, 'fallback_calls': 0,
            'errors': [], 'start_time': time.time()
        }
        
        logger.info(f"PromptGenerator initialized. Mode: {'GEMINI' if self.model else 'RULE_BASED'}")
    
    def _init_gemini(self):
        if not GEMINI_AVAILABLE or not self.api_key: return
        try:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel(
                model_name='gemini-2.0-flash',
                generation_config={'temperature': 1.0, 'max_output_tokens': 1024}
            )
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
            self.model = None
    
    def generate_prompt(
        self,
        current_track_analysis: Dict,
        deck_a_analysis: Optional[Dict] = None,
        deck_b_analysis: Optional[Dict] = None,
        energy_target: Optional[int] = None,
        preferred_genre: Optional[str] = None,
        vocal: bool = False
    ) -> Dict:
        """
        Suno UI形式でプロンプトを生成
        
        戦略（Strategy）は履歴と操作ログから自動判定されます。
        """
        start_time = time.time()
        
        # 1. 履歴更新
        self._add_to_energy_history(current_track_analysis)
        
        # 2. コンテキスト分析と戦略自動決定
        self.strategy, self.strategy_reasoning = self._analyze_context(current_track_analysis)
        logger.info(f"Detected Strategy: {self.strategy.value} ({self.strategy_reasoning})")
        
        mode = self._determine_mode()
        
        try:
            if mode == GenerationMode.GEMINI:
                result = self._generate_with_gemini(
                    current_track_analysis, deck_a_analysis, deck_b_analysis,
                    energy_target, preferred_genre, vocal
                )
            else:
                result = self._generate_rule_based(
                    current_track_analysis, energy_target, preferred_genre, vocal=vocal
                )
            
            result['generation_time'] = time.time() - start_time
            result['mode'] = mode.value
            result['strategy'] = self.strategy.value
            result['quota_remaining'] = self.quota.remaining
            
            return result
            
        except Exception as e:
            logger.error(f"Prompt generation failed: {e}", exc_info=True)
            return self._generate_rule_based(
                current_track_analysis, energy_target, preferred_genre, 
                vocal=vocal, is_fallback=True
            )

    def _analyze_context(self, current: Dict) -> Tuple[EnergyStrategy, str]:
        """コンテキスト（履歴、エナジーフロー、DJ操作）を分析して戦略を決定する"""
        if len(self.energy_history) < 2:
            return EnergyStrategy.STORY, "Initial track"

        reasoning_parts = []
        
        # --- A. エナジーフロー分析 ---
        recent = self.energy_history[-3:]
        energies = [e.energy_level for e in recent]
        variance = 1.0
        if len(energies) > 1:
            mean = sum(energies) / len(energies)
            variance = sum((x - mean) ** 2 for x in energies) / len(energies)
            
        is_flat_energy = variance < 0.3
        is_rising = energies[-1] > energies[0]
        
        # --- B. DJ操作スタイル分析 ---
        style = self.dj_style.analyze_tendencies()
        is_dynamic_ops = style.get('build_preference') == 'dynamic'
        
        # --- C. ジャンルの一貫性 ---
        current_genre = current.get('genre', '')
        minimal_keywords = ['Minimal', 'Dub', 'Deep', 'Tech', 'Ambient']
        is_minimal_genre = any(k in current_genre for k in minimal_keywords)
        
        # === 判定ロジック ===
        if is_minimal_genre and not is_dynamic_ops:
            reasoning_parts.append(f"Minimal genre detected ({current_genre})")
            if is_flat_energy: reasoning_parts.append("Maintaining steady groove")
            return EnergyStrategy.HYPNOTIC, " / ".join(reasoning_parts)
            
        if is_flat_energy and not is_dynamic_ops:
            reasoning_parts.append("Flat energy flow detected")
            reasoning_parts.append("Subtle mixing style")
            return EnergyStrategy.HYPNOTIC, " / ".join(reasoning_parts)
            
        if is_rising:
            reasoning_parts.append("Energy is rising")
            return EnergyStrategy.STORY, " / ".join(reasoning_parts)
            
        if is_dynamic_ops:
            reasoning_parts.append("Dynamic filtering detected")
            return EnergyStrategy.STORY, " / ".join(reasoning_parts)
            
        return EnergyStrategy.STORY, "Standard progression"
    
    def _determine_mode(self) -> GenerationMode:
        if not self.model: return GenerationMode.RULE_BASED
        if self.quota.exhausted: return GenerationMode.RULE_BASED
        if not self.quota.check_and_increment(): return GenerationMode.RULE_BASED
        return GenerationMode.GEMINI
    
    def _generate_with_gemini(
        self,
        current: Dict,
        deck_a: Optional[Dict],
        deck_b: Optional[Dict],
        energy_target: Optional[int],
        preferred_genre: Optional[str],
        vocal: bool = False
    ) -> Dict:
        """Gemini APIでプロンプト生成"""
        
        context = self._build_gemini_context_suno(
            current, deck_a, deck_b, energy_target, preferred_genre, vocal
        )
        
        try:
            response = self.model.generate_content(context, request_options={'timeout': 30})
            
            if hasattr(response, 'usage_metadata'):
                usage = response.usage_metadata
                self.token_usage.add(getattr(usage, 'prompt_token_count', 0), getattr(usage, 'candidates_token_count', 0))
            
            result = self._parse_gemini_response_suno(response.text, current, vocal)
            self.session_stats['gemini_calls'] += 1
            return result
            
        except Exception as e:
            error_type = self._classify_error(e)
            self._handle_api_error(error_type, e)
            return self._generate_rule_based(current, energy_target, preferred_genre, vocal=vocal, is_fallback=True)
    
    def _build_gemini_context_suno(self, current: Dict, deck_a: Optional[Dict], deck_b: Optional[Dict], energy_target: Optional[int], preferred_genre: Optional[str], vocal: bool) -> str:
        """Geminiコンテキスト構築"""
        
        current_genre = current.get('genre', 'Unknown')
        current_bpm = current.get('bpm', 120)
        current_key = current.get('key', 'Unknown')
        current_energy = current.get('energy', {}).get('numeric', 3)
        
        strategy_instruction = ""
        if self.strategy == EnergyStrategy.HYPNOTIC:
            strategy_instruction = (
                f"【AI分析: HYPNOTIC MODE (維持・没入戦略) が選択されました】\n"
                f"理由: {self.strategy_reasoning}\n"
                "- 派手な『ドロップ』や急激な『ビルドアップ』は厳禁です。\n"
                "- 『変化しないことの美学』を重視し、微細な音色の変化（フィルター開閉など）を指示してください。\n"
                "- 楽曲構造（lyrics欄）は [Main Groove] や [Loop] を長く保ち、急な展開を作らないこと。\n"
                "- スタイルタグには 'Hypnotic', 'Loop-based', 'Linear Progression', 'Subtle transitions' を含めてください。\n"
                "- エネルギーレベルは現状維持(Level {current_energy})か、微増にとどめてください。"
            )
        else:
            strategy_instruction = (
                f"【AI分析: STORY MODE (展開・ストーリー戦略) が選択されました】\n"
                f"理由: {self.strategy_reasoning}\n"
                "- エネルギーフローを考慮し、序盤は上げ、中盤はピーク維持、終盤は下げる展開を作ってください。\n"
                "- 明確なビルドアップとドロップを作成し、フロアを盛り上げてください。"
            )

        blueprint_rules = [
            "あなたは伝説的なDJ/プロデューサーです。",
            "回答はJSON形式のみで行ってください。",
            "",
            "【重要】Suno v5 において lyrics フィールドは楽曲構造の設計図です。",
            "- 【必須】構造タグは必ず6個以上含めること(最低限6個、推奨8-10個)",
            "- 各セクションには適切な小節数を指定すること(例: [Intro - 64bars])",
            "",
            "【重要】インストゥルメンタルの場合、歌詞欄の全ての行を [ ] で囲んでください。",
            "良い例: [Deep pulsing bassline] / 悪い例: Deep pulsing bassline (歌ってしまうため)",
            "",
        ]
        
        context_parts = blueprint_rules + [
            "",
            "## 現在のコンテキスト",
            f"- Current Track: {current_genre}, {current_bpm} BPM, Key: {current_key}, Energy: {current_energy}",
            f"- Set History Variance: {self.strategy_reasoning}", 
            "",
            "## 生成要求",
            strategy_instruction,
            "",
            "1. ハーモニックミキシングを考慮したキー選択",
            "2. BPMは±5BPM以内の変化が望ましい",
            "3. 時代考証(特に90s-00s)に基づいた音質指定",
            "4. reasoning（解説）フィールドの値は、必ず『日本語』で記述してください。",
        ]
        
        if vocal:
            context_parts.extend(["5. ボーカル入り楽曲として作成 (lyrics欄には歌詞を記述)"])
        else:
            context_parts.extend(["5. インストゥルメンタルとして作成 (lyrics欄は全てタグ化する)"])
        
        if preferred_genre:
            context_parts.append(f"6. 優先ジャンル: {preferred_genre}")
        
        context_parts.extend([
            "",
            "## 出力フォーマット（JSON）",
            "```json",
            "{",
            '  "lyrics": "[Intro - 64bars]\\n[Bassline enters]...",',
            '  "styles": "Genre, Tag1, Tag2, 128 BPM, Am",',
            '  "title": "Title",',
            '  "genre": "Genre",',
            '  "bpm": 128,',
            '  "key": "Am",',
            '  "energy_level": 3,',
            '  "reasoning": { "genre_transition": "...", "energy_strategy": "..." }',
            "}",
            "```"
        ])
        
        return "\n".join(context_parts)
    
    def _parse_gemini_response_suno(self, response_text: str, current: Dict, vocal: bool = False) -> Dict:
        try:
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            data = json.loads(json_match.group(1) if json_match else response_text)
            
            styles = data.get('styles', '')
            if not vocal and 'Instrumental' not in styles: styles = f"Instrumental, {styles}"
            elif vocal and 'Vocal' not in styles: styles = f"Vocal, {styles}"
            
            # --- ここで lyrics を整形 (インスト時のみ) ---
            lyrics = data.get('lyrics', '')
            if not vocal:
                lyrics = self._format_instrumental_structure(lyrics)
            
            suno_prompt = SunoPrompt(
                lyrics=lyrics,
                styles=styles,
                title=data.get('title', ''),
                genre=data.get('genre', current.get('genre', 'House')),
                bpm=float(data.get('bpm', current.get('bpm', 125))),
                key=data.get('key', current.get('key', 'C')),
                energy_level=int(data.get('energy_level', 3))
            )
            
            return {
                'suno': suno_prompt.to_dict(),
                'prompt': suno_prompt.styles,
                'parameters': {
                    'genre': suno_prompt.genre, 'bpm': suno_prompt.bpm,
                    'key': suno_prompt.key, 'energy_level': self._numeric_to_energy_level(suno_prompt.energy_level),
                    'energy_numeric': suno_prompt.energy_level
                },
                'reasoning': data.get('reasoning', {}),
                'source': 'gemini',
                'detected_strategy': self.strategy.value
            }
        except Exception as e:
            logger.warning(f"Failed to parse Gemini response: {e}")
            return self._generate_rule_based(current, vocal=vocal, is_fallback=True)
            
    def _generate_rule_based(self, current: Dict, energy_target: Optional[int], preferred_genre: Optional[str], vocal: bool, is_fallback: bool = False) -> Dict:
        """ルールベース生成"""
        
        current_genre = current.get('genre', 'House')
        current_energy = current.get('energy', {}).get('numeric', 3)
        
        # 1. ジャンル選択
        if preferred_genre:
            next_genre = preferred_genre
        elif self.strategy == EnergyStrategy.HYPNOTIC:
            hypnotic_pool = ["Minimal Techno", "Dub Techno", "Deep Tech", "Deep House"]
            if current_genre in hypnotic_pool and random.random() < 0.7:
                next_genre = current_genre
            else:
                next_genre = random.choice(hypnotic_pool)
        else:
            transitions = self.kb.get('transitions', {}).get('energy_progression', {})
            if energy_target and energy_target >= 4:
                next_genre = random.choice(transitions.get('peak', ['Techno', 'Trance']))
            else:
                next_genre = random.choice(transitions.get('building', ['Tech House', 'Progressive House']))

        # 2. エネルギー計算
        if self.strategy == EnergyStrategy.HYPNOTIC:
            next_energy_numeric = max(1, min(5, current_energy + random.choice([-1, 0, 0, 1])))
        else:
            target = energy_target if energy_target else min(5, current_energy + 1)
            next_energy_numeric = target
            
        next_energy_level = self._numeric_to_energy_level(next_energy_numeric)
        
        # 3. プロンプト構築
        blueprint = self.SUNO_SECTION_BLUEPRINTS.get(
            next_genre, 
            self.SUNO_SECTION_BLUEPRINTS.get("Techno" if self.strategy == EnergyStrategy.HYPNOTIC else "House")
        )
        lyrics = "\n".join(blueprint)
        
        style_parts = [next_genre, "Vocal" if vocal else "Instrumental"]
        if self.strategy == EnergyStrategy.HYPNOTIC:
            style_parts.extend(["Hypnotic", "Loop-based", "Minimalist"])
        if next_energy_numeric >= 4: style_parts.append("Raw")
        
        bpm = current.get('bpm', 120) + (random.uniform(-1, 1) if self.strategy == EnergyStrategy.HYPNOTIC else random.uniform(-3, 3))
        
        # --- ここで lyrics を整形 (ルールベースでも適用) ---
        if not vocal:
            lyrics = self._format_instrumental_structure(lyrics)

        suno_prompt = SunoPrompt(
            lyrics=lyrics, styles=", ".join(style_parts), title=f"AI Generated {next_genre}",
            genre=next_genre, bpm=bpm, key=current.get('key', 'C'), energy_level=next_energy_numeric
        )
        
        if is_fallback: self.session_stats['fallback_calls'] += 1
        else: self.session_stats['rule_based_calls'] += 1
        
        return {
            'suno': suno_prompt.to_dict(),
            'prompt': suno_prompt.styles,
            'parameters': {'genre': next_genre, 'bpm': bpm, 'key': suno_prompt.key, 'energy_level': next_energy_level, 'energy_numeric': next_energy_numeric},
            'reasoning': {
                'genre_transition': f"Auto-selected based on {self.strategy.value} strategy ({self.strategy_reasoning})",
                'energy_strategy': f"Strategy: {self.strategy.value}"
            },
            'source': 'fallback' if is_fallback else 'rule_based',
            'detected_strategy': self.strategy.value
        }
    
    def _build_suno_prompt(self, genre: str, bpm: float, key: str, energy_level: int, vocal: bool = False) -> SunoPrompt:
        """ヘルパー: Sunoプロンプトオブジェクト構築"""
        blueprint = self.SUNO_SECTION_BLUEPRINTS.get(
            genre,
            self.SUNO_SECTION_BLUEPRINTS.get("Techno" if self.strategy == EnergyStrategy.HYPNOTIC else "House")
        )
        lyrics = "\n".join(blueprint)
        
        # インスト時の強制フォーマット適用
        if not vocal:
            lyrics = self._format_instrumental_structure(lyrics)

        style_parts = [genre, "Vocal" if vocal else "Instrumental"]
        style_parts.append(f"{bpm:.0f} BPM")
        style_parts.append(key)
        
        title = self._generate_creative_title(genre, energy_level, key, bpm)
        
        return SunoPrompt(
            lyrics=lyrics, styles=", ".join(style_parts), title=title,
            genre=genre, bpm=bpm, key=key, energy_level=energy_level
        )

    def _format_instrumental_structure(self, lyrics_text: str) -> str:
        """インストの場合、全ての行が [] で囲まれているかチェックし、なければ補完する"""
        lines = lyrics_text.split('\n')
        formatted_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # 既に [] で囲まれている場合はそのまま
            if line.startswith('[') and line.endswith(']'):
                formatted_lines.append(line)
            else:
                # 囲まれていない場合は囲む
                formatted_lines.append(f"[{line}]")
        
        return "\n".join(formatted_lines)

    # === ヘルパーメソッド ===
    def _classify_error(self, error: Exception) -> ErrorType:
        s = str(error).lower()
        if '429' in s or 'quota' in s: return ErrorType.RESOURCE_EXHAUSTED
        if '503' in s or 'overloaded' in s: return ErrorType.OVERLOADED
        if 'timeout' in s: return ErrorType.TIMEOUT
        return ErrorType.UNKNOWN
    
    def _handle_api_error(self, type: ErrorType, error: Exception):
        self.session_stats['errors'].append({'type': type.value, 'msg': str(error), 'time': time.time()})
        if type == ErrorType.RESOURCE_EXHAUSTED: self.quota.mark_exhausted()
        self.session_stats['fallback_calls'] += 1
    
    def _numeric_to_energy_level(self, n: int) -> str:
        return {1: "Very Low", 2: "Low", 3: "Medium", 4: "High", 5: "Very High"}.get(n, "Medium")
        
    def _add_to_energy_history(self, analysis: Dict):
        entry = EnergyHistoryEntry(
            track_name=analysis.get('filename', 'Unknown'),
            energy_level=analysis.get('energy', {}).get('numeric', 3),
            genre=analysis.get('genre', 'House'),
            bpm=analysis.get('bpm', 120.0),
            key=analysis.get('key', 'C')
        )
        with self._lock:
            self.energy_history.append(entry)
            if len(self.energy_history) > self.max_history: self.energy_history.pop(0)

    # タイトル生成
    def _generate_creative_title(self, genre: str, energy_level: int, key: str, bpm: float) -> str:
        words = ["Groove", "Pulse", "Rhythm", "Signal", "Wave", "Motion", "Phase", "Loop"]
        adj = ["Deep", "Hypnotic", "Electric", "Dark", "Bright", "Raw", "Analog"]
        return f"{random.choice(adj)} {random.choice(words)}"
        
    def _generate_simple_lyrics(self, genre: str, energy_level: int) -> str:
        """ボーカル用簡易歌詞"""
        return "[Verse]\nFeel the rhythm\nIn the night\n[Chorus]\nDance with me\nTo the light"

    # 外部操作ログ
    def record_eq_operation(self, band: str, value: float):
        if band == 'high': self.dj_style.record_eq_high(value)
        elif band == 'mid': self.dj_style.record_eq_mid(value)
        elif band == 'low': self.dj_style.record_eq_low(value)
    
    def record_filter_operation(self, value: float):
        self.dj_style.record_filter(value)
        
    def get_session_stats(self) -> Dict:
        return {
            'gemini_calls': self.session_stats['gemini_calls'],
            'rule_based_calls': self.session_stats['rule_based_calls'],
            'total_tokens': self.token_usage.total_tokens,
            'current_strategy': self.strategy.value
        }
    
    def update_library_stats(self, filename: str): pass


if __name__ == "__main__":
    print("=" * 60)
    print("PromptGenerator Test (Auto-Bracket for Instrumental)")
    print("=" * 60)
    
    gen = PromptGenerator()
    
    # 1. 履歴注入（ミニマルモードを誘発）
    for _ in range(3):
        gen._add_to_energy_history({
            'filename': 'min.mp3', 'genre': 'Minimal Techno',
            'bpm': 128.0, 'key': 'Am', 'energy': {'numeric': 3}
        })
    
    # 2. 生成実行（インスト指定）
    result = gen.generate_prompt(
        {'genre': 'Minimal Techno', 'bpm': 128.0, 'key': 'Am', 'energy': {'numeric': 3}},
        vocal=False
    )
    
    print(f"\nDetected Strategy: {result.get('detected_strategy')}")
    print(f"Generated Style: {result['suno']['styles']}")
    print(f"\n--- Structure Blueprint (Auto-Bracketed) ---")
    print(result['suno']['lyrics'])