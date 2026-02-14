"""
GUI Styles
==========
Phase 9: High Contrast Dark Theme (Final Fixed Version)
"""

COLORS = {
    # Base Colors
    'background': '#121212',       # Deep dark background
    'surface': '#1e1e1e',          # Card background
    'surface_hover': '#2d2d2d',    # Hover state
    'border': '#333333',           # Borders
    
    # Text
    'text': '#ffffff',             # Main text (White)
    'text_dim': '#b0b0b0',         # Secondary text (Light Grey)
    'text_dark': '#000000',        # Text on light background
    
    # Accents
    'accent': '#00bcd4',           # Cyan
    'deck_a': '#ff1744',           # Red
    'deck_b': '#00e5ff',           # Cyan
    
    # Waveform
    'waveform_bg': '#000000',
    'waveform_grid': '#333333',
    'success': '#00ff88',
    'warning': '#ff9800',
    'error': '#f44336',
}

STYLESHEETS = {
    'main_window': f"""
        QMainWindow {{
            background-color: {COLORS['background']};
        }}
        QSplitter::handle {{
            background-color: {COLORS['border']};
            width: 2px;
        }}
        QStatusBar {{
            background-color: {COLORS['surface']};
            color: {COLORS['text_dim']};
            border-top: 1px solid {COLORS['border']};
        }}
    """,
    
    'library_table': f"""
        QTableWidget {{
            background-color: {COLORS['background']};
            color: {COLORS['text']};
            gridline-color: {COLORS['border']};
            border: none;
            selection-background-color: rgba(0, 255, 0, 0.3);
            selection-color: {COLORS['text']};
        }}
        QHeaderView::section {{
            background-color: {COLORS['surface']};
            color: {COLORS['text_dim']};
            padding: 4px;
            border: none;
            border-bottom: 1px solid {COLORS['border']};
        }}
    """,

    'icon_button': f"""
        QPushButton {{
            background-color: transparent;
            color: {COLORS['text_dim']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: 4px;
            font-size: 14px;
        }}
        QPushButton:hover {{
            background-color: {COLORS['surface_hover']};
            color: {COLORS['text']};
            border-color: {COLORS['accent']};
        }}
    """,

    'search_edit': f"""
        QLineEdit {{
            background-color: {COLORS['background']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QLineEdit:focus {{
            border-color: {COLORS['accent']};
        }}
    """,
    
    'input_field': f"""
        QLineEdit, QTextEdit {{
            background-color: {COLORS['surface']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            padding: 4px 8px;
        }}
    """,
    
    'button_primary': f"""
        QPushButton {{
            background-color: #2563eb;
            color: white;
            border-radius: 4px;
            padding: 8px 16px;
            font-weight: bold;
        }}
        QPushButton:hover {{ background-color: #3b82f6; }}
    """,
    
    'progress_bar': f"""
        QProgressBar {{
            background-color: {COLORS['surface']};
            color: {COLORS['text']};
            border: 1px solid {COLORS['border']};
            border-radius: 4px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {COLORS['accent']};
        }}
    """
}

def get_deck_color(deck_id):
    return COLORS['deck_a'] if deck_id == "A" else COLORS['deck_b']