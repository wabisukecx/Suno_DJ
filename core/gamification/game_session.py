"""
Game Session & Venue Rules (Phase R8.1 / R8.2 / R8.4)
=======================================================

GameSession  — セッション管理・tick 委譲・ランク判定
VenueRules   — 都市別ルール定義（venues.json から読み込み）
RankResult   — セッション終了時のランク結果

使い方（mixer_core から）:
    session = GameSession.from_venue("berlin", venues_json_path)
    session.start()
    ...
    events = session.tick(snapshot)   # 100ms ごと
    state  = session.get_state()      # ScoreState を取得
    ...
    result = session.finish()         # RankResult を取得
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from core.gamification.score_engine import (
    ScoreEngine, ScoreSnapshot, ScoreEvent, ScoreState,
    HYPE_INIT,
)

logger = logging.getLogger(__name__)

# デフォルト venues.json パス
DEFAULT_VENUES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "venues.json"
)


# ─────────────────────────────────────────────
# VenueRules
# ─────────────────────────────────────────────

@dataclass
class VenueRules:
    """
    都市別ルール定義。venues.json の1エントリに対応。

    Attributes:
        id:                  識別子（例: "berlin"）
        name:                会場名（例: "Berghain"）
        location:            都市名（例: "ベルリン"）
        flag:                国旗絵文字
        genre_tags:          期待ジャンル
        bpm_range:           (min, max) BPM
        technical_weight:    Technical Score の重み（0.0〜1.0）
        vibe_weight:         Vibe Score の重み
        long_mix_bonus:      32小節以上のミックスで加点するか
        vocal_preference:    -1.0（嫌い）〜+1.0（好き）
        energy_jump_tolerance: 許容エネルギー変動
        audience_persona:    Gemini ペルソナ文字列
        critique_style:      "Strict" / "Encouraging" / "Party"
        suno_mood_prompt:    Suno 向け Mood Prompt
        beatmatch_tolerance_bpm: Beatmatch Perfect 判定の BPM 許容幅
        rank_thresholds:     ランク S/A/B/C の最低スコア
    """
    id:                   str
    name:                 str
    location:             str
    flag:                 str = "🌐"
    genre_tags:           list[str] = field(default_factory=list)
    bpm_range:            tuple[int, int] = (120, 130)
    technical_weight:     float = 0.6
    vibe_weight:          float = 0.4
    long_mix_bonus:       bool  = False
    vocal_preference:     float = 0.0
    energy_jump_tolerance:float = 2.0
    audience_persona:     str   = "音楽ファン"
    critique_style:       str   = "Encouraging"
    suno_mood_prompt:     str   = ""
    beatmatch_tolerance_bpm: float = 0.5
    rank_thresholds:      dict  = field(default_factory=lambda: {
                              "S": 9000, "A": 6500, "B": 4000, "C": 2000
                          })

    @classmethod
    def from_dict(cls, d: dict) -> "VenueRules":
        bpm = d.get("bpm_range", [120, 130])
        return cls(
            id=d.get("id", "unknown"),
            name=d.get("name", "Unknown"),
            location=d.get("location", ""),
            flag=d.get("flag", "🌐"),
            genre_tags=d.get("genre_tags", []),
            bpm_range=(bpm[0], bpm[1]),
            technical_weight=d.get("technical_weight", 0.6),
            vibe_weight=d.get("vibe_weight", 0.4),
            long_mix_bonus=d.get("long_mix_bonus", False),
            vocal_preference=d.get("vocal_preference", 0.0),
            energy_jump_tolerance=d.get("energy_jump_tolerance", 2.0),
            audience_persona=d.get("audience_persona", "音楽ファン"),
            critique_style=d.get("critique_style", "Encouraging"),
            suno_mood_prompt=d.get("suno_mood_prompt", ""),
            beatmatch_tolerance_bpm=d.get("beatmatch_tolerance_bpm", 0.5),
            rank_thresholds=d.get("rank_thresholds",
                                  {"S": 9000, "A": 6500, "B": 4000, "C": 2000}),
        )

    def calc_rank(self, total_score: float) -> str:
        """スコアからランクを算出。"""
        th = self.rank_thresholds
        if total_score >= th.get("S", 9000):
            return "S"
        elif total_score >= th.get("A", 6500):
            return "A"
        elif total_score >= th.get("B", 4000):
            return "B"
        elif total_score >= th.get("C", 2000):
            return "C"
        return "D"


def load_venues(path: str = DEFAULT_VENUES_PATH) -> dict[str, VenueRules]:
    """venues.json を読み込んで {id: VenueRules} を返す。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        result = {}
        for v in data.get("venues", []):
            vr = VenueRules.from_dict(v)
            result[vr.id] = vr
        logger.info(f"Loaded {len(result)} venues from {path}")
        return result
    except Exception as e:
        logger.warning(f"venues.json load failed: {e}. Using default venue.")
        return {"tokyo": VenueRules(id="tokyo", name="Shibuya Club", location="東京")}


# ─────────────────────────────────────────────
# RankResult（セッション終了時）
# ─────────────────────────────────────────────

@dataclass
class RankResult:
    """GameSession.finish() の戻り値。"""
    venue_id:      str
    venue_name:    str
    rank:          str
    total_score:   float
    tech_score:    float
    vibe_score:    float
    duration_sec:  float
    peak_hype:     float
    max_combo_sec: float
    timestamp:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "venue_id":     self.venue_id,
            "venue_name":   self.venue_name,
            "rank":         self.rank,
            "total_score":  round(self.total_score, 1),
            "tech_score":   round(self.tech_score, 1),
            "vibe_score":   round(self.vibe_score, 1),
            "duration_sec": round(self.duration_sec, 1),
            "peak_hype":    round(self.peak_hype, 1),
            "max_combo_sec":round(self.max_combo_sec, 1),
            "timestamp":    self.timestamp,
        }

    def is_s_rank(self) -> bool:
        return self.rank == "S"


# ─────────────────────────────────────────────
# GameSession
# ─────────────────────────────────────────────

class GameSession:
    """
    ゲームセッション管理（Phase R8.1 / R8.2 / R8.4）。

    ScoreEngine の tick を委譲し、VenueRules に基づいたランク判定を行う。
    Mixer core から 100ms ごとに tick() を呼ぶ。

    使い方:
        session = GameSession.from_venue_id("berlin")
        session.start()
        events = session.tick(snapshot)
        state  = session.get_state()
        result = session.finish()
    """

    # 全会場キャッシュ（プロセス内で共有）
    _venues_cache: dict[str, VenueRules] = {}

    def __init__(self, venue: VenueRules):
        self._venue   = venue
        self._engine  = ScoreEngine(venue.technical_weight, venue.vibe_weight)
        self._active  = False
        self._start_t = 0.0
        self._peak_hype    = HYPE_INIT
        self._max_combo_sec= 0.0

    # ─────────────────────────────────────────
    # ファクトリ
    # ─────────────────────────────────────────

    @classmethod
    def ensure_venues_loaded(cls, path: str = DEFAULT_VENUES_PATH) -> None:
        if not cls._venues_cache:
            cls._venues_cache = load_venues(path)

    @classmethod
    def available_venues(cls, path: str = DEFAULT_VENUES_PATH) -> list[VenueRules]:
        cls.ensure_venues_loaded(path)
        return list(cls._venues_cache.values())

    @classmethod
    def from_venue_id(cls, venue_id: str,
                      path: str = DEFAULT_VENUES_PATH) -> "GameSession":
        cls.ensure_venues_loaded(path)
        venue = cls._venues_cache.get(venue_id)
        if venue is None:
            logger.warning(f"Venue '{venue_id}' not found, using tokyo.")
            venue = cls._venues_cache.get("tokyo") or VenueRules(
                id="tokyo", name="Shibuya Club", location="東京"
            )
        return cls(venue)

    # ─────────────────────────────────────────
    # ライフサイクル
    # ─────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def venue(self) -> VenueRules:
        return self._venue

    def start(self) -> None:
        """セッション開始。"""
        self._engine.reset()
        self._active       = True
        self._start_t      = time.time()
        self._peak_hype    = HYPE_INIT
        self._max_combo_sec= 0.0
        logger.info(f"GameSession started: {self._venue.name} ({self._venue.location})")

    def finish(self) -> RankResult:
        """セッション終了。RankResult を返す。"""
        self._active = False
        state = self._engine.get_state()
        duration = time.time() - self._start_t
        rank = self._venue.calc_rank(state.total_score)
        state.rank = rank

        result = RankResult(
            venue_id=self._venue.id,
            venue_name=self._venue.name,
            rank=rank,
            total_score=state.total_score,
            tech_score=state.tech_score,
            vibe_score=state.vibe_score,
            duration_sec=duration,
            peak_hype=self._peak_hype,
            max_combo_sec=self._max_combo_sec,
        )
        logger.info(
            f"GameSession finished: {self._venue.name} "
            f"Rank={rank} Score={state.total_score:.0f}"
        )
        return result

    def pause(self) -> None:
        """セッション一時停止（ゲーム判定を止める）。"""
        self._active = False

    def resume(self) -> None:
        """セッション再開。"""
        self._active = True

    # ─────────────────────────────────────────
    # tick（100ms ごと）
    # ─────────────────────────────────────────

    def tick(self, snapshot: ScoreSnapshot) -> list[ScoreEvent]:
        """
        100ms ごとに呼ぶ。

        Args:
            snapshot: 現在状態のスナップショット

        Returns:
            このティックで発生した ScoreEvent リスト
        """
        if not self._active:
            return []

        # 会場 ID をスナップショットに注入
        snapshot.venue_id = self._venue.id

        events = self._engine.tick(snapshot)
        state  = self._engine.get_state()

        # ピーク・コンボ更新
        if state.hype > self._peak_hype:
            self._peak_hype = state.hype
        if state.combo_sec > self._max_combo_sec:
            self._max_combo_sec = state.combo_sec

        # 会場基準でランクを再計算
        state.rank = self._venue.calc_rank(state.total_score)

        return events

    def get_state(self) -> ScoreState:
        """現在の ScoreState を返す。"""
        return self._engine.get_state()

    def get_venue(self) -> VenueRules:
        return self._venue
