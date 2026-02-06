"""
Library Panel (Phase 9 Final: High Contrast)
============================================
Fixes:
- Applied consistent white text styling to library list.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QLineEdit, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from gui_styles import COLORS, STYLESHEETS

class LibraryPanel(QFrame):
    load_track_requested = pyqtSignal(str, str) # deck_id, filepath
    analyze_track_requested = pyqtSignal(str)
    bpm_update_requested = pyqtSignal(str, float)
    refresh_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        
        self.setStyleSheet(f"""
            LibraryPanel {{
                background-color: {COLORS['surface']};
                border-top: 1px solid {COLORS['border']};
            }}
            QLabel {{ color: {COLORS['text']}; }}
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("LIBRARY")
        title.setFont(QFont("Bahnschrift", 12, QFont.Weight.Bold))
        toolbar.addWidget(title)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search tracks...")
        self.search_bar.setStyleSheet(STYLESHEETS['search_edit'])
        toolbar.addWidget(self.search_bar)
        
        refresh_btn = QPushButton("â†»")
        refresh_btn.setToolTip("Refresh Library")
        refresh_btn.setStyleSheet(STYLESHEETS['icon_button'])
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        toolbar.addWidget(refresh_btn)
        
        layout.addLayout(toolbar)
        
        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Title", "BPM", "Key", "Energy", "Genre"])
        self.table.setStyleSheet(STYLESHEETS['library_table'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        
        layout.addWidget(self.table)
        self.setLayout(layout)
        
        self.all_tracks = []
        self.compatible_keys = []  # Phase 8C Week 2: 互換キーリスト

    def update_library(self, tracks: list):
        self.all_tracks = tracks
        self.table.setRowCount(len(tracks))
        
        for i, t in enumerate(tracks):
            # Title
            title_item = QTableWidgetItem(t.get('filename', 'Unknown'))
            title_item.setForeground(QColor(COLORS['text']))
            self.table.setItem(i, 0, title_item)
            
            # BPM
            bpm_val = t.get('bpm', 0.0)
            bpm_item = QTableWidgetItem(f"{bpm_val:.1f}")
            bpm_item.setForeground(QColor(COLORS['text_dim']))
            self.table.setItem(i, 1, bpm_item)
            
            # Key (互換性チェック - Phase 8C Week 2)
            key_str = t.get('key', '-')
            key_item = QTableWidgetItem(key_str)
            
            # Camelotキーを抽出して互換性判定
            from track_analyzer import extract_camelot_from_key
            track_camelot = extract_camelot_from_key(key_str)
            
            if track_camelot in self.compatible_keys:
                # 互換キーの場合は緑色でハイライト
                key_item.setForeground(QColor('#00ff88'))  # 明るい緑
                key_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            else:
                key_item.setForeground(QColor(COLORS['text_dim']))
            
            self.table.setItem(i, 2, key_item)
            
            # Energy
            energy_val = t.get('energy', {}).get('numeric', 0.0)
            energy_item = QTableWidgetItem(f"{energy_val:.1f}")
            energy_item.setForeground(QColor(COLORS['accent']))
            self.table.setItem(i, 3, energy_item)
            
            # Genre
            genre_item = QTableWidgetItem(t.get('genre', '-'))
            genre_item.setForeground(QColor(COLORS['text_dim']))
            self.table.setItem(i, 4, genre_item)
    
    def set_compatible_keys(self, compatible: list):
        """
        互換キーリストを設定してライブラリ表示を更新（Phase 8C Week 2）
        Args:
            compatible: 互換キーのリスト（例: ['8A', '7A', '9A', '8B']）
        """
        self.compatible_keys = compatible
        # ライブラリ表示を更新（ハイライトを反映）
        self.update_library(self.all_tracks)

    def select_by_index(self, index: int):
        if 0 <= index < self.table.rowCount():
            self.table.selectRow(index)
            self.table.scrollToItem(self.table.item(index, 0))

    def _on_double_clicked(self, item):
        row = item.row()
        if 0 <= row < len(self.all_tracks):
            track = self.all_tracks[row]
            # Default to Deck A on double click, or logic can be added
            self.load_track_requested.emit("A", track['filepath'])