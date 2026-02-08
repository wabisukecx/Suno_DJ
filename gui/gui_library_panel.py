"""
Library Panel (Phase 9 Final: High Contrast)
============================================
Fixes:
- Applied consistent white text styling to library list.
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
        
        # Toolbar
        toolbar = QHBoxLayout()
        title = QLabel("LIBRARY")
        title.setFont(QFont("Bahnschrift", 12, QFont.Weight.Bold))
        toolbar.addWidget(title)
        
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search tracks...")
        self.search_bar.setStyleSheet(STYLESHEETS['search_edit'])
        self.search_bar.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_bar)
        
        refresh_btn = QPushButton("ÃƒÂ¢Ã¢â‚¬Â Ã‚Â»")
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
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._show_context_menu)
        
        layout.addWidget(self.table)
        self.setLayout(layout)
        
        self.all_tracks = []
        self.compatible_keys = []  # Phase 8C Week 2: Ã¤Âºâ€™Ã¦Ââ€ºÃ£â€šÂ­Ã£Æ’Â¼Ã£Æ’ÂªÃ£â€šÂ¹Ã£Æ’Ë†

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
            
            # Key (Ã¤Âºâ€™Ã¦Ââ€ºÃ¦â‚¬Â§Ã£Æ’ÂÃ£â€šÂ§Ã£Æ’Æ’Ã£â€šÂ¯ - Phase 8C Week 2)
            key_str = t.get('key', '-')
            key_item = QTableWidgetItem(key_str)
            
            # CamelotÃ£â€šÂ­Ã£Æ’Â¼Ã£â€šâ€™Ã¦Å Â½Ã¥â€¡ÂºÃ£Ââ€”Ã£ÂÂ¦Ã¤Âºâ€™Ã¦Ââ€ºÃ¦â‚¬Â§Ã¥Ë†Â¤Ã¥Â®Å¡
            from core.track_analyzer import extract_camelot_from_key
            track_camelot = extract_camelot_from_key(key_str)
            
            if track_camelot in self.compatible_keys:
                # Ã¤Âºâ€™Ã¦Ââ€ºÃ£â€šÂ­Ã£Æ’Â¼Ã£ÂÂ®Ã¥Â Â´Ã¥ÂË†Ã£ÂÂ¯Ã§Â·â€˜Ã¨â€°Â²Ã£ÂÂ§Ã£Æ’ÂÃ£â€šÂ¤Ã£Æ’Â©Ã£â€šÂ¤Ã£Æ’Ë†
                key_item.setForeground(QColor('#00ff88'))  # Ã¦ËœÅ½Ã£â€šâ€¹Ã£Ââ€žÃ§Â·â€˜
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
    

    def _on_search_changed(self, text: str):
        """æ¤œç´¢ãƒ†ã‚­ã‚¹ãƒˆãŒå¤‰æ›´ã•ã‚ŒãŸã¨ãã®ãƒ•ã‚£ãƒ«ã‚¿ãƒªãƒ³ã‚°"""
        search_text = text.lower().strip()
        
        if not search_text:
            # æ¤œç´¢ãƒ†ã‚­ã‚¹ãƒˆãŒç©ºã®å ´åˆã¯å…¨ãƒˆãƒ©ãƒƒã‚¯ã‚’è¡¨ç¤º
            self._display_tracks(self.all_tracks)
        else:
            # æ¤œç´¢æ¡ä»¶ã«ãƒžãƒƒãƒã™ã‚‹ãƒˆãƒ©ãƒƒã‚¯ã®ã¿è¡¨ç¤º
            filtered = []
            for track in self.all_tracks:
                # ãƒ•ã‚¡ã‚¤ãƒ«åã€BPMã€Keyã€Genreã§æ¤œç´¢
                searchable = f"{track.get('filename', '')} {track.get('bpm', '')} {track.get('key', '')} {track.get('genre', '')}".lower()
                if search_text in searchable:
                    filtered.append(track)
            self._display_tracks(filtered)
    
    def _display_tracks(self, tracks: list):
        """ãƒˆãƒ©ãƒƒã‚¯ãƒªã‚¹ãƒˆã‚’ãƒ†ãƒ¼ãƒ–ãƒ«ã«è¡¨ç¤º"""
        self.table.setRowCount(len(tracks))
        
        for i, t in enumerate(tracks):
            # Title
            title_item = QTableWidgetItem(t.get('filename', 'Unknown'))
            self.table.setItem(i, 0, title_item)
            
            # BPM
            bpm = t.get('bpm', 0)
            bpm_item = QTableWidgetItem(f"{bpm:.1f}" if bpm > 0 else "---")
            self.table.setItem(i, 1, bpm_item)
            
            # Key
            key_item = QTableWidgetItem(t.get('key', '---'))
            
            # Key compatibility highlighting
            if t.get('filepath', '') in self.compatible_keys:
                key_item.setForeground(QColor(0, 255, 0))
                key_item.setFont(QFont("Bahnschrift", 9, QFont.Weight.Bold))
            
            self.table.setItem(i, 2, key_item)
            
            # Energy
            energy_profile = t.get('energy', [])
            if energy_profile:
                avg_energy = sum(e['rms'] for e in energy_profile) / len(energy_profile)
                energy_item = QTableWidgetItem(f"{avg_energy:.2f}")
            else:
                energy_item = QTableWidgetItem("---")
            self.table.setItem(i, 3, energy_item)
            
            # Genre
            genre_item = QTableWidgetItem(t.get('genre', 'Unknown'))
            self.table.setItem(i, 4, genre_item)


    def set_compatible_keys(self, compatible: list):
        """
        Ã¤Âºâ€™Ã¦Ââ€ºÃ£â€šÂ­Ã£Æ’Â¼Ã£Æ’ÂªÃ£â€šÂ¹Ã£Æ’Ë†Ã£â€šâ€™Ã¨Â¨Â­Ã¥Â®Å¡Ã£Ââ€”Ã£ÂÂ¦Ã£Æ’Â©Ã£â€šÂ¤Ã£Æ’â€“Ã£Æ’Â©Ã£Æ’ÂªÃ¨Â¡Â¨Ã§Â¤ÂºÃ£â€šâ€™Ã¦â€ºÂ´Ã¦â€“Â°Ã¯Â¼Ë†Phase 8C Week 2Ã¯Â¼â€°
        Args:
            compatible: Ã¤Âºâ€™Ã¦Ââ€ºÃ£â€šÂ­Ã£Æ’Â¼Ã£ÂÂ®Ã£Æ’ÂªÃ£â€šÂ¹Ã£Æ’Ë†Ã¯Â¼Ë†Ã¤Â¾â€¹: ['8A', '7A', '9A', '8B']Ã¯Â¼â€°
        """
        self.compatible_keys = compatible
        # Ã£Æ’Â©Ã£â€šÂ¤Ã£Æ’â€“Ã£Æ’Â©Ã£Æ’ÂªÃ¨Â¡Â¨Ã§Â¤ÂºÃ£â€šâ€™Ã¦â€ºÂ´Ã¦â€“Â°Ã¯Â¼Ë†Ã£Æ’ÂÃ£â€šÂ¤Ã£Æ’Â©Ã£â€šÂ¤Ã£Æ’Ë†Ã£â€šâ€™Ã¥ÂÂÃ¦ËœÂ Ã¯Â¼â€°
        self.update_library(self.all_tracks)

    def select_by_index(self, index: int):
        if 0 <= index < self.table.rowCount():
            self.table.selectRow(index)
            self.table.scrollToItem(self.table.item(index, 0))

    def _on_double_clicked(self, item):
        """ãƒ€ãƒ–ãƒ«ã‚¯ãƒªãƒƒã‚¯: é€šå¸¸=Deck Aã€ShiftæŠ¼ä¸‹=Deck B"""
        row = item.row()
        if 0 <= row < len(self.all_tracks):
            track = self.all_tracks[row]
            
            # Shiftä¿®é£¾å­ã§Deck Bã€ãã‚Œä»¥å¤–ã¯Deck A
            modifiers = QApplication.keyboardModifiers()
            deck_id = "B" if modifiers == Qt.KeyboardModifier.ShiftModifier else "A"
            
            self.load_track_requested.emit(deck_id, track['filepath'])
    
    def _show_context_menu(self, position):
        """å³ã‚¯ãƒªãƒƒã‚¯ãƒ¡ãƒ‹ãƒ¥ãƒ¼"""
        item = self.table.itemAt(position)
        if item is None:
            return
        
        row = item.row()
        if row < 0 or row >= len(self.all_tracks):
            return
        
        track = self.all_tracks[row]
        
        menu = QMenu(self)
        
        # Deck A/Bã¸ã®ãƒ­ãƒ¼ãƒ‰
        load_a_action = menu.addAction("Load to Deck A")
        load_b_action = menu.addAction("Load to Deck B")
        
        menu.addSeparator()
        
        # ãƒˆãƒ©ãƒƒã‚¯æƒ…å ±
        info_action = menu.addAction(f"ðŸ“Š BPM: {track.get('bpm', '---')}")
        info_action.setEnabled(False)
        
        key_action = menu.addAction(f"ðŸŽµ Key: {track.get('key', '---')}")
        key_action.setEnabled(False)
        
        # ãƒ¡ãƒ‹ãƒ¥ãƒ¼ã‚’è¡¨ç¤º
        action = menu.exec(self.table.viewport().mapToGlobal(position))
        
        if action == load_a_action:
            self.load_track_requested.emit("A", track['filepath'])
        elif action == load_b_action:
            self.load_track_requested.emit("B", track['filepath'])