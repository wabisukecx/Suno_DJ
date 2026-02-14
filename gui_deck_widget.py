"""
Deck Widget (Phase 9 Final: High Contrast)
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFrame, 
    QPushButton
)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QFont, QPainter, QColor, QPen, QBrush, QPolygonF
import numpy as np
from typing import Optional
from gui_styles import COLORS, get_deck_color

class WaveformWidget(QWidget):
    def __init__(self, accent_color: str):
        super().__init__()
        self.accent_color = accent_color
        self.waveform_data: Optional[np.ndarray] = None
        self.position_ratio: float = 0.0
        self.normalization_factor = 1.0
        self.loop_active = False
        self.loop_start_ratio = 0.0
        self.loop_width_ratio = 0.0
        self.setMinimumHeight(100)
        self.setMaximumHeight(140)
        
    def set_waveform(self, waveform: Optional[np.ndarray]):
        self.waveform_data = waveform
        if self.waveform_data is not None and len(self.waveform_data) > 0:
            max_val = np.max(np.abs(self.waveform_data))
            self.normalization_factor = 1.0 / max_val if max_val > 0 else 1.0
        self.update()
    
    def set_position(self, position: float, duration: float):
        self.position_ratio = position / duration if duration > 0 else 0.0
        self.update()

    def set_loop(self, active: bool, start: float, duration: float, track_duration: float):
        self.loop_active = active
        if active and track_duration > 0:
            self.loop_start_ratio = start / track_duration
            self.loop_width_ratio = duration / track_duration
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(COLORS['waveform_bg']))
        
        width, height = self.width(), self.height()
        mid_y = height / 2
        
        # Grid
        painter.setPen(QPen(QColor(COLORS['waveform_grid']), 1, Qt.PenStyle.DotLine))
        painter.drawLine(0, int(mid_y), width, int(mid_y))
        
        # Waveform Drawing
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
            for x in range(len(points)-1, -1, -1):
                p = points[x]
                points.append(QPointF(p.x(), mid_y + (mid_y - p.y())))
            painter.drawPolygon(QPolygonF(points))

        # Loop & Playhead
        if self.loop_active:
            lx, lw = self.loop_start_ratio * width, self.loop_width_ratio * width
            loop_color = QColor(self.accent_color)
            loop_color.setAlpha(60)
            painter.fillRect(int(lx), 0, int(lw), height, loop_color)
            
        px = self.position_ratio * width
        painter.setPen(QPen(QColor('#ffffff'), 2))
        painter.drawLine(int(px), 0, int(px), height)

class DeckWidget(QFrame):
    def __init__(self, deck_id: str):
        super().__init__()
        self.deck_id = deck_id
        self.accent_color = get_deck_color(deck_id)
        self.tempo_percent = 0.0
        
        self.setStyleSheet(f"background-color: {COLORS['surface']}; border: 1px solid {COLORS['border']}; border-radius: 8px;")
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        
        # Header (Deck Name & Time)
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
        
        # Track Info
        self.track_title = QLabel("NO TRACK LOADED")
        self.track_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.track_title.setStyleSheet(f"color: {COLORS['text']}; border: none;")
        layout.addWidget(self.track_title)
        
        self.track_meta = QLabel("-")
        self.track_meta.setStyleSheet(f"color: {COLORS['text_dim']}; border: none;")
        layout.addWidget(self.track_meta)
        
        # Waveform
        self.waveform_widget = WaveformWidget(self.accent_color)
        layout.addWidget(self.waveform_widget)
        
        # Hot Cues
        cue_row = QHBoxLayout()
        self.hot_cue_btns = []
        for i in range(4):
            btn = QPushButton(f"{i+1}")
            btn.setFixedSize(32, 22)
            btn.setStyleSheet(f"background-color: {COLORS['surface_hover']}; color: {COLORS['text_dim']}; border: 1px solid {COLORS['border']};")
            btn.setProperty("cue_slot", i)
            self.hot_cue_btns.append(btn)
            cue_row.addWidget(btn)
        
        self.sync_btn = QPushButton("SYNC")
        self.sync_btn.setCheckable(True)
        self.sync_btn.setFixedSize(60, 22)
        cue_row.addStretch()
        cue_row.addWidget(self.sync_btn)
        layout.addLayout(cue_row)

    def update_info(self, info: dict):
        if not info: return
        self.track_title.setText(info.get('filename', 'Unknown'))
        bpm = info.get('bpm', 0.0)
        key = info.get('key', '-')
        energy = info.get('energy', {}).get('numeric', 0.0)
        self.track_meta.setText(f"{info.get('genre', '-').upper()} | {bpm:.1f} BPM | KEY: {key} | LVL: {energy:.1f}")

    def update_time(self, position: float, duration: float):
        mins, secs = divmod(int(position), 60)
        self.time_label.setText(f"{mins:02d}:{secs:02d}")
        self.waveform_widget.set_position(position, duration)

    def set_waveform(self, waveform_data):
        self.waveform_widget.set_waveform(waveform_data)

    def set_highlight(self, highlight: bool):
        border_width = "2px" if highlight else "1px"
        self.setStyleSheet(f"DeckWidget {{ background-color: {COLORS['surface']}; border: {border_width} solid {self.accent_color}; border-radius: 8px; }}")
    
    def update_loop_state(self, active: bool, start: float, duration: float, total: float):
        """
        ループ状態を更新（Phase 8C Loop Upgrade対応）
        
        Args:
            active: ループが有効かどうか
            start: ループ開始位置（秒）
            duration: ループ長（秒）
            total: トラック全体の長さ（秒）
        """
        self.waveform_widget.set_loop(active, start, duration, total)