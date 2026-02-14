"""
Suno Prompt Builder Module
===========================

Phase 8L: Suno UI形式プロンプト生成

このモジュールは以下を提供します:
1. Lyrics生成（セクション構造テンプレート）
2. Styles生成（ジャンル、キーワード、BPM）
3. Title生成（クリエイティブタイトル）
4. 自動ブラケット処理（Instrumental時の歌唱防止）
"""

import random
import logging

from .prompt_base import SunoPrompt, EnergyStrategy

# ロギング設定
logger = logging.getLogger(__name__)


class SunoPromptBuilder:
    """
    Suno UI形式プロンプト生成クラス（Phase 8L完全版）
    
    Suno UIで使用する3つのフィールド（lyrics, styles, title）を生成します。
    Hypnotic/Story戦略に応じたセクション構造テンプレートを使用し、
    Instrumental時は自動的に全セクションを[]で囲んで歌唱を防止します。
    
    Phase 8L機能:
    - セクション構造テンプレート（8ジャンル対応）
    - Hypnotic/Story戦略別構造
    - 自動ブラケット処理（Instrumental時）
    - Vocal/Instrumental対応
    - クリエイティブタイトル生成
    
    Attributes:
        SUNO_SECTION_BLUEPRINTS (Dict): ジャンル別セクション構造テンプレート
    
    Example:
        >>> builder = SunoPromptBuilder()
        >>> prompt = builder.build_suno_prompt(
        ...     genre="Techno",
        ...     bpm=130.0,
        ...     key="Am",
        ...     energy_level=4,
        ...     strategy=EnergyStrategy.STORY,
        ...     vocal=False
        ... )
        >>> print(prompt.lyrics[:50])
        [Intro - Industrial Atmosphere]
        >>> print(prompt.styles)
        Techno, Instrumental, 130 BPM, Am
    """
    
    def __init__(self):
        """SunoPromptBuilderを初期化"""
        # セクション構造テンプレートの定義
        self.SUNO_SECTION_BLUEPRINTS = {
            # ============================================================
            # Hypnotic / Minimal Styles（歌唱防止のため全て[]で囲む）
            # ============================================================
            
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
            
            # ============================================================
            # Standard / Story Styles
            # ============================================================
            
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
            
            # デフォルトテンプレート（Deep House）
            "Deep House": [
                "[Intro - Warm Pads]",
                "[Main Groove - Deep Bass]",
                "[Vocal Sample - Soulful]",
                "[Breakdown - Rhodes Piano]",
                "[Build - Rising Energy]",
                "[Drop - Groove Returns]",
                "[Outro - Smooth Transition]",
            ],
        }
    
    # ============================================================
    # Phase 8L: メインプロンプト構築
    # ============================================================
    
    def build_suno_prompt(
        self,
        genre: str,
        bpm: float,
        key: str,
        energy_level: int,
        strategy: EnergyStrategy,
        vocal: bool = False
    ) -> SunoPrompt:
        """
        Suno UI形式プロンプトを構築
        
        3つのフィールド（lyrics, styles, title）を生成し、
        SunoPromptオブジェクトとして返します。
        
        Args:
            genre (str): ジャンル名
            bpm (float): BPM
            key (str): キー（例: "Am", "C", "F#m"）
            energy_level (int): エネルギーレベル（1-5）
            strategy (EnergyStrategy): 戦略（HYPNOTIC/STORY）
            vocal (bool): Vocalモードかどうか（デフォルト: False）
        
        Returns:
            SunoPrompt: 生成されたプロンプト
        
        Example:
            >>> builder = SunoPromptBuilder()
            >>> prompt = builder.build_suno_prompt(
            ...     genre="Minimal Techno",
            ...     bpm=125.0,
            ...     key="Am",
            ...     energy_level=3,
            ...     strategy=EnergyStrategy.HYPNOTIC,
            ...     vocal=False
            ... )
            >>> print(prompt.lyrics.count('['))  # 全てブラケット化
            18
            >>> print("Instrumental" in prompt.styles)
            True
        """
        # 1. Lyrics構築
        lyrics = self._build_lyrics(genre, strategy, vocal)
        
        # 2. Styles構築
        styles = self._build_styles(genre, bpm, key, energy_level, strategy, vocal)
        
        # 3. Title生成
        title = self._generate_creative_title(genre, energy_level, key, bpm)
        
        # 4. SunoPromptオブジェクト作成
        return SunoPrompt(
            lyrics=lyrics,
            styles=styles,
            title=title,
            genre=genre,
            bpm=bpm,
            key=key,
            energy_level=energy_level
        )
    
    # ============================================================
    # Phase 8L: Lyrics構築
    # ============================================================
    
    def _build_lyrics(
        self,
        genre: str,
        strategy: EnergyStrategy,
        vocal: bool
    ) -> str:
        """
        Lyrics構築（セクション構造選択）
        
        ジャンルと戦略に応じたセクション構造テンプレートを選択し、
        Instrumental時は自動的にブラケット処理を行います。
        
        Args:
            genre (str): ジャンル名
            strategy (EnergyStrategy): 戦略（HYPNOTIC/STORY）
            vocal (bool): Vocalモードかどうか
        
        Returns:
            str: 生成されたLyrics
        
        Example:
            >>> builder = SunoPromptBuilder()
            >>> lyrics = builder._build_lyrics(
            ...     genre="Techno",
            ...     strategy=EnergyStrategy.STORY,
            ...     vocal=False
            ... )
            >>> lyrics.startswith('[Intro')
            True
        """
        # セクション構造テンプレートを選択
        blueprint = self.SUNO_SECTION_BLUEPRINTS.get(genre)
        
        # ジャンルが見つからない場合はフォールバック
        if blueprint is None:
            # Hypnotic戦略ならMinimal系、Story戦略ならHouse系
            fallback_genre = "Minimal Techno" if strategy == EnergyStrategy.HYPNOTIC else "House"
            blueprint = self.SUNO_SECTION_BLUEPRINTS.get(fallback_genre)
            logger.debug(f"Genre '{genre}' not found, using '{fallback_genre}' template")
        
        # Lyricsを結合
        lyrics = "\n".join(blueprint)
        
        # Instrumental時は自動ブラケット処理
        if not vocal:
            lyrics = self._format_instrumental_structure(lyrics)
        
        return lyrics
    
    # ============================================================
    # Phase 8L: 自動ブラケット処理
    # ============================================================
    
    def _format_instrumental_structure(self, lyrics_text: str) -> str:
        """
        Instrumental時の自動ブラケット処理
        
        全ての行が[]で囲まれているかチェックし、
        囲まれていない行は自動的に[]で囲みます。
        これにより、Suno AIがInstrumentalを歌唱してしまうのを防ぎます。
        
        Args:
            lyrics_text (str): 元のLyrics文字列
        
        Returns:
            str: ブラケット処理後のLyrics
        
        Example:
            >>> builder = SunoPromptBuilder()
            >>> lyrics = "Intro\\n[Main Groove]\\nOutro"
            >>> result = builder._format_instrumental_structure(lyrics)
            >>> result
            '[Intro]\\n[Main Groove]\\n[Outro]'
        """
        lines = lyrics_text.split('\n')
        formatted_lines = []
        
        for line in lines:
            line = line.strip()
            
            # 空行はスキップ
            if not line:
                continue
            
            # 既に[]で囲まれている場合はそのまま
            if line.startswith('[') and line.endswith(']'):
                formatted_lines.append(line)
            else:
                # 囲まれていない場合は囲む
                formatted_lines.append(f"[{line}]")
        
        return "\n".join(formatted_lines)
    
    # ============================================================
    # Phase 8L: Styles構築
    # ============================================================
    
    def _build_styles(
        self,
        genre: str,
        bpm: float,
        key: str,
        energy_level: int,
        strategy: EnergyStrategy,
        vocal: bool
    ) -> str:
        """
        Styles構築（ジャンル、キーワード、BPM）
        
        Suno UIのStylesフィールドに設定する文字列を生成します。
        戦略（Hypnotic/Story）とエネルギーレベルに応じたキーワードを追加します。
        
        Args:
            genre (str): ジャンル名
            bpm (float): BPM
            key (str): キー
            energy_level (int): エネルギーレベル（1-5）
            strategy (EnergyStrategy): 戦略（HYPNOTIC/STORY）
            vocal (bool): Vocalモードかどうか
        
        Returns:
            str: Styles文字列（カンマ区切り）
        
        Example:
            >>> builder = SunoPromptBuilder()
            >>> styles = builder._build_styles(
            ...     genre="Minimal Techno",
            ...     bpm=125.0,
            ...     key="Am",
            ...     energy_level=3,
            ...     strategy=EnergyStrategy.HYPNOTIC,
            ...     vocal=False
            ... )
            >>> "Hypnotic" in styles
            True
            >>> "Instrumental" in styles
            True
        """
        style_parts = []
        
        # 1. ジャンル
        style_parts.append(genre)
        
        # 2. Vocal/Instrumental
        style_parts.append("Vocal" if vocal else "Instrumental")
        
        # 3. BPM
        style_parts.append(f"{bpm:.0f} BPM")
        
        # 4. キー
        style_parts.append(key)
        
        # 5. 戦略別キーワード
        if strategy == EnergyStrategy.HYPNOTIC:
            style_parts.extend(["Hypnotic", "Loop-based", "Minimalist"])
        
        # 6. エネルギーレベル別キーワード
        if energy_level >= 4:
            style_parts.append("Raw")
        
        return ", ".join(style_parts)
    
    # ============================================================
    # Phase 8L: クリエイティブタイトル生成
    # ============================================================
    
    def _generate_creative_title(
        self,
        genre: str,
        energy_level: int,
        key: str,
        bpm: float
    ) -> str:
        """
        クリエイティブタイトル生成
        
        形容詞と名詞をランダムに組み合わせて、
        クリエイティブな楽曲タイトルを生成します。
        
        Args:
            genre (str): ジャンル名
            energy_level (int): エネルギーレベル（1-5）
            key (str): キー
            bpm (float): BPM
        
        Returns:
            str: 生成されたタイトル
        
        Example:
            >>> builder = SunoPromptBuilder()
            >>> title = builder._generate_creative_title(
            ...     genre="Techno",
            ...     energy_level=4,
            ...     key="Am",
            ...     bpm=130.0
            ... )
            >>> len(title.split()) == 2  # "形容詞 名詞" の形式
            True
        """
        # 形容詞プール
        adjectives = [
            "Deep", "Hypnotic", "Electric", "Dark", "Bright",
            "Raw", "Analog", "Cosmic", "Midnight", "Neon",
            "Digital", "Underground"
        ]
        
        # 名詞プール
        nouns = [
            "Groove", "Pulse", "Rhythm", "Signal", "Wave",
            "Motion", "Phase", "Loop", "Drive", "Journey",
            "Dreams", "Ritual"
        ]
        
        # ランダムに組み合わせ
        adj = random.choice(adjectives)
        noun = random.choice(nouns)
        
        return f"{adj} {noun}"
