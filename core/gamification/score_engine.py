"""
Score Engine (Phase R8.1)
==========================

リアルタイムミックス採点・HypeMeter・Combo管理。

採点軸（優先度順）:
1. Beatmatch精度  — BPM差によるリアルタイム加減点
2. Key相性        — Camelot Wheel判定（トランジション検出時に1回）
3. EQ Mixing      — Bass Clash検出（クロスフェーダー中央付近）
4. Energy Flow    — エネルギー差の滑らかさ

HypeMeter:
  範囲 0〜100、初期値 50
  自然減衰 -0.5/秒（100ms ティックで -0.05）

Combo:
  Perfect（BPM差≤0.3）が4秒継続でコンボ開始
  倍率 1.0x → 1.5x → 2.0x（8秒継続で最大）
  Bad 判定でリセット

呼び出し方（mixer_core から 100ms ごと）:
    snapshot = ScoreSnapshot(...)
    events = score_engine.tick(snapshot)
    # events: list[ScoreEvent] — GUI・AI講評トリガーに使う
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ─────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────

TICK_SEC          = 0.1    # 1ティック = 100ms

# Beatmatch 閾値
BEATMATCH_PERFECT = 0.3    # BPM差
BEATMATCH_GOOD    = 1.0
BEATMATCH_BAD     = 2.0

# Bass Clash 閾値
EQ_LOW_CLASH_MIN  = 0.8    # 両デッキの Low ≥ この値
CF_CENTER_MIN     = 0.3    # クロスフェーダー中央判定（0.3〜0.7）
CF_CENTER_MAX     = 0.7
CF_EDGE           = 0.1    # この値以下 or 以上なら片デッキのみ → 判定スキップ

# Clean Swap 閾値
EQ_LOW_CLEAN_OUT  = 0.3    # フェードアウト側 Low ≤ この値
EQ_LOW_CLEAN_IN   = 0.7    # フェードイン側 Low ≥ この値

# Energy Flow 閾値
ENERGY_SMOOTH_MAX = 1.5    # エネルギー差（5秒ウィンドウ）≤ Smooth
ENERGY_JARRING_MIN= 2.5    # エネルギー差 ≥ Jarring

# HypeMeter
HYPE_INIT         = 50.0
HYPE_MIN          = 0.0
HYPE_MAX          = 100.0
HYPE_DECAY_TICK   = 0.05   # -0.05/ティック = -0.5/秒

# Combo
COMBO_PERFECT_SEC = 4.0    # Perfect が何秒続いたらコンボ開始
COMBO_MAX_SEC     = 8.0    # 最大倍率到達時間

# スコア加減点（1ティック = 100ms あたり）
SCORE_BEATMATCH_PERFECT_TICK = 0.5   # = 5/秒
SCORE_BEATMATCH_GOOD_TICK    = 0.2   # = 2/秒
SCORE_BEATMATCH_BAD_TICK     = -1.0  # = -10/秒
SCORE_EQ_CLEAN_TICK          = 0.3   # = 3/秒
SCORE_EQ_CLASH_TICK          = -0.5  # = -5/秒
HYPE_BEATMATCH_PERFECT_TICK  = 0.5
HYPE_BEATMATCH_GOOD_TICK     = 0.2
HYPE_BEATMATCH_BAD_TICK      = -1.0
HYPE_EQ_CLEAN_TICK           = 0.3
HYPE_EQ_CLASH_TICK           = -0.5

# Key相性（トランジション時の一発スコア）
KEY_SCORE = {
    "perfect":   (8.0, 50),   # (hype_delta, score_delta)
    "compatible":(4.0, 30),
    "boost":     (2.0, 20),
    "avoid":     (-5.0, -20),
}

# Energy Flow（5秒ごと）
ENERGY_SCORE = {
    "smooth":  (2.0, 5),
    "jarring": (-3.0, -10),
}

# トランジション検出 — クロスフェーダーが edge から中央に入った瞬間
CF_TRANSITION_ENTER = 0.15  # この値を超えたら "トランジション開始"
CF_TRANSITION_EXIT  = 0.85  # この値を超えたら "トランジション終了"


# ─────────────────────────────────────────────
# データクラス
# ─────────────────────────────────────────────

class BeatmatchRating(Enum):
    PERFECT = "perfect"
    GOOD    = "good"
    OK      = "ok"       # 1.0〜2.0 BPM差（採点なし）
    BAD     = "bad"
    SKIP    = "skip"     # クロスフェーダー端（片デッキのみ）


class ScoreEventType(Enum):
    BEATMATCH_PERFECT = "beatmatch_perfect"
    BEATMATCH_BAD     = "beatmatch_bad"
    KEY_RESULT        = "key_result"
    BASS_CLASH        = "bass_clash"
    CLEAN_SWAP        = "clean_swap"
    ENERGY_SMOOTH     = "energy_smooth"
    ENERGY_JARRING    = "energy_jarring"
    COMBO_START       = "combo_start"
    COMBO_BREAK       = "combo_break"
    HYPE_SPIKE        = "hype_spike"    # Hype が ±20 以上急変
    HYPE_LOW          = "hype_low"      # Hype ≤ 20


@dataclass
class ScoreSnapshot:
    """
    mixer_core から 100ms ごとに渡される現在状態スナップショット。

    Attributes:
        bpm_a, bpm_b:     両デッキの現在 BPM（Sync Engine 取得値）
        eq_low_a/b:       EQ Low ノブ値（0.0〜1.0）
        crossfader:       クロスフェーダー位置（0.0〜1.0）
        key_compat:       Camelot 相性文字列（"perfect"/"compatible"/"boost"/"avoid"）
        energy_a/b:       現在のエネルギー値（0.0〜5.0）
        is_playing_a/b:   再生中か
        venue_id:         選択中の会場 ID（スコア重み調整に使用）
    """
    bpm_a:       float = 120.0
    bpm_b:       float = 120.0
    eq_low_a:    float = 1.0
    eq_low_b:    float = 1.0
    crossfader:  float = 0.5
    key_compat:  str   = "unknown"
    energy_a:    float = 3.0
    energy_b:    float = 3.0
    is_playing_a:bool  = False
    is_playing_b:bool  = False
    venue_id:    str   = "tokyo"


@dataclass
class ScoreEvent:
    """採点イベント。GUI 更新・AI 講評トリガーに使う。"""
    event_type: ScoreEventType
    score_delta: float
    hype_delta:  float
    detail:      str = ""
    timestamp:   float = field(default_factory=time.time)


@dataclass
class ScoreState:
    """外部（GUI・AI）に公開するスコア状態。"""
    total_score:  float = 0.0
    tech_score:   float = 0.0
    vibe_score:   float = 0.0
    hype:         float = HYPE_INIT
    combo_mult:   float = 1.0
    combo_sec:    float = 0.0
    beatmatch:    BeatmatchRating = BeatmatchRating.SKIP
    hype_delta:   float = 0.0   # 直近 tick での Hype 変化量（AI 講評トリガー用）
    rank:         str   = "-"


# ─────────────────────────────────────────────
# ScoreEngine
# ─────────────────────────────────────────────

class ScoreEngine:
    """
    リアルタイムミックス採点エンジン（Phase R8.1）。

    GameSession から 100ms ごとに tick() を呼ぶ。
    返される ScoreEvent リストを GUI や AI 講評トリガーに使う。
    """

    def __init__(self, venue_technical_w: float = 0.6, venue_vibe_w: float = 0.4):
        self._tw = venue_technical_w   # Technical Score 重み
        self._vw = venue_vibe_w        # Vibe Score 重み

        # 状態
        self._state = ScoreState()
        self._perfect_start: Optional[float] = None  # Perfect 継続開始時刻
        self._last_hype     = HYPE_INIT

        # エネルギーウィンドウ（5秒 = 50 ティック）
        self._energy_window: list[tuple[float, float]] = []  # (energy_a, energy_b)
        self._energy_tick   = 0
        ENERGY_WINDOW_TICKS = 50

        self._ENERGY_WINDOW = ENERGY_WINDOW_TICKS

        # クロスフェーダー前回値（トランジション検出）
        self._prev_cf      = 0.5
        self._in_transition= False  # トランジション中フラグ
        self._key_checked  = False  # 現トランジションで Key 判定済みか

    def set_venue_weights(self, technical_w: float, vibe_w: float) -> None:
        """会場切り替え時に重みを更新。"""
        self._tw = technical_w
        self._vw = vibe_w

    def reset(self) -> None:
        """セッション開始時にリセット。"""
        self._state = ScoreState()
        self._last_hype    = HYPE_INIT
        self._perfect_start = None
        self._energy_window.clear()
        self._energy_tick  = 0
        self._prev_cf      = 0.5
        self._in_transition= False
        self._key_checked  = False

    def get_state(self) -> ScoreState:
        return self._state

    # ─────────────────────────────────────────
    # メイン tick
    # ─────────────────────────────────────────

    def tick(self, snap: ScoreSnapshot) -> list[ScoreEvent]:
        """
        100ms ごとに呼び出す。

        Args:
            snap: 現在の状態スナップショット

        Returns:
            このティックで発生した ScoreEvent のリスト
        """
        events: list[ScoreEvent] = []

        # 両デッキ再生中でないならほぼ何もしない
        both_playing = snap.is_playing_a and snap.is_playing_b

        # 1. HypeMeter 自然減衰（常時）
        self._state.hype = max(HYPE_MIN,
                               min(HYPE_MAX, self._state.hype - HYPE_DECAY_TICK))

        if not both_playing:
            self._update_rank()
            return events

        # 2. Beatmatch 採点（優先度 1）
        bm_events = self._eval_beatmatch(snap)
        events.extend(bm_events)

        # 3. Bass Clash / Clean Swap（優先度 3）
        eq_events = self._eval_eq_mixing(snap)
        events.extend(eq_events)

        # 4. Key 相性（トランジション検出、優先度 2）
        key_events = self._eval_key_transition(snap)
        events.extend(key_events)

        # 5. Energy Flow（50 ティックごと = 5秒）
        energy_events = self._eval_energy_flow(snap)
        events.extend(energy_events)

        # 6. Combo 処理
        combo_events = self._update_combo(snap)
        events.extend(combo_events)

        # 7. スコアに Combo 倍率とウェイトを適用して合計
        self._apply_events(events)

        # 8. Hype 急変チェック
        hype_delta = self._state.hype - self._last_hype
        self._state.hype_delta = hype_delta
        if abs(hype_delta) >= 20.0:
            events.append(ScoreEvent(ScoreEventType.HYPE_SPIKE, 0, 0,
                                     f"Hype {hype_delta:+.1f}"))
        if self._state.hype <= 20.0:
            events.append(ScoreEvent(ScoreEventType.HYPE_LOW, 0, 0,
                                     f"Hype={self._state.hype:.0f}"))
        self._last_hype = self._state.hype

        # 9. ランク更新
        self._update_rank()

        self._prev_cf = snap.crossfader
        return events

    # ─────────────────────────────────────────
    # 採点サブルーチン
    # ─────────────────────────────────────────

    def _eval_beatmatch(self, snap: ScoreSnapshot) -> list[ScoreEvent]:
        cf = snap.crossfader

        # クロスフェーダーが端なら片デッキのみ → 判定スキップ
        if cf <= CF_EDGE or cf >= (1.0 - CF_EDGE):
            self._state.beatmatch = BeatmatchRating.SKIP
            return []

        diff = abs(snap.bpm_a - snap.bpm_b)
        events = []

        if diff <= BEATMATCH_PERFECT:
            self._state.beatmatch = BeatmatchRating.PERFECT
            events.append(ScoreEvent(
                ScoreEventType.BEATMATCH_PERFECT,
                SCORE_BEATMATCH_PERFECT_TICK,
                HYPE_BEATMATCH_PERFECT_TICK,
                f"BPM diff {diff:.2f}",
            ))
        elif diff <= BEATMATCH_GOOD:
            self._state.beatmatch = BeatmatchRating.GOOD
            events.append(ScoreEvent(
                ScoreEventType.BEATMATCH_PERFECT,   # GUI 上は Good として扱う
                SCORE_BEATMATCH_GOOD_TICK,
                HYPE_BEATMATCH_GOOD_TICK,
                f"BPM diff {diff:.2f}",
            ))
        elif diff > BEATMATCH_BAD:
            self._state.beatmatch = BeatmatchRating.BAD
            events.append(ScoreEvent(
                ScoreEventType.BEATMATCH_BAD,
                SCORE_BEATMATCH_BAD_TICK,
                HYPE_BEATMATCH_BAD_TICK,
                f"BPM diff {diff:.2f}",
            ))
        else:
            self._state.beatmatch = BeatmatchRating.OK

        return events

    def _eval_eq_mixing(self, snap: ScoreSnapshot) -> list[ScoreEvent]:
        cf = snap.crossfader
        # クロスフェーダーが中央付近のみ判定
        if not (CF_CENTER_MIN <= cf <= CF_CENTER_MAX):
            return []

        la, lb = snap.eq_low_a, snap.eq_low_b
        events = []

        if la >= EQ_LOW_CLASH_MIN and lb >= EQ_LOW_CLASH_MIN:
            events.append(ScoreEvent(
                ScoreEventType.BASS_CLASH,
                SCORE_EQ_CLASH_TICK,
                HYPE_EQ_CLASH_TICK,
                f"Low A={la:.2f} B={lb:.2f}",
            ))
        elif (la <= EQ_LOW_CLEAN_OUT and lb >= EQ_LOW_CLEAN_IN) or \
             (lb <= EQ_LOW_CLEAN_OUT and la >= EQ_LOW_CLEAN_IN):
            events.append(ScoreEvent(
                ScoreEventType.CLEAN_SWAP,
                SCORE_EQ_CLEAN_TICK,
                HYPE_EQ_CLEAN_TICK,
                f"Clean swap Low A={la:.2f} B={lb:.2f}",
            ))

        return events

    def _eval_key_transition(self, snap: ScoreSnapshot) -> list[ScoreEvent]:
        """クロスフェーダーが端→中央に入った瞬間に Key 判定を1回実行。"""
        cf = snap.crossfader
        prev = self._prev_cf
        events = []

        # トランジション開始検出（端→中央への移動）
        was_edge = (prev <= CF_EDGE or prev >= 1.0 - CF_EDGE)
        is_center = (CF_TRANSITION_ENTER < cf < CF_TRANSITION_EXIT)

        if was_edge and is_center and not self._in_transition:
            self._in_transition = True
            self._key_checked   = False

        # トランジション終了
        if self._in_transition and (cf <= CF_EDGE or cf >= 1.0 - CF_EDGE):
            self._in_transition = False
            self._key_checked   = False

        # Key 判定（トランジション中に1回）
        if self._in_transition and not self._key_checked and snap.key_compat != "unknown":
            self._key_checked = True
            compat = snap.key_compat
            hd, sd = KEY_SCORE.get(compat, (0.0, 0))
            etype = ScoreEventType.KEY_RESULT
            events.append(ScoreEvent(etype, float(sd), hd,
                                     f"Key: {compat}"))

        return events

    def _eval_energy_flow(self, snap: ScoreSnapshot) -> list[ScoreEvent]:
        """5秒ウィンドウでエネルギー差を評価。"""
        self._energy_window.append((snap.energy_a, snap.energy_b))
        self._energy_tick += 1

        if self._energy_tick < self._ENERGY_WINDOW:
            return []

        # ウィンドウが溜まったら評価してリセット
        self._energy_tick = 0
        energies = [abs(a - b) for a, b in self._energy_window]
        self._energy_window.clear()

        avg_diff = sum(energies) / len(energies) if energies else 0.0
        events = []

        if avg_diff <= ENERGY_SMOOTH_MAX:
            hd, sd = ENERGY_SCORE["smooth"]
            events.append(ScoreEvent(ScoreEventType.ENERGY_SMOOTH, float(sd), hd,
                                     f"Energy diff avg={avg_diff:.2f}"))
        elif avg_diff >= ENERGY_JARRING_MIN:
            hd, sd = ENERGY_SCORE["jarring"]
            events.append(ScoreEvent(ScoreEventType.ENERGY_JARRING, float(sd), hd,
                                     f"Energy diff avg={avg_diff:.2f}"))

        return events

    def _update_combo(self, snap: ScoreSnapshot) -> list[ScoreEvent]:
        """Combo 倍率の更新。"""
        events = []

        if self._state.beatmatch == BeatmatchRating.PERFECT:
            if self._perfect_start is None:
                self._perfect_start = time.time()
            elapsed = time.time() - self._perfect_start
            self._state.combo_sec = elapsed

            prev_mult = self._state.combo_mult
            if elapsed >= COMBO_MAX_SEC:
                self._state.combo_mult = 2.0
            elif elapsed >= COMBO_PERFECT_SEC:
                # 4秒〜8秒で 1.0 → 2.0 に線形補間
                t = (elapsed - COMBO_PERFECT_SEC) / (COMBO_MAX_SEC - COMBO_PERFECT_SEC)
                self._state.combo_mult = 1.0 + t

            if self._state.combo_mult >= 1.5 and prev_mult < 1.5:
                events.append(ScoreEvent(ScoreEventType.COMBO_START, 0, 5.0,
                                         f"Combo x{self._state.combo_mult:.1f}"))
        elif self._state.beatmatch == BeatmatchRating.BAD:
            if self._state.combo_mult > 1.0:
                events.append(ScoreEvent(ScoreEventType.COMBO_BREAK, 0, 0,
                                         "Combo reset"))
            self._state.combo_mult = 1.0
            self._state.combo_sec  = 0.0
            self._perfect_start    = None

        return events

    def _apply_events(self, events: list[ScoreEvent]) -> None:
        """イベントのスコア・Hype デルタを状態に反映（Combo 倍率・ウェイト適用）。"""
        mult = self._state.combo_mult

        for ev in events:
            sd = ev.score_delta * mult

            # Tech / Vibe 振り分け
            if ev.event_type in (ScoreEventType.BEATMATCH_PERFECT,
                                  ScoreEventType.BEATMATCH_BAD,
                                  ScoreEventType.KEY_RESULT):
                self._state.tech_score += sd * self._tw
                self._state.total_score += sd * self._tw
            else:
                self._state.vibe_score += sd * self._vw
                self._state.total_score += sd * self._vw

            # Hype
            self._state.hype = max(HYPE_MIN,
                                   min(HYPE_MAX,
                                       self._state.hype + ev.hype_delta))

    def _update_rank(self) -> None:
        """暫定ランクをスコアから算出（会場ごとの閾値は GameSession が上書き）。"""
        s = self._state.total_score
        if s >= 10000:
            self._state.rank = "S"
        elif s >= 7000:
            self._state.rank = "A"
        elif s >= 4000:
            self._state.rank = "B"
        elif s >= 2000:
            self._state.rank = "C"
        else:
            self._state.rank = "D"
