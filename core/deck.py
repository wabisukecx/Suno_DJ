"""
Deck Control Module
===================

デッキ制御クラス

このモジュールは以下を提供します:
1. Deckクラス（トラック再生制御）
2. AudioConfigデータクラス
3. EQ/Filter/Loop/CUE機能
"""

import logging
import ctypes
import os
import math
from typing import Optional
from dataclasses import dataclass

from .audio_constants import (
    BASS_LIB, BASS_FX_LIB, BASS_AVAILABLE, BASS_FX_AVAILABLE,
    NUMPY_AVAILABLE,
    BASS_ATTRIB_VOL, BASS_ATTRIB_TEMPO, BASS_ATTRIB_TEMPO_PITCH,
    BASS_STREAM_DECODE, BASS_STREAM_PRESCAN, BASS_SAMPLE_FLOAT, BASS_UNICODE,
    BASS_FX_FREESOURCE, BASS_POS_BYTE,
    BASS_SYNC_POS, BASS_SYNC_MIXTIME, SYNCPROC,
    BASS_FX_DX8_PARAMEQ, BASS_FX_BFX_BQF,
    BASS_BFX_BQF_LOWPASS, BASS_BFX_BQF_HIGHPASS,
    BASS_DX8_PARAMEQ, BASS_BFX_BQF
)

if NUMPY_AVAILABLE:
    import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class AudioConfig:
    """
    オーディオ設定
    
    Attributes:
        sample_rate (int): サンプルレート (Hz)
        channels (int): チャンネル数
        block_size (int): ブロックサイズ
    """
    sample_rate: int = 48000
    channels: int = 2
    block_size: int = 2048


class Deck:
    def __init__(self, name: str, config: AudioConfig):
        self.name = name
        self.config = config
        
        self.stream_decode = 0
        self.stream_fx = 0
        self.duration = 0.0
        self.waveform_cache = None
        
        # Track Analysis Data
        self.original_bpm = 0.0
        
        self.channel_volume = 1.0
        self.mix_volume = 1.0
        self.trim_db = 0.0
        
        self.eq_high = 0.0
        self.eq_mid = 0.0
        self.eq_low = 0.0
        self.filter_val = 0.0
        self.tempo_percent = 0.0
        self.pitch_semitones = 0.0
        
        # EQ Upgrade: 3-stage cascade handles
        self.fx_eq_low = []   # 3-stage cascade handles
        self.fx_eq_mid = []   # 3-stage cascade handles
        self.fx_eq_high = []  # 3-stage cascade handles
        self.fx_filter = 0
        
        # Loop State + Loop Upgrade
        self.loop_active = False
        self.loop_sync_handle = 0
        self.loop_start_bytes = 0
        self.loop_cb_ref = None
        self.loop_start_sec = 0.0     # Loop Upgrade: ã‚¹ãƒŠãƒƒãƒ—æ¸ˆã¿ãƒ«ãƒ¼ãƒ—é–‹å§‹ä½ç½®(ç§’)
        self.loop_duration_sec = 0.0  # Loop Upgrade: ãƒ«ãƒ¼ãƒ—é•·(ç§’)
        
        # HOT CUE State
        self.hot_cues: list[Optional[float]] = [None] * 4
        
        self.on_load_complete = None

    def load(self, filepath: str):
        if not BASS_AVAILABLE: return False
        self.unload()
        if not os.path.exists(filepath):
            if self.on_load_complete: self.on_load_complete(self.name, False)
            return False

        self.stream_decode = BASS_LIB.BASS_StreamCreateFile(False, filepath, 0, 0, BASS_STREAM_DECODE | BASS_SAMPLE_FLOAT | BASS_STREAM_PRESCAN | BASS_UNICODE)
        if self.stream_decode == 0:
            if self.on_load_complete: self.on_load_complete(self.name, False)
            return False

        len_bytes = BASS_LIB.BASS_ChannelGetLength(self.stream_decode, BASS_POS_BYTE)
        self.duration = BASS_LIB.BASS_ChannelBytes2Seconds(self.stream_decode, len_bytes) if len_bytes > 0 else 0.0
        self.waveform_cache = self._generate_waveform(self.stream_decode)
        BASS_LIB.BASS_ChannelSetPosition(self.stream_decode, 0, BASS_POS_BYTE)

        success = False
        if BASS_FX_AVAILABLE:
            self.stream_fx = BASS_FX_LIB.BASS_FX_TempoCreate(self.stream_decode, BASS_FX_FREESOURCE)
            if self.stream_fx != 0: success = True

        if not success:
            if self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_decode); self.stream_decode = 0
            self.stream_fx = BASS_LIB.BASS_StreamCreateFile(False, filepath, 0, 0, BASS_SAMPLE_FLOAT | BASS_STREAM_PRESCAN | BASS_UNICODE)
            if self.stream_fx == 0:
                if self.on_load_complete: self.on_load_complete(self.name, False)
                return False
            logger.info(f"Deck {self.name}: Fallback stream (No Tempo)")
        
        self._setup_dsp()
        self._update_volume()
        self.set_tempo(self.tempo_percent)
        self.set_pitch(self.pitch_semitones)

        logger.info(f"Deck {self.name} Ready: {os.path.basename(filepath)}")
        if self.on_load_complete: self.on_load_complete(self.name, True)
        return True

    def unload(self):
        self.clear_loop()
        self.clear_all_hot_cues()
        if self.stream_fx and self.stream_fx != self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_fx)
        if self.stream_decode: BASS_LIB.BASS_StreamFree(self.stream_decode)
        self.stream_decode = 0; self.stream_fx = 0
        self.duration = 0.0; self.waveform_cache = None
        # EQ Upgrade: ãƒªã‚¹ãƒˆåž‹ã«å¯¾å¿œ
        self.fx_eq_low = []; self.fx_eq_mid = []; self.fx_eq_high = []

    def _setup_dsp(self):
        if not self.stream_fx: return
        
        # EQ Upgrade: 3-Stage Cascade DX8 EQ (DJ-grade kill EQ)
        # å„ãƒãƒ³ãƒ‰3æ®µé‡ã­: -15dB Ã— 3 = -45dB max attenuation
        EQ_CASCADE_STAGES = 3
        
        self.fx_eq_low = []
        self.fx_eq_mid = []
        self.fx_eq_high = []
        
        for _ in range(EQ_CASCADE_STAGES):
            h_low = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
            h_mid = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
            h_high = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_DX8_PARAMEQ, 0)
            if h_low: self.fx_eq_low.append(h_low)
            if h_mid: self.fx_eq_mid.append(h_mid)
            if h_high: self.fx_eq_high.append(h_high)
        
        # Initialize all stages with DJ-standard crossover frequencies
        # (based on Mixxx's default EQ settings)
        for h in self.fx_eq_low:
            self._update_dx8_eq(h, 246.0, 8.0, self.eq_low)  # Low: 246Hz (DJ standard)
        for h in self.fx_eq_mid:
            self._update_dx8_eq(h, 2500.0, 12.0, self.eq_mid)  # Mid: 2.5kHz (DJ standard)
        for h in self.fx_eq_high:
            self._update_dx8_eq(h, 10000.0, 8.0, self.eq_high)  # High: 10kHz (same)

        if BASS_FX_AVAILABLE:
            self.fx_filter = BASS_LIB.BASS_ChannelSetFX(self.stream_fx, BASS_FX_BFX_BQF, 0)
        
        logger.debug(f"Deck {self.name}: EQ Setup - {len(self.fx_eq_low)}x3 cascade stages")

    def _update_dx8_eq(self, handle, center, bw, gain):
        if not handle: return
        # ã‚«ã‚¹ã‚±ãƒ¼ãƒ‰ã§ã‚²ã‚¤ãƒ³ãŒ3å€ã«ãªã‚‹ãŸã‚ã€1æ®µã‚ãŸã‚Šã¯æŽ§ãˆã‚ã«
        safe_gain = max(-15.0, min(15.0, gain))
        p = BASS_DX8_PARAMEQ(center, bw, safe_gain)
        BASS_LIB.BASS_FXSetParameters(handle, ctypes.byref(p))

    def set_eq_low(self, db: float):
        self.eq_low = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} Low: {db:.1f}dB (x{len(self.fx_eq_low)} cascade)") 
        for h in self.fx_eq_low:
            self._update_dx8_eq(h, 246.0, 8.0, db)  # 246Hz (DJ standard)

    def set_eq_mid(self, db: float):
        self.eq_mid = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} Mid: {db:.1f}dB (x{len(self.fx_eq_mid)} cascade)")
        for h in self.fx_eq_mid:
            self._update_dx8_eq(h, 2500.0, 12.0, db)  # 2.5kHz (DJ standard)

    def set_eq_high(self, db: float):
        self.eq_high = db
        if abs(db) > 1.0: logger.info(f"Deck {self.name} High: {db:.1f}dB (x{len(self.fx_eq_high)} cascade)")
        for h in self.fx_eq_high:
            self._update_dx8_eq(h, 10000.0, 8.0, db)  # 10kHz

    def set_filter(self, val: float):
        self.filter_val = val
        if not self.fx_filter: return
        p = BASS_BFX_BQF(lChannel=-1, fGain=0.0, fBandwidth=1.0, fQ=1.0, fS=0.0)
        
        if abs(val) < 0.05:
            p.lFilter = BASS_BFX_BQF_LOWPASS; p.fCenter = 20000.0; p.fQ = 0.707
        elif val < 0: # LPF
            p.lFilter = BASS_BFX_BQF_LOWPASS
            p.fCenter = max(100.0, 20000.0 + val * 19800.0)
            p.fQ = 0.707
        else: # HPF
            p.lFilter = BASS_BFX_BQF_HIGHPASS
            p.fCenter = min(10000.0, 20.0 + val * 9980.0)
            p.fQ = 0.707
        
        BASS_LIB.BASS_FXSetParameters(self.fx_filter, ctypes.byref(p))

    def set_tempo(self, percent: float):
        self.tempo_percent = max(-50.0, min(50.0, percent))
        if self.stream_fx and BASS_FX_AVAILABLE:
            BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_TEMPO, self.tempo_percent)

    def set_pitch(self, semitones: float):
        self.pitch_semitones = max(-12.0, min(12.0, semitones))
        if self.stream_fx and BASS_FX_AVAILABLE:
            BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_TEMPO_PITCH, self.pitch_semitones)

    def set_volume(self, v: float):
        self.channel_volume = max(0.0, min(1.0, v))
        self._update_volume()

    def set_trim(self, db: float):
        self.trim_db = max(-10.0, min(10.0, db))
        self._update_volume()

    def set_master_volume_coeff(self, coeff: float):
        self.mix_volume = coeff
        self._update_volume()

    def _update_volume(self):
        if not self.stream_fx: return
        trim_linear = 10.0 ** (self.trim_db / 20.0)
        final_vol = self.channel_volume * trim_linear * self.mix_volume
        BASS_LIB.BASS_ChannelSetAttribute(self.stream_fx, BASS_ATTRIB_VOL, final_vol)

    def play(self):
        if self.stream_fx: BASS_LIB.BASS_ChannelPlay(self.stream_fx, False)

    def pause(self):
        if self.stream_fx: BASS_LIB.BASS_ChannelPause(self.stream_fx)

    def stop(self):
        if self.stream_fx:
            BASS_LIB.BASS_ChannelPause(self.stream_fx)
            BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, 0, BASS_POS_BYTE)

    def cue(self):
        if self.stream_fx:
            BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, 0, BASS_POS_BYTE)
            BASS_LIB.BASS_ChannelPause(self.stream_fx)

    def is_playing(self) -> bool:
        if not self.stream_fx: return False
        return BASS_LIB.BASS_ChannelIsActive(self.stream_fx) == 1

    def get_position(self) -> float:
        if not self.stream_fx: return 0.0
        pos_bytes = BASS_LIB.BASS_ChannelGetPosition(self.stream_fx, BASS_POS_BYTE)
        return BASS_LIB.BASS_ChannelBytes2Seconds(self.stream_fx, pos_bytes)

    def get_duration(self) -> float:
        return self.duration

    def get_waveform_data(self, num_points=800):
        return self.waveform_cache

    def set_position(self, seconds: float):
        if not self.stream_fx: return
        pos_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, seconds)
        BASS_LIB.BASS_ChannelSetPosition(self.stream_fx, pos_bytes, BASS_POS_BYTE)

    def sync_bpm(self, target_bpm: float) -> bool:
        if not BASS_FX_AVAILABLE or self.original_bpm <= 0:
            return False
        tempo_adjust = ((target_bpm / self.original_bpm) - 1.0) * 100.0
        tempo_adjust = max(-50.0, min(50.0, tempo_adjust))
        self.set_tempo(tempo_adjust)
        logger.info(f"Deck {self.name}: Synced to {target_bpm:.1f} BPM "
                   f"(Original: {self.original_bpm:.1f}, Adjust: {tempo_adjust:+.1f}%)")
        return True

    # --- Loop Implementation ---
    def set_loop(self, start_pos: float, duration: float):
        """Set a seamless loop using BASS_ChannelSetSync"""
        if not self.stream_fx:
            logger.warning(f"Deck {self.name}: No stream loaded")
            return
        
        self.clear_loop()
        
        # ãƒ«ãƒ¼ãƒ—çµ‚äº†ä½ç½®ï¼ˆèª¿æ•´ãªã— - BASS_SYNC_MIXTIMEãŒæ­£ç¢ºã«å‹•ä½œï¼‰
        end_pos = start_pos + duration
        
        start_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, ctypes.c_double(start_pos))
        end_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(self.stream_fx, ctypes.c_double(end_pos))
        
        self.loop_start_bytes = start_bytes
        
        def loop_callback(handle, channel, data, user):
            BASS_LIB.BASS_ChannelSetPosition(channel, self.loop_start_bytes, BASS_POS_BYTE)
        
        self.loop_cb_ref = SYNCPROC(loop_callback)
        self.loop_sync_handle = BASS_LIB.BASS_ChannelSetSync(
            self.stream_fx,
            BASS_SYNC_POS | BASS_SYNC_MIXTIME,
            end_bytes,
            self.loop_cb_ref,
            None
        )
        
        if self.loop_sync_handle:
            self.loop_active = True
            logger.info(f"Deck {self.name}: Loop set {start_pos:.2f}s - {end_pos:.2f}s (duration: {duration:.2f}s)")
        else:
            logger.error(f"Deck {self.name}: Loop sync failed, Error: {BASS_LIB.BASS_ErrorGetCode()}")

    def clear_loop(self):
        if self.loop_sync_handle:
            BASS_LIB.BASS_ChannelRemoveSync(self.stream_fx, self.loop_sync_handle)
            self.loop_sync_handle = 0
            self.loop_active = False
            self.loop_cb_ref = None
            logger.info(f"Deck {self.name}: Loop cleared")

    def set_loop_snapped(self, bpm: float, first_beat: float = 0.0, bars: int = 4):
        """
        Loop Upgrade: ãƒ“ãƒ¼ãƒˆã‚°ãƒªãƒƒãƒ‰ã«ã‚¹ãƒŠãƒƒãƒ—ã—ãŸ4å°ç¯€ãƒ«ãƒ¼ãƒ—ã‚’è¨­å®š
        
        æ”¹å–„ç‚¹:
        - floor() ã§ã€Œä»Šé³´ã£ã¦ã„ã‚‹å°ç¯€ã€ã®é ­ã«ã‚¹ãƒŠãƒƒãƒ— (roundâ†’floor)
        - ãƒ«ãƒ¼ãƒ—é–‹å§‹/é•·ã•ã‚’å±žæ€§ã«ä¿å­˜ã—å¤–éƒ¨ã‹ã‚‰å‚ç…§å¯èƒ½ã«
        - first_beatãŒä¸æ­£ãªå ´åˆã®ãƒ•ã‚©ãƒ¼ãƒ«ãƒãƒƒã‚¯å¼·åŒ–
        - ãƒ“ãƒ¼ãƒˆã‚°ãƒªãƒƒãƒ‰ä½ç½®ã®ãƒãƒªãƒ‡ãƒ¼ã‚·ãƒ§ãƒ³è¿½åŠ 
        """
        if not self.stream_fx:
            return
        
        # BPMãƒ•ã‚©ãƒ¼ãƒ«ãƒãƒƒã‚¯
        if bpm <= 0:
            logger.warning(f"Deck {self.name}: Invalid BPM ({bpm}), using 120.0")
            bpm = 120.0
        
        beat_duration = 60.0 / bpm
        bar_duration = beat_duration * 4  # 4/4æ‹å­å‰æ
        loop_duration = bar_duration * bars
        
        current = self.get_position()
        
        # first_beatãƒãƒªãƒ‡ãƒ¼ã‚·ãƒ§ãƒ³: è² å€¤ã‚„æ›²å°ºè¶…ãˆã¯ç„¡åŠ¹
        if first_beat < 0 or first_beat > self.duration:
            logger.warning(f"Deck {self.name}: Invalid first_beat ({first_beat:.3f}s), resetting to 0.0")
            first_beat = 0.0
        
        # ãƒ“ãƒ¼ãƒˆã‚°ãƒªãƒƒãƒ‰ã‹ã‚‰ã®çµŒéŽã‚’è¨ˆç®—
        if current >= first_beat:
            elapsed = current - first_beat
            # floor: ã€Œä»Šã„ã‚‹å°ç¯€ã€ã®é ­ã«ã‚¹ãƒŠãƒƒãƒ— (roundã ã¨æ¬¡ã®å°ç¯€ã«é£›ã¶å ´åˆãŒã‚ã‚‹)
            bar_index = int(elapsed / bar_duration)  # int() = floor for positive values
            snap_start = first_beat + (bar_index * bar_duration)
            
            # ãƒ‡ãƒãƒƒã‚°æƒ…å ±
            logger.info(f"Deck {self.name} Loop Snap Debug:")
            logger.info(f"  Current position: {current:.3f}s")
            logger.info(f"  First beat: {first_beat:.3f}s")
            logger.info(f"  Elapsed from first beat: {elapsed:.3f}s")
            logger.info(f"  Bar duration: {bar_duration:.3f}s ({beat_duration:.3f}s Ã— 4)")
            logger.info(f"  Bar index (floor): {bar_index}")
            logger.info(f"  Snap start: {snap_start:.3f}s")
            logger.info(f"  Expected bars in loop: 0={first_beat:.3f}s, 1={first_beat + bar_duration:.3f}s, 2={first_beat + bar_duration*2:.3f}s, 3={first_beat + bar_duration*3:.3f}s")
        else:
            # å†ç”Ÿä½ç½®ãŒfirst_beatã‚ˆã‚Šå‰ (ã‚¤ãƒ³ãƒˆãƒ­ç­‰)
            # first_beatã‹ã‚‰ã®ãƒ«ãƒ¼ãƒ—ã«ã™ã‚‹
            snap_start = first_beat
        
        # ã‚¹ãƒŠãƒƒãƒ—ä½ç½®ã®ãƒãƒªãƒ‡ãƒ¼ã‚·ãƒ§ãƒ³
        snap_start = max(0.0, snap_start)
        
        # ãƒ«ãƒ¼ãƒ—çµ‚äº†ãŒæ›²å°¾ã‚’è¶…ãˆã‚‹å ´åˆã€é–‹å§‹ä½ç½®ã‚’æ‰‹å‰ã«ãšã‚‰ã™
        if self.duration > 0 and (snap_start + loop_duration) > self.duration:
            # æ›²æœ«ã‹ã‚‰é€†ç®—ã—ã¦æœ€å¾Œã®å®Œå…¨ãªNå°ç¯€åŒºé–“ã‚’å–ã‚‹
            total_bars = int((self.duration - first_beat) / bar_duration)
            if total_bars >= bars:
                snap_start = first_beat + ((total_bars - bars) * bar_duration)
            else:
                # æ›²ãŒçŸ­ã™ãŽã‚‹å ´åˆã€æ›²é ­ã‹ã‚‰
                snap_start = first_beat
        
        # Loop Upgrade: ãƒ«ãƒ¼ãƒ—é–‹å§‹/é•·ã•ã‚’å±žæ€§ã«ä¿å­˜ (å¤–éƒ¨å‚ç…§ç”¨)
        self.loop_start_sec = snap_start
        self.loop_duration_sec = loop_duration
        
        # ãƒ«ãƒ¼ãƒ—è¨­å®š
        self.set_loop(snap_start, loop_duration)
        
        logger.info(f"Deck {self.name}: Loop SNAPPED to bar {int((snap_start - first_beat) / bar_duration):.0f} "
                   f"(Start: {snap_start:.3f}s, Duration: {loop_duration:.3f}s, "
                   f"BPM: {bpm:.1f}, FirstBeat: {first_beat:.3f}s)")

    # --- HOT CUE Implementation ---
    def set_hot_cue(self, slot: int, position: float):
        if 0 <= slot < 4:
            self.hot_cues[slot] = position
            logger.info(f"Deck {self.name}: HOT CUE {slot+1} set at {position:.2f}s")

    def jump_to_hot_cue(self, slot: int):
        if 0 <= slot < 4 and self.hot_cues[slot] is not None:
            self.set_position(self.hot_cues[slot])
            logger.info(f"Deck {self.name}: Jumped to HOT CUE {slot+1}")

    def clear_hot_cue(self, slot: int):
        if 0 <= slot < 4:
            self.hot_cues[slot] = None
            logger.info(f"Deck {self.name}: HOT CUE {slot+1} cleared")

    def clear_all_hot_cues(self):
        self.hot_cues = [None] * 4
        logger.debug(f"Deck {self.name}: All HOT CUEs cleared")

    def get_dsp_settings(self):
        stages = len(self.fx_eq_low) if self.fx_eq_low else 1
        return {
            'type': f"DX8(x{stages} Cascade)",
            'eq_high': f"{self.eq_high:.1f}dB (eff: {self.eq_high * stages:.0f}dB)",
            'eq_mid': f"{self.eq_mid:.1f}dB (eff: {self.eq_mid * stages:.0f}dB)",
            'eq_low': f"{self.eq_low:.1f}dB (eff: {self.eq_low * stages:.0f}dB)",
        }

    def apply_track_analysis(self, analysis: dict):
        """ãƒˆãƒ©ãƒƒã‚¯è§£æžçµæžœã‚’é©ç”¨"""
        if 'auto_gain' in analysis:
            self.set_trim(analysis['auto_gain'])
        if 'bpm' in analysis:
            self.original_bpm = analysis['bpm']
            logger.debug(f"Deck {self.name}: Original BPM set to {self.original_bpm}")

    def _generate_waveform(self, decode_stream, points=800):
        if not NUMPY_AVAILABLE or not decode_stream: return None
        try:
            len_bytes = BASS_LIB.BASS_ChannelGetLength(decode_stream, BASS_POS_BYTE)
            if len_bytes <= 0: return None
            chunk = max(8, int(len_bytes // points // 8) * 8)
            buf = (ctypes.c_float * (4096 // 4))()
            vals = []
            for i in range(points):
                BASS_LIB.BASS_ChannelSetPosition(decode_stream, i * chunk, BASS_POS_BYTE)
                read = BASS_LIB.BASS_ChannelGetData(decode_stream, buf, min(chunk, 4096))
                if read > 0:
                    arr = np.ctypeslib.as_array(buf)[:read//4]
                    vals.append(min(1.0, np.sqrt(np.mean(arr**2)) * 1.5))
                else: vals.append(0.0)
            return np.convolve(np.array(vals), np.ones(3)/3, mode='same')
        except: return None

