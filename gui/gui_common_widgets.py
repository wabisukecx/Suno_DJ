"""
Common GUI Widgets
==================

再利用可能なGUIコンポーネント

使用方法:
    from gui_common_widgets import CopyableField
    
    field = CopyableField("Label", "Placeholder text", multiline=True)
    field.set_text("Content")
"""

from PyQt6.QtWidgets import (
    QApplication,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
    QTextEdit, QLineEdit, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
# pyperclip removed - using QApplication.clipboard()

from gui.gui_styles import COLORS, STYLESHEETS


class CopyableField(QWidget):
    """
    コピーボタン付きフィールド
    
    フィールド右上に📋ボタンが配置され、クリックでクリップボードにコピー
    
    Args:
        label: フィールドのラベルテキスト
        placeholder: プレースホルダーテキスト
        multiline: True=QTextEdit、False=QLineEdit
    """
    
    def __init__(self, label: str, placeholder: str = "", multiline: bool = False):
        super().__init__()
        
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2) # ラベルとフィールドの間隔を詰める
        
        # ヘッダー（ラベル + コピーボタン）
        header = QHBoxLayout()
        header.setSpacing(4)
        
        self.label = QLabel(label)
        self.label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.label.setStyleSheet(f"color: {COLORS['text_dim']};")
        
        self.copy_btn = QPushButton("📋")
        self.copy_btn.setFixedSize(24, 24) # ボタンを少し小さく
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.setToolTip("Copy to clipboard")
        # ボタンのスタイル（インライン定義でシンプルに）
        self.copy_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                color: {COLORS['text_dim']};
            }}
            QPushButton:hover {{
                background-color: {COLORS['surface_hover']};
                color: {COLORS['text']};
            }}
        """)
        self.copy_btn.clicked.connect(self._copy_to_clipboard)
        
        header.addWidget(self.label)
        header.addStretch()
        header.addWidget(self.copy_btn)
        
        layout.addLayout(header)
        
        # 入力フィールド
        if multiline:
            self.field = QTextEdit()
            self.field.setPlaceholderText(placeholder)
            # 高さの固定制限を撤廃し、最小サイズのみ定義して伸縮可能に
            self.field.setMinimumHeight(60)
            self.field.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        else:
            self.field = QLineEdit()
            self.field.setPlaceholderText(placeholder)
        
        self.field.setReadOnly(True)
        self.field.setStyleSheet(STYLESHEETS['input_field'])
        
        layout.addWidget(self.field)
        self.setLayout(layout)
        
        self._multiline = multiline
    
    def set_text(self, text: str):
        """テキストを設定"""
        if self._multiline:
            self.field.setText(text)
        else:
            self.field.setText(text)
    
    def get_text(self) -> str:
        """テキストを取得"""
        if self._multiline:
            return self.field.toPlainText()
        else:
            return self.field.text()
    
    def clear(self):
        """テキストをクリア"""
        self.field.clear()
    
    def set_read_only(self, read_only: bool):
        """読み取り専用状態を設定"""
        self.field.setReadOnly(read_only)
    
    def _copy_to_clipboard(self):
        """クリップボードにコピー"""
        text = self.get_text()
        if text:
            QApplication.clipboard().setText(text)
            # ボタンテキストを一時的に変更
            self.copy_btn.setText("✓")
            QTimer.singleShot(1000, lambda: self.copy_btn.setText("📋"))


class StatusLabel(QLabel):
    """
    ステータス表示用ラベル
    """
    
    def __init__(self, text: str = "", status_type: str = "normal"):
        super().__init__(text)
        self.setFont(QFont("Segoe UI", 10))
        self.set_status(text, status_type)
    
    def set_status(self, text: str, status_type: str = "normal"):
        """ステータスを設定"""
        self.setText(text)
        
        color_map = {
            "normal": COLORS['text'],
            "success": COLORS['success'],
            "warning": COLORS['warning'],
            "error": COLORS['error'],
            "dim": COLORS['text_dim'],
        }
        
        color = color_map.get(status_type, COLORS['text'])
        self.setStyleSheet(f"color: {color}; font-size: 10px;")


class SectionDivider(QFrame):
    """
    セクション区切り線
    """
    
    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.HLine)
        self.setStyleSheet(f"background-color: {COLORS['border']};")
        self.setFixedHeight(1)


class InfoRow(QWidget):
    """
    情報行表示ウィジェット
    ラベル: 値 形式の情報行を作成
    """
    
    def __init__(self, label: str, value: str = ""):
        super().__init__()
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        self.label_widget = QLabel(f"{label}:")
        self.label_widget.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        
        self.value_widget = QLabel(value)
        self.value_widget.setStyleSheet(f"color: {COLORS['text']}; font-size: 11px; font-weight: bold;")
        
        layout.addWidget(self.label_widget)
        layout.addWidget(self.value_widget)
        layout.addStretch()
        
        self.setLayout(layout)
    
    def set_value(self, value: str):
        """値を更新"""
        self.value_widget.setText(value)
    
    def get_value(self) -> str:
        """現在の値を取得"""
        return self.value_widget.text()


class IconButton(QPushButton):
    """
    アイコンボタン
    絵文字アイコンとテキストを表示するボタン
    """
    
    def __init__(self, icon: str, text: str, style: str = "secondary"):
        super().__init__(f"{icon} {text}")
        
        style_map = {
            "primary": STYLESHEETS['button_primary'],
            "secondary": STYLESHEETS['button_secondary'],
            "accent": STYLESHEETS['button_accent'],
        }
        
        self.setStyleSheet(style_map.get(style, STYLESHEETS['button_secondary']))


class CompactProgressBar(QWidget):
    """
    コンパクトプログレスバー
    ラベル付きの小型プログレスバー
    """
    
    def __init__(self, label: str, min_val: int = 0, max_val: int = 100):
        super().__init__()
        
        from PyQt6.QtWidgets import QProgressBar
        
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        self.label = QLabel(f"{label}:")
        self.label.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 10px;")
        self.label.setFixedWidth(60)
        
        self.progress = QProgressBar()
        self.progress.setRange(min_val, max_val)
        self.progress.setTextVisible(True)
        self.progress.setFormat("%v / %m (%p%)")
        self.progress.setFixedHeight(20)
        self.progress.setStyleSheet(STYLESHEETS['progress_bar'])
        
        layout.addWidget(self.label)
        layout.addWidget(self.progress, 1)
        
        self.setLayout(layout)
    
    def set_value(self, value: int):
        """値を設定"""
        self.progress.setValue(value)
    
    def set_color(self, color: str):
        """バーの色を変更"""
        self.progress.setStyleSheet(f"""
            QProgressBar {{
                border: none;
                background-color: {COLORS['border']};
                border-radius: 2px;
                height: 4px;
                text-align: center;
                color: {COLORS['text']};
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 2px;
            }}
        """)


# ============================================================================
# テスト
# ============================================================================

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication, QVBoxLayout
    
    print("=" * 60)
    print("Common Widgets Test")
    print("=" * 60)
    
    app = QApplication(sys.argv)
    
    # テストウィンドウ
    window = QWidget()
    window.setWindowTitle("Common Widgets Test")
    window.setStyleSheet(f"background-color: {COLORS['background']}; color: {COLORS['text']};")
    
    layout = QVBoxLayout()
    
    # CopyableField
    field1 = CopyableField("Single Line Field", "Enter text here")
    field1.set_text("Tech House, Driving, 126 BPM")
    layout.addWidget(field1)
    
    field2 = CopyableField("Multi Line Field (Expandable)", "Enter text here", multiline=True)
    field2.set_text("[Intro - Extended]\n[Main Groove - Hypnotic]\n[Drop - Euphoric]\n" * 5)
    layout.addWidget(field2)
    
    # StatusLabel
    layout.addWidget(SectionDivider())
    status1 = StatusLabel("Normal status", "normal")
    status2 = StatusLabel("Success status", "success")
    status3 = StatusLabel("Warning status", "warning")
    status4 = StatusLabel("Error status", "error")
    layout.addWidget(status1)
    layout.addWidget(status2)
    layout.addWidget(status3)
    layout.addWidget(status4)
    
    # InfoRow
    layout.addWidget(SectionDivider())
    info1 = InfoRow("BPM", "128")
    info2 = InfoRow("Key", "Am")
    info3 = InfoRow("Genre", "Tech House")
    layout.addWidget(info1)
    layout.addWidget(info2)
    layout.addWidget(info3)
    
    # IconButton
    layout.addWidget(SectionDivider())
    btn1 = IconButton("📋", "Copy", "primary")
    btn2 = IconButton("🔄", "Regenerate", "secondary")
    btn3 = IconButton("⚙️", "Settings", "accent")
    layout.addWidget(btn1)
    layout.addWidget(btn2)
    layout.addWidget(btn3)
    
    # CompactProgressBar
    layout.addWidget(SectionDivider())
    progress1 = CompactProgressBar("Tokens", 0, 1500)
    progress1.set_value(300)
    progress2 = CompactProgressBar("Energy", 0, 5)
    progress2.set_value(4)
    progress2.set_color(COLORS['warning'])
    layout.addWidget(progress1)
    layout.addWidget(progress2)
    
    layout.addStretch()
    
    window.setLayout(layout)
    window.resize(500, 600)
    window.show()
    
    print("\nTest window displayed. Close to exit.")
    sys.exit(app.exec())