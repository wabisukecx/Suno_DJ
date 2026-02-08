"""
Main Window (Phase 9 Final: Perfect Integration)
==================================================
調整内容:
1. 理想の状態 (image_f46c3b.png) を初期値として定義
2. スプリッターの比率を [Deck: 18%, Library: 82%] に設定
3. Energy Flow の高さを 225px (1.5倍) に固定
4. デッキ A/B の枠線（赤・青）を常に表示するよう DeckWidget と連携
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal

from gui.gui_deck_widget import DeckWidget
from gui.gui_prompt_panel import SunoPromptPanel
from gui.gui_energy_panel import EnergyFlowPanel
from gui.gui_library_panel import LibraryPanel
from gui.gui_styles import STYLESHEETS


class MainWindow(QMainWindow):
    """
    AI DJ Mixer メインウィンドウ
    """
    
    refresh_library_requested = pyqtSignal()
    analyze_track_requested = pyqtSignal(str)
    load_track_requested = pyqtSignal(str, str)
    bpm_update_requested = pyqtSignal(str, float)
    
    # 手動生成リクエスト用のシグナル
    generate_prompt_requested = pyqtSignal(bool) # vocal_enabled
    
    # HOT CUE操作シグナル (Phase 8C)
    hot_cue_trigger_requested = pyqtSignal(str, int)  # deck_id, slot
    hot_cue_set_requested = pyqtSignal(str, int)      # deck_id, slot
    hot_cue_clear_requested = pyqtSignal(str, int)    # deck_id, slot

    def __init__(self, prompt_generator=None):
        super().__init__()
        self.setWindowTitle("VCI-100 AI DJ Mixer - Phase 9 (Pro Layout)")
        
        # 立ち上げサイズを理想の比率に設定 (幅3/4, 高さ4/5程度)
        self.resize(1200, 800) 
        self.setStyleSheet(STYLESHEETS['main_window'])
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # PromptGeneratorはmixerから受け取る（二重初期化を避ける）
        self.prompt_gen = prompt_generator
        
        self._init_ui()
        self._connect_internal_ui()
        
    def _init_ui(self):
        # メイン垂直レイアウト
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # --- 全体の横分割スプリッター (左: Prompt / 右: Decks+Library) ---
        self.main_h_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. 左側: Suno プロンプトパネル (幅をスリムに固定)
        self.prompt_panel = SunoPromptPanel("A", self.prompt_gen)
        self.prompt_panel.setMinimumWidth(300)
        self.main_h_splitter.addWidget(self.prompt_panel)
        
        # 2. 右側: デッキとライブラリを垂直に並べるスプリッター
        self.right_v_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 上段: デッキ A/B 横並び
        decks_widget = QWidget()
        decks_layout = QHBoxLayout(decks_widget)
        decks_layout.setContentsMargins(0, 0, 0, 0)
        decks_layout.setSpacing(5)
        
        self.deck_a_widget = DeckWidget("A")
        self.deck_b_widget = DeckWidget("B")
        
        # デッキの高さを最適化（波形+HOT CUE+SYNC表示のため）
        self.deck_a_widget.setMinimumHeight(240)
        self.deck_b_widget.setMinimumHeight(240)
        self.deck_a_widget.setMaximumHeight(300)
        self.deck_b_widget.setMaximumHeight(300)
        
        decks_layout.addWidget(self.deck_a_widget)
        decks_layout.addWidget(self.deck_b_widget)
        
        self.right_v_splitter.addWidget(decks_widget)
        
        # 中段: ライブラリ（高さを抑える）
        self.library_panel = LibraryPanel()
        self.library_panel.setMinimumHeight(150)  # 最小高さ
        self.library_panel.setMaximumHeight(250)  # 最大高さ
        self.library_panel.load_track_requested.connect(lambda d, f: self.load_track_requested.emit(d, f))
        self.library_panel.analyze_track_requested.connect(lambda f: self.analyze_track_requested.emit(f))
        self.library_panel.bpm_update_requested.connect(lambda f, b: self.bpm_update_requested.emit(f, b))
        
        self.right_v_splitter.addWidget(self.library_panel)
        
        # 右側スプリッターの初期サイズ（Deckを優先、Libraryはコンパクトに）
        # [Decks高さ, Library高さ] の比率 = 3:1
        self.right_v_splitter.setSizes([360, 150])
        
        self.main_h_splitter.addWidget(self.right_v_splitter)
        
        # 左右の初期サイズ設定
        self.main_h_splitter.setSizes([300, 900])
        
        main_layout.addWidget(self.main_h_splitter, stretch=8)
        
        # --- 最下段: Energy Flow Panel (高さを1.5倍に拡大) ---
        self.energy_panel = EnergyFlowPanel()
        self.energy_panel.setFixedHeight(225) 
        main_layout.addWidget(self.energy_panel, stretch=2)
        
        # --- Status Bar ---
        self.status_bar = self.statusBar()
        self.status_bar.setStyleSheet(STYLESHEETS.get('status_bar', ""))
        self.status_bar.showMessage("Ready")

    def _connect_internal_ui(self):
        """パネル内のボタンをメインウィンドウのシグナルに接続"""
        self.prompt_panel.gen_btn.clicked.connect(self._on_gen_btn_clicked)
        
        # HOT CUE Buttons (Phase 8C)
        for btn in self.deck_a_widget.hot_cue_btns:
            slot = btn.property("cue_slot")
            btn.clicked.connect(lambda checked, s=slot: self._on_hot_cue_clicked("A", s))
        
        for btn in self.deck_b_widget.hot_cue_btns:
            slot = btn.property("cue_slot")
            btn.clicked.connect(lambda checked, s=slot: self._on_hot_cue_clicked("B", s))

    def _on_gen_btn_clicked(self):
        vocal_on = self.prompt_panel.vocal_checkbox.isChecked()
        self.generate_prompt_requested.emit(vocal_on)
    
    def _on_hot_cue_clicked(self, deck_id: str, slot: int):
        """
        HOT CUEボタンクリック処理
        - 通常クリック: Trigger (ジャンプ)
        - Shift+クリック: Set (現在位置に設定)
        - Ctrl+クリック: Clear (削除)
        """
        from PyQt6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        
        from PyQt6.QtCore import Qt
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            # Set CUE at current position
            self.hot_cue_set_requested.emit(deck_id, slot)
        elif modifiers == Qt.KeyboardModifier.ControlModifier:
            # Clear CUE
            self.hot_cue_clear_requested.emit(deck_id, slot)
        else:
            # Trigger CUE (jump to position)
            self.hot_cue_trigger_requested.emit(deck_id, slot)

    def update_deck_info(self, deck_id: str, info: dict):
        """デッキ情報を更新し、枠線の強調を切り替える"""
        if deck_id == "A":
            self.deck_a_widget.update_info(info)
            self.deck_a_widget.set_highlight(True)
            self.deck_b_widget.set_highlight(False)
        else:
            self.deck_b_widget.update_info(info)
            self.deck_b_widget.set_highlight(True)
            self.deck_a_widget.set_highlight(False)
            
        if hasattr(self.prompt_panel, 'update_track_info'):
            self.prompt_panel.update_track_info(info)

    def update_waveform(self, deck_id: str, waveform_data):
        if deck_id == "A":
            self.deck_a_widget.set_waveform(waveform_data)
        else:
            self.deck_b_widget.set_waveform(waveform_data)

    def update_position(self, deck_id: str, position: float, duration: float):
        if deck_id == "A":
            self.deck_a_widget.update_time(position, duration)
            if hasattr(self.energy_panel, 'update_deck_position'):
                self.energy_panel.update_deck_position("A", position, duration)
        else:
            self.deck_b_widget.update_time(position, duration)
            if hasattr(self.energy_panel, 'update_deck_position'):
                self.energy_panel.update_deck_position("B", position, duration)

    def update_energy_profile(self, deck_id: str, profile: list, duration: float):
        if hasattr(self.energy_panel, 'update_deck_energy_profile'):
            self.energy_panel.update_deck_energy_profile(deck_id, profile, duration)

    def on_prompt_generated(self, prompt: dict):
        suno_data = prompt.get('suno', {})
        reasoning_data = prompt.get('reasoning', {})
        
        r_lines = [f"■ {k}: {v}" for k, v in reasoning_data.items()] if isinstance(reasoning_data, dict) else [str(reasoning_data)]
        r_text = "\n\n".join(r_lines)
        
        self.prompt_panel.set_prompt(
            lyrics=suno_data.get('lyrics', ''),
            style=suno_data.get('styles', ''),
            title=suno_data.get('title', ''),
            reasoning=r_text
        )
    
    def update_energy_flow(self, energy_data: list):
        if hasattr(self.energy_panel, 'update_energy_data'):
            self.energy_panel.update_energy_data(energy_data)
    
    def update_library(self, track_list: list):
        self.library_panel.update_library(track_list)
    
    def update_library_cursor(self, index: int):
        self.library_panel.select_by_index(index)

    def on_track_added(self, filename: str):
        self.status_bar.showMessage(f"🎵 New track added: {filename}", 5000)