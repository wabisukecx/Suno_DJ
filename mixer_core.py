"""
Mixer Core Logic (Phase 9G: Auto-Analysis & HotFolder Fix)
=============================================================
ä¿®æ­£ç‚¹:
- èµ·å‹•æ™‚ã®æœªè§£æžãƒˆãƒ©ãƒƒã‚¯è‡ªå‹•è§£æžã‚’è¿½åŠ 
- HotFolderWatcher ã® destination_folder è¨­å®šã‚’ä¿®æ­£
- _emit_library_update ãƒ¡ã‚½ãƒƒãƒ‰ã‚’è¿½åŠ ï¼ˆå†å¸°å‘¼ã³å‡ºã—é˜²æ­¢ï¼‰
"""

import os
import logging
import time
import math
from pathlib import Path
from threading import Thread
from PyQt6.QtCore import QObject, pyqtSignal

from track_analyzer import TrackAnalyzer
from prompt_generator import PromptGenerator
from audio_engine import AudioEngine, AudioConfig
from hot_folder_watcher import HotFolderWatcher
from prompt_worker import PromptGeneratorWorker
from midi_controller import MIDIController

logger = logging.getLogger(__name__)


class AIVCIMixer(QObject):
    # --- GUIã¸ã®é€šçŸ¥ç”¨ã‚·ã‚°ãƒŠãƒ« ---
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
    key_compatibility_updated = pyqtSignal(list)  # compatible_keys (Phase 8C Week 2)
    
    def __init__(self, tracks_folder="./tracks", debug_mode=False):
        super().__init__()
        self.tracks_folder = os.path.abspath(tracks_folder)  # çµ¶å¯¾ãƒ‘ã‚¹ã«å¤‰æ›
        self.config = AudioConfig()
        self.audio_engine = AudioEngine(self.config)
        self.analyzer = TrackAnalyzer()
        self.prompt_generator = PromptGenerator()
        
        # ä¿®æ­£: destination_folder ã‚’ã‚³ãƒ³ã‚¹ãƒˆãƒ©ã‚¯ã‚¿ã§æ­£ã—ãè¨­å®š
        self.hot_folder_watcher = HotFolderWatcher(
            destination_folder=self.tracks_folder
        )
        
        self.midi_controller = MIDIController(debug_mode=debug_mode)
        self.prompt_worker = PromptGeneratorWorker(self.prompt_generator)
        
        self.track_list = []
        self.library_cursor = 0
        self.deck_a_info = None
        self.deck_b_info = None
        self._safe_start_mode = True
        self._analyzing = False  # è§£æžä¸­ãƒ•ãƒ©ã‚°ï¼ˆå†å¸°é˜²æ­¢ï¼‰
        
        self._setup_connections()
        self._init_library()
        
        from PyQt6.QtCore import QTimer
        self._time_update_timer = QTimer()
        self._time_update_timer.timeout.connect(self._update_positions)
        self._time_update_timer.setInterval(100)
        self.running = False

    def _setup_connections(self):
        """MIDIãŠã‚ˆã³å†…éƒ¨ã‚³ãƒ³ãƒãƒ¼ãƒãƒ³ãƒˆã®é…ç·š"""
        self.midi_controller.register_callback('crossfader', self.on_crossfader)
        self.midi_controller.register_callback('master_volume', self.on_master_volume)
        
        # Deck A Controls
        self.midi_controller.register_callback('deck_a_volume', lambda v: self.audio_engine.deck_a.set_volume(v))
        self.midi_controller.register_callback('deck_a_trim', lambda v: self.audio_engine.deck_a.set_trim(self._norm_to_db(v)))
        self.midi_controller.register_callback('deck_a_eq_high', lambda v: self.audio_engine.deck_a.set_eq_high(self._norm_to_eq_db(v)))
        self.midi_controller.register_callback('deck_a_eq_mid', lambda v: self.audio_engine.deck_a.set_eq_mid(self._norm_to_eq_db(v)))
        self.midi_controller.register_callback('deck_a_eq_low', lambda v: self.audio_engine.deck_a.set_eq_low(self._norm_to_eq_db(v)))
        self.midi_controller.register_callback('deck_a_filter', lambda v: self.audio_engine.deck_a.set_filter(self._norm_to_filter(v)))
        self.midi_controller.register_callback('deck_a_tempo', lambda v: self._handle_tempo("A", v))
        
        # Deck B Controls
        self.midi_controller.register_callback('deck_b_volume', lambda v: self.audio_engine.deck_b.set_volume(v))
        self.midi_controller.register_callback('deck_b_trim', lambda v: self.audio_engine.deck_b.set_trim(self._norm_to_db(v)))
        self.midi_controller.register_callback('deck_b_eq_high', lambda v: self.audio_engine.deck_b.set_eq_high(self._norm_to_eq_db(v)))
        self.midi_controller.register_callback('deck_b_eq_mid', lambda v: self.audio_engine.deck_b.set_eq_mid(self._norm_to_eq_db(v)))
        self.midi_controller.register_callback('deck_b_eq_low', lambda v: self.audio_engine.deck_b.set_eq_low(self._norm_to_eq_db(v)))
        self.midi_controller.register_callback('deck_b_filter', lambda v: self.audio_engine.deck_b.set_filter(self._norm_to_filter(v)))
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

        # External Events
        self.hot_folder_watcher.file_detected.connect(self._on_new_file_detected)
        self.hot_folder_watcher.file_moved.connect(self._on_file_moved)
        self.hot_folder_watcher.status_changed.connect(lambda s: self.status_updated.emit(s))
        self.hot_folder_watcher.error_occurred.connect(lambda e: logger.error(f"HotFolder error: {e}"))
        self.prompt_worker.finished.connect(self._on_prompt_generated)
        self.prompt_worker.status_changed.connect(self.generation_status_changed)

    def connect_controller(self): return self.midi_controller.connect()
    def _norm_to_db(self, val): return (val - 0.5) * 20.0
    def _norm_to_eq_db(self, val): return (val - 0.5) * 30.0
    def _norm_to_filter(self, val): return (val - 0.5) * 2.0
    
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
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        deck.play() 

    # --- Loop Logic (Phase 8C Week 3: Beat Snap) ---
    def toggle_4bar_loop(self, deck_id: str):
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        info = self.deck_a_info if deck_id == "A" else self.deck_b_info
        
        if not deck.stream_fx or not info: return

        if deck.loop_active:
            deck.clear_loop()
            self.status_updated.emit(f"Deck {deck_id}: Loop OUT")
            self.loop_updated.emit(deck_id, False, 0.0, 0.0)
        else:
            bpm = info.get('bpm', 120.0)
            first_beat = info.get('first_beat', 0.0)  # Phase 8C Week 3
            
            # ビートスナップ対応のループ設定
            deck.set_loop_snapped(bpm, first_beat, bars=4)
            
            # ループ情報を取得してGUIに通知
            # set_loop_snappedが内部でset_loopを呼ぶので、実際のループ位置を取得
            loop_start = deck.get_position() if deck.loop_active else 0.0
            loop_duration = 960.0 / (bpm if bpm > 0 else 120.0)
            
            self.status_updated.emit(f"Deck {deck_id}: Loop 4 Bars (Snapped)")
            self.loop_updated.emit(deck_id, True, loop_start, loop_duration)

    # --- HOT CUE Logic (Phase 8C Week 3: Auto-save) ---
    def set_hot_cue(self, deck_id: str, slot: int):
        """Set HOT CUE at current position"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        info = self.deck_a_info if deck_id == "A" else self.deck_b_info
        
        if not deck.stream_fx:
            self.status_updated.emit(f"Error: No track loaded on Deck {deck_id}")
            return
        
        deck.set_hot_cue(slot)
        self.status_updated.emit(f"Deck {deck_id}: HOT CUE {slot+1} SET")
        
        # HOT CUE自動保存（Phase 8C Week 3）
        if info and 'filepath' in info:
            self.analyzer.save_hot_cues(info['filepath'], deck.hot_cues)
    
    def trigger_hot_cue(self, deck_id: str, slot: int):
        """Trigger HOT CUE (jump to position)"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        if not deck.stream_fx:
            return
        
        deck.trigger_hot_cue(slot)
        # ステータスメッセージはaudio_engine側で出力済み
    
    def clear_hot_cue(self, deck_id: str, slot: int):
        """Clear HOT CUE point"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        info = self.deck_a_info if deck_id == "A" else self.deck_b_info
        
        deck.clear_hot_cue(slot)
        self.status_updated.emit(f"Deck {deck_id}: HOT CUE {slot+1} CLEARED")
        
        # HOT CUE自動保存（Phase 8C Week 3）
        if info and 'filepath' in info:
            self.analyzer.save_hot_cues(info['filepath'], deck.hot_cues)

    # --- Key Matching Logic (Phase 8C Week 2) ---
    def _update_key_compatibility(self):
        """現在ロードされているトラックのキー互換性を計算してライブラリに通知"""
        from track_analyzer import get_compatible_keys, extract_camelot_from_key
        
        # 両デッキがロードされていない場合は何もしない
        if not self.deck_a_info and not self.deck_b_info:
            self.key_compatibility_updated.emit([])
            return
        
        # 現在アクティブなデッキのキーを取得
        active_deck_info = self.deck_a_info if self.deck_a_info else self.deck_b_info
        key_string = active_deck_info.get('key', '')
        
        if not key_string:
            self.key_compatibility_updated.emit([])
            return
        
        # Camelot表記を抽出
        camelot = extract_camelot_from_key(key_string)
        
        if not camelot:
            logger.warning(f"Could not extract Camelot key from: {key_string}")
            self.key_compatibility_updated.emit([])
            return
        
        # 互換キーリストを取得
        compatible = get_compatible_keys(camelot)
        
        logger.info(f"Key compatibility: {camelot} → {compatible}")
        self.key_compatibility_updated.emit(compatible)

    # --- AI Prompt Logic ---
    def manual_prompt_generate(self, vocal_enabled: bool):
        """æ‰‹å‹•ã§ãƒ—ãƒ­ãƒ³ãƒ—ãƒˆç”Ÿæˆã‚’ãƒˆãƒªã‚¬ãƒ¼"""
        current = self.deck_a_info if self.deck_a_info else self.deck_b_info
        if not current: 
            self.status_updated.emit("Error: Load a track first")
            return
            
        self.prompt_worker.setup(
            current_analysis=current,
            deck_a_analysis=self.deck_a_info,
            deck_b_analysis=self.deck_b_info,
            energy_target=4,
            vocal=vocal_enabled
        )
        self.prompt_worker.start()

    # --- Library & BPM Update ---
    def update_track_bpm(self, filepath: str, new_bpm: float):
        """æ‰‹å‹•ã§ã®BPMä¿®æ­£ã‚’ã‚­ãƒ£ãƒƒã‚·ãƒ¥ã¨ç¾åœ¨ã®ãƒ‡ãƒƒã‚­ã«é©ç”¨"""
        if self.analyzer.update_bpm(filepath, new_bpm):
            self.refresh_library()
            # ãƒ­ãƒ¼ãƒ‰ä¸­ã®ãƒ‡ãƒƒã‚­æƒ…å ±ã‚‚æ›´æ–°
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
        """ãƒ©ã‚¤ãƒ–ãƒ©ãƒªã‚’ã‚¹ã‚­ãƒ£ãƒ³ã—ã€æœªè§£æžãƒˆãƒ©ãƒƒã‚¯ã‚’è‡ªå‹•è§£æž"""
        root = self.tracks_folder
        if not os.path.exists(root): 
            os.makedirs(root)
            logger.info(f"Created tracks folder: {root}")
            
        files = [f for f in os.listdir(root) if f.lower().endswith('.mp3')]
        self.track_list = []
        
        unanalyzed = []  # æœªè§£æžãƒˆãƒ©ãƒƒã‚¯ã®ãƒªã‚¹ãƒˆ
        
        for f in files:
            path = os.path.join(root, f)
            h = self.analyzer._get_file_hash(path)
            cached = self.analyzer.cache.get(h)
            item = {'filename': f, 'filepath': path, 'analyzed': cached is not None}
            if cached: 
                item.update(cached)
            else:
                unanalyzed.append(path)  # æœªè§£æžã‚’ãƒªã‚¹ãƒˆã«è¿½åŠ 
            self.track_list.append(item)
        
        self.apply_relative_energy_evaluation()
        self.library_updated.emit(self.track_list)
        
        # æœªè§£æžãƒˆãƒ©ãƒƒã‚¯ã‚’ãƒãƒƒã‚¯ã‚°ãƒ©ã‚¦ãƒ³ãƒ‰ã§è§£æžï¼ˆå†å¸°é˜²æ­¢ãƒã‚§ãƒƒã‚¯ï¼‰
        if unanalyzed and not self._analyzing:
            logger.info(f"Found {len(unanalyzed)} unanalyzed tracks. Starting auto-analysis...")
            self.status_updated.emit(f"Analyzing {len(unanalyzed)} tracks...")
            self._analyze_unanalyzed_tracks(unanalyzed)

    def _analyze_unanalyzed_tracks(self, paths: list):
        """æœªè§£æžãƒˆãƒ©ãƒƒã‚¯ã‚’ãƒãƒƒã‚¯ã‚°ãƒ©ã‚¦ãƒ³ãƒ‰ã§é †æ¬¡è§£æž"""
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
                
                # å…¨ã¦å®Œäº†å¾Œã«ãƒ©ã‚¤ãƒ–ãƒ©ãƒªã‚’æ›´æ–°
                logger.info(f"Auto-analysis complete: {total} tracks processed")
                self.status_updated.emit(f"Analysis complete: {total} tracks")
                self._emit_library_update()
            finally:
                self._analyzing = False
                
        Thread(target=run, daemon=True).start()

    def _emit_library_update(self):
        """è§£æžæ¸ˆã¿ãƒ‡ãƒ¼ã‚¿ã§ãƒ©ã‚¤ãƒ–ãƒ©ãƒªã‚’å†æ§‹ç¯‰ã—ã¦é€šçŸ¥ï¼ˆå†å¸°å‘¼ã³å‡ºã—é˜²æ­¢ï¼‰"""
        root = self.tracks_folder
        if not os.path.exists(root):
            return
            
        files = [f for f in os.listdir(root) if f.lower().endswith('.mp3')]
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
        self.library_updated.emit(self.track_list)

    def analyze_track(self, filepath: str, force=False):
        """å˜ä¸€ãƒˆãƒ©ãƒƒã‚¯ã‚’è§£æžï¼ˆæ‰‹å‹•ãƒˆãƒªã‚¬ãƒ¼ç”¨ï¼‰"""
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
        
        # track_listã«ãªã„å ´åˆã¯è§£æžã‚’å®Ÿè¡Œ
        if not info: 
            logger.info(f"Track not in library, analyzing: {os.path.basename(filepath)}")
            info = self.analyzer.analyze_track(filepath)
            self._emit_library_update()
        # ã‚­ãƒ£ãƒƒã‚·ãƒ¥ãŒãªã„ï¼ˆæœªè§£æžï¼‰ã®å ´åˆã‚‚è§£æž
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
                    self.deck_updated.emit("A", info)
                    self.waveform_updated.emit("A", deck.get_waveform_data())
                    self.energy_profile_updated.emit("A", energy_profile, duration)
                else: 
                    self.deck_b_info = info
                    self.deck_updated.emit("B", info)
                    self.waveform_updated.emit("B", deck.get_waveform_data())
                    self.energy_profile_updated.emit("B", energy_profile, duration)
                deck.apply_track_analysis(info)
                
                # HOT CUE読み込み（Phase 8C Week 3）
                hot_cues = self.analyzer.load_hot_cues(filepath)
                deck.hot_cues = hot_cues
                logger.info(f"Deck {name}: HOT CUEs restored: {hot_cues}")
                
                # Key互換性を計算して通知（Phase 8C Week 2）
                self._update_key_compatibility()
                
        deck.on_load_complete = on_loaded
        deck.load(filepath)

    def _on_prompt_generated(self, result): 
        self.prompt_generated.emit(result)
    
    def _move_cursor(self, delta):
        if not self.track_list: return
        self.library_cursor = max(0, min(len(self.track_list)-1, self.library_cursor + delta))
        self.library_cursor_changed.emit(self.library_cursor)
        
    def _load_selected_track(self, deck_id):
        if 0 <= self.library_cursor < len(self.track_list):
            self.load_track_by_path(deck_id, self.track_list[self.library_cursor]['filepath'])
            
    def _on_new_file_detected(self, filename): 
        logger.info(f"HotFolder: New file detected: {filename}")
        self.status_updated.emit(f"New file detected: {filename}")
        
    def _on_file_moved(self, src, dst): 
        """ãƒ›ãƒƒãƒˆãƒ•ã‚©ãƒ«ãƒ€ã‹ã‚‰ãƒ•ã‚¡ã‚¤ãƒ«ãŒç§»å‹•ã•ã‚ŒãŸæ™‚ã®å‡¦ç†"""
        filename = os.path.basename(dst)
        logger.info(f"HotFolder: File moved to library: {filename}")
        self.track_added.emit(filename)
        
        # ç§»å‹•ã•ã‚ŒãŸãƒ•ã‚¡ã‚¤ãƒ«ã‚’è§£æžã—ã¦ãƒ©ã‚¤ãƒ–ãƒ©ãƒªæ›´æ–°
        def run():
            logger.info(f"Auto-analyzing new track: {filename}")
            self.status_updated.emit(f"Analyzing new track: {filename}")
            self.analyzer.analyze_track(dst, force_reanalyze=True)
            self._emit_library_update()
            self.status_updated.emit(f"New track ready: {filename}")
        Thread(target=run, daemon=True).start()
    
    def _update_positions(self):
        if not self.running: return
        self.position_updated.emit("A", self.audio_engine.deck_a.get_position(), self.audio_engine.deck_a.get_duration())
        self.position_updated.emit("B", self.audio_engine.deck_b.get_position(), self.audio_engine.deck_b.get_duration())
        
    def process_midi(self):
        while self.running: 
            self.midi_controller.get_message()
            time.sleep(0.001)
            
    def start(self):
        if not self.audio_engine.start(): 
            logger.warning("Audio engine failed to start")
            return
        self.running = True
        Thread(target=self.process_midi, daemon=True).start()
        
        # HotFolderWatcherã®èµ·å‹•å‰ã«çŠ¶æ…‹ã‚’ãƒ­ã‚°
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
        
    def apply_relative_energy_evaluation(self):
        try:
            # ã‚­ãƒ£ãƒƒã‚·ãƒ¥ã«ã‚ã‚‹åˆ†æžãƒ‡ãƒ¼ã‚¿ã®ã¿ã‚’æŠ½å‡º
            all_a = []
            for t in self.track_list:
                h = self.analyzer._get_file_hash(t['filepath'])
                if h in self.analyzer.cache:
                    all_a.append(self.analyzer.cache[h])
            if all_a: 
                self.energy_data_updated.emit(self.analyzer.recalculate_relative_energy(all_a))
        except Exception as e:
            logger.error(f"Relative energy evaluation error: {e}")


    # --- BPM Sync Functions (Phase 8C Week 2) ---
    def sync_deck_a(self):
        """Deck AをDeck BのBPMに同期"""
        if not self.deck_b_info:
            self.status_updated.emit("Error: Deck B not loaded")
            return
        
        target_bpm = self.deck_b_info.get('bpm', 0)
        if target_bpm <= 0:
            self.status_updated.emit("Error: Deck B BPM invalid")
            return
        
        if self.audio_engine.deck_a.sync_tempo_to(target_bpm):
            self.status_updated.emit(f"Deck A synced to {target_bpm:.1f} BPM")
        else:
            self.status_updated.emit("Deck A sync failed")
    
    def sync_deck_b(self):
        """Deck BをDeck AのBPMに同期"""
        if not self.deck_a_info:
            self.status_updated.emit("Error: Deck A not loaded")
            return
        
        target_bpm = self.deck_a_info.get('bpm', 0)
        if target_bpm <= 0:
            self.status_updated.emit("Error: Deck A BPM invalid")
            return
        
        if self.audio_engine.deck_b.sync_tempo_to(target_bpm):
            self.status_updated.emit(f"Deck B synced to {target_bpm:.1f} BPM")
        else:
            self.status_updated.emit("Deck B sync failed")