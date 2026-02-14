"""
Mixer Core Logic (Phase 9G + EQ Upgrade + Loop Upgrade)
=========================================================
修正点:
- Phase1フィードバック対応: EQブーストを+3dB/段に制限 (実効+9dB)
- Loop Upgrade: toggle_4bar_loop()でdeck.loop_start_sec/loop_duration_secを使用
- 起動時の未解析トラック自動解析を追加
- HotFolderWatcher の destination_folder 設定を修正
- _emit_library_update メソッドを追加(再帰呼び出し防止)
"""

import os
import logging
import time
import math
from pathlib import Path
from threading import Thread, Lock
from PyQt6.QtCore import QObject, pyqtSignal

from track_analyzer import TrackAnalyzer
from core.ai import PromptCoordinator
from core import AudioEngine, AudioConfig
from hot_folder_watcher import HotFolderWatcher
from prompt_worker import PromptGeneratorWorker
from midi_controller import MIDIController

logger = logging.getLogger(__name__)


# サポートされているオーディオ拡張子
SUPPORTED_AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg", ".m4a")


class AIVCIMixer(QObject):
    # --- GUIへの通知用シグナル ---
    deck_updated = pyqtSignal(str, dict)
    waveform_updated = pyqtSignal(str, object)
    prompt_generated = pyqtSignal(dict)
    energy_updated = pyqtSignal(str)
    energy_data_updated = pyqtSignal(list)
    energy_profile_updated = pyqtSignal(str, list, float)
    library_updated = pyqtSignal(list)
    library_cursor_changed = pyqtSignal(int)
    position_updated = pyqtSignal(str, float, float)
    dsp_updated = pyqtSignal(str, dict)
    status_updated = pyqtSignal(str)
    generation_status_changed = pyqtSignal(str)
    track_added = pyqtSignal(str)
    loop_updated = pyqtSignal(str, bool, float, float) # deck_id, active, start, duration
    key_compatibility_updated = pyqtSignal(list)  # 互換キー (Phase 8C Week 2)
    
    def __init__(self, tracks_folder="./tracks", debug_mode=False):
        super().__init__()
        self.tracks_folder = os.path.abspath(tracks_folder)  # 絶対パスに変換
        self.config = AudioConfig()
        self.audio_engine = AudioEngine(self.config)
        self.analyzer = TrackAnalyzer()
        self.prompt_coordinator = PromptCoordinator()
        
        # 修正: destination_folder をコンストラクタで正しく設定
        self.hot_folder_watcher = HotFolderWatcher(
            watch_folder=os.path.join(os.path.expanduser("~"), "Downloads"),
            destination_folder=self.tracks_folder
        )
        
        self.midi_controller = MIDIController(debug_mode=debug_mode)
        self.prompt_worker = PromptGeneratorWorker(self.prompt_coordinator)
        
        self.track_list = []
        self.track_list_lock = Lock()  # track_listのスレッドセーフ用
        self.library_cursor = 0
        self.deck_a_info = None
        self.deck_b_info = None
        self._safe_start_mode = True
        self._analyzing = False  # 解析中フラグ(再帰防止)
        
        # MIDIコールバックは connect_controller() 後に登録
        # _setup_connections() はここでは呼ばない
        
        # HotFolderとPromptWorkerの接続は常に必要
        self.hot_folder_watcher.file_detected.connect(self._on_new_file_detected)
        self.hot_folder_watcher.file_moved.connect(self._on_file_moved)
        self.hot_folder_watcher.status_changed.connect(lambda s: self.status_updated.emit(s))
        self.hot_folder_watcher.error_occurred.connect(lambda e: logger.error(f"HotFolder error: {e}"))
        self.prompt_worker.finished.connect(self._on_prompt_generated)
        self.prompt_worker.status_changed.connect(self.generation_status_changed)
        
        logger.info("About to initialize library...")
        self._init_library()
        logger.info("Library initialization complete")
        
        from PyQt6.QtCore import QTimer
        self._time_update_timer = QTimer()
        self._time_update_timer.timeout.connect(self._update_positions)
        self._time_update_timer.setInterval(100)
        self.running = False

    def connect_controller(self):
        """MIDIコントローラーに接続し、成功したらコールバックを設定"""
        connected = self.midi_controller.connect()
        if connected:
            self._setup_connections()
        return connected
    
    def _setup_connections(self):
        """MIDIおよび内部コンポーネントの配線"""
        self.midi_controller.register_callback('crossfader', self.on_crossfader)
        self.midi_controller.register_callback('master_volume', self.on_master_volume)
        
        # Deck A Controls
        self.midi_controller.register_callback('deck_a_volume', lambda v: self.audio_engine.deck_a.set_volume(v))
        self.midi_controller.register_callback('deck_a_trim', lambda v: self.audio_engine.deck_a.set_trim(self._norm_to_db(v)))
        self.midi_controller.register_callback('deck_a_eq_high', lambda v: (
            self.audio_engine.deck_a.set_eq_high(self._norm_to_eq_db(v)),
            self.prompt_coordinator.record_eq_operation('high', self._norm_to_eq_db(v))
        ))
        self.midi_controller.register_callback('deck_a_eq_mid', lambda v: (
            self.audio_engine.deck_a.set_eq_mid(self._norm_to_eq_db(v)),
            self.prompt_coordinator.record_eq_operation('mid', self._norm_to_eq_db(v))
        ))
        self.midi_controller.register_callback('deck_a_eq_low', lambda v: (
            self.audio_engine.deck_a.set_eq_low(self._norm_to_eq_db(v)),
            self.prompt_coordinator.record_eq_operation('low', self._norm_to_eq_db(v))
        ))
        self.midi_controller.register_callback('deck_a_filter', lambda v: (
            self.audio_engine.deck_a.set_filter(self._norm_to_filter(v)),
            self.prompt_coordinator.record_filter_operation(self._norm_to_filter(v))
        ))
        self.midi_controller.register_callback('deck_a_tempo', lambda v: self._handle_tempo("A", v))
        
        # Deck B Controls
        self.midi_controller.register_callback('deck_b_volume', lambda v: self.audio_engine.deck_b.set_volume(v))
        self.midi_controller.register_callback('deck_b_trim', lambda v: self.audio_engine.deck_b.set_trim(self._norm_to_db(v)))
        self.midi_controller.register_callback('deck_b_eq_high', lambda v: (
            self.audio_engine.deck_b.set_eq_high(self._norm_to_eq_db(v)),
            self.prompt_coordinator.record_eq_operation('high', self._norm_to_eq_db(v))
        ))
        self.midi_controller.register_callback('deck_b_eq_mid', lambda v: (
            self.audio_engine.deck_b.set_eq_mid(self._norm_to_eq_db(v)),
            self.prompt_coordinator.record_eq_operation('mid', self._norm_to_eq_db(v))
        ))
        self.midi_controller.register_callback('deck_b_eq_low', lambda v: (
            self.audio_engine.deck_b.set_eq_low(self._norm_to_eq_db(v)),
            self.prompt_coordinator.record_eq_operation('low', self._norm_to_eq_db(v))
        ))
        self.midi_controller.register_callback('deck_b_filter', lambda v: (
            self.audio_engine.deck_b.set_filter(self._norm_to_filter(v)),
            self.prompt_coordinator.record_filter_operation(self._norm_to_filter(v))
        ))
        self.midi_controller.register_callback('deck_b_tempo', lambda v: self._handle_tempo("B", v))

        # Transport
        self.midi_controller.register_callback('play_a', lambda v: self._toggle_play("A"))
        self.midi_controller.register_callback('play_b', lambda v: self._toggle_play("B"))
        self.midi_controller.register_callback('cue_a', lambda v: self.audio_engine.deck_a.cue())
        self.midi_controller.register_callback('cue_b', lambda v: self.audio_engine.deck_b.cue())
        
        # Loop
        self.midi_controller.register_callback('loop_a', lambda v: self.toggle_4bar_loop("A"))
        self.midi_controller.register_callback('loop_b', lambda v: self.toggle_4bar_loop("B"))

        # Library & Navigation
        self.midi_controller.register_callback('prev_track', lambda v: self._move_cursor(-1))
        self.midi_controller.register_callback('next_track', lambda v: self._move_cursor(1))
        self.midi_controller.register_callback('load_a', lambda v: self._load_selected_track("A"))
        self.midi_controller.register_callback('load_b', lambda v: self._load_selected_track("B"))

    def _norm_to_db(self, val): 
        return (val - 0.5) * 20.0
    
    def _norm_to_eq_db(self, val):
        """
        MIDI 0.0-1.0 → EQ dB変換(非対称・DJミキサー仕様)
        
        Phase1フィードバック対応:
        - ブーストを+3dB/段に制限 (実効+9dB)
        - カットは-15dB/段 (実効-45dB)
        
        カーブ設計(1段あたりの値、3段カスケードで×3倍が実効値):
          val=0.0   → -15.0dB (実効: -45dB ≈ full kill)
          val=0.5   →   0.0dB (flat)
          val=1.0   →  +3.0dB (実効: +9dB = safe boost, クリップなし)
        """
        if val <= 0.5:
            # Cut: 0.0→-15dB, 0.5→0dB
            return (val - 0.5) * 30.0
        else:
            # Boost: 0.5→0dB, 1.0→+3dB (Phase1修正: +6dB→+3dB)
            return (val - 0.5) * 6.0
    
    def _norm_to_filter(self, val): 
        return (val - 0.5) * 2.0
    
    def on_crossfader(self, val): 
        self._check_safe_start()
        self.audio_engine.set_crossfader(val)
        
    def on_master_volume(self, val): 
        self._check_safe_start()
        self.audio_engine.set_master_volume(val)
        
    def _check_safe_start(self):
        if self._safe_start_mode: 
            self._safe_start_mode = False
            self.status_updated.emit("Ready")

    def _toggle_play(self, deck_id):
        """Play/Pauseをトグル"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        if not deck.stream_fx:
            return
        
        # BASS_ChannelIsActiveで再生状態を確認
        # 1=BASS_ACTIVE_PLAYING, 3=BASS_ACTIVE_PAUSED
        from core.audio_constants import BASS_LIB
        if BASS_LIB:
            state = BASS_LIB.BASS_ChannelIsActive(deck.stream_fx)
            if state == 1:  # Playing
                deck.pause()
            else:  # Paused or Stopped
                deck.play() 

    # --- Loop Logic (Phase 8C Week 3 + Loop Upgrade) ---
    def toggle_4bar_loop(self, deck_id: str):
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        info = self.deck_a_info if deck_id == "A" else self.deck_b_info
        
        if not deck.stream_fx or not info: 
            return

        if deck.loop_active:
            deck.clear_loop()
            self.status_updated.emit(f"Deck {deck_id}: Loop OUT")
            self.loop_updated.emit(deck_id, False, 0.0, 0.0)
        else:
            bpm = info.get('bpm', 120.0)
            first_beat = info.get('first_beat', 0.0)
            
            # ビートスナップ対応のループ設定
            deck.set_loop_snapped(bpm, first_beat, bars=4)
            
            # Loop Upgrade: Deckに保存されたスナップ済み情報を使ってGUI通知
            # ※ deck.get_position()はリアルタイム再生位置なので使わない
            self.status_updated.emit(
                f"Deck {deck_id}: Loop 4 Bars @ {deck.loop_start_sec:.1f}s "
                f"({deck.loop_duration_sec:.2f}s)"
            )
            self.loop_updated.emit(
                deck_id, True, 
                deck.loop_start_sec, 
                deck.loop_duration_sec
            )

    # --- HOT CUE Logic (Phase 8C) ---
    def set_hot_cue(self, deck_id: str, slot: int):
        """現在の再生位置をHOT CUEに記録"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        if not deck.stream_fx:
            return
        
        position = deck.get_position()
        deck.set_hot_cue(slot, position)
        self.status_updated.emit(f"Deck {deck_id}: HOT CUE {slot+1} set at {position:.1f}s")

    def trigger_hot_cue(self, deck_id: str, slot: int):
        """HOT CUEにジャンプ"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        deck.jump_to_hot_cue(slot)

    def clear_hot_cue(self, deck_id: str, slot: int):
        """HOT CUEをクリア"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        deck.clear_hot_cue(slot)

    # --- Sync Logic (Phase 8C Week 2) ---
    def sync_deck_a(self):
        """Deck AをDeck BのBPMに同期"""
        if self.deck_b_info and self.deck_b_info.get('bpm'):
            target_bpm = self.deck_b_info['bpm']
            if self.audio_engine.deck_a.sync_bpm(target_bpm):
                self.status_updated.emit(f"Deck A synced to {target_bpm:.1f} BPM")
            else:
                self.status_updated.emit("Sync failed: No BPM info")

    def sync_deck_b(self):
        """Deck BをDeck AのBPMに同期"""
        if self.deck_a_info and self.deck_a_info.get('bpm'):
            target_bpm = self.deck_a_info['bpm']
            if self.audio_engine.deck_b.sync_bpm(target_bpm):
                self.status_updated.emit(f"Deck B synced to {target_bpm:.1f} BPM")
            else:
                self.status_updated.emit("Sync failed: No BPM info")

    # --- Library Navigation ---
    def _move_cursor(self, delta: int):
        with self.track_list_lock:
            if not self.track_list: 
                return
            self.library_cursor = (self.library_cursor + delta) % len(self.track_list)
            self.library_cursor_changed.emit(self.library_cursor)

    def _load_selected_track(self, deck_id: str):
        with self.track_list_lock:
            if not self.track_list or self.library_cursor >= len(self.track_list): 
                return
            track = self.track_list[self.library_cursor]
        self.load_track_by_path(deck_id, track['filepath'])

    def _on_new_file_detected(self, filename: str):
        """ホットフォルダで新規ファイル検出時の通知(移動前)"""
        self.status_updated.emit(f"New file detected: {filename}")
        
    def _on_file_moved(self, src, dst): 
        """ホットフォルダからファイルが移動された時の処理"""
        filename = os.path.basename(dst)
        logger.info(f"HotFolder: File moved to library: {filename}")
        self.track_added.emit(filename)
        
        # 移動されたファイルを解析してライブラリ更新
        def run():
            logger.info(f"Auto-analyzing new track: {filename}")
            self.status_updated.emit(f"Analyzing new track: {filename}")
            self.analyzer.analyze_track(dst, force_reanalyze=True)
            self._emit_library_update()
            self.status_updated.emit(f"New track ready: {filename}")
        Thread(target=run, daemon=True).start()
    
    def _update_positions(self):
        if not self.running: 
            return
        self.position_updated.emit("A", self.audio_engine.deck_a.get_position(), self.audio_engine.deck_a.get_duration())
        self.position_updated.emit("B", self.audio_engine.deck_b.get_position(), self.audio_engine.deck_b.get_duration())
        
    def start(self):
        if not self.audio_engine.start(): 
            logger.warning("Audio engine failed to start")
            return
        self.running = True
        
        # HotFolderWatcherの起動前に状態をログ
        logger.info(f"Starting HotFolderWatcher...")
        logger.info(f"  Watch folder: {self.hot_folder_watcher.watch_folder}")
        logger.info(f"  Destination: {self.hot_folder_watcher.destination_folder}")
        
        self.hot_folder_watcher.start()
        self._time_update_timer.start()
        
        logger.info("Mixer started successfully")
        
    def stop(self):
        self.running = False
        self._time_update_timer.stop()
        self.hot_folder_watcher.stop()
        self.audio_engine.stop()
        self.midi_controller.close()
        logger.info("Mixer stopped")

    def manual_prompt_generate(self, vocal_enabled: bool = False):
        """手動プロンプト生成トリガー"""
        if self.prompt_worker.isRunning():
            logger.warning("Prompt generation already in progress")
            return

        current = self.deck_a_info if self.audio_engine.deck_a.is_playing() else self.deck_b_info
        if not current:
            self.status_updated.emit("No track loaded for prompt generation")
            return

        self.prompt_worker.setup(
            current_analysis=current,
            deck_a_analysis=self.deck_a_info,
            deck_b_analysis=self.deck_b_info,
            vocal=vocal_enabled
        )
        self.prompt_worker.start()
        self.status_updated.emit("Generating AI prompt...")

    def _on_prompt_generated(self, result: dict):
        """プロンプト生成完了時のコールバック"""
        self.prompt_generated.emit(result)
        self.status_updated.emit("Prompt generated successfully")

    def apply_relative_energy_evaluation(self):
        """全トラックの相対エネルギーレベルを再計算（注: 呼び出し側で既にロック取得済み）"""
        if not self.track_list:
            return
        
        analyzed_tracks = [t for t in self.track_list if t.get('analyzed')]
        if len(analyzed_tracks) < 2:
            return
        
        self.analyzer.recalculate_relative_energy(analyzed_tracks)
        
        for track in self.track_list:
            if track.get('analyzed'):
                h = self.analyzer._get_file_hash(track['filepath'])
                cached = self.analyzer.cache.get(h)
                if cached and 'energy' in cached:
                    track['energy'] = cached['energy']

    def update_track_bpm(self, filepath: str, new_bpm: float):
        """BPMを手動補正し、該当のデッキに適用"""
        if self.analyzer.update_bpm(filepath, new_bpm):
            self.refresh_library()
            # ロード中のデッキ情報も更新
            if self.deck_a_info and self.deck_a_info['filepath'] == filepath:
                self.deck_a_info['bpm'] = new_bpm
                self.deck_updated.emit("A", self.deck_a_info)
            if self.deck_b_info and self.deck_b_info['filepath'] == filepath:
                self.deck_b_info['bpm'] = new_bpm
                self.deck_updated.emit("B", self.deck_b_info)
            logger.info(f"BPM Updated: {os.path.basename(filepath)} -> {new_bpm}")

    def _handle_tempo(self, deck_id, val):
        percent = (val - 0.5) * 20.0 
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        deck.set_tempo(percent)

    def _init_library(self): 
        self.refresh_library()

    def refresh_library(self):
        """ライブラリをスキャンし、未解析トラックを自動解析"""
        logger.info("refresh_library: START")
        root = self.tracks_folder
        if not os.path.exists(root): 
            os.makedirs(root)
            logger.info(f"Created tracks folder: {root}")
        
        logger.info(f"Scanning folder: {root}")
        files = [f for f in os.listdir(root) if f.lower().endswith(SUPPORTED_AUDIO_EXTENSIONS)]
        logger.info(f"Found {len(files)} audio files")
        
        logger.info("Entering track_list_lock...")
        with self.track_list_lock:
            logger.info("Lock acquired, building track list...")
            self.track_list = []
            
            unanalyzed = []  # 未解析トラックのリスト
            
            for i, f in enumerate(files):
                logger.info(f"Processing file {i+1}/{len(files)}: {f}")
                path = os.path.join(root, f)
                logger.info(f"  Getting file hash...")
                h = self.analyzer._get_file_hash(path)
                logger.info(f"  Hash: {h[:16]}...")
                logger.info(f"  Checking cache...")
                cached = self.analyzer.cache.get(h)
                logger.info(f"  Cached: {cached is not None}")
                item = {'filename': f, 'filepath': path, 'analyzed': cached is not None}
                if cached: 
                    item.update(cached)
                else:
                    unanalyzed.append(path)  # 未解析をリストに追加
                self.track_list.append(item)
                logger.info(f"  Added to track_list")
            
            logger.info(f"Track list built: {len(self.track_list)} items")
            logger.info("Calling apply_relative_energy_evaluation()...")
            self.apply_relative_energy_evaluation()
            logger.info("apply_relative_energy_evaluation() complete")
            # ロック内でリストのコピーを作成してemit
            track_list_copy = list(self.track_list)
            logger.info("Exiting track_list_lock...")
        
        logger.info("Lock released")
        # ロック外でemit(GUIスレッドでの処理を避ける)
        logger.info(f"Emitting library_updated signal with {len(track_list_copy)} tracks")
        self.library_updated.emit(track_list_copy)
        logger.info("library_updated signal emitted")
        
        # 未解析トラックをバックグラウンドで解析(再帰防止チェック)
        if unanalyzed and not self._analyzing:
            logger.info(f"Found {len(unanalyzed)} unanalyzed tracks. Starting auto-analysis...")
            self.status_updated.emit(f"Analyzing {len(unanalyzed)} tracks...")
            self._analyze_unanalyzed_tracks(unanalyzed)

    def _analyze_unanalyzed_tracks(self, paths: list):
        """未解析トラックをバックグラウンドで順次解析"""
        def run():
            self._analyzing = True
            try:
                total = len(paths)
                for i, path in enumerate(paths, 1):
                    filename = os.path.basename(path)
                    logger.info(f"Auto-analyzing ({i}/{total}): {filename}")
                    self.status_updated.emit(f"Analyzing ({i}/{total}): {filename}")
                    
                    try:
                        self.analyzer.analyze_track(path)
                    except Exception as e:
                        logger.error(f"Failed to analyze {filename}: {e}")
                
                # 全て完了後にライブラリを更新
                logger.info(f"Auto-analysis complete: {total} tracks processed")
                self.status_updated.emit(f"Analysis complete: {total} tracks")
                self._emit_library_update()
            finally:
                self._analyzing = False
                
        Thread(target=run, daemon=True).start()

    def _emit_library_update(self):
        """解析済みデータでライブラリを再構築して通知(再帰呼び出し防止)"""
        root = self.tracks_folder
        if not os.path.exists(root):
            return
            
        files = [f for f in os.listdir(root) if f.lower().endswith(SUPPORTED_AUDIO_EXTENSIONS)]
        
        with self.track_list_lock:
            self.track_list = []
            
            for f in files:
                path = os.path.join(root, f)
                h = self.analyzer._get_file_hash(path)
                cached = self.analyzer.cache.get(h)
                item = {'filename': f, 'filepath': path, 'analyzed': cached is not None}
                if cached: 
                    item.update(cached)
                self.track_list.append(item)
            
            self.apply_relative_energy_evaluation()
            track_list_copy = list(self.track_list)
        
        self.library_updated.emit(track_list_copy)

    def analyze_track(self, filepath: str, force=False):
        def run():
            logger.info(f"Analyzing track: {os.path.basename(filepath)}")
            self.status_updated.emit(f"Analyzing: {os.path.basename(filepath)}")
            self.analyzer.analyze_track(filepath, force_reanalyze=force)
            self._emit_library_update()
            self.status_updated.emit("Analysis complete")
        Thread(target=run, daemon=True).start()

    def load_track_by_path(self, deck_id: str, filepath: str):
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        info = next((t for t in self.track_list if t['filepath'] == filepath), None)
        
        # track_listにない場合は解析を実行
        if not info: 
            logger.info(f"Track not in library, analyzing: {os.path.basename(filepath)}")
            info = self.analyzer.analyze_track(filepath)
            self._emit_library_update()
        # キャッシュがない(未解析)の場合も解析
        elif not info.get('analyzed', False):
            logger.info(f"Track not analyzed, analyzing: {os.path.basename(filepath)}")
            info = self.analyzer.analyze_track(filepath)
            self._emit_library_update()
            
        def on_loaded(name, success):
            if success:
                duration = deck.get_duration()
                energy_profile = info.get('energy', {}).get('profile', [])
                if name == "A": 
                    self.deck_a_info = info
                else: 
                    self.deck_b_info = info
                
                deck.apply_track_analysis(info)
                self.deck_updated.emit(deck_id, info)
                self.waveform_updated.emit(deck_id, deck.get_waveform_data())
                self.energy_profile_updated.emit(deck_id, energy_profile, duration)
                self.dsp_updated.emit(deck_id, deck.get_dsp_settings())
                
                # Phase 8C Week 2: キー互換性チェック
                self._update_key_compatibility()
                
                logger.info(f"Deck {deck_id}: Loaded {info.get('filename', 'Unknown')}")
            else:
                logger.error(f"Deck {deck_id}: Failed to load track")

        deck.on_load_complete = on_loaded
        deck.load(filepath)

    def _update_key_compatibility(self):
        """両デッキがロード済みの場合、キー互換性を計算してGUIに通知"""
        if not self.deck_a_info or not self.deck_b_info:
            self.key_compatibility_updated.emit([])
            return
        
        key_a = self.deck_a_info.get('key')
        key_b = self.deck_b_info.get('key')
        
        if not key_a or not key_b:
            self.key_compatibility_updated.emit([])
            return
        
        # Camelot Wheel風の互換性チェック(簡易版)
        compatible = self._get_compatible_keys(key_a)
        
        # Deck Bのキーが互換リストに含まれている場合、ライブラリ中の互換曲を抽出
        compatible_tracks = []
        if key_b in compatible:
            with self.track_list_lock:
                for track in self.track_list:
                    if track.get('key') in compatible and track['filepath'] != self.deck_a_info['filepath']:
                        compatible_tracks.append(track.get('key', ''))
        
        self.key_compatibility_updated.emit(list(set(compatible_tracks)))

    def _get_compatible_keys(self, key: str) -> list:
        """簡易的なキー互換性判定(±1セミトーン、相対調)"""
        # 簡略化のため、同キー・±1セミトーンのみ
        key_sequence = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        
        if key not in key_sequence:
            return [key]
        
        idx = key_sequence.index(key)
        compatible = [
            key,  # 同キー
            key_sequence[(idx + 1) % 12],  # +1
            key_sequence[(idx - 1) % 12],  # -1
        ]
        return compatible