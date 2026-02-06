"""
MIDI Controller Handler for VCI-100
====================================

VCI-100コントローラーのMIDI入出力を管理するモジュール。
"""

import logging
import rtmidi
from pathlib import Path
from audio_engine import VCI100_MIDI

logger = logging.getLogger(__name__)


class MIDIController:
    """
    VCI-100 MIDIコントローラーとの通信を管理
    
    機能:
    - MIDIデバイスの検出と接続
    - MIDIメッセージの受信とパース
    - コールバックベースのイベント通知
    """
    
    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode
        self.midiin = None
        self.callbacks = {}
        
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
            
            vci_port = None
            for i, port_name in enumerate(ports):
                if "VCI" in port_name or "Vestax" in port_name:
                    vci_port = i
                    break
            
            if vci_port is not None:
                self.midiin.open_port(vci_port)
                logger.info(f"Connected to VCI-100: {ports[vci_port]}")
                self.midiin.set_callback(self._midi_callback)
                return True
            else:
                logger.warning("VCI-100 not found. Check USB connection.")
                if ports:
                    logger.info(f"Available ports: {ports}")
                    # Fallback to first port for dev/testing if needed
                    # self.midiin.open_port(0)
                    # return True
                return False
                
        except Exception as e:
            logger.error(f"MIDI Connection Error: {e}")
            return False

    def close(self):
        if self.midiin:
            self.midiin.close_port()
            del self.midiin

    def register_callback(self, event_name: str, callback):
        """イベントリスナーを登録"""
        self.callbacks[event_name] = callback

    def _emit(self, event_name: str, value):
        if event_name in self.callbacks:
            try:
                self.callbacks[event_name](value)
            except Exception as e:
                logger.error(f"Error in MIDI callback {event_name}: {e}")

    def get_message(self):
        """ポーリング用（rtmidiコールバックを使う場合は不要だが互換性のため残す）"""
        pass

    def _midi_callback(self, message, time_stamp):
        """rtmidiからの生メッセージを処理"""
        msg = message[0]
        if not msg: return
        
        status = msg[0] & 0xF0
        control = msg[1]
        value = msg[2]
        
        if self.debug_mode:
            # フィルタリングせずに全て表示
            msg_type = "Note" if (status == 0x90 or status == 0x80) else "CC"
            logger.info(f"[MIDI Debug] Type: {msg_type}, CC: {control:3d} (0x{control:02X}), Value: {value:3d}")

        # Note On (Button Press)
        if status == 0x90 and value > 0:
            self._handle_note(control)
            
        # Control Change (Fader/Knob)
        elif status == 0xB0:
            self._handle_cc(control, value)

    def _handle_cc(self, control: int, value: int):
        """CCメッセージ（フェーダー、ノブ）を処理"""
        norm_val = value / 127.0
        
        cc_map = {
            VCI100_MIDI.CROSSFADER: 'crossfader',
            VCI100_MIDI.MASTER_VOLUME: 'master_volume',
            VCI100_MIDI.CH1_VOLUME: 'deck_a_volume',
            VCI100_MIDI.CH1_TRIM: 'deck_a_trim',
            VCI100_MIDI.CH1_EQ_HIGH: 'deck_a_eq_high',
            VCI100_MIDI.CH1_EQ_MID: 'deck_a_eq_mid',
            VCI100_MIDI.CH1_EQ_LOW: 'deck_a_eq_low',
            VCI100_MIDI.CH1_FILTER: 'deck_a_filter',
            VCI100_MIDI.CH1_TEMPO: 'deck_a_tempo',
            VCI100_MIDI.CH2_VOLUME: 'deck_b_volume',
            VCI100_MIDI.CH2_TRIM: 'deck_b_trim',
            VCI100_MIDI.CH2_EQ_HIGH: 'deck_b_eq_high',
            VCI100_MIDI.CH2_EQ_MID: 'deck_b_eq_mid',
            VCI100_MIDI.CH2_EQ_LOW: 'deck_b_eq_low',
            VCI100_MIDI.CH2_FILTER: 'deck_b_filter',
            VCI100_MIDI.CH2_TEMPO: 'deck_b_tempo',
        }
        
        if control in cc_map:
            event_name = cc_map[control]
            # Debugログは大量に出るのでCCはフィルタ
            # if self.debug_mode: logger.info(...) 
            self._emit(event_name, norm_val)
    
    def _handle_note(self, control: int):
        """ノートメッセージを処理"""
        note_map = {
            0x32: 'play_a', # 50
            0x36: 'play_b', # 54
            0x34: 'cue_a',  # 52
            0x38: 'cue_b',  # 56
            0x60: 'load_a', # 96
            0x61: 'load_b', # 97
            0x5C: 'prev_track', # 92
            0x5D: 'next_track', # 93
            
            # Loop Controls (Added based on logs)
            VCI100_MIDI.CH1_LOOP: 'loop_a', # 66 (0x42)
            VCI100_MIDI.CH2_LOOP: 'loop_b', # 67 (0x43)
        }
        
        if control in note_map:
            event_name = note_map[control]
            if self.debug_mode:
                logger.info(f"  → Action: {event_name}")
            self._emit(event_name, True)