"""
Mixer Core Logic (Phase 9G + EQ Upgrade + Loop Upgrade + Phase R8 Gamification)
================================================================================
修正点:
- Phase1フィードバック対応: EQブーストを+3dB/段に制限 (実効+9dB)
- Loop Upgrade: toggle_4bar_loop()でdeck.loop_start_sec/loop_duration_secを使用
- 起動時の未解析トラック自動解析を追加
- HotFolderWatcher の destination_folder 設定を修正
- _emit_library_update メソッドを追加(再帰呼び出し防止)
- Phase R8: Gamification統合（GameSession, GeminiOrchestrator, AiCommentator）
- Refactor Step1: _setup_connections() デッキコールバック重複を共通ファクトリメソッドに抽出
- Refactor Step2: _tick_gamification() 責務分離 + _get_key_compat_level() 重複ロジック統合
"""

import os
import logging
import time
import math
from pathlib import Path
from threading import Thread
from PyQt6.QtCore import QObject, pyqtSignal

from track_analyzer import TrackAnalyzer
from core.ai import PromptCoordinator
from core import AudioEngine, AudioConfig
from hot_folder_watcher import HotFolderWatcher
from prompt_worker import PromptGeneratorWorker
from midi_controller import MIDIController
from core.sync_engine import SyncEngine
from core.camelot_wheel import CamelotWheel
from core.mix_advisor import MixAdvisor
from core.style_logger import StyleLogger, OP_EQ_HIGH, OP_EQ_MID, OP_EQ_LOW, OP_FILTER, OP_CROSSFADE, OP_TEMPO, OP_PLAY, OP_LOOP
from core.hotcue_manager import HotCueManager, CueMode, LedCommand
from library_manager import LibraryManager
# Phase R8: Gamification
from core.gamification import (
    GameSession, ScoreSnapshot, ScoreEventType,
    GeminiOrchestrator, AiCommentator,
)

logger = logging.getLogger(__name__)


# サポートされているオーディオ拡張子
SUPPORTED_AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg", ".m4a")


class AIVCIMixer(QObject):
    # --- GUIへの通知用シグナル ---
    deck_updated = pyqtSignal(str, dict)
    waveform_updated = pyqtSignal(str, object, float)  # deck_id, waveform, duration
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
    loop_bars_updated = pyqtSignal(str, int)             # deck_id, current_bars (P-01)
    beatgrid_updated = pyqtSignal(str, list)             # deck_id, beat_times (P-02)
    key_compatibility_updated = pyqtSignal(list)  # 互換キー (Phase 8C Week 2)
    mix_advice_updated = pyqtSignal(dict)            # ミックスアドバイス (Phase R4)
    game_score_updated = pyqtSignal(dict)              # Phase R8: スコア更新
    commentary_received = pyqtSignal(str)              # Phase R8: AI講評テキスト
    
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
        
        self.library_cursor = 0
        self.deck_a_info = None
        self.deck_b_info = None
        self._safe_start_mode = True
        self.sync_engine = SyncEngine()
        self.camelot_wheel = CamelotWheel()
        self.mix_advisor = MixAdvisor()  # Phase R4: Gemini APIキーは設定から後から注入可能
        self.style_logger = StyleLogger()       # Phase R4: MIDI操作ログ
        self.hcm_a = HotCueManager("A")              # Phase R4: HOT CUE 8スロット管理
        self.hcm_b = HotCueManager("B")

        # LibraryManager: ライブラリ管理を委譲
        self.library_manager = LibraryManager(
            tracks_folder=self.tracks_folder,
            analyzer=self.analyzer,
            on_library_updated=self.library_updated.emit,
            on_status_updated=self.status_updated.emit,
            on_track_added=self.track_added.emit,
        )

        # Phase R8: Gamification初期化
        _venues_path = os.path.join(os.path.dirname(__file__), "data", "venues.json")
        self._game_session: GameSession = GameSession.from_venue_id("tokyo", _venues_path)
        self._game_enabled: bool = False   # デフォルトOFF（GUI側でONにする）
        self._gemini_orchestrator: GeminiOrchestrator | None = None
        self._ai_commentator: AiCommentator | None = None

        # PromptCoordinator が Gemini API を初期化済みなら
        # 同じ API キーで GeminiOrchestrator を自動初期化する
        _api_key = os.environ.get("GEMINI_API_KEY")
        if _api_key and getattr(self.prompt_coordinator, 'gemini_model', None):
            self._gemini_orchestrator = GeminiOrchestrator(api_key=_api_key)
            self._ai_commentator = AiCommentator(self._gemini_orchestrator, self._game_session.venue)
            if hasattr(self.mix_advisor, "set_orchestrator"):
                self.mix_advisor.set_orchestrator(self._gemini_orchestrator)
            logger.info("Phase R8: GeminiOrchestrator auto-initialized from GEMINI_API_KEY")

        # Phase R6: キャッシュを v7 へ自動マイグレーション
        n = self.analyzer.migrate_cache()
        if n:
            logger.info(f"Phase R6: cache migration done ({n} entries)")
        
        # P-01: 可変長ループ、デッキごとの現在ループバー数
        # 標準: 1/2, 1, 2, 4, 8, 16 拍小節単位
        self._loop_bars: dict[str, int] = {'A': 4, 'B': 4}
        # サポートするループサイズ値（拍小節）
        LOOP_SIZES = [1, 2, 4, 8, 16, 32]
        self._loop_sizes = LOOP_SIZES
        
        # MIDIコールバックは connect_controller() 後に登録
        # _setup_connections() はここでは呼ばない
        
        # HotFolderとPromptWorkerの接続は常に必要
        self.hot_folder_watcher.file_detected.connect(self._on_new_file_detected)
        self.hot_folder_watcher.file_moved.connect(self.library_manager.on_file_moved)
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
    
    # ─────────────────────────────────────────────────────────────────
    # Step 1: コールバックファクトリメソッド（重複排除）
    # ─────────────────────────────────────────────────────────────────

    def _get_deck(self, deck_id: str):
        """deck_id ('A'/'B') に対応する Deck オブジェクトを返す"""
        return self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b

    def _make_eq_high_cb(self, deck_id: str):
        """EQ High コールバックファクトリ（Deck A/B 共通）"""
        deck = self._get_deck(deck_id)
        log_fn = self.style_logger.log_eq_high
        def cb(v):
            db = self._norm_to_eq_db(v)
            deck.set_eq_high(db)
            self.prompt_coordinator.record_eq_operation('high', db)
            log_fn(deck_id, v)
        return cb

    def _make_eq_mid_cb(self, deck_id: str):
        """EQ Mid コールバックファクトリ（Deck A/B 共通）"""
        deck = self._get_deck(deck_id)
        log_fn = self.style_logger.log_eq_mid
        def cb(v):
            db = self._norm_to_eq_db(v)
            deck.set_eq_mid(db)
            self.prompt_coordinator.record_eq_operation('mid', db)
            log_fn(deck_id, v)
        return cb

    def _make_eq_low_cb(self, deck_id: str):
        """EQ Low コールバックファクトリ（Deck A/B 共通）"""
        deck = self._get_deck(deck_id)
        log_fn = self.style_logger.log_eq_low
        def cb(v):
            db = self._norm_to_eq_db(v)
            deck.set_eq_low(db)
            self.prompt_coordinator.record_eq_operation('low', db)
            log_fn(deck_id, v)
        return cb

    def _make_filter_cb(self, deck_id: str):
        """Filter コールバックファクトリ（Deck A/B 共通）"""
        deck = self._get_deck(deck_id)
        log_fn = self.style_logger.log_filter
        def cb(v):
            fval = self._norm_to_filter(v)
            deck.set_filter(fval)
            self.prompt_coordinator.record_filter_operation(fval)
            log_fn(deck_id, v)
        return cb

    def _setup_connections(self):
        """MIDIおよび内部コンポーネントの配線"""
        self.midi_controller.register_callback('crossfader', self.on_crossfader)
        self.midi_controller.register_callback('master_volume', self.on_master_volume)

        for deck_id in ('A', 'B'):
            p = deck_id.lower()  # 'a' or 'b'
            deck = self._get_deck(deck_id)
            self.midi_controller.register_callback(f'deck_{p}_volume', lambda v, d=deck: d.set_volume(v))
            self.midi_controller.register_callback(f'deck_{p}_trim',   lambda v, d=deck: d.set_trim(self._norm_to_db(v)))
            self.midi_controller.register_callback(f'deck_{p}_eq_high', self._make_eq_high_cb(deck_id))
            self.midi_controller.register_callback(f'deck_{p}_eq_mid',  self._make_eq_mid_cb(deck_id))
            self.midi_controller.register_callback(f'deck_{p}_eq_low',  self._make_eq_low_cb(deck_id))
            self.midi_controller.register_callback(f'deck_{p}_filter',  self._make_filter_cb(deck_id))
            self.midi_controller.register_callback(f'deck_{p}_tempo',   lambda v, did=deck_id: self._handle_tempo(did, v))

        # Transport
        self.midi_controller.register_callback('play_a', lambda v: self._toggle_play("A"))
        self.midi_controller.register_callback('play_b', lambda v: self._toggle_play("B"))
        self.midi_controller.register_callback('cue_a',  lambda v: self.audio_engine.deck_a.cue())
        self.midi_controller.register_callback('cue_b',  lambda v: self.audio_engine.deck_b.cue())

        # Loop (P-01: 可変長ループ)
        self.midi_controller.register_callback('loop_a', lambda v: self.toggle_loop("A"))
        self.midi_controller.register_callback('loop_b', lambda v: self.toggle_loop("B"))
        self.midi_controller.register_callback('loop_size_up_a', lambda v: self.change_loop_size("A", +1))
        self.midi_controller.register_callback('loop_size_dn_a', lambda v: self.change_loop_size("A", -1))
        self.midi_controller.register_callback('loop_size_up_b', lambda v: self.change_loop_size("B", +1))
        self.midi_controller.register_callback('loop_size_dn_b', lambda v: self.change_loop_size("B", -1))

        # Sync (Phase R3)
        self.midi_controller.register_callback('sync_a', lambda v: self.toggle_sync("A"))
        self.midi_controller.register_callback('sync_b', lambda v: self.toggle_sync("B"))

        # Beat Grid Offset
        self.midi_controller.register_callback('beat_grid_fwd_a', lambda v: self.shift_beat_grid("A", +1))
        self.midi_controller.register_callback('beat_grid_bwd_a', lambda v: self.shift_beat_grid("A", -1))
        self.midi_controller.register_callback('beat_grid_fwd_b', lambda v: self.shift_beat_grid("B", +1))
        self.midi_controller.register_callback('beat_grid_bwd_b', lambda v: self.shift_beat_grid("B", -1))

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
        self.style_logger.log_crossfader(val)
        
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
        self.style_logger.log_play(deck_id)
        
        # BASS_ChannelIsActiveで再生状態を確認
        # 1=BASS_ACTIVE_PLAYING, 3=BASS_ACTIVE_PAUSED
        from core.audio_constants import BASS_LIB
        if BASS_LIB:
            state = BASS_LIB.BASS_ChannelIsActive(deck.stream_fx)
            if state == 1:  # Playing
                deck.pause()
            else:  # Paused or Stopped
                deck.play() 

    # --- Loop Logic (P-01: 可変長ループ) ---

    def toggle_loop(self, deck_id: str):
        """現在のループバー数でON/OFFトグル（P-01）"""
        import time as _time
        now = _time.monotonic()
        last_key = f'_loop_last_{deck_id}'
        if (now - getattr(self, last_key, 0.0)) < 0.3:  # 300msデバウンス
            return
        setattr(self, last_key, now)

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
            bars = self._loop_bars[deck_id]  # P-01: 現在設定値を使用
            
            deck.set_loop_snapped(bpm, first_beat, bars=bars)
            
            bars_label = self._bars_label(bars)
            self.status_updated.emit(
                f"Deck {deck_id}: Loop {bars_label} @ {deck.loop_start_sec:.1f}s "
                f"({deck.loop_duration_sec:.2f}s)"
            )
            self.loop_updated.emit(deck_id, True, deck.loop_start_sec, deck.loop_duration_sec)

    def change_loop_size(self, deck_id: str, direction: int):
        """
        ループサイズを一段増減する（P-01）
        direction: +1 = 倍増、-1 = 半分
        ループ中は即座に再設定する。
        """
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        info = self.deck_a_info if deck_id == "A" else self.deck_b_info

        current = self._loop_bars[deck_id]
        idx = self._loop_sizes.index(current) if current in self._loop_sizes else 2
        new_idx = max(0, min(len(self._loop_sizes) - 1, idx + direction))
        new_bars = self._loop_sizes[new_idx]
        self._loop_bars[deck_id] = new_bars
        self.loop_bars_updated.emit(deck_id, new_bars)

        # ループ中なら即座に再設定
        if deck.loop_active and info:
            bpm = info.get('bpm', 120.0)
            first_beat = info.get('first_beat', 0.0)
            deck.set_loop_snapped(bpm, first_beat, bars=new_bars)
            self.loop_updated.emit(deck_id, True, deck.loop_start_sec, deck.loop_duration_sec)

        bars_label = self._bars_label(new_bars)
        self.status_updated.emit(f"Deck {deck_id}: Loop size → {bars_label}")

    # 後方互換: 旧名命を維持
    def toggle_4bar_loop(self, deck_id: str):
        self.toggle_loop(deck_id)

    @staticmethod
    def _bars_label(bars: int) -> str:
        """bars数を表示用文字列に変換"""
        return f"{bars} Bars"

    # --- HOT CUE Logic (Phase R4: HotCueManager 8スロット) ---

    def _get_hcm(self, deck_id: str) -> HotCueManager:
        return self.hcm_a if deck_id == "A" else self.hcm_b

    def set_hot_cue(self, deck_id: str, slot: int, mode: CueMode = CueMode.AUTO):
        """現在の再生位置を HOT CUE に記録（8スロット対応）"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        if not deck.stream_fx:
            return

        position    = deck.get_position()
        is_loop     = deck.loop_active
        loop_dur    = deck.loop_duration_sec
        hcm         = self._get_hcm(deck_id)
        led_event   = hcm.set_cue(slot, position, mode=mode,
                                   is_loop=is_loop, loop_duration=loop_dur)
        self._send_led(led_event)
        self.style_logger.log_hotcue(deck_id, slot)
        label = "LoopCue" if hcm.get_slot(slot).is_loop_cue else "Cue"
        self.status_updated.emit(
            f"Deck {deck_id}: HOT CUE {slot+1} ({label}) set @ {position:.1f}s"
        )

    def trigger_hot_cue(self, deck_id: str, slot: int, play: bool = True):
        """HOT CUE にジャンプし、必要に応じて再生（8スロット対応）"""
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        hcm  = self._get_hcm(deck_id)
        info = self.deck_a_info if deck_id == "A" else self.deck_b_info
        slot_data = hcm.goto(slot)

        if slot_data.position is None:
            return  # 未設定スロット

        deck.set_position(slot_data.position)

        if slot_data.is_loop_cue and slot_data.loop_duration > 0 and info:
            # LoopCue: ジャンプ後にループを再設定
            bpm        = info.get("bpm", 120.0)
            first_beat = info.get("first_beat", 0.0)
            bars       = self._loop_bars[deck_id]
            deck.set_loop_snapped(bpm, first_beat, bars=bars)
            led_event = hcm.activate(slot)
            self._send_led(led_event)
            self.loop_updated.emit(deck_id, True, deck.loop_start_sec, deck.loop_duration_sec)
        else:
            if play and not deck.is_playing():
                deck.play()

    def clear_hot_cue(self, deck_id: str, slot: int):
        """HOT CUE スロットをクリア（8スロット対応）"""
        hcm = self._get_hcm(deck_id)
        led_event = hcm.clear(slot)
        self._send_led(led_event)
        self.status_updated.emit(f"Deck {deck_id}: HOT CUE {slot+1} cleared")

    def swap_hot_cues(self, deck_id: str, slot_a: int, slot_b: int):
        """HOT CUE スロットを入れ替える"""
        hcm = self._get_hcm(deck_id)
        for led_event in hcm.swap(slot_a, slot_b):
            self._send_led(led_event)

    def sync_hotcue_leds(self, deck_id: str):
        """接続直後に LED 状態を全スロット同期する"""
        hcm = self._get_hcm(deck_id)
        for led_event in hcm.led_sync_all():
            self._send_led(led_event)

    def _send_led(self, led_event) -> None:
        """
        LED コマンドを MIDIController に送信する。

        MIDIController に send_led() が実装されていない場合は
        ログに記録するだけ（将来の LED 実装まで安全に無視）。
        """
        try:
            if hasattr(self.midi_controller, "send_led"):
                self.midi_controller.send_led(
                    led_event.note,
                    led_event.velocity,
                )
        except Exception as e:
            logger.debug(f"LED send skipped: {e}")

    # --- Sync Logic (Phase R3: SyncEngine統合) ---
    def toggle_sync(self, deck_id: str):
        """
        Sync ON/OFFをトグルする（Phase R3）

        現在の実装: Deck B = Follower 固定（Deck A = Leader）
        - deck_id='B' → SyncEngineを有効化し、Deck AのBPM/位相に追従
        - deck_id='A' → 将来拡張用（現状は簡易BPM同期のみ）
        """
        if deck_id == 'B':
            if self.sync_engine.is_sync_enabled('B'):
                self.sync_engine.disable_sync('B')
                # テンポを元に戻す（Deck B の original_bpm で計算）
                self.audio_engine.deck_b.set_tempo(0.0)
                self.status_updated.emit("Sync B: OFF")
            else:
                if not self.deck_a_info or not self.deck_b_info:
                    self.status_updated.emit("Sync: No track loaded")
                    return
                self.sync_engine.enable_sync('B', self.audio_engine.deck_b, self.deck_b_info)
                self.status_updated.emit(
                    f"Sync B: ON → Following A "
                    f"({self.deck_a_info.get('bpm', 0):.1f} BPM)"
                )
        else:
            # Deck A（将来: dual sync対応）
            # 現在は簡易BPM同期のみ（後方互換）
            if self.deck_b_info and self.deck_b_info.get('bpm'):
                target_bpm = self.deck_b_info['bpm']
                if self.audio_engine.deck_a.sync_bpm(target_bpm):
                    self.status_updated.emit(f"Deck A synced to {target_bpm:.1f} BPM")
                else:
                    self.status_updated.emit("Sync failed: No BPM info")

    def sync_deck_a(self):
        """後方互換: toggle_sync('A') に委譲"""
        self.toggle_sync('A')

    def sync_deck_b(self):
        """後方互換: toggle_sync('B') に委譲"""
        self.toggle_sync('B')

    def shift_beat_grid(self, deck_id: str, direction: int):
        """
        ビートグリッドを1拍単位でずらす。

        BPMから1拍の秒数を計算し、first_beat および beat_times 全体を
        direction 拍分だけオフセットする。ループ中は再スナップも行う。

        Args:
            deck_id:   'A' or 'B'
            direction: +1 (前方へ1拍) or -1 (後方へ1拍)
        """
        info = self.deck_a_info if deck_id == 'A' else self.deck_b_info
        deck = self.audio_engine.deck_a if deck_id == 'A' else self.audio_engine.deck_b

        if not info or not deck.beat_times:
            self.status_updated.emit(f"Beat Grid {deck_id}: No track loaded")
            return

        bpm = info.get('bpm', 0.0)
        if bpm <= 0:
            return

        beat_dur = 60.0 / bpm
        offset = beat_dur * direction

        # beat_times 全体をシフト（0秒未満にならないようクランプ）
        new_beat_times = [max(0.0, t + offset) for t in deck.beat_times]
        deck.beat_times = new_beat_times

        # first_beat も連動して更新
        if new_beat_times:
            info['first_beat'] = new_beat_times[0]

        # ビートグリッドをGUIに反映
        self.beatgrid_updated.emit(deck_id, deck.beat_times)

        # ループ中なら再スナップ
        if deck.loop_active:
            bars = self._loop_bars[deck_id]
            deck.set_loop_snapped(bpm, info['first_beat'], bars=bars)

        direction_str = "+1" if direction > 0 else "-1"
        self.status_updated.emit(f"Beat Grid {deck_id}: {direction_str} beat ({offset*1000:.0f}ms)")

    # --- Library Navigation ---
    def _move_cursor(self, delta: int):
        track_list = self.library_manager.get_track_list_copy()
        if not track_list:
            return
        self.library_cursor = (self.library_cursor + delta) % len(track_list)
        self.library_cursor_changed.emit(self.library_cursor)

    def _load_selected_track(self, deck_id: str):
        track_list = self.library_manager.get_track_list_copy()
        if not track_list or self.library_cursor >= len(track_list):
            return
        track = track_list[self.library_cursor]
        self.load_track_by_path(deck_id, track['filepath'])

    def _on_new_file_detected(self, filename: str):
        """ホットフォルダで新規ファイル検出時の通知(移動前)"""
        self.status_updated.emit(f"New file detected: {filename}")
    
    def _update_positions(self):
        if not self.running: 
            return
        da, db = self.audio_engine.deck_a, self.audio_engine.deck_b
        self.position_updated.emit("A", da.get_position(), da.get_duration())
        self.position_updated.emit("B", db.get_position(), db.get_duration())
        # DSP状態を100msごとに通知
        self.dsp_updated.emit("A", {
            'eq_high': da.eq_high, 'eq_mid': da.eq_mid, 'eq_low': da.eq_low,
            'filter_val': da.filter_val
        })
        self.dsp_updated.emit("B", {
            'eq_high': db.eq_high, 'eq_mid': db.eq_mid, 'eq_low': db.eq_low,
            'filter_val': db.filter_val
        })
        # ループ折り返し監視（BASS_SYNC_POSがstream_fxで動作しないためポーリング）
        da.check_loop()
        db.check_loop()

        # Phase R3: SyncEngine 100ms更新
        self.sync_engine.update(
            deck_a=da,
            deck_b=db,
            info_a=self.deck_a_info,
            info_b=self.deck_b_info
        )

        # Phase R8: スコアリング 100ms tick
        if self._game_enabled and self._game_session.is_active:
            self._tick_gamification(da, db)
        
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
        # Phase R4: セッションログを保存
        saved = self.style_logger.save_session()
        if saved:
            logger.info(f"Style log saved: {saved}")
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
        """全トラックの相対エネルギーレベルを再計算。LibraryManager に委譲。"""
        self.library_manager.apply_relative_energy_evaluation()

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
        """ライブラリをスキャンし、未解析トラックを自動解析。LibraryManager に委譲。"""
        self.library_manager.refresh_library()

    def analyze_track(self, filepath: str, force=False):
        """単一トラックを強制解析する。LibraryManager に委譲。"""
        self.library_manager.analyze_track(filepath, force=force)

    def load_track_by_path(self, deck_id: str, filepath: str):
        deck = self.audio_engine.deck_a if deck_id == "A" else self.audio_engine.deck_b
        info = next((t for t in self.library_manager.track_list if t['filepath'] == filepath), None)
        
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
                    # HOT CUE を HotCueManager 経由でクリア（旧 Deck.clear_all_hot_cues() の代替）
                    for led_event in self.hcm_a.clear_all():
                        self._send_led(led_event)
                else:
                    self.deck_b_info = info
                    for led_event in self.hcm_b.clear_all():
                        self._send_led(led_event)
                
                deck.apply_track_analysis(info)
                self.deck_updated.emit(deck_id, info)
                self.waveform_updated.emit(deck_id, deck.get_waveform_data(), duration)
                self.energy_profile_updated.emit(deck_id, energy_profile, duration)
                self.dsp_updated.emit(deck_id, deck.get_dsp_settings())
                
                # P-02 Beatgrid: ビート位置をGUIに送出
                self.beatgrid_updated.emit(deck_id, deck.beat_times)
                
                # Phase 8C Week 2: キー互換性チェック
                self._update_key_compatibility()
                
                logger.info(f"Deck {deck_id}: Loaded {info.get('filename', 'Unknown')}")
            else:
                logger.error(f"Deck {deck_id}: Failed to load track")

        deck.on_load_complete = on_loaded
        deck.load(filepath)

    def _update_key_compatibility(self):
        """
        両デッキがロード済みの場合、Camelot Wheelでキー互換性を計算してGUIに通知。
        (Phase R4: CamelotWheel統合)
        """
        if not self.deck_a_info or not self.deck_b_info:
            self.key_compatibility_updated.emit([])
            return

        key_a = self.deck_a_info.get('key', '')
        key_b = self.deck_b_info.get('key', '')

        if not key_a or not key_b:
            self.key_compatibility_updated.emit([])
            return

        # CamelotWheelで変換・相性判定（計算ロジックは _get_key_compat_level() に統合済み）
        camelot_a = self.camelot_wheel.to_camelot(key_a)
        camelot_b = self.camelot_wheel.to_camelot(key_b)
        compat_level = self._get_key_compat_level()

        # 相性情報をステータスに表示
        self.status_updated.emit(
            f"Key: {camelot_a} → {camelot_b} = {compat_level}"
        )

        # Deck Aのキーと相性の良いCamelotコード一覧
        compatible_camelots = self.camelot_wheel.get_compatible_keys(camelot_a)

        # ライブラリ中で互換キーを持つトラックのCamelot表記を収集
        compatible_key_strs: list[str] = []
        for track in self.library_manager.get_track_list_copy():
            t_key = track.get('key', '')
            if not t_key:
                continue
            t_camelot = self.camelot_wheel.to_camelot(t_key)
            if t_camelot in compatible_camelots:
                compatible_key_strs.append(t_camelot)

        self.key_compatibility_updated.emit(list(set(compatible_key_strs)))

    # --- Phase R4: ミックスアドバイス ---

    def get_mix_advice(self, use_gemini: bool = True) -> None:
        """
        Deck A/B のトラック情報からミックスアドバイスを生成し、
        mix_advice_updated シグナルで通知する。

        両デッキにトラックがロードされていない場合は何もしない。
        バックグラウンドスレッドで実行するのでGUIをブロックしない。
        """
        if not self.deck_a_info or not self.deck_b_info:
            self.status_updated.emit("Mix Advice: 両デッキにトラックをロードしてください")
            return

        def _run():
            try:
                deck_a_data = {
                    **self.deck_a_info,
                    "energy_numeric": self.deck_a_info.get("energy", {}).get("numeric", 3),
                    "energy_flow":    self.deck_a_info.get("energy", {}).get("profile", []),
                    "duration":       self.audio_engine.deck_a.get_duration(),
                }
                deck_b_data = {
                    **self.deck_b_info,
                    "energy_numeric": self.deck_b_info.get("energy", {}).get("numeric", 3),
                    "energy_flow":    self.deck_b_info.get("energy", {}).get("profile", []),
                    "duration":       self.audio_engine.deck_b.get_duration(),
                }
                advice = self.mix_advisor.get_advice(deck_a_data, deck_b_data, use_gemini=use_gemini)
                logger.info(
                    f"MixAdvice: {advice.technique} | "
                    f"key={advice.key_compatibility.get('level')} | "
                    f"source={advice.source}"
                )
                self.mix_advice_updated.emit(advice.to_dict())
                self.status_updated.emit(
                    f"Mix Advice: {advice.technique_label} ({advice.source})"
                )
            except Exception as e:
                logger.error(f"get_mix_advice failed: {e}")
                self.status_updated.emit("Mix Advice: 生成に失敗しました")

        Thread(target=_run, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────
    # Phase R8: Gamification パブリック API
    # ─────────────────────────────────────────────────────────────────

    def set_gamification_api_key(self, api_key: str) -> None:
        """
        Gemini APIキーを設定し、GeminiOrchestrator / AiCommentator を初期化する。
        MixAdvisor と同じキーを共有するため set_mix_advisor_api_key() と
        セットで呼ぶのが基本。
        """
        self._gemini_orchestrator = GeminiOrchestrator(api_key=api_key)
        self._ai_commentator = AiCommentator(self._gemini_orchestrator, self._game_session.venue)
        # MixAdvisorにも共有する（Phase R4との統合）
        if hasattr(self.mix_advisor, "set_orchestrator"):
            self.mix_advisor.set_orchestrator(self._gemini_orchestrator)
        logger.info("Phase R8: GeminiOrchestrator initialized")

    def set_gamification_enabled(self, enabled: bool) -> None:
        """ゲーミフィケーション機能のON/OFF切替。既存機能への影響なし。"""
        self._game_enabled = enabled
        if enabled and not self._game_session.is_active:
            self._game_session.start()
            logger.info("Phase R8: GameSession started")
        elif not enabled and self._game_session.is_active:
            result = self._game_session.finish()
            logger.info(f"Phase R8: GameSession finished — rank={result.rank}")
        self.status_updated.emit(f"Gamification: {'ON' if enabled else 'OFF'}")

    def set_venue(self, venue_id: str) -> None:
        """
        ワールドツアーの会場を切り替える。
        セッション中でも切り替え可能（スコアはリセット）。
        """
        _venues_path = os.path.join(os.path.dirname(__file__), "data", "venues.json")
        was_active = self._game_session.is_active
        if was_active:
            self._game_session.finish()

        self._game_session = GameSession.from_venue_id(venue_id, _venues_path)

        if was_active or self._game_enabled:
            self._game_session.start()

        venue = self._game_session.venue
        # AiCommentator の venue も同期する
        if self._ai_commentator is not None:
            self._ai_commentator.set_venue(venue)
        self.status_updated.emit(
            f"Venue: {venue.flag} {venue.name} ({venue.location})")
        logger.info(f"Phase R8: Venue changed to {venue_id}")

    def finish_game_session(self) -> dict:
        """
        ゲームセッションを終了してランク結果を返す。
        GUI の「セッション終了」ボタンから呼ぶ想定。
        """
        if not self._game_session.is_active:
            return {}
        result = self._game_session.finish()
        self._game_enabled = False
        self.status_updated.emit(
            f"Session finished — Rank {result.rank} / Score {result.total_score:.0f}"
        )
        return result.__dict__

    def request_commentary(self) -> None:
        """
        ユーザー要求によるAI講評を非同期で生成してシグナル送出する。
        GeminiOrchestrator が未初期化の場合はルールベースコメントにフォールバック。
        """
        if self._ai_commentator is None:
            self.commentary_received.emit("（APIキー未設定のため講評を生成できません）")
            return

        state = self._game_session.get_state()
        venue = self._game_session.venue

        def _run():
            commentary = self._ai_commentator.request_comment(state)
            text = commentary.text if commentary else "（講評を生成できませんでした）"
            self.commentary_received.emit(text)

        Thread(target=_run, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────
    # Phase R8: 内部メソッド
    # ─────────────────────────────────────────────────────────────────

    def _get_key_compat_level(self) -> str:
        """
        両デッキのキー相性レベルを返す（Camelot Wheel 使用）。

        _update_key_compatibility() と _tick_gamification() で重複していた
        Camelot 計算ロジックをここに統合。
        両デッキ未ロードの場合は "unknown" を返す。
        """
        if not (self.deck_a_info and self.deck_b_info):
            return "unknown"
        ca = self.camelot_wheel.to_camelot(self.deck_a_info.get("key", ""))
        cb = self.camelot_wheel.to_camelot(self.deck_b_info.get("key", ""))
        compat_obj = self.camelot_wheel.get_compatibility(ca, cb)
        return getattr(compat_obj, "level", "unknown")

    def _build_score_snapshot(self, da, db) -> ScoreSnapshot:
        """
        ScoreSnapshot を構築して返す。

        _tick_gamification() から責務を分離。
        crossfader は audio_engine.crossfader を直接参照（bugfix 済み）。
        """
        return ScoreSnapshot(
            bpm_a        = da.original_bpm or (self.deck_a_info or {}).get("bpm", 120.0),
            bpm_b        = db.original_bpm or (self.deck_b_info or {}).get("bpm", 120.0),
            eq_low_a     = da._eq_low_norm,
            eq_low_b     = db._eq_low_norm,
            crossfader   = self.audio_engine.crossfader,
            key_compat   = self._get_key_compat_level(),
            energy_a     = (self.deck_a_info or {}).get("energy", {}).get("numeric", 3.0),
            energy_b     = (self.deck_b_info or {}).get("energy", {}).get("numeric", 3.0),
            is_playing_a = da.is_playing(),
            is_playing_b = db.is_playing(),
            venue_id     = self._game_session.venue.id if self._game_session.venue else "tokyo",
        )

    def _emit_score_state(self, state) -> None:
        """スコア状態を game_score_updated シグナルで GUI に通知する。"""
        venue = self._game_session.venue
        self.game_score_updated.emit({
            "active":         True,
            "total_score":    state.total_score,
            "tech_score":     state.tech_score,
            "vibe_score":     state.vibe_score,
            "hype":           state.hype,
            "combo_mult":     state.combo_mult,
            "combo_sec":      state.combo_sec,
            "rank":           state.rank,
            "beatmatch":      state.beatmatch.value,
            "hype_delta":     state.hype_delta,
            "venue_name":     venue.name     if venue else "",
            "venue_location": venue.location if venue else "",
            "venue_flag":     venue.flag     if venue else "",
        })

    def _trigger_commentary_async(self, events, state) -> None:
        """指定イベントが含まれていれば AI 講評を非同期で生成してシグナル送出する。"""
        if not (self._ai_commentator and events):
            return
        trigger_types = {
            ScoreEventType.KEY_RESULT,
            ScoreEventType.HYPE_SPIKE,
            ScoreEventType.COMBO_START,
        }
        triggered = [e for e in events if e.event_type in trigger_types]
        if not triggered:
            return

        def _gen(triggered=triggered, state=state):
            commentary = self._ai_commentator.process_events(triggered, state)
            if commentary:
                self.commentary_received.emit(commentary.text)

        Thread(target=_gen, daemon=True).start()

    def _tick_gamification(self, da, db) -> None:
        """
        100ms ごとに呼ばれるスコアリング処理。
        _update_positions() から呼び出す。
        「両デッキどちらも再生中」でないと有意なスコアが出ないが、
        それは ScoreEngine 内部で SKIP 判定するため、ここでは渡すだけ。
        """
        snap   = self._build_score_snapshot(da, db)
        events = self._game_session.tick(snap)
        state  = self._game_session.get_state()

        self._emit_score_state(state)
        self._trigger_commentary_async(events, state)

    def set_mix_advisor_api_key(self, api_key: str) -> bool:
        """実行中に MixAdvisor の Gemini API キーを更新する。"""
        return self.mix_advisor.update_api_key(api_key)

    # --- Phase R1: MIDIマッピング ---

    def apply_midi_mapping(self, mapping):
        """
        MIDIマッピングをMIDIControllerに反映する。

        MIDIMappingWizardまたはPresetSelectorDialogで保存・選択された
        MIDIMappingインスタンスを受け取り、MIDIControllerのルックアップ
        テーブルをホットリロードする。

        MIDIコントローラーが未接続の場合は次回接続時に自動適用される。

        Args:
            mapping: core.midi_mapping.MIDIMapping インスタンス
        """
        try:
            self.midi_controller.reload_mapping(mapping)
            logger.info(f"MIDI mapping applied: '{mapping.preset_name}'")
            self.status_updated.emit(f"MIDI: {mapping.preset_name} を適用しました")
        except Exception as e:
            logger.error(f"apply_midi_mapping failed: {e}")
            self.status_updated.emit("MIDIマッピングの適用に失敗しました")