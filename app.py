"""
VCI-100 AI DJ Mixer - Main Entry Point
========================================
Phase 9G: Auto-Analysis & HotFolder Fix
- 起動時の自動解析対応
- HotFolderWatcher連携修正
- 重複シグナル処理の整理
"""

import sys
import os
from pathlib import Path
from logging.handlers import RotatingFileHandler

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from gui.gui_main_window import MainWindow
from mixer_core import AIVCIMixer

from PyQt6.QtWidgets import QApplication
import logging


def setup_logging(debug_mode: bool = False):
    """
    ログファイル出力とローテーション設定
    - logs/ai_dj_mixer.log に出力
    - ファイルサイズ 5MB でローテーション
    - 最大3世代保持
    """
    log_dir = project_root / 'logs'
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / 'ai_dj_mixer.log'
    
    # ログフォーマット
    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # ファイルハンドラ（ローテーション対応）
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=3,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    # コンソールハンドラ（標準出力）
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # ルートロガー設定
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # 起動ログ
    logger = logging.getLogger(__name__)
    logger.info("="*60)
    logger.info("VCI-100 AI DJ Mixer - Starting")
    logger.info(f"Log file: {log_file}")
    logger.info(f"Debug mode: {debug_mode}")
    logger.info("="*60)


logger = logging.getLogger(__name__)


def main():
    # 引数解析: python app.py <tracks_folder> [--debug]
    debug_mode = "--debug" in sys.argv or "-d" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    
    # ログ設定（最初に実行）
    setup_logging(debug_mode)
    
    # 引数がない場合はカレントディレクトリの ./tracks を使用
    tracks_folder = args[0] if args else "./tracks"
    
    # フォルダが存在しない場合は作成
    if not os.path.exists(tracks_folder):
        try:
            os.makedirs(tracks_folder)
            logger.info(f"Created tracks folder: {tracks_folder}")
        except Exception as e:
            logger.error(f"Failed to create folder {tracks_folder}: {e}")
    
    app = QApplication(sys.argv)
    
    # 1. コンポーネントの初期化
    mixer = AIVCIMixer(tracks_folder, debug_mode=debug_mode)
    window = MainWindow(prompt_coordinator=mixer.prompt_coordinator)
    
    # 2. シグナル接続（Mixer -> Window: 状態の反映）
    mixer.deck_updated.connect(window.update_deck_info)
    mixer.waveform_updated.connect(window.update_waveform)
    mixer.position_updated.connect(window.update_position)
    mixer.energy_profile_updated.connect(window.update_energy_profile)
    mixer.prompt_generated.connect(window.on_prompt_generated)
    mixer.library_updated.connect(window.update_library)
    mixer.library_cursor_changed.connect(window.update_library_cursor)
    mixer.energy_data_updated.connect(window.update_energy_flow)
    mixer.status_updated.connect(lambda s: window.status_bar.showMessage(s))
    mixer.generation_status_changed.connect(window.prompt_panel.set_generation_status)
    
    # ループ状態の視覚的同期
    def on_loop_updated(deck_id, active, start, duration):
        total = 0.0
        if deck_id == "A":
            total = mixer.audio_engine.deck_a.get_duration()
        else:
            total = mixer.audio_engine.deck_b.get_duration()
        
        try:
            if deck_id == "A":
                if hasattr(window.deck_a_widget, 'update_loop_state'):
                    window.deck_a_widget.update_loop_state(active, start, duration, total)
                else:
                    logger.warning(f"Deck A widget missing update_loop_state method")
            else:
                if hasattr(window.deck_b_widget, 'update_loop_state'):
                    window.deck_b_widget.update_loop_state(active, start, duration, total)
                else:
                    logger.warning(f"Deck B widget missing update_loop_state method")
        except Exception as e:
            logger.error(f"Error updating loop state for Deck {deck_id}: {e}", exc_info=True)

    mixer.loop_updated.connect(on_loop_updated)

    # P-02 Beatgrid: ビートグリッドを各デッキウィジェットに反映
    def on_beatgrid_updated(deck_id: str, times: list):
        widget = window.deck_a_widget if deck_id == 'A' else window.deck_b_widget
        if hasattr(widget, 'set_beat_grid'):
            widget.set_beat_grid(times)

    mixer.beatgrid_updated.connect(on_beatgrid_updated)

    # ホットフォルダからのトラック追加通知（GUIへのトースト表示）
    mixer.track_added.connect(window.on_track_added)
    
    # Key互換性更新（Phase 8C Week 2）
    mixer.key_compatibility_updated.connect(window.library_panel.set_compatible_keys)
    
    # 3. シグナル接続（Window -> Mixer: 操作の伝達）
    
    # 手動プロンプト生成ボタン（ボーカルON/OFFフラグ付き）
    window.generate_prompt_requested.connect(mixer.manual_prompt_generate)
    
    # 同期ボタン（将来用）
    window.deck_a_widget.sync_btn.clicked.connect(mixer.sync_deck_a)
    window.deck_b_widget.sync_btn.clicked.connect(mixer.sync_deck_b)
    
    # ライブラリ操作
    window.refresh_library_requested.connect(mixer.refresh_library)
    window.analyze_track_requested.connect(lambda f: mixer.analyze_track(f, force=True))
    window.bpm_update_requested.connect(mixer.update_track_bpm)
    window.load_track_requested.connect(mixer.load_track_by_path)
    
    # HOT CUE操作 (Phase 8C)
    window.hot_cue_trigger_requested.connect(mixer.trigger_hot_cue)
    window.hot_cue_set_requested.connect(mixer.set_hot_cue)
    window.hot_cue_clear_requested.connect(mixer.clear_hot_cue)

    # MIDIマッピング変更（XMLインポート/プリセット切り替え後に反映）
    window.midi_mapping_changed.connect(mixer.apply_midi_mapping)

    # ---- Gamification シグナル接続（Phase R8）----

    # Mixer → Window: スコア・講評更新
    mixer.game_score_updated.connect(window.update_game_score)
    mixer.commentary_received.connect(window.update_commentary)

    # Window → Mixer: ゲーム機能のオンオフ・会場切替・講評リクエスト
    window.gamification_enabled_changed.connect(mixer.set_gamification_enabled)
    window.venue_changed.connect(mixer.set_venue)
    window.commentary_requested.connect(mixer.request_commentary)

    # セッション終了：結果取得→ダイアログ表示
    def _on_finish_session():
        result = mixer.finish_game_session()
        window.show_session_result(result)
    window.finish_session_requested.connect(_on_finish_session)

    # VUメーター更新（position_updatedと同タイミング）
    def _update_vu(deck_id: str, pos: float, dur: float):
        if deck_id == "A":
            l, r = mixer.audio_engine.deck_a.get_level()
            window.deck_a_widget.update_vu(l, r)
        else:
            l, r = mixer.audio_engine.deck_b.get_level()
            window.deck_b_widget.update_vu(l, r)
    mixer.position_updated.connect(_update_vu)

    # DSP状態可視化（EQ/Filter値をデッキウィジェットに反映）
    def _update_dsp(deck_id: str, dsp: dict):
        w = window.deck_a_widget if deck_id == "A" else window.deck_b_widget
        w.update_dsp(
            dsp.get('eq_high', 0.0),
            dsp.get('eq_mid',  0.0),
            dsp.get('eq_low',  0.0),
            dsp.get('filter_val', 0.0)
        )
    mixer.dsp_updated.connect(_update_dsp)

    # 波形クリックでシーク
    def _on_seek_requested(deck_id: str, seconds: float):
        deck = mixer.audio_engine.deck_a if deck_id == "A" else mixer.audio_engine.deck_b
        if deck.stream_fx:
            from core.audio_constants import BASS_LIB, BASS_POS_BYTE
            byte_pos = BASS_LIB.BASS_ChannelSeconds2Bytes(deck.stream_fx, seconds)
            BASS_LIB.BASS_ChannelSetPosition(deck.stream_fx, byte_pos, BASS_POS_BYTE)
    window.deck_a_widget.seek_requested.connect(_on_seek_requested)
    window.deck_b_widget.seek_requested.connect(_on_seek_requested)

    # HOT CUE表示更新（position_updatedに便乗り）
    # HotCueManager経由で取得（deck.hot_cuesは廃止）
    def _update_hot_cues(deck_id: str, pos: float, dur: float):
        if deck_id == "A":
            slots = [s.position for s in mixer.hcm_a.all_slots()]
            window.deck_a_widget.update_hot_cues(slots)
        else:
            slots = [s.position for s in mixer.hcm_b.all_slots()]
            window.deck_b_widget.update_hot_cues(slots)
    mixer.position_updated.connect(_update_hot_cues)

    # 4. 実行開始
    # MIDIコントローラーの接続確認
    if mixer.connect_controller():
        window.status_bar.showMessage(f"Connected to VCI-100. Library: {tracks_folder}")
    else:
        logger.warning("VCI-100 not found. Running in UI-only mode.")
        window.status_bar.showMessage("VCI-100 Not Found (Simulation Mode)")

    window.show()
    mixer.start()
    
    # 接続後にライブラリを強制リフレッシュして初期表示を確実にする
    mixer.refresh_library()
    

    # Application cleanup on exit
    def cleanup():
        logger.info("Application shutting down...")
        mixer.stop()
    
    app.aboutToQuit.connect(cleanup)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()