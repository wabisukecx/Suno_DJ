"""
Audio Engine Module
===================

オーディオエンジン本体

このモジュールは以下を提供します:
1. AudioEngineクラス（ミキサー管理）
2. VCI100_MIDIクラス（MIDI定数）
3. デュアルデッキ制御
4. クロスフェーダー制御
"""

import logging
import math

from .audio_constants import BASS_AVAILABLE, BASS_LIB
from .deck import Deck, AudioConfig

logger = logging.getLogger(__name__)


class AudioEngine:
    """
    オーディオエンジン本体
    
    2つのデッキ（Deck A/B）とクロスフェーダーを管理します。
    
    Attributes:
        config (AudioConfig): オーディオ設定
        deck_a (Deck): デッキA
        deck_b (Deck): デッキB
        master_volume (float): マスターボリューム（0.0-1.0）
        crossfader (float): クロスフェーダー位置（0.0=A, 1.0=B）
        running (bool): エンジン動作状態
    
    Example:
        >>> config = AudioConfig(sample_rate=48000)
        >>> engine = AudioEngine(config)
        >>> engine.start()
        >>> engine.deck_a.load('track1.mp3')
        >>> engine.deck_a.play()
        >>> engine.set_crossfader(0.5)  # センター
    """
    
    def __init__(self, config: AudioConfig):
        """
        AudioEngineを初期化
        
        Args:
            config (AudioConfig): オーディオ設定
        """
        self.config = config
        self.deck_a = Deck("A", config)
        self.deck_b = Deck("B", config)
        self.master_volume = 1.0
        self.crossfader = 0.5
        self.running = False
    
    def start(self) -> bool:
        """
        エンジンを起動
        
        Returns:
            bool: 起動成功ならTrue
        """
        if not BASS_AVAILABLE:
            logger.error("BASS library not available")
            return False
        
        self.running = True
        logger.info("AudioEngine started")
        return True
    
    def stop(self):
        """
        エンジンを停止
        
        両デッキをアンロードし、BASSライブラリを解放します。
        """
        self.running = False
        self.deck_a.unload()
        self.deck_b.unload()
        
        if BASS_AVAILABLE:
            BASS_LIB.BASS_Free()
        
        logger.info("AudioEngine stopped")
    
    def set_crossfader(self, v: float):
        """
        クロスフェーダー位置を設定
        
        コンスタントパワークロスフェーダーを使用:
        - v=0.0: Deck A のみ
        - v=0.5: 両デッキ均等
        - v=1.0: Deck B のみ
        
        Args:
            v (float): クロスフェーダー位置（0.0-1.0）
        """
        self.crossfader = max(0.0, min(1.0, v))
        self._update_mix()
    
    def set_master_volume(self, v: float):
        """
        マスターボリュームを設定
        
        Args:
            v (float): マスターボリューム（0.0-1.0）
        """
        self.master_volume = max(0.0, min(1.0, v))
        self._update_mix()
    
    # ① Xfader transform: Mixxx enginexfader.cpp 準拠
    # transform=1.0 がデフォルト（現行の cos/sin に近い安全側の結果）。
    # 将来的に GUI設定から変更可能にするため属性として公開。
    # transform > 1.0 → カーブが錐になる（スクラッチ履行向き）
    # transform < 1.0 → カーブが緩やかになる（ブレンド履行向き）
    xfader_transform: float = 1.0

    def _calc_xfade_gains(self, pos: float) -> tuple[float, float]:
        """クロスフェーダーゲインを計算（Mixxx enginexfader.cpp 準拠）

        ① Xfader transform対応版。transform=1.0 時は cos/sin 方式とほぼ同等。
        transform が大きいほどクロスポイントが鄐しくなる（DJXフェーダーカーブ設定対応）。

        Args:
            pos: クロスフェーダー位置 (0.0=A全強, 1.0=B全強)

        Returns:
            (gain_a, gain_b): 両デッキのゲイン (0.0-1.0)
        """
        t = max(0.1, self.xfader_transform)  # 0除算防止

        # Mixxx: getPowerCalibration() = 0.5^(1/transform)
        # クロスポイントを3dB点に引き寄せる校正値
        calibration = 0.5 ** (1.0 / t)

        # pos を calibration でスケーリング（-calibration 〜 +calibration の範囲に居ねる）
        pos_cal = pos * calibration
        left_side  = pos_cal - calibration   # Deck A側（負の時は全強）
        right_side = pos_cal + calibration   # Deck B側（正の時は全強）

        gain_a = max(0.0, 1.0 - right_side ** t) if right_side > 0 else 1.0
        gain_b = max(0.0, 1.0 - (-left_side) ** t) if left_side < 0 else 1.0

        # Constant Power補正: gain_a² + gain_b² = 1 に正規化
        norm = math.sqrt(gain_a ** 2 + gain_b ** 2)
        if norm > 0:
            gain_a /= norm
            gain_b /= norm

        return gain_a, gain_b

    def _update_mix(self):
        """
        ミックス状態を更新

        ① Xfader transform 対応版クロスフェーダー:
        - xfader_transform=1.0 時は Mixxx デフォルト（cos/sin とほぼ同等）
        - xfader_transform は将来的に GUI設定から変更可能
        """
        coeff_a, coeff_b = self._calc_xfade_gains(self.crossfader)
        self.deck_a.set_master_volume_coeff(coeff_a * self.master_volume)
        self.deck_b.set_master_volume_coeff(coeff_b * self.master_volume)


class VCI100_MIDI:
    """
    VCI-100 MIDIコントロール定数
    
    Vestax VCI-100のMIDI CCナンバー定義
    
    Attributes:
        CROSSFADER (int): クロスフェーダー (CC#8)
        MASTER_VOLUME (int): マスターボリューム (CC#24)
        CH1_VOLUME (int): チャンネル1ボリューム (CC#12)
        CH1_TRIM (int): チャンネル1トリム (CC#28)
        CH1_EQ_HIGH (int): チャンネル1 High EQ (CC#20)
        CH1_EQ_MID (int): チャンネル1 Mid EQ (CC#21)
        CH1_EQ_LOW (int): チャンネル1 Low EQ (CC#22)
        CH1_FILTER (int): チャンネル1フィルター (CC#23)
        CH1_TEMPO (int): チャンネル1テンポ (CC#14)
        CH2_VOLUME (int): チャンネル2ボリューム (CC#13)
        CH2_TRIM (int): チャンネル2トリム (CC#29)
        CH2_EQ_HIGH (int): チャンネル2 High EQ (CC#24)
        CH2_EQ_MID (int): チャンネル2 Mid EQ (CC#25)
        CH2_EQ_LOW (int): チャンネル2 Low EQ (CC#26)
        CH2_FILTER (int): チャンネル2フィルター (CC#27)
        CH2_TEMPO (int): チャンネル2テンポ (CC#15)
        CH1_LOOP (int): チャンネル1ループ (CC#66)
        CH2_LOOP (int): チャンネル2ループ (CC#67)
    """
    # グローバル
    CROSSFADER = 8
    MASTER_VOLUME = 24
    
    # チャンネル1（Deck A）
    CH1_VOLUME = 12
    CH1_TRIM = 28
    CH1_EQ_HIGH = 20
    CH1_EQ_MID = 21
    CH1_EQ_LOW = 22
    CH1_FILTER = 23
    CH1_TEMPO = 14
    CH1_LOOP = 66
    
    # チャンネル2（Deck B）
    CH2_VOLUME = 13
    CH2_TRIM = 29
    CH2_EQ_HIGH = 24
    CH2_EQ_MID = 25
    CH2_EQ_LOW = 26
    CH2_FILTER = 27
    CH2_TEMPO = 15
    CH2_LOOP = 67
