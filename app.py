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
from core.mixer_core import AIVCIMixer

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
    window = MainWindow(prompt_generator=mixer.prompt_generator)
    
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
        
        if deck_id == "A":
            window.deck_a_widget.update_loop_state(active, start, duration, total)
        else:
            window.deck_b_widget.update_loop_state(active, start, duration, total)

    mixer.loop_updated.connect(on_loop_updated)
    
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