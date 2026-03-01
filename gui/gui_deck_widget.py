"""
Deck Widget — Phase R2 P-10 Waveform Enhanced
==============================================
PyQtGraph ベースの波形表示。
  - 高速レンダリング（QPainter ポリゴン → PlotDataItem）
  - 再生位置マーカー（InfiniteLine）
  - ループ範囲マーカー（LinearRegionItem）
  - HOT CUE マーカー（InfiniteLine ×4）
  - クリックでシーク（mouseClickEvent → seek_requested シグナル）
フォールバック: PyQtGraph が無い場合は旧 QPainter 版を使用。
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFrame, QPushButton
)
from PyQt6.QtCore import Qt, QPointF, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QPolygonF
import numpy as np
from typing import Optional

from gui.gui_styles import COLORS, get_deck_color
from gui.gui_vu_meter import VUMeterWidget

try:
    import pyqtgraph as pg
    pg.setConfigOption('background', COLORS.get('waveform_bg', '#0a0a0a'))
    pg.setConfigOption('foreground', '#444444')
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None

# ──────────────────────────────────────────────
# HOT CUE カラーパレット（スロット 0-3）
# ──────────────────────────────────────────────
HOT_CUE_COLORS = ['#ff4081', '#ffab40', '#69f0ae', '#40c4ff']


# ══════════════════════════════════════════════
# PyQtGraph 版波形ウィジェット
# ══════════════════════════════════════════════
class WaveformWidgetPG(QWidget):
    """PyQtGraph を使った高速波形表示ウィジェット。"""

    seek_requested = pyqtSignal(float)   # クリック位置の再生秒数を通知

    def __init__(self, accent_color: str):
        super().__init__()
        self.accent_color = accent_color
        self._duration: float = 0.0
        self._hot_cue_times: list[Optional[float]] = [None] * 4

        self.setMinimumHeight(100)
        self.setMaximumHeight(140)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # PlotWidget 生成
        self._plot = pg.PlotWidget()
        self._plot.setMenuEnabled(False)
        self._plot.setMouseEnabled(x=False, y=False)
        self._plot.hideAxis('left')
        self._plot.hideAxis('bottom')
        self._plot.setBackground(COLORS.get('waveform_bg', '#0a0a0a'))

        # グリッド中央線
        self._center_line = pg.InfiniteLine(
            pos=0, angle=0,
            pen=pg.mkPen(color='#333333', width=1, style=Qt.PenStyle.DotLine)
        )
        self._plot.addItem(self._center_line)

        # 波形データアイテム
        accent = QColor(self.accent_color)
        self._waveform_item = pg.PlotDataItem(
            pen=pg.mkPen(color=accent, width=1),
            fillLevel=0,
            brush=pg.mkBrush(QColor(accent.red(), accent.green(), accent.blue(), 80))
        )
        self._plot.addItem(self._waveform_item)

        # ループ範囲
        loop_accent = QColor(self.accent_color)
        self._loop_region = pg.LinearRegionItem(
            values=(0, 0),
            brush=pg.mkBrush(QColor(loop_accent.red(), loop_accent.green(), loop_accent.blue(), 50)),
            pen=pg.mkPen(color=self.accent_color, width=1),
            movable=False
        )
        self._loop_region.setVisible(False)
        self._plot.addItem(self._loop_region)

        # 再生位置マーカー
        self._playhead = pg.InfiniteLine(
            pos=0, angle=90,
            pen=pg.mkPen(color='#ffffff', width=2)
        )
        self._plot.addItem(self._playhead)

        # HOT CUE マーカー（4本）
        self._cue_lines: list[pg.InfiniteLine] = []
        for color in HOT_CUE_COLORS:
            line = pg.InfiniteLine(
                pos=0, angle=90,
                pen=pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine)
            )
            line.setVisible(False)
            self._plot.addItem(line)
            self._cue_lines.append(line)

        # P-02 Beatgrid: ビート縦線グループ
        # パフォーマンスのため最大100本の総数を事先生成して入れ替えで使用
        self._beat_lines: list[pg.InfiniteLine] = []
        self._beat_bar_lines: list[pg.InfiniteLine] = []  # 4拍目の太線
        BEAT_POOL = 100
        BAR_POOL = 30
        for _ in range(BEAT_POOL):
            line = pg.InfiniteLine(
                pos=-9999, angle=90,
                pen=pg.mkPen(color='#2a2a2a', width=1)
            )
            line.setVisible(False)
            self._plot.addItem(line)
            self._beat_lines.append(line)
        for _ in range(BAR_POOL):
            line = pg.InfiniteLine(
                pos=-9999, angle=90,
                pen=pg.mkPen(color='#404040', width=2)
            )
            line.setVisible(False)
            self._plot.addItem(line)
            self._beat_bar_lines.append(line)
        self._all_beat_times: list[float] = []  # 全ビート位置を保持

        layout.addWidget(self._plot)

        # クリックイベント
        self._plot.scene().sigMouseClicked.connect(self._on_mouse_clicked)

    # ── データ更新 ──────────────────────────────
    def set_waveform(self, waveform: Optional[np.ndarray]):
        if waveform is None or len(waveform) == 0:
            self._waveform_item.setData([], [])
            return
        max_val = np.max(np.abs(waveform))
        norm = 1.0 / max_val if max_val > 0 else 1.0
        n = len(waveform)
        x = np.linspace(0.0, self._duration if self._duration > 0 else 1.0, n)
        y = waveform * norm
        # 上下対称の塗り潰し用に反転データを結合
        x_fill = np.concatenate([x, x[::-1]])
        y_fill = np.concatenate([y, -y[::-1]])
        self._waveform_item.setData(x_fill, y_fill)
        # Y軸範囲を固定
        self._plot.setYRange(-1.05, 1.05, padding=0)
        self._center_line.setPos(0)

    def set_position(self, position: float, duration: float):
        self._duration = duration
        self._playhead.setPos(position)
        # X軸範囲: 現在位置を中心に ±15秒 表示
        half = 15.0
        x_min = position - half
        x_max = position + half
        self._plot.setXRange(x_min, x_max, padding=0)
        # P-02 Beatgrid: 表示窓内のビート線だけ更新
        if self._all_beat_times:
            self._update_beat_lines(x_min, x_max)

    def set_loop(self, active: bool, start: float, duration: float, _track_duration: float = 0):
        if active:
            self._loop_region.setRegion((start, start + duration))
            self._loop_region.setVisible(True)
        else:
            self._loop_region.setVisible(False)

    def set_hot_cues(self, times: list[Optional[float]]):
        """HOT CUE 4スロットの時間（秒）リストを受け取り表示更新。None=未設定。"""
        self._hot_cue_times = times
        for i, (line, t) in enumerate(zip(self._cue_lines, times)):
            if t is not None:
                line.setPos(t)
                line.setVisible(True)
            else:
                line.setVisible(False)

    # ── P-02 Beatgrid ────────────────────────────
    def set_beat_grid(self, beat_times: list[float]):
        """ビートグリッドを設定する。beat_times は秒単位の全ビート位置リスト。"""
        self._all_beat_times = beat_times

    def _update_beat_lines(self, x_min: float, x_max: float):
        """表示窓（x_min〜x_max 秒）内のビート線のみ更新する。"""
        visible = [
            (i, t) for i, t in enumerate(self._all_beat_times)
            if x_min <= t <= x_max
        ]

        beat_idx = 0
        bar_idx = 0
        for list_i, t in visible:
            is_bar = (list_i % 4 == 0)  # 4拍ごとが小節頭
            if is_bar:
                if bar_idx < len(self._beat_bar_lines):
                    self._beat_bar_lines[bar_idx].setPos(t)
                    self._beat_bar_lines[bar_idx].setVisible(True)
                    bar_idx += 1
            else:
                if beat_idx < len(self._beat_lines):
                    self._beat_lines[beat_idx].setPos(t)
                    self._beat_lines[beat_idx].setVisible(True)
                    beat_idx += 1

        # 使われなかったプールアイテムを非表示化
        for i in range(beat_idx, len(self._beat_lines)):
            self._beat_lines[i].setVisible(False)
        for i in range(bar_idx, len(self._beat_bar_lines)):
            self._beat_bar_lines[i].setVisible(False)

    # ── クリックでシーク ────────────────────────
    def _on_mouse_clicked(self, event):
        if self._duration <= 0:
            return
        pos = self._plot.plotItem.vb.mapSceneToView(event.scenePos())
        t = max(0.0, min(self._duration, pos.x()))
        self.seek_requested.emit(t)


# ══════════════════════════════════════════════
# フォールバック: QPainter 版（旧実装）
# ══════════════════════════════════════════════
class WaveformWidgetLegacy(QWidget):
    seek_requested = pyqtSignal(float)

    def __init__(self, accent_color: str):
        super().__init__()
        self.accent_color = accent_color
        self.waveform_data: Optional[np.ndarray] = None
        self.position_ratio: float = 0.0
        self.normalization_factor = 1.0
        self.loop_active = False
        self.loop_start_ratio = 0.0
        self.loop_width_ratio = 0.0
        self._duration: float = 0.0
        self.setMinimumHeight(100)
        self.setMaximumHeight(140)

    def set_waveform(self, waveform: Optional[np.ndarray]):
        self.waveform_data = waveform
        if self.waveform_data is not None and len(self.waveform_data) > 0:
            max_val = np.max(np.abs(self.waveform_data))
            self.normalization_factor = 1.0 / max_val if max_val > 0 else 1.0
        self.update()

    def set_position(self, position: float, duration: float):
        self._duration = duration
        self.position_ratio = position / duration if duration > 0 else 0.0
        self.update()

    def set_loop(self, active: bool, start: float, duration: float, track_duration: float = 0):
        self.loop_active = active
        td = track_duration if track_duration > 0 else self._duration
        if active and td > 0:
            self.loop_start_ratio = start / td
            self.loop_width_ratio = duration / td
        self.update()

    def set_hot_cues(self, times: list[Optional[float]]):
        pass   # レガシー版は未対応

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(COLORS['waveform_bg']))
        width, height = self.width(), self.height()
        mid_y = height / 2
        painter.setPen(QPen(QColor(COLORS['waveform_grid']), 1, Qt.PenStyle.DotLine))
        painter.drawLine(0, int(mid_y), width, int(mid_y))
        if self.waveform_data is not None and len(self.waveform_data) > 0:
            color = QColor(self.accent_color)
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(color))
            sample_count = len(self.waveform_data)
            step = max(1, sample_count // width)
            display_data = self.waveform_data[::step]
            points = []
            for x, val in enumerate(display_data):
                if x >= width: break
                h = val * self.normalization_factor * (height / 2) * 0.9
                points.append(QPointF(x, mid_y - h))
            for x in range(len(points) - 1, -1, -1):
                p = points[x]
                points.append(QPointF(p.x(), mid_y + (mid_y - p.y())))
            painter.drawPolygon(QPolygonF(points))
        if self.loop_active:
            lx = self.loop_start_ratio * width
            lw = self.loop_width_ratio * width
            loop_color = QColor(self.accent_color)
            loop_color.setAlpha(60)
            painter.fillRect(int(lx), 0, int(lw), height, loop_color)
        px = self.position_ratio * width
        painter.setPen(QPen(QColor('#ffffff'), 2))
        painter.drawLine(int(px), 0, int(px), height)


# 利用可能な方を選択
WaveformWidget = WaveformWidgetPG if PYQTGRAPH_AVAILABLE else WaveformWidgetLegacy


# ══════════════════════════════════════════════
# DeckWidget
# ══════════════════════════════════════════════
class DeckWidget(QFrame):
    """デッキ情報・波形・VUメーター・DSP状態を統合表示するウィジェット。"""

    seek_requested = pyqtSignal(str, float)   # (deck_id, seconds)

    def __init__(self, deck_id: str):
        super().__init__()
        self.deck_id = deck_id
        self.accent_color = get_deck_color(deck_id)
        self.tempo_percent = 0.0
        self._track_duration: float = 0.0

        self.setStyleSheet(
            f"background-color: {COLORS['surface']}; "
            f"border: 1px solid {COLORS['border']}; border-radius: 8px;"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)

        # ── ヘッダー ─────────────────────────────
        header = QHBoxLayout()
        self.deck_label = QLabel(f"DECK {deck_id}")
        self.deck_label.setFont(QFont("Bahnschrift", 14, QFont.Weight.Bold))
        self.deck_label.setStyleSheet(f"color: {self.accent_color}; border: none;")

        self.time_label = QLabel("--:--")
        self.time_label.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.time_label.setStyleSheet(f"color: {COLORS['text']}; border: none;")

        header.addWidget(self.deck_label)
        header.addStretch()
        header.addWidget(self.time_label)
        layout.addLayout(header)

        # ── トラック情報 ──────────────────────────
        self.track_title = QLabel("NO TRACK LOADED")
        self.track_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.track_title.setStyleSheet(f"color: {COLORS['text']}; border: none;")
        layout.addWidget(self.track_title)

        self.track_meta = QLabel("-")
        self.track_meta.setStyleSheet(f"color: {COLORS['text_dim']}; border: none;")
        layout.addWidget(self.track_meta)

        # ── 波形 + VUメーター ─────────────────────
        waveform_row = QHBoxLayout()
        waveform_row.setContentsMargins(0, 0, 0, 0)
        waveform_row.setSpacing(4)

        self.waveform_widget = WaveformWidget(self.accent_color)
        self.waveform_widget.seek_requested.connect(
            lambda t: self.seek_requested.emit(self.deck_id, t)
        )
        self.vu_meter = VUMeterWidget()

        waveform_row.addWidget(self.waveform_widget, stretch=1)
        waveform_row.addWidget(self.vu_meter)
        layout.addLayout(waveform_row)

        # ── DSP 状態表示行 ────────────────────────
        dsp_row = QHBoxLayout()
        dsp_row.setContentsMargins(0, 0, 0, 0)
        dsp_row.setSpacing(6)
        _ds = f"color: {COLORS['text_dim']}; border: none; font-size: 10px; font-family: Consolas;"

        def _lbl(text):
            l = QLabel(text); l.setStyleSheet(_ds); return l

        self.dsp_hi_label     = _lbl("+0.0")
        self.dsp_mid_label    = _lbl("+0.0")
        self.dsp_low_label    = _lbl("+0.0")
        self.dsp_filter_label = _lbl("FLAT")

        for w in (_lbl("HI:"), self.dsp_hi_label,
                  _lbl("MID:"), self.dsp_mid_label,
                  _lbl("LOW:"), self.dsp_low_label,
                  _lbl("FILTER:"), self.dsp_filter_label):
            dsp_row.addWidget(w)
        dsp_row.addStretch()
        layout.addLayout(dsp_row)

        # ── Hot Cues + SYNC ───────────────────────
        cue_row = QHBoxLayout()
        self.hot_cue_btns: list[QPushButton] = []
        for i in range(4):
            btn = QPushButton(f"{i + 1}")
            btn.setFixedSize(32, 22)
            btn.setStyleSheet(
                f"background-color: {COLORS['surface_hover']}; "
                f"color: {COLORS['text_dim']}; "
                f"border: 1px solid {COLORS['border']};"
            )
            btn.setProperty("cue_slot", i)
            self.hot_cue_btns.append(btn)
            cue_row.addWidget(btn)

        self.sync_btn = QPushButton("SYNC")
        self.sync_btn.setCheckable(True)
        self.sync_btn.setFixedSize(60, 22)
        cue_row.addStretch()
        cue_row.addWidget(self.sync_btn)
        layout.addLayout(cue_row)

    # ── 公開 API ─────────────────────────────────

    def update_info(self, info: dict):
        if not info:
            return
        self.track_title.setText(info.get('filename', 'Unknown'))
        bpm    = info.get('bpm', 0.0)
        key    = info.get('key', '-')
        energy = info.get('energy', {}).get('numeric', 0.0)
        self.track_meta.setText(
            f"{info.get('genre', '-').upper()} | {bpm:.1f} BPM | KEY: {key} | LVL: {energy:.1f}"
        )

    def update_time(self, position: float, duration: float):
        self._track_duration = duration
        mins, secs = divmod(int(position), 60)
        self.time_label.setText(f"{mins:02d}:{secs:02d}")
        self.waveform_widget.set_position(position, duration)

    def set_waveform(self, waveform_data, duration: float = 0.0):
        """波形データを描画する。duration を渡すと X 軸スケールが正確になる。"""
        if duration > 0:
            # set_waveform より先に _duration を確定させる
            self.waveform_widget._duration = duration
            self._track_duration = duration
        self.waveform_widget.set_waveform(waveform_data)

    def update_hot_cues(self, times: list[Optional[float]]):
        """HOT CUE 時間リスト（秒, None=未設定）を波形に反映。ボタン色も更新。"""
        self.waveform_widget.set_hot_cues(times)
        for i, (btn, t) in enumerate(zip(self.hot_cue_btns, times)):
            if t is not None:
                btn.setStyleSheet(
                    f"background-color: {HOT_CUE_COLORS[i]}; "
                    f"color: #000000; border: 1px solid {HOT_CUE_COLORS[i]};"
                )
            else:
                btn.setStyleSheet(
                    f"background-color: {COLORS['surface_hover']}; "
                    f"color: {COLORS['text_dim']}; "
                    f"border: 1px solid {COLORS['border']};"
                )

    def update_vu(self, left: float, right: float):
        self.vu_meter.update_level(left, right)

    def update_dsp(self, eq_high: float, eq_mid: float, eq_low: float, filter_val: float):
        _ds_base = "border: none; font-size: 10px; font-family: Consolas;"

        def _db_text(v):  return f"+{v:.1f}" if v >= 0 else f"{v:.1f}"
        def _db_color(v): return '#ff6b6b' if v > 1.0 else ('#4fc3f7' if v < -1.0 else COLORS['text_dim'])

        for label, val in ((self.dsp_hi_label, eq_high),
                           (self.dsp_mid_label, eq_mid),
                           (self.dsp_low_label, eq_low)):
            label.setText(_db_text(val))
            label.setStyleSheet(f"color: {_db_color(val)}; {_ds_base}")

        if filter_val < -0.02:
            f_text, f_color = f"HPF {abs(filter_val)*100:.0f}%", '#ce93d8'
        elif filter_val > 0.02:
            f_text, f_color = f"LPF {filter_val*100:.0f}%", '#80cbc4'
        else:
            f_text, f_color = "FLAT", COLORS['text_dim']
        self.dsp_filter_label.setText(f_text)
        self.dsp_filter_label.setStyleSheet(f"color: {f_color}; {_ds_base}")

    def set_highlight(self, highlight: bool):
        bw = "2px" if highlight else "1px"
        self.setStyleSheet(
            f"DeckWidget {{ background-color: {COLORS['surface']}; "
            f"border: {bw} solid {self.accent_color}; border-radius: 8px; }}"
        )

    def update_loop_state(self, active: bool, start: float, duration: float, total: float):
        """ループ状態を波形に反映（引数は絶対秒）。"""
        self.waveform_widget.set_loop(active, start, duration, total)

    def set_beat_grid(self, beat_times: list[float]):
        """ビートグリッドを波形ウィジェットに設定する（P-02）。"""
        if hasattr(self.waveform_widget, 'set_beat_grid'):
            self.waveform_widget.set_beat_grid(beat_times)
