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

# Stylesフィールドの最大文字数（Suno UI仕様）
_STYLES_MAX_CHARS = 200


class SunoPromptBuilder:
    """
    Suno UI形式プロンプト生成クラス（Phase 8L完全版）

    Suno UIで使用する3つのフィールド（lyrics, styles, title）を生成します。
    Hypnotic/Story戦略に応じたセクション構造テンプレートを使用し、
    Instrumental時は自動的に全セクションを[]で囲んで歌唱を防止します。

    Phase 8L機能:
    - セクション構造テンプレート（9ジャンル対応）
    - Hypnotic/Story戦略別構造
    - 自動ブラケット処理（Instrumental時）
    - Vocal/Instrumental対応
    - クリエイティブタイトル生成
    - Styles 200文字上限チェック（Suno UI仕様準拠）

    Class Attributes:
        SUNO_SECTION_BLUEPRINTS (Dict): ジャンル別セクション構造テンプレート
        GENRE_STYLE_KEYWORDS (Dict): ジャンル別スタイルキーワード辞書
        ENERGY_KEYWORDS (Dict): エネルギー別キーワード
        HYPNOTIC_KEYWORDS (List): Hypnotic戦略キーワード
        STORY_KEYWORDS (List): Story戦略キーワード
        TITLE_VOCAB (Dict): ジャンル別タイトル語彙

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
        [Intro 16 bars]
        >>> print(prompt.styles)
        Techno, Dark, Industrial, Pounding, ...
    """

    # ============================================================
    # クラス変数: セクション構造テンプレート
    # ============================================================

    SUNO_SECTION_BLUEPRINTS = {

        "Minimal Techno": [
            "[Intro 16 bars]",
            "[sparse kick, low-pass filter almost closed]",
            "[sub bass pulse fading in]",
            "[Groove A 32 bars]",
            "[tight kick and closed hats locked in]",
            "[single repeating synth motif, cold and mechanical]",
            "[filter opening slowly over 16 bars]",
            "[Groove B 32 bars]",
            "[second percussive layer added, shaker enters]",
            "[modular synth texture weaving underneath]",
            "[Breakdown 16 bars]",
            "[kick drops out, reverb tails expand]",
            "[isolated synth loop, spacious and hypnotic]",
            "[Groove C 32 bars]",
            "[full groove returns, kick harder]",
            "[filter sweeping, layered metallic percussion]",
            "[Outro 16 bars]",
            "[elements dropping one by one]",
            "[low-pass filter closing back down]",
        ],

        "Dub Techno": [
            "[Intro 16 bars]",
            "[tape hiss and static, deep reverb atmosphere]",
            "[sub bass drone entering slowly]",
            "[Groove A 32 bars]",
            "[chord stabs with heavy tape delay]",
            "[kick muffled, dub-processed, Detroit warmth]",
            "[delay feedback bleeding into the mix]",
            "[Modulation Phase 32 bars]",
            "[reverb room expanding, chords smearing into texture]",
            "[hi-pass filter isolating mid frequencies]",
            "[Breakdown 16 bars]",
            "[only delay feedback loops remain]",
            "[cavernous space, almost silent]",
            "[Groove B 32 bars]",
            "[full groove returns with sub bass leading]",
            "[chord stabs denser, reverb tails cascading]",
            "[Outro 16 bars]",
            "[elements dissolving into noise and hiss]",
        ],

        "Deep Tech": [
            "[Intro 16 bars]",
            "[minimal kick, dry and tight]",
            "[bass groove barely audible, teasing]",
            "[Groove A 24 bars]",
            "[rolling bassline locked with kick]",
            "[closed hats adding texture, understated]",
            "[Groove B 32 bars]",
            "[filter opening, mid-range groove emerging]",
            "[subtle percussive layers building density]",
            "[Transition 8 bars]",
            "[filter sweep up, tension building]",
            "[Groove C 32 bars]",
            "[full groove, driving rhythm, afterhours energy]",
            "[acid line weaving through the mix]",
            "[Outro 16 bars]",
            "[elements stripping back one by one]",
            "[kick alone, then silence]",
        ],

        "Progressive House": [
            "[Intro 16 bars]",
            "[warm pads rising slowly, low-pass filter closed]",
            "[kick enters softly, four on the floor]",
            "[Groove A 32 bars]",
            "[bassline rolling, melodic synth motif introduced]",
            "[filter gradually opening, energy building]",
            "[layers adding, strings or pads thickening]",
            "[Breakdown 32 bars]",
            "[kick drops, only pads and melody remain]",
            "[emotional build, reverb expanding]",
            "[snare roll entering, tension rising]",
            "[Build 16 bars]",
            "[synth stabs rising, filter sweep upward]",
            "[anticipation at peak, crowd energy rising]",
            "[Drop 32 bars]",
            "[full kick returns, euphoric release]",
            "[bassline and melody together, dancefloor peak]",
            "[Outro 16 bars]",
            "[filter closing slowly, DJ-friendly tail]",
        ],

        "Trance": [
            "[Intro 16 bars]",
            "[atmospheric pads, reverb-soaked and floating]",
            "[kick enters, four on the floor, driving]",
            "[Theme A 32 bars]",
            "[arpeggiated synth lead entering]",
            "[supersaws building in the background]",
            "[Breakdown 32 bars]",
            "[kick drops, only melody and pads]",
            "[emotional peak of the melody, wide stereo]",
            "[Build 16 bars]",
            "[gated reverb on snare, filter opening]",
            "[supersaws rising, pitch building to climax]",
            "[Drop 32 bars]",
            "[full kick and supersaws, hands up energy]",
            "[euphoric release, crowd at peak]",
            "[Outro 16 bars]",
            "[pads and reverb returning, floating fade]",
        ],

        "Techno": [
            "[Intro 16 bars]",
            "[industrial noise texture, dark and cold]",
            "[kick entering hard and mechanical]",
            "[Groove A 32 bars]",
            "[driving kick, distorted bassline underneath]",
            "[metallic percussion layering in]",
            "[noise elements and reverb tails filling space]",
            "[Break 16 bars]",
            "[kick drops, only industrial texture remains]",
            "[tension and silence, dark atmosphere]",
            "[Build 16 bars]",
            "[kick returns, layered hard, relentless]",
            "[filter opening, pressure building]",
            "[Drop 32 bars]",
            "[full force kick and bass, warehouse energy]",
            "[underground Berlin intensity]",
            "[Outro 16 bars]",
            "[elements cutting out hard, DJ tool tail]",
        ],

        "House": [
            "[Intro 16 bars]",
            "[four on the floor kick, warm and classic]",
            "[organ or piano chord stabs entering]",
            "[Groove A 32 bars]",
            "[soulful bassline, Chicago warmth]",
            "[vocal sample or hook introduced]",
            "[feel-good energy building naturally]",
            "[Breakdown 16 bars]",
            "[kick drops, piano chords and vocals only]",
            "[soulful and uplifting moment]",
            "[Build 8 bars]",
            "[kick building back in, filter opening]",
            "[Drop 32 bars]",
            "[full groove, dancefloor peak, joyful energy]",
            "[organ stabs punching through the mix]",
            "[Outro 16 bars]",
            "[groove stripping back, DJ-friendly exit]",
        ],

        "Deep House": [
            "[Intro 16 bars]",
            "[warm pad wash, sub bass barely present]",
            "[kick entering soft and deep]",
            "[Groove A 32 bars]",
            "[deep rolling bassline, late night feel]",
            "[Rhodes or jazz chord stabs, understated]",
            "[whispering vocal sample floating in the mix]",
            "[Breakdown 16 bars]",
            "[kick drops, only pads and bass texture]",
            "[introspective and soulful moment]",
            "[Groove B 32 bars]",
            "[groove returns, slightly denser layering]",
            "[smooth and hypnotic, afterhours energy]",
            "[Outro 16 bars]",
            "[elements fading gently, warm and slow]",
        ],

        "Tech House": [
            "[Intro 16 bars]",
            "[tight kick entering dry, minimal texture]",
            "[bass groove teasing, filter almost closed]",
            "[Groove A 32 bars]",
            "[rolling bassline locked with kick, funky and driving]",
            "[clicky hats and percussion layering in]",
            "[acid element weaving, dancefloor tension building]",
            "[Breakdown 16 bars]",
            "[kick drops, bass loop isolated]",
            "[filter sweeping, crowd anticipation]",
            "[Build 8 bars]",
            "[snare roll, filter opening wide]",
            "[Drop 32 bars]",
            "[full groove, punchy kick, rolling bassline dominant]",
            "[club energy peak, hypnotic and relentless]",
            "[Outro 16 bars]",
            "[elements stripping back, DJ-friendly tail]",
        ],
    }

    # ============================================================
    # クラス変数: ジャンル別スタイルキーワード辞書
    # ============================================================

    GENRE_STYLE_KEYWORDS = {
        "Progressive House": {
            "base": ["Progressive House", "Melodic", "Uplifting", "Euphoric"],
            "atmosphere": ["Warm Pads", "Lush Strings", "Emotional", "Epic"],
            "production": ["Wide Stereo", "Layered Synths", "Filtered Bass"],
        },
        "Tech House": {
            "base": ["Tech House", "Groovy", "Funky", "Club"],
            "atmosphere": ["Driving", "Dancefloor", "Rolling Bassline", "Punchy"],
            "production": ["Tight Kick", "Clicky Hats", "Minimal Vocals", "Acid Elements"],
        },
        "House": {
            "base": ["House", "Classic House", "Four on the Floor"],
            "atmosphere": ["Soulful", "Warm", "Chicago", "Feel Good"],
            "production": ["Piano Chords", "Organ", "Pitched Vocals", "Deep Bass"],
        },
        "Deep House": {
            "base": ["Deep House", "Atmospheric", "Soulful"],
            "atmosphere": ["Late Night", "Introspective", "Smooth", "Jazzy"],
            "production": ["Sub Bass", "Rhodes", "Whispering Vocals", "Ambient Textures"],
        },
        "Minimal Techno": {
            "base": ["Minimal Techno", "Hypnotic", "Loop-based"],
            "atmosphere": ["Sparse", "Industrial", "Cold", "Berlin"],
            "production": ["Modular Synth", "Metallic Percussion", "Repeating Patterns"],
        },
        "Techno": {
            "base": ["Techno", "Dark", "Industrial", "Pounding"],
            "atmosphere": ["Underground", "Warehouse", "Raw", "Relentless"],
            "production": ["Hard Kick", "Distorted Bass", "Noise Elements", "Reverb Tails"],
        },
        "Trance": {
            "base": ["Trance", "Uplifting", "Euphoric"],
            "atmosphere": ["Floating", "Emotional", "Epic", "Hands Up"],
            "production": ["Arpeggiated Synths", "Gated Reverb", "Supersaws"],
        },
        "Dub Techno": {
            "base": ["Dub Techno", "Ambient", "Spacious"],
            "atmosphere": ["Deep", "Echoing", "Hypnotic", "Detroit"],
            "production": ["Tape Delay", "Heavy Reverb", "Chord Stabs", "Sub Bass"],
        },
        "Deep Tech": {
            "base": ["Deep Tech", "Minimal", "Groovy"],
            "atmosphere": ["Underground", "Rolling", "After Hours"],
            "production": ["Tight Groove", "Subtle Percussion", "Deep Bass"],
        },
    }

    # エネルギー別キーワード
    ENERGY_KEYWORDS = {
        1: ["Ambient", "Chill", "Subtle", "Soft"],
        2: ["Laid-back", "Smooth", "Mellow"],
        3: ["Steady", "Driving", "Solid"],
        4: ["Intense", "Pumping", "Powerful"],
        5: ["Peak Time", "Massive", "Euphoric", "Full Throttle"],
    }

    # Hypnotic戦略キーワード
    HYPNOTIC_KEYWORDS = [
        "Hypnotic", "Repetitive", "Trance-inducing", "Meditative",
        "Looping", "Groove-forward", "Minimalist"
    ]

    # Story戦略キーワード
    STORY_KEYWORDS = [
        "Dynamic", "Evolving", "Journey", "Narrative",
        "Build and Release", "Emotional Arc"
    ]

    # ============================================================
    # クラス変数: ジャンル別タイトル語彙
    # ============================================================

    TITLE_VOCAB = {
        "Progressive House": {
            "adj": ["Eternal", "Floating", "Golden", "Rising", "Boundless", "Luminous"],
            "noun": ["Horizon", "Ascent", "Journey", "Dawn", "Voyage", "Odyssey"],
        },
        "Tech House": {
            "adj": ["Raw", "Sleek", "Locked", "Rolling", "Punchy"],
            "noun": ["Groove", "Function", "Engine", "Drive", "Current"],
        },
        "House": {
            "adj": ["Warm", "Soulful", "Classic", "Smooth", "Deep"],
            "noun": ["Groove", "Soul", "Spirit", "Feeling", "Ritual"],
        },
        "Deep House": {
            "adj": ["Midnight", "Velvet", "Quiet", "Hazy", "Distant"],
            "noun": ["Drift", "Shade", "Current", "Murmur", "Depth"],
        },
        "Minimal Techno": {
            "adj": ["Sparse", "Cold", "Silent", "Bare", "Still"],
            "noun": ["Pulse", "Grid", "Void", "Loop", "Signal"],
        },
        "Techno": {
            "adj": ["Dark", "Industrial", "Hard", "Iron", "Brutal"],
            "noun": ["Chamber", "Machine", "Force", "Protocol", "Grid"],
        },
        "Trance": {
            "adj": ["Euphoric", "Astral", "Electric", "Infinite", "Radiant"],
            "noun": ["Ecstasy", "Ascension", "Dimension", "Rapture", "Wave"],
        },
        "Dub Techno": {
            "adj": ["Echoing", "Cavernous", "Misty", "Deep", "Ancient"],
            "noun": ["Space", "Echo", "Void", "Resonance", "Fog"],
        },
        "Deep Tech": {
            "adj": ["Rolling", "Subtle", "After", "Low", "Late"],
            "noun": ["Hours", "Motion", "Frequency", "System", "Cycle"],
        },
    }

    # ============================================================
    # 初期化
    # ============================================================

    def __init__(self):
        """SunoPromptBuilderを初期化"""
        pass

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
            >>> print("Instrumental" in prompt.styles)
            True
            >>> print(len(prompt.styles) <= 200)
            True
        """
        # 1. Lyrics構築
        lyrics = self._build_lyrics(genre, strategy, vocal)

        # 2. Styles構築（200文字上限チェック込み）
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

        if vocal:
            # Vocal時: セクションタグ行のみ抽出してGeminiへ渡すベース構造を作る
            # パフォーマンス指示行（[]内にカンマがある行）は除外し、セクション見出しのみ残す
            section_lines = [
                line for line in blueprint
                if line.startswith('[') and ',' not in line
            ]
            lyrics = "\n".join(section_lines)
        else:
            # Instrumental時: 全行を結合してブラケット処理
            lyrics = "\n".join(blueprint)
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
        Styles構築 — ジャンル特性・エネルギー・戦略を反映した豊かなキーワード列

        生成結果が200文字を超える場合は、BPM・キー・Vocal/Instrumental
        などの必須トークンを保持しつつ末尾からキーワードを削ります。

        Returns:
            str: カンマ区切りのStyles文字列（最大200文字）
        """
        style_parts = []

        # 1. ジャンル固有キーワード
        kw = self.GENRE_STYLE_KEYWORDS.get(genre, {})
        base = kw.get("base", [genre])
        atmosphere = kw.get("atmosphere", [])
        production = kw.get("production", [])

        style_parts.extend(base)

        # 雰囲気からランダム2語
        if atmosphere:
            style_parts.extend(random.sample(atmosphere, min(2, len(atmosphere))))

        # サウンドプロダクションからランダム2語
        if production:
            style_parts.extend(random.sample(production, min(2, len(production))))

        # 2. Vocal/Instrumental（必須）
        style_parts.append("Vocal" if vocal else "Instrumental")

        # 3. BPMとリズムの安定化（必須・拍ズレ対策）
        bpm_token = f"{bpm:.0f} BPM"
        style_parts.append(bpm_token)
        style_parts.extend(["Steady 4/4 beat", "Four on the floor"])

        # 4. キー（必須）
        style_parts.append(key)

        # 5. エネルギー別キーワード（1〜2語）
        energy_kws = self.ENERGY_KEYWORDS.get(energy_level, ["Driving"])
        style_parts.extend(random.sample(energy_kws, min(2, len(energy_kws))))

        # 6. 戦略別キーワード（1語）
        if strategy == EnergyStrategy.HYPNOTIC:
            style_parts.append(random.choice(self.HYPNOTIC_KEYWORDS))
        else:
            style_parts.append(random.choice(self.STORY_KEYWORDS))

        # 重複除去しつつ順序を維持
        seen = set()
        deduped = []
        for p in style_parts:
            if p not in seen:
                seen.add(p)
                deduped.append(p)

        # 200文字上限チェック: 超過した場合は末尾から削る
        # ただし必須トークン（genre先頭1語・vocal/instrumental・BPM・key）は保持する
        mandatory = {deduped[0], "Vocal", "Instrumental", bpm_token, key}
        result = ", ".join(deduped)
        while len(result) > _STYLES_MAX_CHARS and len(deduped) > len(mandatory):
            # 末尾から非必須トークンを探して削除
            for i in range(len(deduped) - 1, -1, -1):
                if deduped[i] not in mandatory:
                    removed = deduped.pop(i)
                    logger.debug(f"Styles truncated: removed '{removed}'")
                    break
            else:
                # 非必須トークンがなくなったら強制打ち切り
                break
            result = ", ".join(deduped)

        if len(result) > _STYLES_MAX_CHARS:
            result = result[:_STYLES_MAX_CHARS]
            logger.warning(f"Styles hard-truncated to {_STYLES_MAX_CHARS} chars")

        return result

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
        ジャンル特性を反映したクリエイティブタイトル生成

        エネルギーレベルが高い（>=4）場合は「形容詞 + 名詞」の
        シンプルな2単語タイトルを返します。
        低〜中エネルギーの場合は4種類のパターンから均等にランダム選択します。

        Args:
            genre (str): ジャンル名
            energy_level (int): エネルギーレベル（1-5）
            key (str): キー（未使用・将来拡張用）
            bpm (float): BPM

        Returns:
            str: タイトル文字列
        """
        vocab = self.TITLE_VOCAB.get(genre, {
            "adj": ["Deep", "Dark", "Electric", "Analog", "Neon", "Cosmic"],
            "noun": ["Groove", "Pulse", "Phase", "Loop", "Drive", "Signal"]
        })

        adj = random.choice(vocab["adj"])
        noun = random.choice(vocab["noun"])

        if energy_level >= 4:
            return f"{adj} {noun}"
        else:
            # 修正: 重複パターンを排除し、4種類を均等に選択
            patterns = [
                f"{adj} {noun}",
                f"{noun} {bpm:.0f}",
                f"Into the {noun}",
                f"The {adj} {noun}",
            ]
            return random.choice(patterns)
