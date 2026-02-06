"""
Deck Widget (Phase 9 Final: High Contrast)
==========================================
Fixes:
- Forced White color for Track Title and Time.
- Improved visibility on dark background.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QHBoxLayout, QFrame, 
    QGraphicsDropShadowEffect, QPushButton
)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QFont, QPainter, QColor, QPen, QBrush, QPolygonF
)
import numpy as np
from typing import Optional

from gui_styles import COLORS, get_deck_color


class WaveformWidget(QWidget):
    def __init__(self, accent_color: str):
        super().__init__()
        self.accent_color = accent_color
        self.waveform_data: Optional[np.ndarray] = None
        self.position_ratio: float = 0.0
        self.normalization_factor: float = 1.0
        
        # Loop State
        self.loop_active = False
        self.loop_start_ratio = 0.0
        self.loop_width_ratio = 0.0
        
        self.setMinimumHeight(80)
        
    def set_waveform(self, waveform: Optional[np.ndarray]):
        self.waveform_data = waveform
        self.normalization_factor = 1.0
        if self.waveform_data is not None and len(self.waveform_data) > 0:
            try:
                max_val = np.max(np.abs(self.waveform_data))
                if max_val > 0:
                    self.normalization_factor = 1.0 / max_val
            except Exception as e:
                self.normalization_factor = 1.0
        self.update()
    
    def set_position(self, position: float, duration: float):
        if duration > 0:
            self.position_ratio = position / duration
        else:
            self.position_ratio = 0.0
        self.update()

    def set_loop(self, active: bool, start: float, duration: float, track_duration: float):
        self.loop_active = active
        if active and track_duration > 0:
            self.loop_start_ratio = start / track_duration
            self.loop_width_ratio = duration / track_duration
        else:
            self.loop_start_ratio = 0.0
            self.loop_width_ratio = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        painter.fillRect(self.rect(), QColor(COLORS['waveform_bg']))
        
        width = self.width()
        height = self.height()
        mid_y = height / 2
        
        # Grid
        painter.setPen(QPen(QColor(COLORS['waveform_grid']), 1, Qt.PenStyle.DotLine))
        painter.drawLine(0, int(mid_y), width, int(mid_y))
        for i in range(1, 4):
            x = i * (width / 4)
            painter.drawLine(int(x), 0, int(x), height)
            
        # Waveform
        if self.waveform_data is not None and len(self.waveform_data) > 0:
            color = QColor(self.accent_color)
            painter.setPen(QPen(color, 1))
            painter.setBrush(QBrush(color))
            
            points = []
            sample_count = len(self.waveform_data)
            step = max(1, sample_count // width)
            display_data = self.waveform_data[::step]
            
            for x, val in enumerate(display_data):
                if x >= width: break
                h = val * self.normalization_factor * (height / 2) * 0.9
                points.append(QPointF(x, mid_y - h))
            
            for x in range(len(display_data) - 1, -1, -1):
                if x >= width: continue
                val = display_data[x]
                h = val * self.normalization_factor * (height / 2) * 0.9
                points.append(QPointF(x, mid_y + h))
            
            painter.drawPolygon(QPolygonF(points))

        # Loop Region
        if self.loop_active:
            lx = self.loop_start_ratio * width
            lw = self.loop_width_ratio * width
            
            loop_color = QColor(self.accent_color)
            loop_color.setAlpha(60)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(loop_color))
            painter.drawRect(int(lx), 0, int(lw), height)
            
            painter.setPen(QPen(QColor(self.accent_color), 2))
            painter.drawLine(int(lx), 0, int(lx), height)
            painter.drawLine(int(lx + lw), 0, int(lx + lw), height)
            
            painter.setPen(QPen(QColor('#ffffff'), 1))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(int(lx) + 4, 12, "LOOP")

        # Playhead
        px = self.position_ratio * width
        painter.setPen(QPen(QColor('#ffffff'), 2))
        painter.drawLine(int(px), 0, int(px), height)


class DeckWidget(QFrame):
    def __init__(self, deck_id: str):
        super().__init__()
        self.deck_id = deck_id
        self.accent_color = get_deck_color(deck_id)
        
        self.current_bpm = 0.0
        self.tempo_percent = 0.0
        self.loop_active = False
        
        # Force styles for visibility
        self.setStyleSheet(f"""
            DeckWidget {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
            QLabel {{ color: {COLORS['text']}; }}
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)
        
        # Header
        header = QHBoxLayout()
        deck_label = QLabel(f"DECK {deck_id}")
        deck_label.setFont(QFont("Bahnschrift", 14, QFont.Weight.Bold))
        deck_label.setStyleSheet(f"color: {self.accent_color};")
        
        self.time_label = QLabel("--:--")
        self.time_label.setFont(QFont("Consolas", 14, QFont.Weight.Bold))
        self.time_label.setStyleSheet(f"color: {COLORS['text']};") # Force White
        
        header.addWidget(deck_label)
        header.addStretch()
        header.addWidget(self.time_label)
        layout.addLayout(header)
        
        # Track Info
        self.track_title = QLabel("NO TRACK LOADED")
        self.track_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.track_title.setWordWrap(True)
        self.track_title.setStyleSheet(f"color: {COLORS['text']};") # Force White
        layout.addWidget(self.track_title)
        
        self.track_meta = QLabel("-")
        self.track_meta.setFont(QFont("Segoe UI", 9))
        self.track_meta.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.track_meta)
        
        # Waveform
        self.waveform_widget = WaveformWidget(self.accent_color)
        layout.addWidget(self.waveform_widget)
        
        # HOT CUE Buttons (Phase 8C)
        cue_row = QHBoxLayout()
        cue_row.setSpacing(3)
        cue_row.setContentsMargins(0, 2, 0, 0)  # 上に2pxマージン
        self.hot_cue_btns = []
        for i in range(4):
            btn = QPushButton(f"{i+1}")  # "CUE 1" → "1" でコンパクト化
            btn.setFixedSize(32, 22)  # 幅32px, 高さ22pxに縮小
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['surface_hover']};
                    border: 1px solid {COLORS['border']};
                    color: {COLORS['text_dim']};
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['border']};
                    color: {COLORS['text']};
                }}
            """)
            # ツールチップで説明表示
            btn.setToolTip(f"HOT CUE {i+1}\nClick: Trigger | Shift+Click: Set | Ctrl+Click: Clear")
            btn.setProperty("cue_slot", i)
            btn.setProperty("deck_id", deck_id)
            self.hot_cue_btns.append(btn)
            cue_row.addWidget(btn)
        cue_row.addStretch()  # 右側にスペース追加
        layout.addLayout(cue_row)
        
        # Sync/Loop Button
        self.sync_btn = QPushButton("SYNC")
        self.sync_btn.setCheckable(True)
        self.sync_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['surface_hover']};
                border: 1px solid {COLORS['border']};
                color: {COLORS['text_dim']};
                border-radius: 4px;
                padding: 4px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background-color: {self.accent_color};
                color: #000000;
                border: 1px solid {self.accent_color};
            }}
        """)
        layout.addWidget(self.sync_btn, alignment=Qt.AlignmentFlag.AlignRight)
        
        self.setLayout(layout)
        
        # Shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(15)
        shadow.setColor(QColor(0, 0, 0, 80))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    def update_info(self, info: dict):
        if not info: return
        filename = info.get('filename', 'Unknown')
        bpm = info.get('bpm', 0.0)
        self.current_bpm = bpm
        genre = info.get('genre', '-')
        key = info.get('key', '-')
        energy_val = info.get('energy', {}).get('numeric', 0.0)
        
        effective_bpm = bpm * (1.0 + self.tempo_percent / 100.0)
        
        self.track_title.setText(filename)
        if abs(self.tempo_percent) > 0.1:
            bpm_str = f"{bpm:.1f}â†’{effective_bpm:.1f} BPM"
        else:
            bpm_str = f"{bpm:.1f} BPM"
        
        self.track_meta.setText(f"{genre.upper()} | {bpm_str} | KEY: {key} | LVL: {energy_val:.1f}")

    def update_time(self, position: float, duration: float):
        mins = int(position // 60)
        secs = int(position % 60)
        self.time_label.setText(f"{mins:02d}:{secs:02d}")
        self.waveform_widget.set_position(position, duration)

    def set_waveform(self, waveform_data: Optional[np.ndarray]):
        self.waveform_widget.set_waveform(waveform_data)

    def update_loop_state(self, active: bool, start: float, duration: float, track_duration: float):
        self.loop_active = active
        self.waveform_widget.set_loop(active, start, duration, track_duration)
        
        current_text = self.track_meta.text().split(" | LOOP")[0]
        if active:
            self.track_meta.setText(f"{current_text} | LOOP ON")
            self.track_meta.setStyleSheet(f"color: {self.accent_color}; font-weight: bold;")
        else:
            self.track_meta.setText(current_text)
            self.track_meta.setStyleSheet(f"color: {COLORS['text_dim']};")

    def clear(self):
        self.track_title.setText("NO TRACK LOADED")
        self.track_meta.setText("-")
        self.time_label.setText("--:--")
        self.waveform_widget.set_waveform(None)
        self.waveform_widget.set_loop(False, 0, 0, 0)

    def set_highlight(self, highlight: bool):
        if highlight:
            self.setStyleSheet(f"""
                DeckWidget {{
                    background-color: {COLORS['surface']};
                    border: 2px solid {self.accent_color};
                    border-radius: 12px;
                }}
                QLabel {{ color: {COLORS['text']}; }}
            """)
        else:
            self.setStyleSheet(f"""
                DeckWidget {{
                    background-color: {COLORS['surface']};
                    border: 1px solid {COLORS['border']};
                    border-radius: 8px;
                }}
                QLabel {{ color: {COLORS['text']}; }}
            """)