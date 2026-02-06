"""
Energy Flow Panel (Split View)
==============================
Deck A/B を上下に分割表示し、時間軸を同期。
相対評価による「見た目の音量差」の誤解を防ぐ。
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from gui_styles import COLORS

try:
    import pyqtgraph as pg
    PYQTGRAPH_AVAILABLE = True
except ImportError:
    PYQTGRAPH_AVAILABLE = False
    pg = None


class EnergyFlowPanel(QFrame):
    """
    エネルギーフロー可視化パネル
    Deck A/B を上下2段に分けて表示（X軸同期）
    """
    
    def __init__(self):
        super().__init__()
        
        self.setStyleSheet(f"""
            EnergyFlowPanel {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
            }}
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(1, 1, 1, 1)
        
        # === ヘッダー ===
        self._create_header(layout)
        
        # === グラフ表示 ===
        if PYQTGRAPH_AVAILABLE:
            self._create_split_graph_display(layout)
        else:
            self._create_ascii_display(layout)
        
        self.setLayout(layout)
        
        # 内部状態
        self._deck_a_profile = []
        self._deck_b_profile = []
        self._deck_a_position = 0.0
        self._deck_b_position = 0.0
        self._deck_a_duration = 0.0
        self._deck_b_duration = 0.0
    
    def _create_header(self, parent_layout):
        header_widget = QFrame()
        header_widget.setStyleSheet(f"background-color: {COLORS['surface']}; border-bottom: 1px solid {COLORS['border']};")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        title = QLabel("ENERGY FLOW (STRUCTURE)")
        title.setFont(QFont("Bahnschrift", 9, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {COLORS['text_dim']}; border: none;")
        header_layout.addWidget(title)
        
        header_layout.addStretch()
        
        # Deck A Label
        self.deck_a_energy_label = QLabel("A: -")
        self.deck_a_energy_label.setFont(QFont("Bahnschrift", 9, QFont.Weight.Bold))
        self.deck_a_energy_label.setStyleSheet(f"color: {COLORS['deck_a']}; border: none;")
        header_layout.addWidget(self.deck_a_energy_label)
        
        # Spacer
        spacer = QLabel(" | ")
        spacer.setStyleSheet(f"color: {COLORS['border']}; border: none;")
        header_layout.addWidget(spacer)
        
        # Deck B Label
        self.deck_b_energy_label = QLabel("B: -")
        self.deck_b_energy_label.setFont(QFont("Bahnschrift", 9, QFont.Weight.Bold))
        self.deck_b_energy_label.setStyleSheet(f"color: {COLORS['deck_b']}; border: none;")
        header_layout.addWidget(self.deck_b_energy_label)
        
        parent_layout.addWidget(header_widget)
    
    def _create_split_graph_display(self, parent_layout):
        # GraphicsLayoutWidget を使用して複数のプロットを配置
        self.graph_layout = pg.GraphicsLayoutWidget()
        self.graph_layout.setBackground(COLORS['background'])
        
        # --- 上段: Deck A ---
        self.plot_a = self.graph_layout.addPlot(row=0, col=0)
        self.plot_a.setMouseEnabled(x=True, y=False)
        self.plot_a.hideAxis('left')
        self.plot_a.hideAxis('bottom') # 中間の軸は隠す
        self.plot_a.setYRange(0, 5.5)
        self.plot_a.showGrid(x=True, y=False, alpha=0.3)
        
        # Deck A 曲線（塗りつぶしあり）
        self.energy_curve_a = self.plot_a.plot(
            pen=pg.mkPen(color=COLORS['deck_a'], width=1),
            fillLevel=0,
            brush=pg.mkBrush(color=f"{COLORS['deck_a']}40") # 半透明
        )
        # マーカー
        self.marker_a = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color='#ffffff', width=1))
        self.plot_a.addItem(self.marker_a)
        
        # --- 下段: Deck B ---
        self.graph_layout.nextRow()
        self.plot_b = self.graph_layout.addPlot(row=1, col=0)
        self.plot_b.setMouseEnabled(x=True, y=False)
        self.plot_b.hideAxis('left')
        
        # X軸同期（重要：AをズームするとBもズーム）
        self.plot_b.setXLink(self.plot_a)
        self.plot_b.setYRange(0, 5.5)
        self.plot_b.showGrid(x=True, y=False, alpha=0.3)
        
        # Deck B 曲線
        self.energy_curve_b = self.plot_b.plot(
            pen=pg.mkPen(color=COLORS['deck_b'], width=1),
            fillLevel=0,
            brush=pg.mkBrush(color=f"{COLORS['deck_b']}40")
        )
        # マーカー
        self.marker_b = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(color='#ffffff', width=1))
        self.plot_b.addItem(self.marker_b)
        
        parent_layout.addWidget(self.graph_layout)
    
    def _create_ascii_display(self, parent_layout):
        self.ascii_display = QTextEdit()
        self.ascii_display.setReadOnly(True)
        self.ascii_display.setMinimumHeight(200)
        parent_layout.addWidget(self.ascii_display)
    
    def update_deck_energy_profile(self, deck: str, profile: list, duration: float = 0.0):
        if deck == "A":
            self._deck_a_profile = profile
            self._deck_a_duration = duration
        else:
            self._deck_b_profile = profile
            self._deck_b_duration = duration
        
        if PYQTGRAPH_AVAILABLE:
            self._update_graph()
    
    def update_deck_position(self, deck: str, position: float, duration: float):
        if deck == "A":
            self._deck_a_position = position
            self._deck_a_duration = duration
        else:
            self._deck_b_position = position
            self._deck_b_duration = duration
        
        if PYQTGRAPH_AVAILABLE:
            self._update_markers()
            self._update_energy_labels()
    
    def _update_graph(self):
        if not PYQTGRAPH_AVAILABLE: return
        
        # Deck A
        if self._deck_a_profile:
            x_a = [p['time'] for p in self._deck_a_profile]
            y_a = [p['level'] for p in self._deck_a_profile]
            self.energy_curve_a.setData(x_a, y_a)
        else:
            self.energy_curve_a.setData([], [])
            
        # Deck B
        if self._deck_b_profile:
            x_b = [p['time'] for p in self._deck_b_profile]
            y_b = [p['level'] for p in self._deck_b_profile]
            self.energy_curve_b.setData(x_b, y_b)
        else:
            self.energy_curve_b.setData([], [])
            
        # X軸範囲の自動調整（長い方の曲に合わせる）
        max_dur = 60.0
        if self._deck_a_profile: max_dur = max(max_dur, self._deck_a_profile[-1]['time'])
        if self._deck_b_profile: max_dur = max(max_dur, self._deck_b_profile[-1]['time'])
        
        self.plot_a.setXRange(0, max_dur)
        # plot_bはLinkされているので自動追従するが、念のため
        # self.plot_b.setXRange(0, max_dur) 
    
    def _update_markers(self):
        if not PYQTGRAPH_AVAILABLE: return
        
        # A
        if self._deck_a_position >= 0:
            self.marker_a.setValue(self._deck_a_position)
            self.marker_a.setVisible(True)
        
        # B
        if self._deck_b_position >= 0:
            self.marker_b.setValue(self._deck_b_position)
            self.marker_b.setVisible(True)
            
    def _update_energy_labels(self):
        # A
        if self._deck_a_profile:
            val = self._get_level_at_position(self._deck_a_profile, self._deck_a_position)
            self.deck_a_energy_label.setText(f"A: {val:.1f}")
        else:
            self.deck_a_energy_label.setText("A: -")
            
        # B
        if self._deck_b_profile:
            val = self._get_level_at_position(self._deck_b_profile, self._deck_b_position)
            self.deck_b_energy_label.setText(f"B: {val:.1f}")
        else:
            self.deck_b_energy_label.setText("B: -")

    def _get_level_at_position(self, profile: list, position: float) -> float:
        if not profile: return 0.0
        import bisect
        times = [p['time'] for p in profile]
        idx = bisect.bisect_right(times, position)
        if idx == 0: return profile[0]['level']
        if idx >= len(profile): return profile[-1]['level']
        return profile[idx-1]['level']

    def clear(self):
        self._deck_a_profile = []
        self._deck_b_profile = []
        if PYQTGRAPH_AVAILABLE:
            self.energy_curve_a.setData([], [])
            self.energy_curve_b.setData([], [])
    
    # 後方互換性
    def update_energy_data(self, data): pass
    def clear_deck(self, deck): pass