"""
Sync Engine (Phase R3)
======================

BPM同期 + 位相同期エンジン

Mixxxの bpmcontrol.cpp / synccontrol.cpp アルゴリズムを参照し、
BASS Audio Library の BASS_ATTRIB_TEMPO で実現する。

方針:
  1. Sync ON 時: BPM一致（tempo_percent 調整）
  2. 位相補正: 100msコールバック毎に calcSyncAdjustment() を呼び出し、
     テンポを微小変動させて位相差を収束させる（クリックノイズなし）
  3. 初回位相シーク: 位相差 > PHASE_SEEK_THRESHOLD の場合のみ1回だけシーク

参照:
  bpmcontrol.cpp L552-627 : calcSyncAdjustment()
  bpmcontrol.cpp L459-492 : shortestPercentageChange()
  bpmcontrol.cpp L494-550 : calcSyncedRate()
"""

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)


# --- Mixxxの定数 (bpmcontrol.cpp L587-600 より) ---
SYNC_ERROR_THRESHOLD       = 0.01   # これ以下なら同期完了とみなす
SYNC_TRAINWRECK_THRESHOLD  = 0.2    # これ以上なら大幅ズレ→最大補正
SYNC_ADJUSTMENT_CAP        = 0.05   # テンポ補正上限 (±5%)
SYNC_PROPORTIONAL_GAIN     = 0.7    # 比例制御ゲイン
SYNC_DELTA_CAP             = 0.02   # 1フレームあたりの補正変化量上限
PHASE_SEEK_THRESHOLD       = 0.25   # 初回フェーズシーク閾値（0.25 beat）


class DeckSyncState:
    """1デッキ分のSync状態"""

    def __init__(self, deck_id: str):
        self.deck_id = deck_id
        self.sync_enabled = False
        self.last_adjustment = 1.0   # 前回のadjustment係数（1.0 = 変化なし）
        self.reset_needed = True     # リセットフラグ

    def reset(self):
        self.last_adjustment = 1.0
        self.reset_needed = True


class SyncEngine:
    """
    BPM + 位相同期エンジン（2デッキ固定: Deck A = Leader, Deck B = Follower）

    使い方:
        engine = SyncEngine()
        engine.enable_sync('B')          # Deck B をフォロワーにする
        # 100msタイマーから呼ぶ:
        engine.update(deck_a, deck_b, deck_a_info, deck_b_info)
    """

    def __init__(self):
        self._state_a = DeckSyncState('A')
        self._state_b = DeckSyncState('B')

    # ------------------------------------------------------------------ #
    # 公開 API                                                            #
    # ------------------------------------------------------------------ #

    def enable_sync(self, deck_id: str, deck, info: dict):
        """
        Sync を有効にする。
        BPMを即時一致させ、初回フェーズシークを行う。

        Args:
            deck_id: 'A' または 'B'
            deck:    対象 Deck インスタンス
            info:    トラック解析情報 (bpm, first_beat を含む)
        """
        state = self._state_for(deck_id)
        state.sync_enabled = True
        state.reset()
        logger.info(f"SyncEngine: Deck {deck_id} sync ENABLED")

    def disable_sync(self, deck_id: str):
        """Sync を無効にし、テンポ補正を0%（元の速度）に戻す"""
        state = self._state_for(deck_id)
        if not state.sync_enabled:
            return
        state.sync_enabled = False
        state.reset()
        logger.info(f"SyncEngine: Deck {deck_id} sync DISABLED")

    def is_sync_enabled(self, deck_id: str) -> bool:
        return self._state_for(deck_id).sync_enabled

    def update(self, deck_a, deck_b, info_a: Optional[dict], info_b: Optional[dict]):
        """
        100ms コールバックから呼び出す。
        Deck B が有効な場合、Deck A を Leader として位相補正を適用する。

        現在は Deck B → Deck A に追従する実装（B = Follower 固定）。
        """
        if self._state_b.sync_enabled and info_a and info_b:
            self._update_follower(
                leader_deck=deck_a,
                follower_deck=deck_b,
                leader_info=info_a,
                follower_info=info_b,
                follower_state=self._state_b
            )

    # ------------------------------------------------------------------ #
    # 内部実装                                                            #
    # ------------------------------------------------------------------ #

    def _update_follower(self, leader_deck, follower_deck, leader_info, follower_info, follower_state):
        """
        Follower デッキのテンポを微調整して Leader に位相を合わせる。

        Step 1: BPM 一致（tempo_percent を更新）
        Step 2: 位相差を算出し calcSyncAdjustment() で補正係数を得る
        Step 3: 補正係数を BASS_ATTRIB_TEMPO に反映
        """
        leader_bpm   = leader_info.get('bpm', 0.0)
        follower_bpm = follower_info.get('bpm', 0.0)

        if leader_bpm <= 0 or follower_bpm <= 0:
            return

        # --- Step 1: BPM 倍率補正 ---
        effective_leader_bpm = self._get_effective_bpm(
            leader_bpm, leader_deck.tempo_percent
        )
        # half/double BPM 自動判定
        ratio = effective_leader_bpm / follower_bpm
        if ratio > 1.5:
            ratio /= 2.0    # follower が leader の倍速 → half BPM
        elif ratio < 0.67:
            ratio *= 2.0    # follower が leader の半速 → double BPM

        # follower の目標 tempo_percent を計算
        target_tempo_pct = (ratio - 1.0) * 100.0
        target_tempo_pct = max(-50.0, min(50.0, target_tempo_pct))

        # --- Step 2: 位相差を算出 ---
        leader_beat_dist   = self._get_beat_distance(leader_deck, leader_info)
        follower_beat_dist = self._get_beat_distance(follower_deck, follower_info)

        if leader_beat_dist is None or follower_beat_dist is None:
            # 解析データ不足 → BPMだけ合わせる
            follower_deck.set_tempo(target_tempo_pct)
            return

        # Mixxx: error = shortestPercentageChange(target, my)
        error = self._shortest_percentage_change(leader_beat_dist, follower_beat_dist)

        # --- 初回フェーズシーク判定 ---
        if follower_state.reset_needed:
            follower_state.reset_needed = False
            if abs(error) > PHASE_SEEK_THRESHOLD:
                # 初回のみ位相シークを実行（1ビート以内に寄せる）
                beat_duration = 60.0 / (follower_bpm * ratio)
                seek_offset = error * beat_duration
                current_pos = follower_deck.get_position()
                new_pos = max(0.0, current_pos + seek_offset)
                follower_deck.set_position(new_pos)
                logger.info(
                    f"SyncEngine: Phase seek Deck {follower_state.deck_id}: "
                    f"error={error:.3f} offset={seek_offset:.3f}s → pos={new_pos:.3f}s"
                )

        # --- Step 3: calcSyncAdjustment() で補正係数を算出 ---
        adjustment = self._calc_sync_adjustment(error, follower_state)

        # adjustment は乗算係数 (1.0 = 補正なし)
        # target_tempo_pct を adjustment で調整する
        # tempo_percent 変換: rate_ratio = (tempo_pct / 100 + 1.0)
        # adjusted_rate = rate_ratio * adjustment
        rate_ratio = (target_tempo_pct / 100.0 + 1.0) * adjustment
        adjusted_tempo_pct = (rate_ratio - 1.0) * 100.0
        adjusted_tempo_pct = max(-50.0, min(50.0, adjusted_tempo_pct))

        follower_deck.set_tempo(adjusted_tempo_pct)

        if abs(error) > SYNC_ERROR_THRESHOLD:
            logger.debug(
                f"SyncEngine Deck {follower_state.deck_id}: "
                f"leader_beat={leader_beat_dist:.3f} follower_beat={follower_beat_dist:.3f} "
                f"error={error:.4f} adj={adjustment:.4f} tempo={adjusted_tempo_pct:+.2f}%"
            )

    @staticmethod
    def _get_effective_bpm(original_bpm: float, tempo_percent: float) -> float:
        """tempo_percent を考慮した実効 BPM を返す"""
        return original_bpm * (1.0 + tempo_percent / 100.0)

    @staticmethod
    def _get_beat_distance(deck, info: dict) -> Optional[float]:
        """
        現在の再生位置から「ビート内位相（0.0〜1.0）」を計算する。

        0.0 = 直前ビートにいる
        1.0 = 次のビートに到達する直前

        first_beat と bpm が解析済みであることが前提。
        """
        bpm = info.get('bpm', 0.0)
        first_beat = info.get('first_beat', 0.0)

        if bpm <= 0:
            return None

        current_pos = deck.get_position()
        beat_duration = 60.0 / bpm  # 1ビートの長さ（秒）

        if current_pos < first_beat:
            return 0.0

        elapsed = current_pos - first_beat
        beat_phase = (elapsed % beat_duration) / beat_duration  # 0.0〜1.0
        return beat_phase

    @staticmethod
    def _shortest_percentage_change(target: float, current: float) -> float:
        """
        Mixxx bpmcontrol.cpp L459-492 : shortestPercentageChange()

        ビート位相の差（0.0〜1.0 のループ空間上での最短距離）を返す。
        正: current が target より「遅れている」
        負: current が target より「進んでいる」
        """
        if current == target:
            return 0.0
        elif current < target:
            forward  = target - current
            backward = target - current - 1.0
        else:
            forward  = 1.0 - current + target
            backward = target - current

        return forward if abs(forward) < abs(backward) else backward

    @staticmethod
    def _calc_sync_adjustment(error: float, state: DeckSyncState) -> float:
        """
        Mixxx bpmcontrol.cpp L552-627 : calcSyncAdjustment()

        errorに基づいてテンポ補正係数を算出する。
        1.0 = 補正なし
        > 1.0 = 速くする（遅れている）
        < 1.0 = 遅くする（進んでいる）
        """
        if state.reset_needed:
            state.last_adjustment = 1.0

        if abs(error) > SYNC_TRAINWRECK_THRESHOLD:
            # 大幅ズレ: 最大速度で追従
            adjustment = 1.0 + SYNC_ADJUSTMENT_CAP
        elif abs(error) > SYNC_ERROR_THRESHOLD:
            # 比例制御
            # error > 0 → 遅れている → 速くする (adjustment > 1.0)
            # error < 0 → 進んでいる → 遅くする (adjustment < 1.0)
            raw_adjust = 1.0 + (-error * SYNC_PROPORTIONAL_GAIN)

            # 前回値からの変化量を cap
            delta = raw_adjust - state.last_adjustment
            delta = max(-SYNC_DELTA_CAP, min(SYNC_DELTA_CAP, delta))

            # 全体の補正量を cap
            clamped = max(-SYNC_ADJUSTMENT_CAP,
                          min(SYNC_ADJUSTMENT_CAP,
                              state.last_adjustment - 1.0 + delta))
            adjustment = 1.0 + clamped
        else:
            # 同期完了: 補正なし
            adjustment = 1.0

        state.last_adjustment = adjustment
        return adjustment

    def _state_for(self, deck_id: str) -> DeckSyncState:
        return self._state_a if deck_id == 'A' else self._state_b
