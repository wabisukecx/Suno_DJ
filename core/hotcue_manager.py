"""
Hot Cue Manager Module (Phase R4)
====================================

HOT CUE 8スロット管理・LoopCue・LED制御モジュール。

Phase R4 要件:
- スロット数: 4 → 8 に拡張
- CueMode: Auto / Cue / Loop（LoopCue）
- 状態: Empty / Set / Active
- 操作: Set / Goto / GotoAndPlay / GotoAndStop / Clear / Swap
- LED 制御: VCI-100 パッド LED への ON/OFF/Blink コマンド生成

設計方針:
- `Deck` への直接依存を持たない（位置情報の保持のみ）
- LED コマンドは dict を返すだけ → 実際の MIDI 送信は MIDIController 側
- `deck.py` の既存 4 スロット実装は変更しない（mixer_core でこちらを使用）
- スレッドセーフ（slot ごとに独立した状態、共有 Lock は不要）

LED コマンド例:
    {"type": "on",   "note": 0x50, "velocity": 127}
    {"type": "off",  "note": 0x50, "velocity":   0}
    {"type": "blink","note": 0x50, "interval": 0.5}

VCI-100 HOT CUE LED ノートアサイン（付録 C 拡張案）:
    HOT CUE 1-4 Set   : Note 0x50-0x53
    HOT CUE 1-4 Call  : Note 0x54-0x57
    HOT CUE 5-8 Set   : Note 0x58-0x5B
    HOT CUE 5-8 Call  : Note 0x5C-0x5F
    HOT CUE 1-8 LED   : Note 0x50-0x57（出力）
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

# HOT CUE スロット数
NUM_SLOTS = 8

# VCI-100 LED ノートベース（付録 C）
LED_BASE_NOTE = 0x50  # スロット 0 → 0x50, ..., スロット 7 → 0x57


# ─────────────────────────────────────────────
# Enum 定義
# ─────────────────────────────────────────────

class CueStatus(Enum):
    """HOT CUE スロットの状態"""
    EMPTY  = "empty"   # 未設定
    SET    = "set"     # 設定済み（通常 Cue）
    ACTIVE = "active"  # アクティブ（LoopCue が再生中 等）


class CueMode(Enum):
    """HOT CUE 設定モード"""
    AUTO  = "auto"   # 自動判定（ループ中なら LoopCue）
    CUE   = "cue"    # 通常 Cue 強制
    LOOP  = "loop"   # LoopCue 強制


class LedCommand(Enum):
    """LED 制御コマンド種別"""
    ON    = "on"
    OFF   = "off"
    BLINK = "blink"


# ─────────────────────────────────────────────
# データクラス
# ─────────────────────────────────────────────

@dataclass
class HotCueSlot:
    """
    1 スロット分の HOT CUE データ。

    Attributes:
        slot:         スロット番号（0〜7）
        status:       状態（Empty / Set / Active）
        position:     Cue 位置（秒）、None = 未設定
        is_loop_cue:  LoopCue か否か
        loop_duration: LoopCue の長さ（秒）
        color:        GUI 表示用カラー文字列（例: "#FF4444"）
        label:        任意ラベル（例: "Drop"）
    """
    slot: int
    status: CueStatus = CueStatus.EMPTY
    position: Optional[float] = None
    is_loop_cue: bool = False
    loop_duration: float = 0.0
    color: str = "#FF4444"
    label: str = ""

    def is_set(self) -> bool:
        return self.status != CueStatus.EMPTY

    def to_dict(self) -> dict:
        return {
            "slot":          self.slot,
            "status":        self.status.value,
            "position":      self.position,
            "is_loop_cue":   self.is_loop_cue,
            "loop_duration": self.loop_duration,
            "color":         self.color,
            "label":         self.label,
        }


@dataclass
class LedEvent:
    """LED 制御イベント（MIDI 送信用）"""
    slot: int
    command: LedCommand
    note: int
    velocity: int = 127
    interval: float = 0.5   # blink の場合の点滅間隔（秒）

    def to_dict(self) -> dict:
        return {
            "type":     self.command.value,
            "note":     self.note,
            "velocity": self.velocity,
            "interval": self.interval,
        }


# ─────────────────────────────────────────────
# HotCueManager 本体
# ─────────────────────────────────────────────

# スロットごとのデフォルトカラー（GUI 表示用）
_DEFAULT_COLORS = [
    "#FF4444",  # 1: 赤
    "#44FF44",  # 2: 緑
    "#4444FF",  # 3: 青
    "#FFFF44",  # 4: 黄
    "#FF44FF",  # 5: マゼンタ
    "#44FFFF",  # 6: シアン
    "#FF8844",  # 7: オレンジ
    "#8844FF",  # 8: 紫
]


class HotCueManager:
    """
    HOT CUE 8スロット管理クラス（Phase R4）。

    デッキごとに 1 インスタンス生成する。
    位置の保持・状態管理・LED コマンド生成のみを担い、
    実際の Deck シーク・MIDI 送信は呼び出し元（mixer_core）が行う。

    使い方（mixer_core.py）:
        self.hcm_a = HotCueManager("A")
        self.hcm_b = HotCueManager("B")

        # HOT CUE セット
        position = deck.get_position()
        is_loop  = deck.loop_active
        loop_dur = deck.loop_duration_sec
        led_event = self.hcm_a.set_cue(slot=0, position=position,
                                        is_loop=is_loop, loop_duration=loop_dur)
        midi_controller.send_led(led_event)

        # HOT CUE ジャンプ
        result = self.hcm_a.goto(slot=0)
        if result.position is not None:
            deck.set_position(result.position)
    """

    def __init__(self, deck_id: str = "A"):
        self.deck_id = deck_id
        self._slots: list[HotCueSlot] = [
            HotCueSlot(slot=i, color=_DEFAULT_COLORS[i])
            for i in range(NUM_SLOTS)
        ]

    # ─────────────────────────────────────────
    # 基本操作
    # ─────────────────────────────────────────

    def set_cue(
        self,
        slot: int,
        position: float,
        mode: CueMode = CueMode.AUTO,
        is_loop: bool = False,
        loop_duration: float = 0.0,
        label: str = "",
    ) -> LedEvent:
        """
        HOT CUE を設定する。

        Args:
            slot:          スロット番号（0〜7）
            position:      Cue 位置（秒）
            mode:          設定モード（Auto / Cue / Loop）
            is_loop:       デッキが現在ループ中か（Auto モードで参照）
            loop_duration: ループ長（秒）
            label:         任意ラベル

        Returns:
            LED を ON にするコマンド（LedEvent）
        """
        if not self._valid(slot):
            return self._led(slot, LedCommand.OFF)

        s = self._slots[slot]
        s.position = position
        s.label    = label

        # LoopCue 判定
        if mode == CueMode.LOOP or (mode == CueMode.AUTO and is_loop and loop_duration > 0):
            s.is_loop_cue   = True
            s.loop_duration = loop_duration
        else:
            s.is_loop_cue   = False
            s.loop_duration = 0.0

        s.status = CueStatus.SET
        logger.info(
            f"Deck {self.deck_id}: HOT CUE {slot+1} set "
            f"@ {position:.2f}s loop={s.is_loop_cue}"
        )
        return self._led(slot, LedCommand.ON)

    def goto(self, slot: int) -> HotCueSlot:
        """
        HOT CUE スロットの情報を返す（シークは呼び出し元が実施）。

        Returns:
            HotCueSlot（未設定の場合 position=None）
        """
        if not self._valid(slot) or not self._slots[slot].is_set():
            logger.debug(f"Deck {self.deck_id}: HOT CUE {slot+1} not set")
            return HotCueSlot(slot=slot)  # 空スロット
        logger.info(f"Deck {self.deck_id}: HOT CUE {slot+1} → {self._slots[slot].position:.2f}s")
        return self._slots[slot]

    def clear(self, slot: int) -> LedEvent:
        """
        HOT CUE スロットをクリアする。

        Returns:
            LED を OFF にするコマンド（LedEvent）
        """
        if not self._valid(slot):
            return self._led(slot, LedCommand.OFF)

        s = self._slots[slot]
        s.status       = CueStatus.EMPTY
        s.position     = None
        s.is_loop_cue  = False
        s.loop_duration = 0.0
        s.label        = ""
        logger.info(f"Deck {self.deck_id}: HOT CUE {slot+1} cleared")
        return self._led(slot, LedCommand.OFF)

    def clear_all(self) -> list[LedEvent]:
        """全スロットをクリアし、LED OFF コマンドを返す。"""
        return [self.clear(i) for i in range(NUM_SLOTS)]

    def swap(self, slot_a: int, slot_b: int) -> list[LedEvent]:
        """
        2 つのスロットを入れ替える。

        Returns:
            両スロットの LED コマンドリスト
        """
        if not self._valid(slot_a) or not self._valid(slot_b):
            return []
        self._slots[slot_a], self._slots[slot_b] = self._slots[slot_b], self._slots[slot_a]
        self._slots[slot_a].slot = slot_a
        self._slots[slot_b].slot = slot_b
        events = []
        for s in (slot_a, slot_b):
            cmd = LedCommand.ON if self._slots[s].is_set() else LedCommand.OFF
            events.append(self._led(s, cmd))
        logger.info(f"Deck {self.deck_id}: HOT CUE {slot_a+1} ↔ {slot_b+1} swapped")
        return events

    def activate(self, slot: int) -> LedEvent:
        """
        スロットを Active 状態にする（LoopCue 再生中などに使用）。

        Returns:
            LED を Blink にするコマンド（LedEvent）
        """
        if self._valid(slot) and self._slots[slot].is_set():
            self._slots[slot].status = CueStatus.ACTIVE
        return self._led(slot, LedCommand.BLINK)

    def deactivate(self, slot: int) -> LedEvent:
        """Active → Set に戻す。"""
        if self._valid(slot) and self._slots[slot].status == CueStatus.ACTIVE:
            self._slots[slot].status = CueStatus.SET
        return self._led(slot, LedCommand.ON if self._slots[slot].is_set() else LedCommand.OFF)

    # ─────────────────────────────────────────
    # 情報参照
    # ─────────────────────────────────────────

    def get_slot(self, slot: int) -> HotCueSlot:
        """スロット情報を返す。"""
        if not self._valid(slot):
            return HotCueSlot(slot=slot)
        return self._slots[slot]

    def all_slots(self) -> list[HotCueSlot]:
        """全スロットのリストを返す。"""
        return list(self._slots)

    def set_color(self, slot: int, color: str) -> None:
        """GUI 表示用カラーを設定する。"""
        if self._valid(slot):
            self._slots[slot].color = color

    def to_dict(self) -> dict:
        """全スロット情報を dict に変換する。"""
        return {
            "deck_id": self.deck_id,
            "slots":   [s.to_dict() for s in self._slots],
        }

    def led_sync_all(self) -> list[LedEvent]:
        """
        全スロットの現在状態に合わせた LED コマンド一覧を返す。
        接続直後の LED 状態初期化に使用する。
        """
        events = []
        for s in self._slots:
            if s.status == CueStatus.ACTIVE:
                events.append(self._led(s.slot, LedCommand.BLINK))
            elif s.status == CueStatus.SET:
                events.append(self._led(s.slot, LedCommand.ON))
            else:
                events.append(self._led(s.slot, LedCommand.OFF))
        return events

    # ─────────────────────────────────────────
    # 内部ユーティリティ
    # ─────────────────────────────────────────

    def _valid(self, slot: int) -> bool:
        return 0 <= slot < NUM_SLOTS

    def _led(self, slot: int, command: LedCommand, interval: float = 0.5) -> LedEvent:
        note = LED_BASE_NOTE + slot
        velocity = 127 if command != LedCommand.OFF else 0
        return LedEvent(
            slot=slot,
            command=command,
            note=note,
            velocity=velocity,
            interval=interval,
        )
