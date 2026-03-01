"""
AI Commentator & Gemini Orchestrator (Phase R8.3)
==================================================

GeminiOrchestrator
  mix_advisor.py（Phase R4）と ai_commentator（Phase R8.3）の
  Gemini API 呼び出しを一元管理するレート制限ゲートキーパー。

  責務:
    - 1つの GenerativeModel インスタンスを共有
    - 用途別の最小呼び出し間隔を管理
      * mix_advice  : 4秒（= 15req/min 無料枠）
      * commentary  : 60秒（イベント駆動、連打防止）
    - 日次クォータ管理（Gemini 無料枠 1,500req/day）
    - フォールバック文字列の生成

AiCommentator
  ScoreEvent を受け取り、タイミングを判断して
  GeminiOrchestrator 経由で講評テキストを生成する。

講評タイミング:
    1. トランジション完了（ScoreEventType.KEY_RESULT 検出）
    2. Hype 急変（ScoreEventType.HYPE_SPIKE）
    3. Combo 達成（ScoreEventType.COMBO_START）
    4. ユーザー要求（request_comment() を直接呼ぶ）

使い方（mixer_core から）:
    orchestrator = GeminiOrchestrator(api_key=settings["gemini_api_key"])
    # MixAdvisor へ渡す
    mix_advisor.set_orchestrator(orchestrator)
    # AiCommentator へ渡す
    commentator = AiCommentator(orchestrator, venue)
    ...
    comment = commentator.process_events(events, score_state)
    if comment:
        commentary_updated.emit(comment)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from core.gamification.score_engine import (
    ScoreEvent, ScoreEventType, ScoreState,
)
from core.gamification.game_session import VenueRules

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────

# 用途別の最小呼び出し間隔（秒）
INTERVAL_MIX_ADVICE  = 4.0     # MixAdvisor 用（15req/min 相当）
INTERVAL_COMMENTARY  = 60.0    # AI 講評用（1req/min）

# 日次クォータ
DAILY_QUOTA          = 1_500   # Gemini 無料枠
QUOTA_FILE           = "logs/gemini_quota.json"

# Hype 急変しきい値（ScoreEngine 側と合わせる）
HYPE_SPIKE_THRESHOLD = 20.0

# モデル名
GEMINI_MODEL = "gemini-2.0-flash"

# フォールバック講評（都市・スタイル別）
_FALLBACK_COMMENTS: dict[str, list[str]] = {
    "Strict": [
        "BPM精度を上げろ。それだけだ。",
        "ベースが衝突している。プロはそんなミスはしない。",
        "もっと長くミックスしろ。まだ切り替えが早い。",
    ],
    "Encouraging": [
        "いい感じ！EQの使い方が丁寧ですね。",
        "キーの選択が光っていますよ。",
        "エネルギーの流れが自然でいいですね。",
    ],
    "Party": [
        "最高だ！その調子でもっと盛り上げてくれ！",
        "ドロップが決まった！フロアが沸いてるぞ！",
        "このグルーヴ最高！止まるな！",
    ],
}


# ─────────────────────────────────────────────
# GeminiOrchestrator
# ─────────────────────────────────────────────

class GeminiOrchestrator:
    """
    Gemini API 呼び出しを一元管理するゲートキーパー（Phase R8.3）。

    MixAdvisor と AiCommentator が同じインスタンスを共有し、
    用途別レート制限と日次クォータを管理する。

    使い方:
        orch = GeminiOrchestrator(api_key="YOUR_KEY")
        # MixAdvisor へ
        mix_advisor.set_orchestrator(orch)
        # AiCommentator へ
        commentator = AiCommentator(orch, venue)
    """

    def __init__(self, api_key: Optional[str] = None):
        self._api_key   = api_key
        self._model     = None
        self._last_call: dict[str, float] = {
            "mix_advice":  0.0,
            "commentary":  0.0,
        }
        self._daily_count = 0
        self._quota_date  = ""

        if api_key:
            self._init_model(api_key)

    # ─────────────────────────────────────────
    # 初期化 / 設定
    # ─────────────────────────────────────────

    def _init_model(self, api_key: str) -> bool:
        try:
            try:
                import google.genai as _genai  # 新 SDK
                self._client = _genai.Client(api_key=api_key)
                self._use_new_sdk = True
                self._model = GEMINI_MODEL  # 文字列で保持
            except ImportError:
                import google.generativeai as _genai  # 旧 SDK フォールバック
                _genai.configure(api_key=api_key)
                self._client = None
                self._use_new_sdk = False
                self._model = _genai.GenerativeModel(GEMINI_MODEL)
            logger.info(f"GeminiOrchestrator: model '{GEMINI_MODEL}' initialized "
                        f"({'google.genai' if self._use_new_sdk else 'google.generativeai'}).")
            return True
        except Exception as e:
            logger.warning(f"GeminiOrchestrator: init failed — {e}")
            self._model = None
            self._client = None
            self._use_new_sdk = False
            return False

    def update_api_key(self, api_key: str) -> bool:
        self._api_key = api_key
        return self._init_model(api_key)

    @property
    def is_available(self) -> bool:
        return self._model is not None

    # ─────────────────────────────────────────
    # レート制限チェック
    # ─────────────────────────────────────────

    def can_call(self, purpose: str) -> bool:
        """
        指定用途の呼び出しが可能か判定。

        Args:
            purpose: "mix_advice" or "commentary"
        """
        if not self._model:
            return False
        if not self._check_quota():
            return False
        interval = INTERVAL_MIX_ADVICE if purpose == "mix_advice" else INTERVAL_COMMENTARY
        return (time.time() - self._last_call.get(purpose, 0.0)) >= interval

    def _check_quota(self) -> bool:
        """日次クォータが残っているか確認。"""
        import datetime
        today = datetime.date.today().isoformat()
        if today != self._quota_date:
            self._quota_date  = today
            self._daily_count = 0
        return self._daily_count < DAILY_QUOTA

    # ─────────────────────────────────────────
    # 呼び出しエントリポイント
    # ─────────────────────────────────────────

    def generate(self, purpose: str, prompt: str) -> Optional[str]:
        """
        Gemini にテキストを送信して応答を返す。

        Args:
            purpose: "mix_advice" or "commentary"（レート制限の種別）
            prompt:  送信するプロンプト文字列

        Returns:
            応答テキスト。失敗時は None。
        """
        if not self.can_call(purpose):
            return None
        try:
            self._last_call[purpose] = time.time()
            self._daily_count += 1
            if self._use_new_sdk:
                response = self._client.models.generate_content(
                    model=self._model, contents=prompt
                )
            else:
                response = self._model.generate_content(prompt)
            text = response.text.strip()
            logger.debug(f"GeminiOrchestrator [{purpose}]: {text[:80]}")
            return text
        except Exception as e:
            logger.warning(f"GeminiOrchestrator [{purpose}] error: {e}")
            return None

    def remaining_quota(self) -> int:
        """残り日次クォータ数。"""
        self._check_quota()
        return max(0, DAILY_QUOTA - self._daily_count)


# ─────────────────────────────────────────────
# AiCommentator
# ─────────────────────────────────────────────

@dataclass
class Commentary:
    """AI 講評結果。"""
    text:       str
    source:     str      # "gemini" or "fallback"
    trigger:    str      # 発生トリガー（"transition" / "hype_spike" / "combo" / "manual"）
    timestamp:  float

    def to_dict(self) -> dict:
        return {
            "text":      self.text,
            "source":    self.source,
            "trigger":   self.trigger,
            "timestamp": self.timestamp,
        }


class AiCommentator:
    """
    AI 講評システム（Phase R8.3）。

    ScoreEvent リストを受け取り、タイミングを判断して
    GeminiOrchestrator 経由で講評テキストを非同期生成する。

    ※ Gemini 呼び出しはブロッキング。mixer_core から QThread 経由で呼ぶこと。

    使い方:
        commentator = AiCommentator(orchestrator, venue)
        comment = commentator.process_events(events, state)
        if comment:
            # PyQt シグナルで GUI へ送る
            commentary_updated.emit(comment.to_dict())
    """

    def __init__(self, orchestrator: GeminiOrchestrator, venue: VenueRules):
        self._orch   = orchestrator
        self._venue  = venue
        self._last_comment_time = 0.0

    def set_venue(self, venue: VenueRules) -> None:
        """会場切り替え時に更新。"""
        self._venue = venue

    # ─────────────────────────────────────────
    # イベント処理（100ms ティックごとに呼ぶ）
    # ─────────────────────────────────────────

    def process_events(
        self,
        events: list[ScoreEvent],
        state: ScoreState,
    ) -> Optional[Commentary]:
        """
        ScoreEvent リストを検査し、講評すべきタイミングなら Commentary を返す。

        Args:
            events: score_engine.tick() が返した ScoreEvent リスト
            state:  現在の ScoreState

        Returns:
            Commentary（講評あり）or None（タイミングでない / クールダウン中）
        """
        trigger = self._detect_trigger(events)
        if trigger is None:
            return None

        return self._generate(trigger, state)

    def request_comment(self, state: ScoreState) -> Optional[Commentary]:
        """ユーザー要求（「評価して」ボタン）による即時講評。"""
        return self._generate("manual", state)

    # ─────────────────────────────────────────
    # 内部ロジック
    # ─────────────────────────────────────────

    def _detect_trigger(self, events: list[ScoreEvent]) -> Optional[str]:
        """
        講評トリガーを検出する。
        優先度: transition > hype_spike > combo
        クールダウン（INTERVAL_COMMENTARY）が明けていない場合は None。
        """
        if (time.time() - self._last_comment_time) < INTERVAL_COMMENTARY:
            return None

        for ev in events:
            if ev.event_type == ScoreEventType.KEY_RESULT:
                return "transition"
            if ev.event_type == ScoreEventType.HYPE_SPIKE:
                return "hype_spike"
            if ev.event_type == ScoreEventType.COMBO_START:
                return "combo"

        return None

    def _generate(self, trigger: str, state: ScoreState) -> Optional[Commentary]:
        """Gemini に講評を依頼し Commentary を返す。失敗時はフォールバック。"""
        self._last_comment_time = time.time()
        prompt = self._build_prompt(trigger, state)

        text = self._orch.generate("commentary", prompt)
        if text:
            return Commentary(
                text=text,
                source="gemini",
                trigger=trigger,
                timestamp=time.time(),
            )

        # フォールバック
        fallback = self._fallback_text()
        return Commentary(
            text=fallback,
            source="fallback",
            trigger=trigger,
            timestamp=time.time(),
        )

    def _build_prompt(self, trigger: str, state: ScoreState) -> str:
        venue = self._venue
        trigger_desc = {
            "transition": "トランジション（曲の切り替え）が行われた",
            "hype_spike": f"Hype が急変した（現在 {state.hype:.0f}/100）",
            "combo":      f"Combo が {state.combo_sec:.1f}秒 継続中",
            "manual":     "DJが評価を求めている",
        }.get(trigger, "不明なイベント")

        return f"""あなたは{venue.location}の{venue.name}にいる{venue.audience_persona}です。
DJのプレイを{venue.critique_style}スタイルで評価してください。

現在の状況:
- Hype Level: {state.hype:.0f}/100
- Technical Score: {state.tech_score:.0f}
- Vibe Score: {state.vibe_score:.0f}
- ランク: {state.rank}
- Combo: {state.combo_sec:.1f}秒
- トリガー: {trigger_desc}

制約:
- 1〜2文で簡潔に
- 具体的なフィードバックを含める
- 日本語で回答
- {venue.critique_style}スタイルを忠実に守る

講評:"""

    def _fallback_text(self) -> str:
        import random
        style = self._venue.critique_style
        pool = _FALLBACK_COMMENTS.get(style, _FALLBACK_COMMENTS["Encouraging"])
        return random.choice(pool)
