"""
Suno Prompt Panel (Phase 9E: Full UI with Copy Buttons & Vocal Toggle)
====================================================================
機能:
- ボーカルチェックボックス（デフォルトOFF）
- Song Title / Styles / Lyrics の各フィールドに個別コピーボタン
- 手動生成ボタン (GENERATE PROMPT)
- Traktor風ハイコントラスト・ダークテーマ
"""

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit, 
    QPushButton, QCheckBox, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QColor

from gui.gui_styles import COLORS

class SunoPromptPanel(QFrame):
    def __init__(self, deck_name: str, prompt_gen=None):
        super().__init__()
        self.deck_name = deck_name
        self.prompt_gen = prompt_gen
        self.current_track_info = None
        
        self.setStyleSheet(f"""
            SunoPromptPanel {{
                background-color: {COLORS['surface']};
                border: 1px solid {COLORS['border']};
                border-radius: 8px;
            }}
            QLabel {{ color: {COLORS['text']}; }}
            QCheckBox {{ color: {COLORS['text']}; spacing: 8px; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; }}
        """)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        
        # --- Header Section ---
        header_layout = QHBoxLayout()
        self.header_label = QLabel(f"AI PROMPT FOR DECK {deck_name}")
        self.header_label.setFont(QFont("Bahnschrift", 12, QFont.Weight.Bold))
        self.header_label.setStyleSheet(f"color: {COLORS['accent']};")
        
        # Vocal Toggle (Default: OFF)
        self.vocal_checkbox = QCheckBox("VOCAL TRACK")
        self.vocal_checkbox.setChecked(False)
        self.vocal_checkbox.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        
        header_layout.addWidget(self.header_label)
        header_layout.addStretch()
        header_layout.addWidget(self.vocal_checkbox)
        layout.addLayout(header_layout)
        
        # Generation Status
        self.status_label = QLabel("Status: Ready")
        self.status_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        layout.addWidget(self.status_label)

        # --- Input Fields with Copy Buttons ---
        self.title_field = self._create_copyable_field("Song Title", layout, height=35)
        self.style_field = self._create_copyable_field("Styles / Tags", layout, height=60)
        self.lyrics_field = self._create_copyable_field("Lyrics / Structure", layout, height=150)
        
        # Reasoning (Simple view)
        self.reasoning_field = self._create_simple_field("AI Reasoning (JP)", layout, height=100)
        
        # Main Generate Button
        self.gen_btn = QPushButton("GENERATE PROMPT")
        self.gen_btn.setFixedHeight(40)
        self.gen_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.gen_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: #2563eb;
                color: white;
                border-radius: 4px;
                border: none;
            }}
            QPushButton:hover {{ background-color: #3b82f6; }}
            QPushButton:pressed {{ background-color: #1d4ed8; }}
        """)
        layout.addWidget(self.gen_btn)
        
        self.setLayout(layout)

    def _create_copyable_field(self, label_text, parent_layout, height):
        container = QVBoxLayout()
        container.setSpacing(4)
        
        row = QHBoxLayout()
        label = QLabel(label_text.upper())
        label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {COLORS['text_dim']};")
        
        copy_btn = QPushButton("COPY")
        copy_btn.setFixedSize(50, 20)
        copy_btn.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLORS['surface_hover']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                border-radius: 2px;
            }}
            QPushButton:hover {{ background-color: {COLORS['accent']}; color: black; }}
        """)
        
        row.addWidget(label)
        row.addStretch()
        row.addWidget(copy_btn)
        container.addLayout(row)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFixedHeight(height)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['background']};
                color: {COLORS['text']};
                border: 1px solid {COLORS['border']};
                padding: 5px;
            }}
        """)
        container.addWidget(text_edit)
        
        copy_btn.clicked.connect(lambda: self._copy_to_clipboard(text_edit.toPlainText(), label_text))
        
        parent_layout.addLayout(container)
        return text_edit

    def _create_simple_field(self, label_text, parent_layout, height):
        container = QVBoxLayout()
        container.setSpacing(4)
        label = QLabel(label_text.upper())
        label.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        label.setStyleSheet(f"color: {COLORS['text_dim']};")
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setFixedHeight(height)
        text_edit.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLORS['background']};
                color: {COLORS['text_dim']};
                border: 1px solid {COLORS['border']};
                padding: 5px;
            }}
        """)
        container.addWidget(label)
        container.addWidget(text_edit)
        parent_layout.addLayout(container)
        return text_edit

    def _copy_to_clipboard(self, text, label):
        if text.strip():
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.set_generation_status(f"Copied {label}!")
        else:
            self.set_generation_status("Nothing to copy")

    def update_title(self):
        if self.current_track_info:
            filename = self.current_track_info.get('filename', 'Unknown')
            self.header_label.setText(f"AI PROMPT FOR: {filename}")
        else:
            self.header_label.setText(f"AI PROMPT GENERATOR - DECK {self.deck_name}")

    def update_track_info(self, info: dict):
        self.current_track_info = info
        self.update_title()

    def set_prompt(self, lyrics: str, style: str, title: str, reasoning: str):
        self.lyrics_field.setPlainText(lyrics)
        self.style_field.setPlainText(style)
        self.title_field.setPlainText(title)
        self.reasoning_field.setPlainText(reasoning)

    def set_generation_status(self, status: str):
        self.status_label.setText(f"Status: {status}")