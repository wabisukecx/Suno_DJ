"""
Style Logger Module (Phase R4)
================================

DJプレイスタイルのMIDI操作ログ記録・分析モジュール。

機能:
- セッション中のMIDI操作（EQ/Filter/Crossfader/Tempo）をタイムスタンプ付きで記録
- セッション終了時に JSON としてローカルに永続保存
- 操作パターンからスタイルプロファイルを分析
- Gemini プロンプトに組み込めるスタイル要約文字列を生成

保存先: logs/style_YYYYMMDD_HHMMSS.json

設計方針:
- mixer_core.py の既存コールバック内から 1 行追加するだけで連携可能
- 分析は完全に独立（他モジュールへの依存なし）
- スレッドセーフ（Lock + append のみ）
"""

from __future__ import annotations

import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

logger = logging.getLogger(__name__)

# ログ保存先ディレクトリ
DEFAULT_LOG_DIR = Path(__file__).parent.parent / "logs"

# 操作種別
OP_EQ_HIGH   = "eq_high"
OP_EQ_MID    = "eq_mid"
OP_EQ_LOW    = "eq_low"
OP_FILTER    = "filter"
OP_CROSSFADE = "crossfader"
OP_TEMPO     = "tempo"
OP_PLAY      = "play"
OP_CUE       = "cue"
OP_LOOP      = "loop"
OP_HOTCUE    = "hotcue"


# ─────────────────────────────────────────────
# データクラス
# ─────────────────────────────────────────────

@dataclass
class OpEvent:
    """単一のMIDI操作イベント"""
    ts: float        # UNIX タイムスタンプ
    op: str          # 操作種別（OP_* 定数）
    deck: str        # "A" / "B" / "master"
    value: float     # 正規化値（0.0〜1.0）または任意浮動小数


@dataclass
class StyleProfile:
    """
    セッション全体の操作パターン集計結果。

    Attributes:
        session_duration:  セッション長（秒）
        total_ops:         総操作回数
        eq_kill_ratio:     EQ Kill（full cut）の割合（0.0〜1.0）
        filter_sweep_count: フィルタースイープ回数（LPF↔HPF の往復）
        crossfader_moves:  クロスフェーダー移動回数
        tempo_adj_count:   テンポ調整回数
        dominant_style:    推定スタイル文字列
        eq_low_activity:   Low EQ 操作頻度（ops/min）
        filter_activity:   Filter 操作頻度（ops/min）
    """
    session_duration: float = 0.0
    total_ops: int = 0
    eq_kill_ratio: float = 0.0
    filter_sweep_count: int = 0
    crossfader_moves: int = 0
    tempo_adj_count: int = 0
    dominant_style: str = "unknown"
    eq_low_activity: float = 0.0
    filter_activity: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    def to_prompt_text(self) -> str:
        """
        Gemini プロンプトに組み込める 1〜3 行の日本語スタイル要約を生成する。

        例:
            "DJスタイル: Minimal / Low EQ多用型。フィルタースイープ12回。
             テンポ調整少なめ（3回）。EQ Kill率: 42%。"
        """
        parts: list[str] = [f"DJスタイル: {self.dominant_style}"]

        if self.eq_kill_ratio > 0.3:
            parts.append(f"EQ Kill多用（{self.eq_kill_ratio:.0%}）")
        if self.filter_sweep_count > 0:
            parts.append(f"フィルタースイープ {self.filter_sweep_count} 回")
        if self.crossfader_moves > 0:
            parts.append(f"クロスフェーダー操作 {self.crossfader_moves} 回")
        if self.tempo_adj_count > 0:
            parts.append(f"テンポ調整 {self.tempo_adj_count} 回")

        return "。".join(parts) + "。"


# ─────────────────────────────────────────────
# StyleLogger 本体
# ─────────────────────────────────────────────

class StyleLogger:
    """
    DJプレイスタイルのMIDI操作ログを記録・分析するクラス（Phase R4）。

    使い方（mixer_core.py の既存コールバックに 1 行追加）:

        # mixer_core.py の __init__
        self.style_logger = StyleLogger()

        # EQ コールバック内
        self.midi_controller.register_callback('deck_a_eq_low', lambda v: (
            self.audio_engine.deck_a.set_eq_low(self._norm_to_eq_db(v)),
            self.style_logger.log(OP_EQ_LOW, "A", v),   # ← 追加
        ))

        # セッション終了時
        self.style_logger.save_session()
        profile = self.style_logger.get_profile()
        print(profile.to_prompt_text())
    """

    def __init__(self, log_dir: Optional[Path] = None):
        self._log_dir: Path = log_dir or DEFAULT_LOG_DIR
        self._events: list[OpEvent] = []
        self._lock = Lock()
        self._session_start: float = time.time()

    # ─────────────────────────────────────────
    # 記録 API
    # ─────────────────────────────────────────

    def log(self, op: str, deck: str, value: float) -> None:
        """
        MIDI 操作を記録する（スレッドセーフ）。

        Args:
            op:    操作種別（OP_EQ_LOW など）
            deck:  デッキ識別子（"A" / "B" / "master"）
            value: 正規化値（0.0〜1.0）
        """
        event = OpEvent(ts=time.time(), op=op, deck=deck, value=value)
        with self._lock:
            self._events.append(event)

    def log_eq_high(self, deck: str, value: float) -> None:
        self.log(OP_EQ_HIGH, deck, value)

    def log_eq_mid(self, deck: str, value: float) -> None:
        self.log(OP_EQ_MID, deck, value)

    def log_eq_low(self, deck: str, value: float) -> None:
        self.log(OP_EQ_LOW, deck, value)

    def log_filter(self, deck: str, value: float) -> None:
        self.log(OP_FILTER, deck, value)

    def log_crossfader(self, value: float) -> None:
        self.log(OP_CROSSFADE, "master", value)

    def log_tempo(self, deck: str, value: float) -> None:
        self.log(OP_TEMPO, deck, value)

    def log_play(self, deck: str) -> None:
        self.log(OP_PLAY, deck, 1.0)

    def log_loop(self, deck: str, active: bool) -> None:
        self.log(OP_LOOP, deck, 1.0 if active else 0.0)

    def log_hotcue(self, deck: str, slot: int) -> None:
        self.log(OP_HOTCUE, deck, float(slot))

    # ─────────────────────────────────────────
    # 分析 API
    # ─────────────────────────────────────────

    def get_profile(self) -> StyleProfile:
        """
        現在のイベントリストからスタイルプロファイルを生成する。

        Returns:
            StyleProfile
        """
        with self._lock:
            events = list(self._events)

        if not events:
            return StyleProfile(dominant_style="未操作")

        session_duration = time.time() - self._session_start
        duration_min = max(session_duration / 60.0, 0.01)

        # ── EQ 集計 ──────────────────────────
        eq_ops = [e for e in events if e.op in (OP_EQ_HIGH, OP_EQ_MID, OP_EQ_LOW)]
        eq_kill_count = sum(1 for e in eq_ops if e.value < 0.05)  # full cut
        eq_kill_ratio = eq_kill_count / max(len(eq_ops), 1)

        eq_low_ops = [e for e in events if e.op == OP_EQ_LOW]
        eq_low_activity = len(eq_low_ops) / duration_min

        # ── Filter 集計 ──────────────────────
        filter_ops = [e for e in events if e.op == OP_FILTER]
        filter_activity = len(filter_ops) / duration_min
        filter_sweep_count = self._count_sweeps(filter_ops)

        # ── クロスフェーダー 集計 ────────────
        cf_ops = [e for e in events if e.op == OP_CROSSFADE]
        crossfader_moves = self._count_significant_moves(cf_ops, threshold=0.1)

        # ── テンポ 集計 ──────────────────────
        tempo_ops = [e for e in events if e.op == OP_TEMPO]
        tempo_adj_count = len(tempo_ops)

        # ── スタイル判定 ─────────────────────
        dominant_style = self._determine_style(
            eq_kill_ratio=eq_kill_ratio,
            filter_activity=filter_activity,
            filter_sweep_count=filter_sweep_count,
            crossfader_moves=crossfader_moves,
            eq_low_activity=eq_low_activity,
        )

        return StyleProfile(
            session_duration=session_duration,
            total_ops=len(events),
            eq_kill_ratio=eq_kill_ratio,
            filter_sweep_count=filter_sweep_count,
            crossfader_moves=crossfader_moves,
            tempo_adj_count=tempo_adj_count,
            dominant_style=dominant_style,
            eq_low_activity=eq_low_activity,
            filter_activity=filter_activity,
        )

    # ─────────────────────────────────────────
    # 永続化 API
    # ─────────────────────────────────────────

    def save_session(self) -> Optional[Path]:
        """
        セッションのイベントログと分析結果を JSON に保存する。

        Returns:
            保存先パス（失敗時 None）
        """
        with self._lock:
            events_snapshot = list(self._events)

        if not events_snapshot:
            logger.info("StyleLogger: イベントなし、保存スキップ")
            return None

        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self._log_dir / f"style_{ts}.json"

            profile = self.get_profile()
            data = {
                "session_start": datetime.fromtimestamp(self._session_start).isoformat(),
                "session_end":   datetime.now().isoformat(),
                "profile":       profile.to_dict(),
                "events":        [asdict(e) for e in events_snapshot],
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"StyleLogger: セッション保存 → {path} ({len(events_snapshot)} ops)")
            return path
        except Exception as e:
            logger.error(f"StyleLogger: 保存失敗: {e}")
            return None

    @classmethod
    def load_session(cls, path: Path) -> Optional[dict]:
        """
        保存済みセッション JSON を読み込んで dict で返す。

        Args:
            path: JSON ファイルパス

        Returns:
            セッションデータ dict（失敗時 None）
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            logger.info(f"StyleLogger: セッション読込 ← {path}")
            return data
        except Exception as e:
            logger.error(f"StyleLogger: 読込失敗 ({path}): {e}")
            return None

    @classmethod
    def list_sessions(cls, log_dir: Optional[Path] = None) -> list[Path]:
        """
        保存済みセッション JSON の一覧を新しい順で返す。

        Args:
            log_dir: ログディレクトリ（省略時はデフォルト）

        Returns:
            Path リスト
        """
        d = log_dir or DEFAULT_LOG_DIR
        if not d.exists():
            return []
        return sorted(d.glob("style_*.json"), reverse=True)

    def reset(self) -> None:
        """イベントリストをクリアしてセッションをリセットする。"""
        with self._lock:
            self._events.clear()
            self._session_start = time.time()
        logger.info("StyleLogger: セッションリセット")

    # ─────────────────────────────────────────
    # 内部ユーティリティ
    # ─────────────────────────────────────────

    @staticmethod
    def _count_sweeps(filter_ops: list[OpEvent], sweep_threshold: float = 0.3) -> int:
        """
        LPF↔HPF の往復（スイープ）回数をカウントする。

        0.5 をまたいで逆方向に sweep_threshold 以上動いた場合を 1 スイープとして計上。
        """
        if len(filter_ops) < 2:
            return 0

        sweeps = 0
        direction = 0  # +1=HPF方向, -1=LPF方向, 0=未確定
        prev_val = filter_ops[0].value

        for e in filter_ops[1:]:
            delta = e.value - prev_val
            if abs(delta) < 0.05:
                prev_val = e.value
                continue
            new_dir = 1 if delta > 0 else -1
            if direction != 0 and new_dir != direction and abs(e.value - 0.5) > sweep_threshold:
                sweeps += 1
            direction = new_dir
            prev_val = e.value

        return sweeps

    @staticmethod
    def _count_significant_moves(ops: list[OpEvent], threshold: float = 0.1) -> int:
        """
        threshold 以上の値変化を「移動」としてカウントする。
        """
        if len(ops) < 2:
            return 0
        moves = 0
        for i in range(1, len(ops)):
            if abs(ops[i].value - ops[i - 1].value) >= threshold:
                moves += 1
        return moves

    @staticmethod
    def _determine_style(
        eq_kill_ratio: float,
        filter_activity: float,
        filter_sweep_count: int,
        crossfader_moves: int,
        eq_low_activity: float,
    ) -> str:
        """
        集計値から支配的なDJスタイルを推定する。

        優先順位:
        1. EQ Kill 多用（≥30%） → "EQ Kill型"
        2. フィルタースイープ多用（≥5回）→ "フィルタースイープ型"
        3. クロスフェーダー多用（≥10回）→ "カットイン型"
        4. Low EQ 操作頻度高（≥5 ops/min）→ "Bass管理型"
        5. フィルター操作頻度高（≥3 ops/min）→ "フィルター型"
        6. その他 → "Minimal / ロングミックス型"
        """
        if eq_kill_ratio >= 0.30:
            return "EQ Kill型"
        if filter_sweep_count >= 5:
            return "フィルタースイープ型"
        if crossfader_moves >= 10:
            return "カットイン型"
        if eq_low_activity >= 5.0:
            return "Bass管理型"
        if filter_activity >= 3.0:
            return "フィルター型"
        return "Minimal / ロングミックス型"
