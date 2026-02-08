"""
GUI modules for VCI-100 AI DJ Mixer.

This package contains PyQt6-based user interface components:
- gui_main_window: Main application window
- gui_deck_widget: Deck control widgets (A/B)
- gui_library_panel: Track library panel
- gui_energy_panel: Energy flow visualization panel
- gui_prompt_panel: AI prompt generation panel
- gui_common_widgets: Shared UI components
- gui_styles: Application styling and themes
"""

from .gui_main_window import MainWindow
from .gui_deck_widget import DeckWidget, WaveformWidget
from .gui_library_panel import LibraryPanel
from .gui_energy_panel import EnergyFlowPanel
from .gui_prompt_panel import SunoPromptPanel
from .gui_common_widgets import (
    CopyableField,
    StatusLabel,
    SectionDivider,
    InfoRow,
    IconButton,
    CompactProgressBar,
)
from .gui_styles import COLORS, STYLESHEETS

__all__ = [
    'MainWindow',
    'DeckWidget',
    'WaveformWidget',
    'LibraryPanel',
    'EnergyFlowPanel',
    'SunoPromptPanel',
    'CopyableField',
    'StatusLabel',
    'SectionDivider',
    'InfoRow',
    'IconButton',
    'CompactProgressBar',
    'COLORS',
    'STYLESHEETS',
]
