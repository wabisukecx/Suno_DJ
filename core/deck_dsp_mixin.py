"""
Deck DSP Mixin
==============

DeckDspMixin: DSP / EQ / Filter / Volume 処理ロジックの分離 (Step 2 Refactor)

【設計根拠】
  Deck クラスの DSP 関連実装（~200行）を Mixin として分離。
  EQ 定数・BQF 更新メソッド・Filter・Volume スムージング等、
  オーディオ信号処理に特化したロジックを単一責任として管理する。

【移動したロジック】
  - EQ 定数群             : EQ_LOW_FREQ / EQ_MID_FREQ / EQ_HIGH_FREQ / EQ_*_Q / EQ_CASCADE / EQ_SHELF_FS
  - _setup_dsp()          : BQF 3段カスケード EQ の初期化
  - _setup_tempo_options(): BASS_ATTRIB_TEMPO_OPTION_PREVENT_CLICK 設定
  - _update_bqf_eq()      : BQF PeakingEQ パラメータ更新 (Mid 帯域用)
  - _update_bqf_shelf()   : BQF Shelf 型 EQ パラメータ更新 (Low/High 帯域用)
  - _eq_low_norm (property): EQ Low 正規化値（スコアエンジン用）
  - set_eq_low/mid/high() : EQ 設定
  - set_filter()          : DJ Filter (LPF/HPF 対数スケール)
  - VOLUME_SLIDE_MS/MIN_DELTA 定数、_update_volume()

【Mixxx 参照元】
  - enginefilterbiquad1.cpp: BQF PeakingEQ / Shelf 設計
  - filtereffect.cpp       : DJ Filter 対数周波数マッピング

【依存する Deck 側属性】
  - self.name          : デッキ名 (str)
  - self.stream_fx     : BASS ストリームハンドル (int)
  - self.config        : AudioConfig
  - self.eq_low/mid/high : EQ 値 (float)
  - self.filter_val    : Filter 値 (float)
  - self.fx_eq_low/mid/high : FX ハンドルリスト (list[int])
  - self.fx_filter     : Filter FX ハンドル (int)
  - self.channel_volume / mix_volume / trim_db : ボリューム管理 (float)
"""

import ctypes
import logging
import math

from .audio_constants import (
    BASS_LIB, BASS_FX_AVAILABLE,
    BASS_ATTRIB_VOL,
    BASS_FX_BFX_BQF,
    BASS_BFX_BQF_LOWPASS, BASS_BFX_BQF_HIGHPASS, BASS_BFX_BQF_PEAKINGEQ,
    BASS_BFX_BQF_LOWSHELF, BASS_BFX_BQF_HIGHSHELF,
    BASS_BFX_CHANALL,
    BASS_BFX_BQF,
    BASS_ATTRIB_TEMPO_OPTION_PREVENT_CLICK,
)

logger = logging.getLogger(__name__)


class DeckDspMixin:
    """
    DSP / EQ / Filter / Volume 処理を提供する Mixin クラス。

    このクラス単体でインスタンス化せず、必ず Deck クラスに
    多重継承で組み込むこと。以下の属性が Deck 側の __init__ で
    定義済みであることを前提とする:
      - self.name
      - self.stream_fx
      - self.config
      - self.eq_low / eq_mid / eq_high
      - self.filter_val
      - self.fx_eq_low / fx_eq_mid / fx_eq_high  (list[int])
      - self.fx_filter                            (int)
      - self.channel_volume / mix_volume / trim_db
    """

    # ---------------------------------------------------------------
    # D-02: BQF EQ 定数（Mixxx enginefilterbiquad1.cpp 準拠）
    # ---------------------------------------------------------------
    # Low/High シェルフ境界: 246Hz / 10kHz (DJ standard)
    # Mid ピーキング中心: 2500Hz
    # Q 値: Low=0.707 (Butterworth), Mid=1.0, High=0.707

    EQ_LOW_FREQ:  float = 246.0
    EQ_MID_FREQ:  float = 2500.0
    EQ_HIGH_FREQ: float = 10000.0
    EQ_LOW_Q:     float = 0.707   # Butterworth
    EQ_MID_Q:     float = 1.0     # Mixxx EQ Mid default
    EQ_HIGH_Q:    float = 0.707   # Butterworth
    EQ_CASCADE:   int   = 3       # 3段: -15dB × 3 = -45dB Kill 可能
    EQ_SHELF_FS:  float = 1.0     # シェルフスロープ: Mixxx デフォルト値（最大傾斜）

    # ---------------------------------------------------------------
    # P2: ボリュームスムージング定数
    # ---------------------------------------------------------------
    # Crossfader / Channel Volume の急変でクリックノイズが発生する場合がある。
    # BASS_ChannelSlideAttribute で VOLUME_SLIDE_MS ms かけてスムーズに変化させる。
    # 変化量が VOLUME_SLIDE_MIN_DELTA 未満の場合は即時適用でオーバーヘッドを節約する。

    VOLUME_SLIDE_MS:    int   = 10    # ms (2フレーム分 ≈ 11ms @ 48kHz/2048)
    VOLUME_SLIDE_MIN_DELTA: float = 0.01  # これ未満の差分は即時適用

    # ---------------------------------------------------------------
    # DSP セットアップ
    # ---------------------------------------------------------------

    def _setup_dsp(self) -> None:
        """
        BQF シェルフ型 EQ を 3段カスケードでチャンネルにアタッチする。

        Mixxx enginefilterbiquad1.cpp 準拠。
          Low  → LowShelf:  Kill 方向に回すと低域側が単調に減衰
          Mid  → PeakingEQ: 中心周波数 2.5kHz
          High → HighShelf: Kill 方向に回すと高域側が単調に減衰
        """
        if not self.stream_fx:
            return

        self.fx_eq_low  = []
        self.fx_eq_mid  = []
        self.fx_eq_high = []

        for i in range(self.EQ_CASCADE):
            h_low  = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_BFX_BQF, 0)
            h_mid  = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_BFX_BQF, 0)
            h_high = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_BFX_BQF, 0)
            err = BASS_LIB.BASS_ErrorGetCode()
            logger.debug(
                f"Deck {self.name}: EQ FX Stage {i}: "
                f"low={h_low} mid={h_mid} high={h_high} err={err}"
            )
            if h_low:  self.fx_eq_low.append(h_low)
            if h_mid:  self.fx_eq_mid.append(h_mid)
            if h_high: self.fx_eq_high.append(h_high)

        # 各バンドの初期フィルター型をセット
        for h in self.fx_eq_low:
            self._update_bqf_shelf(h, BASS_BFX_BQF_LOWSHELF,  self.EQ_LOW_FREQ,  self.EQ_LOW_Q,  self.eq_low)
        for h in self.fx_eq_mid:
            self._update_bqf_eq(h, self.EQ_MID_FREQ, self.EQ_MID_Q, self.eq_mid)
        for h in self.fx_eq_high:
            self._update_bqf_shelf(h, BASS_BFX_BQF_HIGHSHELF, self.EQ_HIGH_FREQ, self.EQ_HIGH_Q, self.eq_high)

        if BASS_FX_AVAILABLE:
            self.fx_filter = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_BFX_BQF, 0)

        logger.info(
            f"Deck {self.name}: EQ Setup done (LowShelf/PeakEQ/HighShelf) - "
            f"low={len(self.fx_eq_low)} mid={len(self.fx_eq_mid)} "
            f"high={len(self.fx_eq_high)} filter={self.fx_filter}"
        )

    def _setup_tempo_options(self) -> None:
        """
        P3: BASS_FX Tempo オプション設定。

        BASS_ATTRIB_TEMPO_OPTION_PREVENT_CLICK を有効化し、
        ループ切り替えやテンポ急変時のクリックノイズを防止する。
        BASS_FX_TempoCreate でラップした stream_fx にのみ有効。
        """
        if not self.stream_fx or not BASS_FX_AVAILABLE:
            return

        result = BASS_LIB.BASS_ChannelSetAttribute(
            self.stream_fx, BASS_ATTRIB_TEMPO_OPTION_PREVENT_CLICK, ctypes.c_float(1.0)
        )
        if result:
            logger.debug(f"Deck {self.name}: PREVENT_CLICK enabled")
        else:
            err = BASS_LIB.BASS_ErrorGetCode()
            logger.debug(f"Deck {self.name}: PREVENT_CLICK not supported (err={err})")

    # ---------------------------------------------------------------
    # BQF パラメータ更新（内部メソッド）
    # ---------------------------------------------------------------

    def _update_bqf_eq(self, handle: int, center: float, q: float, gain: float) -> bool:
        """
        BQF PeakingEQ 1段分のパラメータを更新する（Mid 帯域用）。

        gain=0.0 のとき係数が恒等変換になるため Flat 時に完全透明。
        DX8 ParamEQ からの移行版（D-02）。

        Args:
            handle: BASS FX ハンドル
            center: 中心周波数（Hz）
            q:      Q 値
            gain:   ゲイン（dB, -15.0 〜 +15.0）

        Returns:
            BASS_FXSetParameters の戻り値
        """
        if not handle:
            return False
        safe_gain = max(-15.0, min(15.0, gain))
        p = BASS_BFX_BQF(
            lFilter=BASS_BFX_BQF_PEAKINGEQ,
            lChannel=BASS_BFX_CHANALL,
            fCenter=center,
            fGain=safe_gain,
            fBandwidth=1.0,  # PeakingEQ では未使用（fQ で制御）
            fQ=q,
            fS=0.0,
        )
        return BASS_LIB.BASS_FXSetParameters(handle, ctypes.byref(p))

    def _update_bqf_shelf(
        self, handle: int, filter_type: int, center: float, q: float, gain: float
    ) -> bool:
        """
        BQF シェルフ型 EQ 1段分のパラメータを更新する（Low/High 帯域用）。

        Mixxx enginefilterbiquad1.cpp 準拠。

        bass_fx.h 注意点:
          "fBandwidth has a priority over fQ"
          → Shelf 型では fS だけを使いたいので fBandwidth=0.0 に設定することで
            fBandwidth の優先を無効化し fS が有効になる。

        Args:
            handle:      BASS FX ハンドル
            filter_type: BASS_BFX_BQF_LOWSHELF または BASS_BFX_BQF_HIGHSHELF
            center:      シェルフ周波数（Hz）
            q:           Q 値（fS 優先のため実質未使用）
            gain:        ゲイン（dB, -15.0 〜 +15.0）

        Returns:
            BASS_FXSetParameters の戻り値
        """
        if not handle:
            return False
        safe_gain = max(-15.0, min(15.0, gain))
        p = BASS_BFX_BQF(
            lFilter=filter_type,
            lChannel=BASS_BFX_CHANALL,
            fCenter=center,
            fGain=safe_gain,
            fBandwidth=0.0,       # fBandwidth の優先を無効化して fS を有効にする
            fQ=0.0,               # Shelf 型では fS がスロープ制御、fQ は不要
            fS=self.EQ_SHELF_FS,  # 1.0=最大傾斜（単調なゲイン変化を保証）
        )
        return BASS_LIB.BASS_FXSetParameters(handle, ctypes.byref(p))

    # ---------------------------------------------------------------
    # EQ プロパティ・セッター
    # ---------------------------------------------------------------

    @property
    def _eq_low_norm(self) -> float:
        """
        EQ Low の正規化値（0.0〜1.0）を返す。スコアエンジン用。

        eq_low は -15.0dB〜+15.0dB の範囲（BQF 1段あたり）。
        0dB(中央)→0.5, +15dB→1.0, -15dB→0.0 に線形変換する。
        Kill 状態（-15dB × 3段 = -45dB 実効）は eq_low ≒ -15 → 約 0.0 となり
        Clean Swap 判定（≤0.3）に合致する。
        """
        return max(0.0, min(1.0, (self.eq_low + 15.0) / 30.0))

    def set_eq_low(self, db: float) -> None:
        """EQ Low バンド（LowShelf）を設定する。"""
        self.eq_low = db
        if abs(db) > 1.0:
            logger.info(
                f"Deck {self.name} Low: {db:.1f}dB "
                f"(LowShelf x{len(self.fx_eq_low)}cascade, eff:{db * len(self.fx_eq_low):.0f}dB)"
            )
        for h in self.fx_eq_low:
            self._update_bqf_shelf(h, BASS_BFX_BQF_LOWSHELF, self.EQ_LOW_FREQ, self.EQ_LOW_Q, db)

    def set_eq_mid(self, db: float) -> None:
        """EQ Mid バンド（PeakingEQ）を設定する。"""
        self.eq_mid = db
        if abs(db) > 1.0:
            logger.info(
                f"Deck {self.name} Mid: {db:.1f}dB "
                f"(BQF x{len(self.fx_eq_mid)}cascade, eff:{db * len(self.fx_eq_mid):.0f}dB)"
            )
        for h in self.fx_eq_mid:
            self._update_bqf_eq(h, self.EQ_MID_FREQ, self.EQ_MID_Q, db)

    def set_eq_high(self, db: float) -> None:
        """EQ High バンド（HighShelf）を設定する。"""
        self.eq_high = db
        if abs(db) > 1.0:
            logger.info(
                f"Deck {self.name} High: {db:.1f}dB "
                f"(HighShelf x{len(self.fx_eq_high)}cascade, eff:{db * len(self.fx_eq_high):.0f}dB)"
            )
        for h in self.fx_eq_high:
            self._update_bqf_shelf(h, BASS_BFX_BQF_HIGHSHELF, self.EQ_HIGH_FREQ, self.EQ_HIGH_Q, db)

    # ---------------------------------------------------------------
    # DJ Filter（対数スケール、Mixxx filtereffect.cpp 参照）
    # ---------------------------------------------------------------

    def set_filter(self, val: float) -> None:
        """
        DJ Filter: val -1.0〜+1.0 で LPF/HPF を切り替える。

        符号の対応:
          val < 0  → HPF 方向（ノブ左 / CC 値 0〜0.5 未満）
          val == 0 → Flat（フィルター OFF）
          val > 0  → LPF 方向（ノブ右 / CC 値 0.5 超〜1.0）

        D-03 改善: 周波数マッピングをリニア→対数スケールに変更。
        参照: Mixxx filtereffect.cpp kMinCorner=13Hz, kMaxCorner=22050Hz
        Q=0.707 (Butterworth、Mixxx デフォルト値)
        """
        self.filter_val = val
        if not self.fx_filter:
            return

        p = BASS_BFX_BQF(lChannel=BASS_BFX_CHANALL, fGain=0.0, fBandwidth=1.0, fQ=0.707, fS=0.0)
        FLAT_THRESHOLD = 0.05  # ±5% 以内はフラット

        if abs(val) < FLAT_THRESHOLD:
            # Flat: 実質バイパス（LPF を 22050Hz に設定）
            p.lFilter = BASS_BFX_BQF_LOWPASS
            p.fCenter  = 22050.0
            p.fQ       = 0.707
        elif val > 0:
            # LPF 方向: val 0.05→1.0 を 22050Hz→80Hz に対数マッピング
            norm      = (val - FLAT_THRESHOLD) / (1.0 - FLAT_THRESHOLD)
            log_freq  = math.exp(math.log(22050.0) + norm * (math.log(80.0) - math.log(22050.0)))
            p.lFilter = BASS_BFX_BQF_LOWPASS
            p.fCenter  = max(80.0, min(22050.0, log_freq))
            p.fQ       = 0.707
        else:
            # HPF 方向: val -0.05→-1.0 を 13Hz→8000Hz に対数マッピング
            norm      = (abs(val) - FLAT_THRESHOLD) / (1.0 - FLAT_THRESHOLD)
            log_freq  = math.exp(math.log(13.0) + norm * (math.log(8000.0) - math.log(13.0)))
            p.lFilter = BASS_BFX_BQF_HIGHPASS
            p.fCenter  = max(13.0, min(8000.0, log_freq))
            p.fQ       = 0.707

        BASS_LIB.BASS_FXSetParameters(self.fx_filter, ctypes.byref(p))

    # ---------------------------------------------------------------
    # ボリューム制御（スムージング付き）
    # ---------------------------------------------------------------

    def _update_volume(self) -> None:
        """
        チャンネルボリューム・Trim・マスターボリューム係数を合成して BASS に適用する。

        P2 スムージング: 変化量が VOLUME_SLIDE_MIN_DELTA 以上の場合は
        BASS_ChannelSlideAttribute で VOLUME_SLIDE_MS ms かけてスムーズに変化させ
        クリックノイズを防止する。微小変化は即時適用でオーバーヘッドを節約する。
        """
        if not self.stream_fx:
            return

        trim_linear = 10.0 ** (self.trim_db / 20.0)
        final_vol   = self.channel_volume * trim_linear * self.mix_volume
        final_vol   = max(0.0, min(2.0, final_vol))

        try:
            cur_vol = ctypes.c_float(0.0)
            BASS_LIB.BASS_ChannelGetAttribute(self.stream_fx, BASS_ATTRIB_VOL, ctypes.byref(cur_vol))
            delta = abs(final_vol - cur_vol.value)
        except Exception:
            delta = 1.0  # 取得失敗時は常にスライド扱い

        if delta >= self.VOLUME_SLIDE_MIN_DELTA:
            BASS_LIB.BASS_ChannelSlideAttribute(
                self.stream_fx, BASS_ATTRIB_VOL,
                ctypes.c_float(final_vol), self.VOLUME_SLIDE_MS,
            )
        else:
            BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_VOL, final_vol)
