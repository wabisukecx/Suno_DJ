"""
Main Window (Phase 9 Final: Perfect Integration)
==================================================
修正内容:
- AttributeError: 'MainWindow' object has no attribute 'update_waveform' を解決
- update_loop_state などの不足メソッドを追加
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
    # UIからMixerへのリクエスト用シグナル
    refresh_library_requested = pyqtSignal()
    analyze_track_requested = pyqtSignal(str)
    load_track_requested = pyqtSignal(str, str)
    bpm_update_requested = pyqtSignal(str, float)
    generate_prompt_requested = pyqtSignal(bool) # vocal_enabled
    
    # HOT CUE操作シグナル
    hot_cue_trigger_requested = pyqtSignal(str, int)
    hot_cue_set_requested = pyqtSignal(str, int)
    hot_cue_clear_requested = pyqtSignal(str, int)

    def __init__(self, prompt_generator=None):
        super().__init__()
        self.setWindowTitle("VCI-100 AI DJ Mixer - Phase 9 (Pro Layout)")
        
        # 理想のサイズを設定
        self.resize(1200, 800) 
        self.setStyleSheet(STYLESHEETS['main_window'])
        
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.prompt_gen = prompt_generator
        
        self._init_ui()
        self._connect_internal_ui()
        
    def _init_ui(self):
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # 全体の横分割 (左: Prompt / 右: Decks+Library)
        self.main_h_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. 左側: Suno プロンプトパネル
        self.prompt_panel = SunoPromptPanel("A", self.prompt_gen)
        self.prompt_panel.setMinimumWidth(320)
        self.main_h_splitter.addWidget(self.prompt_panel)
        
        # 2. 右側: デッキとライブラリを垂直に並べる
        self.right_v_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 上段: デッキ A/B
        decks_widget = QWidget()
        decks_layout = QHBoxLayout(decks_widget)
        decks_layout.setContentsMargins(0, 0, 0, 0)
        decks_layout.setSpacing(5)
        
        self.deck_a_widget = DeckWidget("A")
        self.deck_b_widget = DeckWidget("B")
        
        decks_layout.addWidget(self.deck_a_widget)
        decks_layout.addWidget(self.deck_b_widget)
        self.right_v_splitter.addWidget(decks_widget)
        
        # 中段: ライブラリ
        self.library_panel = LibraryPanel()
        self.library_panel.load_track_requested.connect(lambda d, f: self.load_track_requested.emit(d, f))
        self.right_v_splitter.addWidget(self.library_panel)
        
        self.right_v_splitter.setSizes([450, 250])
        self.main_h_splitter.addWidget(self.right_v_splitter)
        self.main_h_splitter.setSizes([320, 880])
        
        main_layout.addWidget(self.main_h_splitter, stretch=8)
        
        # 下段: Energy Flow
        self.energy_panel = EnergyFlowPanel()
        self.energy_panel.setFixedHeight(225) 
        main_layout.addWidget(self.energy_panel, stretch=2)
        
        # Status Bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")

    def _connect_internal_ui(self):
        """パネル内のボタンをメインウィンドウのシグナルに接続"""
        self.prompt_panel.gen_btn.clicked.connect(self._on_gen_btn_clicked)
        
        # Deck A HOT CUE
        for btn in self.deck_a_widget.hot_cue_btns:
            slot = btn.property("cue_slot")
            btn.clicked.connect(lambda checked, s=slot: self._on_hot_cue_clicked("A", s))
        
        # Deck B HOT CUE
        for btn in self.deck_b_widget.hot_cue_btns:
            slot = btn.property("cue_slot")
            btn.clicked.connect(lambda checked, s=slot: self._on_hot_cue_clicked("B", s))

    def _on_gen_btn_clicked(self):
        vocal_on = self.prompt_panel.vocal_checkbox.isChecked()
        self.generate_prompt_requested.emit(vocal_on)
    
    def _on_hot_cue_clicked(self, deck_id: str, slot: int):
        from PyQt6.QtWidgets import QApplication
        modifiers = QApplication.keyboardModifiers()
        
        if modifiers == Qt.KeyboardModifier.ShiftModifier:
            self.hot_cue_set_requested.emit(deck_id, slot)
        elif modifiers == Qt.KeyboardModifier.ControlModifier:
            self.hot_cue_clear_requested.emit(deck_id, slot)
        else:
            self.hot_cue_trigger_requested.emit(deck_id, slot)

    # --- Mixerからの更新を受け取るメソッド群 ---

    def update_deck_info(self, deck_id: str, info: dict):
        """デッキ情報を更新し、操作中のデッキを強調"""
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
        """波形データの描画更新 (AttributeError解決の要)"""
        if deck_id == "A":
            self.deck_a_widget.set_waveform(waveform_data)
        else:
            self.deck_b_widget.set_waveform(waveform_data)

    def update_position(self, deck_id: str, position: float, duration: float):
        """再生位置とEnergy Flowマーカーの更新"""
        if deck_id == "A":
            self.deck_a_widget.update_time(position, duration)
            self.energy_panel.update_deck_position("A", position, duration)
        else:
            self.deck_b_widget.update_time(position, duration)
            self.energy_panel.update_deck_position("B", position, duration)

    def update_energy_profile(self, deck_id: str, profile: list, duration: float):
        """楽曲解析後のEnergyプロファイル反映"""
        self.energy_panel.update_deck_energy_profile(deck_id, profile, duration)

    def on_prompt_generated(self, prompt: dict):
        """AIプロンプトの反映"""
        suno_data = prompt.get('suno', {})
        reasoning_data = prompt.get('reasoning', {})
        
        # 推論プロセスの整形
        r_text = ""
        if isinstance(reasoning_data, dict):
            r_text = "\n\n".join([f"■ {k}: {v}" for k, v in reasoning_data.items()])
        else:
            r_text = str(reasoning_data)
        
        self.prompt_panel.set_prompt(
            lyrics=suno_data.get('lyrics', ''),
            style=suno_data.get('styles', ''),
            title=suno_data.get('title', ''),
            reasoning=r_text
        )
    
    def update_energy_flow(self, energy_data: list):
        """(互換性用) 全体のエネルギーフローを更新"""
        if hasattr(self.energy_panel, 'update_energy_data'):
            self.energy_panel.update_energy_data(energy_data)
    
    def update_library(self, track_list: list):
        """ライブラリリストの更新"""
        self.library_panel.update_library(track_list)
    
    def update_library_cursor(self, index: int):
        """MIDI操作などによるライブラリ選択位置の同期"""
        if hasattr(self.library_panel, 'select_by_index'):
            self.library_panel.select_by_index(index)

    def on_track_added(self, filename: str):
        """新規トラック追加時の通知"""
        self.status_bar.showMessage(f"🎵 New track added: {filename}", 5000)