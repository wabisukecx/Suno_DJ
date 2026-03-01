"""
VU Meter Widget (Phase R2)
==========================

リアルタイムVUメーター表示ウィジェット。

特徴:
- BASS_ChannelGetLevel() によるL/Rレベル取得
- ピークホールド（2秒保持後にゆっくり落下）
- クリッピングインジケータ（赤点灯、0.5秒後に自動消灯）
- グリーン/イエロー/レッドのゾーン分け
"""

import time
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPainter, QColor, QLinearGradient, QPen

from gui.gui_styles import COLORS

# ----- ゾーン閾値 -----
_YELLOW_THRESH = 0.75   # 0.0-0.75: 緑、0.75-0.95: 黄、0.95-1.0: 赤
_RED_THRESH    = 0.95
_CLIP_THRESH   = 0.99   # これ以上でクリップインジケータ点灯

# ピークホールド設定
_PEAK_HOLD_SEC  = 2.0   # 保持秒数
_PEAK_FALL_RATE = 0.008 # フレームごとの落下量（60fps想定で約0.48/秒）

# ② VUスムージング: Mixxx engineVuMeter 準拠（Attack/Decay 非対称スムージング）
# 参照: Mixxx src/engine/enginevumeter.cpp
# kAttackSmoothing=1.0（即時上昇）、kDecaySmoothing=0.1（ゆっくり減衰）
# 「ビタッと張り付いてゆっくり落ちる」アナログVUメーター挙動を再現する。
_VU_ATTACK = 1.0  # 上昇係数: 1.0=即時追従
_VU_DECAY  = 0.1  # 減衰係数: 0.1=ゆっくり落下（約10フレームで1/e減衰）


def _smooth_vu(current: float, new_val: float) -> float:
    """Attack/Decay 非対称スムージング（Mixxx engineVuMeter準拠）

    Args:
        current: 現在の表示レベル（スムージング済み）
        new_val: BASSから取得した生レベル

    Returns:
        スムージング後のレベル値
    """
    if current > new_val:
        # 減衰方向: ゆっくり落下
        return current - _VU_DECAY * (current - new_val)
    else:
        # 上昇方向: 即時追従
        return current + _VU_ATTACK * (new_val - current)


class VUBar(QWidget):
    """
    1チャンネル分の縦型VUバー。
    ピークホールドとクリッピング表示を内包する。
    """

    def __init__(self, label: str = "", parent=None):
        super().__init__(parent)
        self.label = label
        self.level: float = 0.0          # スムージング済みレベル 0.0-1.0
        self._raw_level: float = 0.0     # BASSからの生レベル（スムージング前）
        self._peak: float = 0.0          # ピークホールド値
        self._peak_time: float = 0.0     # ピーク更新時刻
        self._clip: bool = False          # クリップ中フラグ
        self._clip_time: float = 0.0     # クリップ発生時刻
        self.setMinimumWidth(14)
        self.setMaximumWidth(22)
        self.setMinimumHeight(80)

    def set_level(self, level: float):
        """レベルをセット（0.0-1.0）

        ② VUスムージング適用: BASSの生レベルをそのまま表示せず、
        Mixxx engineVuMeter 準拠の Attack/Decay スムージングを通してから描画する。
        上昇は即時（Attack=1.0）、下降はゆっくり（Decay=0.1）。
        """
        now = time.monotonic()
        self._raw_level = max(0.0, min(level, 1.0))

        # ② Attack/Decay スムージングを適用
        self.level = _smooth_vu(self.level, self._raw_level)
        self.level = max(0.0, min(1.0, self.level))

        # ピークホールド更新（スムージング後の値で判定）
        if self.level >= self._peak:
            self._peak = self.level
            self._peak_time = now
        else:
            elapsed = now - self._peak_time
            if elapsed > _PEAK_HOLD_SEC:
                self._peak = max(0.0, self._peak - _PEAK_FALL_RATE)

        # クリップ検出（生レベルで判定: スムージングで隠れないようにする）
        if self._raw_level >= _CLIP_THRESH:
            self._clip = True
            self._clip_time = now
        elif self._clip and (now - self._clip_time) > 0.5:
            self._clip = False

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        w, h = self.width(), self.height()

        # ---- 背景 ----
        painter.fillRect(0, 0, w, h, QColor(COLORS['waveform_bg']))

        # ---- バー描画 ----
        bar_h = int(self.level * h)
        if bar_h > 0:
            grad = QLinearGradient(0, h, 0, 0)
            grad.setColorAt(0.0,              QColor('#00c853'))  # 緑
            grad.setColorAt(_YELLOW_THRESH,   QColor('#00c853'))
            grad.setColorAt(_YELLOW_THRESH + 0.001, QColor('#ffd600'))  # 黄
            grad.setColorAt(_RED_THRESH,      QColor('#ffd600'))
            grad.setColorAt(_RED_THRESH + 0.001, QColor('#d50000'))     # 赤
            grad.setColorAt(1.0,              QColor('#d50000'))
            painter.fillRect(0, h - bar_h, w, bar_h, grad)

        # ---- ピークホールドライン ----
        if self._peak > 0.01:
            peak_y = int((1.0 - self._peak) * h)
            if self._peak >= _RED_THRESH:
                peak_color = QColor('#ff1744')
            elif self._peak >= _YELLOW_THRESH:
                peak_color = QColor('#ffff00')
            else:
                peak_color = QColor('#69f0ae')
            painter.setPen(QPen(peak_color, 2))
            painter.drawLine(0, peak_y, w, peak_y)

        # ---- クリップインジケータ（上部2px） ----
        clip_color = QColor('#ff1744') if self._clip else QColor('#3a0000')
        painter.fillRect(0, 0, w, 3, clip_color)

        # ---- ラベル ----
        if self.label:
            painter.setPen(QColor(COLORS['text_dim']))
            painter.drawText(0, h - 2, w, 12, Qt.AlignmentFlag.AlignHCenter, self.label)


class VUMeterWidget(QWidget):
    """
    L/R 2チャンネルのVUメーター。
    DeckWidget に埋め込んで使用する。

    使い方:
        vu = VUMeterWidget()
        # タイマーまたは定期呼び出しで
        vu.update_level(left, right)  # 0.0-1.0
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMaximumWidth(50)
        self.setMinimumWidth(36)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self._bar_l = VUBar("L")
        self._bar_r = VUBar("R")
        layout.addWidget(self._bar_l)
        layout.addWidget(self._bar_r)

    def update_level(self, left: float, right: float):
        """L/Rレベルを更新（0.0-1.0）"""
        self._bar_l.set_level(left)
        self._bar_r.set_level(right)

    def reset(self):
        """レベルをゼロにリセット"""
        self._bar_l.set_level(0.0)
        self._bar_r.set_level(0.0)
