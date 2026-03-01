"""
MIDI Controller Handler
=======================

VCI-100コントローラーのMIDI入出力を管理するモジュール。

Phase R1変更点:
- cc_map / note_map のハードコードを廃止
- MIDIMapping（core/midi_mapping.py）からルックアップテーブルを生成
- フォールバック: presets/vci100_default.json が存在しない場合は
  VCI100_MIDI定数ベースの互換マップを使用（後方互換）
"""

import logging
import rtmidi
from pathlib import Path

from core.midi_mapping import MIDIMapping, MIDIEntry, DEFAULT_PRESET_PATH

logger = logging.getLogger(__name__)


# ---- フォールバック用マップ（vci100_default.jsonが存在しない場合） ----
# Phase R0以前の動作を保証するための安全弁。
# 通常はvci100_default.jsonから読み込まれるため使用されない。

def _build_fallback_maps() -> tuple[dict[int, str], dict[int, str]]:
    """VCI100_MIDI定数ベースのハードコードフォールバックマップを生成"""
    # importをここで行い、循環インポートのリスクを最小化
    try:
        # CC: 実機アサイン（midi_monitor.py準拠）
        cc = {
            8:  'crossfader',       # VR1 Crossfader
            7:  'master_volume',    # VR22 Master Level
            12: 'deck_a_volume',    # VR2 Ch1 Fader
            13: 'deck_b_volume',    # VR3 Ch2 Fader
            14: 'deck_a_tempo',     # VR4 Ch1 Pitch
            15: 'deck_b_tempo',     # VR21 Ch2 Pitch
            20: 'deck_a_eq_high',   # VR5 Ch1 EQ Hi
            21: 'deck_a_eq_mid',    # VR6 Ch1 EQ Mid
            22: 'deck_a_eq_low',    # VR7 Ch1 EQ Low
            23: 'deck_a_filter',    # VR8 Ch1 Filter/Low
            24: 'deck_b_eq_high',   # VR13 Ch2 EQ Hi
            25: 'deck_b_eq_mid',    # VR14 Ch2 EQ Mid
            26: 'deck_b_eq_low',    # VR15 Ch2 EQ Low
            27: 'deck_b_filter',    # VR16 Ch2 Filter/Low
            28: 'deck_a_trim',      # VR9 Ch1 Trim
            29: 'deck_b_trim',      # VR11 Ch2 Trim
        }
        # Note: 実機アサイン（midi_monitor.py準拠）
        note = {
            50: 'play_a',           # SW1 Ch1 Play/Pause
            52: 'cue_a',            # SW3 Ch1 Cue
            54: 'play_b',           # SW5 Ch2 Play/Pause
            56: 'cue_b',            # SW7 Ch2 Cue
            66: 'loop_a',           # SW21 Ch1 Loop*4
            67: 'loop_b',           # SW40 Ch2 Loop*4
            70: 'sync_a',           # SW24 Ch1 Sync
            71: 'sync_b',           # SW37 Ch2 Sync
            92: 'prev_track',       # SW16 Cursor上
            93: 'next_track',       # SW18 Cursor下
            96: 'load_a',           # SW19 Cursor左
            97: 'load_b',           # SW20 Cursor右
            101: 'loop_size_up_a',  # SW12 Loop右上
            102: 'loop_size_dn_a',  # SW13 Loop右中
            103: 'loop_size_up_b',  # SW14 Loop右下
            104: 'loop_size_dn_b',  # SW15 Loop丸
            0x56: 'beat_grid_fwd_a',  # SW34 paramA Beat Grid +1
            0x53: 'beat_grid_bwd_a',  # SW33 paramA Beat Grid -1
            0x57: 'beat_grid_fwd_b',  # SW34 paramB Beat Grid +1
            0x54: 'beat_grid_bwd_b',  # SW33 paramB Beat Grid -1
        }
        return cc, note
    except Exception as e:
        logger.error(f"Fallback map build failed: {e}")
        return {}, {}


class MIDIController:
    """
    VCI-100 MIDIコントローラーとの通信を管理

    機能:
    - MIDIデバイスの検出と接続
    - MIDIメッセージの受信とパース
    - コールバックベースのイベント通知
    - MIDIMappingによる動的マッピング（Phase R1）
    """

    def __init__(self, debug_mode: bool = False, mapping: MIDIMapping | None = None):
        """
        Args:
            debug_mode: Trueで全MIDIメッセージをログ出力
            mapping:    使用するMIDIMapping。Noneの場合はデフォルトプリセットを自動ロード
        """
        self.debug_mode = debug_mode
        self.midiin = None
        self.callbacks: dict[str, callable] = {}
        # マッピングのロード
        self._mapping = mapping or self._load_mapping()
        self._cc_map, self._note_map = self._mapping.build_lookup()
        logger.info(
            f"MIDIController: preset='{self._mapping.preset_name}' "
            f"({len(self._cc_map)} CC, {len(self._note_map)} Note entries)"
        )

    # ---- マッピング管理 ----

    @staticmethod
    def _load_mapping() -> MIDIMapping:
        """デフォルトプリセットをロード。失敗時はフォールバックマップを使用"""
        mapping = MIDIMapping.load_default()
        if mapping is not None:
            return mapping

        logger.warning(
            "Default preset not found, using built-in fallback mapping. "
            "Run MIDI Wizard to create a preset."
        )
        cc_map, note_map = _build_fallback_maps()
        entries = []
        for control, event_name in cc_map.items():
            entries.append(MIDIEntry(
                event_name=event_name, msg_type='cc',
                control=control, label=event_name,
            ))
        for control, event_name in note_map.items():
            entries.append(MIDIEntry(
                event_name=event_name, msg_type='note',
                control=control, label=event_name,
            ))
        return MIDIMapping(
            preset_name="Built-in Fallback",
            device_name="VCI",
            entries=entries,
        )

    def reload_mapping(self, mapping: MIDIMapping):
        """
        実行時にマッピングを差し替える（ウィザード保存後の反映用）。

        Args:
            mapping: 新しいMIDIMappingインスタンス
        """
        self._mapping = mapping
        self._cc_map, self._note_map = mapping.build_lookup()
        logger.info(f"MIDIController: mapping reloaded → '{mapping.preset_name}'")

    @property
    def current_mapping(self) -> MIDIMapping:
        """現在のMIDIMappingを返す"""
        return self._mapping

    # ---- MIDI接続 ----

    def connect(self) -> bool:
        """VCI-100を検出して接続"""
        try:
            self.midiin = rtmidi.MidiIn()
            ports = self.midiin.get_ports()

            if self.debug_mode:
                logger.info("=" * 60)
                logger.info("MIDI DEBUG MODE ENABLED")
                logger.info("All MIDI messages will be displayed")
                logger.info("=" * 60)

            # デバイス名ヒントでポートを検索（MIDIMappingのdevice_nameを優先）
            hint = self._mapping.device_name or "VCI"
            vci_port = None
            for i, port_name in enumerate(ports):
                if hint.lower() in port_name.lower():
                    vci_port = i
                    break

            if vci_port is not None:
                self.midiin.open_port(vci_port)
                logger.info(f"Connected to MIDI device: {ports[vci_port]}")
                self.midiin.set_callback(self._midi_callback)
                return True
            else:
                logger.warning(
                    f"MIDI device matching '{hint}' not found. "
                    f"Available: {ports}"
                )
                return False

        except Exception as e:
            logger.error(f"MIDI Connection Error: {e}")
            return False

    def close(self):
        """入力・出力ポートを閉じてリソースを解放"""
        if self.midiin:
            self.midiin.close_port()
            del self.midiin
            self.midiin = None
        if hasattr(self, '_midiout') and self._midiout is not None:
            self._midiout.close_port()
            del self._midiout
            self._midiout = None

    # ---- コールバック管理 ----

    def register_callback(self, event_name: str, callback):
        """
        イベントリスナーを登録。
        event_nameはMIDIEntryのevent_nameと一致する必要がある。
        """
        self.callbacks[event_name] = callback

    def _emit(self, event_name: str, value):
        """登録済みコールバックを安全に呼び出す"""
        if event_name in self.callbacks:
            try:
                self.callbacks[event_name](value)
            except Exception as e:
                import traceback
                logger.error(f"Error in MIDI callback '{event_name}': {e}\n{traceback.format_exc()}")

    def get_message(self):
        """ポーリング用（コールバック使用時は不要、互換性のため残す）"""
        pass

    # ---- MIDIメッセージ処理 ----

    def _midi_callback(self, message, time_stamp):
        """rtmidiからの生メッセージを処理"""
        msg = message[0]
        if not msg:
            return

        status = msg[0] & 0xF0
        control = msg[1]
        value = msg[2]

        if self.debug_mode:
            msg_type = "Note" if status in (0x90, 0x80) else "CC"
            logger.info(
                f"[MIDI] {msg_type} control={control:3d}(0x{control:02X}) value={value:3d}"
            )

        # Note On（velocity > 0）
        if status == 0x90 and value > 0:
            self._handle_note(control)

        # Control Change
        elif status == 0xB0:
            self._handle_cc(control, value)

    def _handle_cc(self, control: int, value: int):
        """CCメッセージをMIDIMappingで解決してemit"""
        event_name = self._cc_map.get(control)
        if event_name:
            self._emit(event_name, value / 127.0)

    def _handle_note(self, control: int):
        """Noteメッセージをクレードルで解決してemit"""
        event_name = self._note_map.get(control)
        if event_name:
            if self.debug_mode:
                logger.info(f"  → Action: {event_name}")
            self._emit(event_name, True)

    # ---- LED 制御（Phase R8 HOT CUE LED）----

    def send_led(self, note: int, on: bool, channel: int = 0) -> bool:
        """
        VCI-100 の LED を制御する。

        Note On (velocity=127) / Note Off (velocity=0) を MIDI Output ポートに送信する。

        Args:
            note:    MIDI ノート番号（0〜127）
            on:      True=点灯（velocity=127）、False=消灯（velocity=0）
            channel: MIDI チャンネル（0〜15）、デフォルト=0→ch1

        Returns:
            bool: 送信成功時 True
        """
        if not hasattr(self, '_midiout') or self._midiout is None:
            if not self._connect_output():
                return False
        velocity = 127 if on else 0
        status = (0x90 if on else 0x80) | (channel & 0x0F)
        try:
            self._midiout.send_message([status, note & 0x7F, velocity])
            if self.debug_mode:
                logger.info(f"[LED] note={note} {'ON' if on else 'OFF'} ch={channel}")
            return True
        except Exception as e:
            logger.error(f"send_led failed: {e}")
            return False

    def _connect_output(self) -> bool:
        """
        MIDI Output ポートに接続する。
        入力と同じデバイス名ヒントで検索する。
        """
        try:
            self._midiout = rtmidi.MidiOut()
            ports = self._midiout.get_ports()
            hint = self._mapping.device_name or "VCI"
            for i, port_name in enumerate(ports):
                if hint.lower() in port_name.lower():
                    self._midiout.open_port(i)
                    logger.info(f"MIDI Output connected: {port_name}")
                    return True
            logger.warning(f"MIDI Output device '{hint}' not found. LED control disabled.")
            self._midiout = None
            return False
        except Exception as e:
            logger.error(f"MIDI Output connection failed: {e}")
            self._midiout = None
            return False
