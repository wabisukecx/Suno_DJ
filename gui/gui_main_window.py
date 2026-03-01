"""
Main Window
===========

AI DJ Mixer メインウィンドウ。

Phase R1変更点:
- gui/gui_main_window.py へ移動（ルートから正しいパッケージ位置へ）
- メニューバー追加（MIDIマッピングウィザード、プリセット切り替え）
- midi_mapping_changed シグナル追加
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QMenu, QFileDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction

from gui.gui_deck_widget import DeckWidget
from gui.gui_prompt_panel import SunoPromptPanel
from gui.gui_energy_panel import EnergyFlowPanel
from gui.gui_library_panel import LibraryPanel
from gui.gui_hype_panel import HypePanel
from gui.gui_venue_selector import VenueSelectorDialog
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
    generate_prompt_requested = pyqtSignal(bool)  # vocal_enabled

    # Gamification 操作シグナル（app.py で mixer に接続）
    gamification_enabled_changed = pyqtSignal(bool)
    venue_changed = pyqtSignal(str)
    commentary_requested = pyqtSignal()
    finish_session_requested = pyqtSignal()  # セッション終了 → app.py へ

    # HOT CUE操作シグナル
    hot_cue_trigger_requested = pyqtSignal(str, int)
    hot_cue_set_requested = pyqtSignal(str, int)
    hot_cue_clear_requested = pyqtSignal(str, int)

    # MIDIマッピング変更通知（MIDIMappingインスタンスを渡す）
    midi_mapping_changed = pyqtSignal(object)

    def __init__(self, prompt_coordinator=None):
        super().__init__()
        self.setWindowTitle("VCI-100 AI DJ Mixer - Phase 9 (Pro Layout)")
        self.resize(1200, 800)
        self.setStyleSheet(STYLESHEETS['main_window'])

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.prompt_coordinator = prompt_coordinator

        self._init_ui()
        self._connect_internal_ui()
        self._init_menu()

    # ---- UI初期化 ----

    def _init_ui(self):
        main_layout = QVBoxLayout(self.central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # 全体の横分割（左: Prompt / 右: Decks+Library）
        self.main_h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. 左側: Suno プロンプトパネル
        self.prompt_panel = SunoPromptPanel("A", self.prompt_coordinator)
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
        self.library_panel.load_track_requested.connect(
            lambda d, f: self.load_track_requested.emit(d, f)
        )
        self.right_v_splitter.addWidget(self.library_panel)

        self.right_v_splitter.setSizes([450, 250])
        self.main_h_splitter.addWidget(self.right_v_splitter)
        self.main_h_splitter.setSizes([320, 880])

        main_layout.addWidget(self.main_h_splitter, stretch=8)

        # 下段: Energy Flow + HypePanel（横並び）
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(5)

        self.energy_panel = EnergyFlowPanel()
        self.energy_panel.setFixedHeight(225)
        bottom_layout.addWidget(self.energy_panel, stretch=3)

        # R8: HypePanel（ゲーミフィケーション表示）
        self.hype_panel = HypePanel()
        self.hype_panel.setFixedHeight(225)
        self.hype_panel.setMinimumWidth(300)
        # HypePanelの「評価して」ボタン → MainWindowのシグナルに中継
        self.hype_panel.request_comment.connect(self.commentary_requested)
        # HypePanelの会場変更 → MainWindowのシグナルに中継
        self.hype_panel.venue_changed.connect(self.venue_changed)
        bottom_layout.addWidget(self.hype_panel, stretch=2)

        main_layout.addWidget(bottom_widget, stretch=2)

        # Status Bar
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("Ready")

    def _connect_internal_ui(self):
        """パネル内のボタンをメインウィンドウのシグナルに接続"""
        self.prompt_panel.gen_btn.clicked.connect(self._on_gen_btn_clicked)

        # Deck A HOT CUE
        for btn in self.deck_a_widget.hot_cue_btns:
            slot = btn.property("cue_slot")
            btn.clicked.connect(
                lambda checked, s=slot: self._on_hot_cue_clicked("A", s)
            )

        # Deck B HOT CUE
        for btn in self.deck_b_widget.hot_cue_btns:
            slot = btn.property("cue_slot")
            btn.clicked.connect(
                lambda checked, s=slot: self._on_hot_cue_clicked("B", s)
            )

    # ---- メニューバー ----

    def _init_menu(self):
        """メニューバーを初期化"""
        menubar = self.menuBar()

        # ---- World Tour メニュー（R8）----
        game_menu: QMenu = menubar.addMenu("ゲーム(&G)")

        act_start = QAction("ゲーム開始(&S)", self)
        act_start.setStatusTip("Gamification スコアリングを開始します")
        act_start.triggered.connect(lambda: self.gamification_enabled_changed.emit(True))
        game_menu.addAction(act_start)

        act_stop = QAction("ゲーム終了(&E)", self)
        act_stop.setStatusTip("Gamification スコアリングを停止します")
        act_stop.triggered.connect(self.finish_session_requested)
        game_menu.addAction(act_stop)

        game_menu.addSeparator()

        act_venue = QAction("会場を選ぶ(&V)...", self)
        act_venue.setStatusTip("World Tour の会場（都市）を選択します")
        act_venue.triggered.connect(self._on_select_venue)
        game_menu.addAction(act_venue)

        # ---- 設定メニュー ----
        settings_menu: QMenu = menubar.addMenu("設定(&S)")

        act_import_xml = QAction("MIXXX XMLをインポート(&X)...", self)
        act_import_xml.setStatusTip(
            "MIXXX形式のXMLコントローラープリセットを読み込みます"
        )
        act_import_xml.triggered.connect(self._on_import_mixxx_xml)
        settings_menu.addAction(act_import_xml)

        act_midi_preset = QAction("MIDIプリセット切り替え(&P)...", self)
        act_midi_preset.setStatusTip("保存済みMIDIプリセット（JSON）を選択して切り替えます")
        act_midi_preset.triggered.connect(self._on_change_midi_preset)
        settings_menu.addAction(act_midi_preset)

    def _on_select_venue(self):
        """会場選択ダイアログを開く（R8）"""
        dialog = VenueSelectorDialog(parent=self)
        dialog.venue_selected.connect(self.hype_panel.set_venue)
        dialog.exec()

    def _on_import_mixxx_xml(self):
        """MIXXX XMLファイルを選択してMIDIMappingに変換・適用する"""
        from pathlib import Path
        from core.midi_mapping import load_from_mixxx_xml, DEFAULT_PRESET_DIR

        xml_path, _ = QFileDialog.getOpenFileName(
            self, "MIXXX XMLプリセットを開く", "",
            "MIXXX Preset (*.xml);;All Files (*)"
        )
        if not xml_path:
            return

        mapping = load_from_mixxx_xml(Path(xml_path))
        if mapping is None:
            QMessageBox.warning(self, "インポート失敗",
                                "XMLの読み込みに失敗しました。\n対応フォーマットか確認してください。")
            return

        # presetsディレクトリにJSONとして保存
        save_name = Path(xml_path).stem + "_imported.json"
        save_path = DEFAULT_PRESET_DIR / save_name
        mapping.save(save_path)

        self.midi_mapping_changed.emit(mapping)
        self.status_bar.showMessage(
            f"MIDIプリセット適用: {mapping.preset_name}  ({len(mapping.entries)}件)", 8000
        )
        QMessageBox.information(
            self, "インポート完了",
            f"{len(mapping.entries)} 件のマッピングを読み込みました。\n保存先: {save_path}"
        )

    def _on_change_midi_preset(self):
        """既存プリセット（JSON / MIXXX XML）選択ダイアログを開く"""
        from pathlib import Path
        from core.midi_mapping import MIDIMapping, load_from_mixxx_xml, DEFAULT_PRESET_DIR

        path_str, _ = QFileDialog.getOpenFileName(
            self, "MIDIプリセットを開く",
            str(DEFAULT_PRESET_DIR),
            "MIDI Preset (*.json *.xml);;JSON (*.json);;MIXXX XML (*.xml);;All Files (*)"
        )
        if not path_str:
            return

        p = Path(path_str)
        if p.suffix.lower() == ".xml":
            mapping = load_from_mixxx_xml(p)
        else:
            mapping = MIDIMapping.load(p)

        if mapping is None:
            QMessageBox.warning(self, "読み込み失敗",
                                "プリセットの読み込みに失敗しました。")
            return

        self.midi_mapping_changed.emit(mapping)
        self.status_bar.showMessage(
            f"MIDIプリセット適用: {mapping.preset_name}", 5000
        )

    # ---- ボタンイベント ----

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

    # ---- Mixerからの更新を受け取るメソッド群 ----

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

    def update_waveform(self, deck_id: str, waveform_data, duration: float = 0.0):
        """波形データの描画更新"""
        if deck_id == "A":
            self.deck_a_widget.set_waveform(waveform_data, duration)
        else:
            self.deck_b_widget.set_waveform(waveform_data, duration)

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
        """（互換性用）全体のエネルギーフローを更新"""
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

    # ---- Gamification（Phase R8）----

    def update_game_score(self, data: dict):
        """スコア更新を HypePanel に転送"""
        self.hype_panel.on_score_updated(data)

    def update_commentary(self, data):
        """AI 講評を HypePanel に転送。str できた場合は dict に変換"""
        if isinstance(data, str):
            data = {"text": data, "source": "fallback", "trigger": "manual", "timestamp": 0.0}
        self.hype_panel.on_commentary(data)

    def show_session_result(self, result: dict):
        """セッション終了時にランク結果ダイアログを表示する（Phase R8.4）"""
        if not result:
            return
        from gui.gui_session_result_dialog import SessionResultDialog
        dialog = SessionResultDialog(result, parent=self)
        dialog.exec()