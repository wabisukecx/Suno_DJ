"""
Library Panel (Phase 9 Final: High Contrast)
============================================
修正内容:
- AttributeError: 'LibraryPanel' object has no attribute 'set_compatible_keys' を解決
- 文字化けの完全除去と日本語コメントの修復
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, 
    QTableWidgetItem, QHeaderView, QLineEdit, QPushButton, QFrame,
    QMenu, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from gui.gui_styles import COLORS, STYLESHEETS

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
        
        # ツールバー
        toolbar = QHBoxLayout()
        title = QLabel("LIBRARY")
        title.setFont(QFont("Bahnschrift", 12, QFont.Weight.Bold))
        toolbar.addWidget(title)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search tracks...")
        self.search_bar.setStyleSheet(STYLESHEETS['search_edit'])
        self.search_bar.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_bar)
        
        refresh_btn = QPushButton("↻") # 更新アイコン
        refresh_btn.setToolTip("Refresh Library")
        refresh_btn.setStyleSheet(STYLESHEETS['icon_button'])
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        toolbar.addWidget(refresh_btn)
        
        layout.addLayout(toolbar)
        
        # テーブル設定
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Title", "BPM", "Key", "Energy", "Genre"])
        self.table.setStyleSheet(STYLESHEETS['library_table'])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        
        self.table.itemDoubleClicked.connect(self._on_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        self.setLayout(layout)
        
        self.all_tracks = []
        self.compatible_keys = [] # 互換性のあるCamelotキーのリスト

    def update_library(self, tracks: list):
        """トラックリストの描画更新"""
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
            
            # Key (互換性チェック)
            key_str = t.get('key', '-')
            key_item = QTableWidgetItem(key_str)
            
            # Key表記からCamelotコードを抽出 (Phase R4: CamelotWheel使用)
            try:
                from core.camelot_wheel import CamelotWheel
                track_camelot = CamelotWheel().to_camelot(key_str)
            except Exception:
                track_camelot = key_str.split(' ')[0]  # 簡易フォールバック
            
            if track_camelot in self.compatible_keys:
                # 互換キーは明るい緑でハイライト
                key_item.setForeground(QColor('#00ff88')) 
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
        Mixerから送られてくる互換キーリストを保持し、表示を更新する
        これが無いと app.py でエラーになります
        """
        self.compatible_keys = compatible
        # 表示中のリストにハイライトを即時反映
        self.update_library(self.all_tracks)

    def _on_search_changed(self, text: str):
        search_text = text.lower().strip()
        if not search_text:
            self._display_filtered_tracks(self.all_tracks)
        else:
            filtered = [
                t for t in self.all_tracks 
                if search_text in f"{t.get('filename','')} {t.get('genre','')}".lower()
            ]
            self._display_filtered_tracks(filtered)

    def _display_filtered_tracks(self, tracks: list):
        """フィルタリング結果の表示（内部用）"""
        # 現在の互換キー設定を維持したまま再描画
        self.update_library(tracks)

    def select_by_index(self, index: int):
        if 0 <= index < self.table.rowCount():
            self.table.selectRow(index)
            self.table.scrollToItem(self.table.item(index, 0))

    def _on_double_clicked(self, item):
        row = item.row()
        if 0 <= row < len(self.all_tracks):
            track = self.all_tracks[row]
            modifiers = QApplication.keyboardModifiers()
            deck_id = "B" if modifiers == Qt.KeyboardModifier.ShiftModifier else "A"
            self.load_track_requested.emit(deck_id, track['filepath'])
    
    def _show_context_menu(self, position):
        item = self.table.itemAt(position)
        if item is None: return
        
        row = item.row()
        track = self.all_tracks[row]
        
        menu = QMenu(self)
        load_a = menu.addAction("Load to Deck A")
        load_b = menu.addAction("Load to Deck B")
        menu.addSeparator()
        menu.addAction(f"BPM: {track.get('bpm', '---')}").setEnabled(False)
        
        action = menu.exec(self.table.viewport().mapToGlobal(position))
        if action == load_a:
            self.load_track_requested.emit("A", track['filepath'])
        elif action == load_b:
            self.load_track_requested.emit("B", track['filepath'])