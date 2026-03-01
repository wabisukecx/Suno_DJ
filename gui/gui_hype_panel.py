"""
GUI Hype Panel (Phase R8.1 / R8.3)
====================================

HypeMeter + スコア表示 + Combo + AI 講評テキストを表示するパネル。

レイアウト:
    ┌─────────────────────────────────────────────────────┐
    │  🎯 WORLD TOUR  [Berghain — ベルリン]    [D] RANK  │
    ├───────────────────────┬─────────────────────────────┤
    │  HYPE      ████▒▒▒▒  │  Tech  ████  3,200          │
    │  [========70=====]    │  Vibe  ████  1,800          │
    │  COMBO x1.5  (4.2s)  │  TOTAL         5,000        │
    ├───────────────────────┴─────────────────────────────┤
    │  💬  "BPM が走ってるぞ！もっと締めろ。"            │
    └─────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import time
from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QPainter, QPen, QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QFrame, QSizePolicy,
)

from core.gamification.score_engine import ScoreState, BeatmatchRating
from core.gamification.game_session import VenueRules
from gui.gui_styles import COLORS


# ─────────────────────────────────────────────
# HypeMeterBar — カスタム描画
# ─────────────────────────────────────────────

class HypeMeterBar(QWidget):
    """
    Hype 値（0〜100）をバーグラフで表示するカスタムウィジェット。

    - 0〜30: 赤（低調）
    - 30〜60: オレンジ（普通）
    - 60〜80: 黄緑（盛り上がり）
    - 80〜100: シアン（最高潮）
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._hype = 50.0
        self.setMinimumHeight(28)
        self.setMinimumWidth(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_hype(self, value: float) -> None:
        self._hype = max(0.0, min(100.0, value))
        self.update()

    def paintEvent(self, event):  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        fill_w = int(w * self._hype / 100.0)

        # 背景
        painter.fillRect(0, 0, w, h, QColor("#1e1e1e"))

        # バー色
        hype = self._hype
        if hype >= 80:
            color = QColor("#00e5ff")   # シアン
        elif hype >= 60:
            color = QColor("#76ff03")   # 黄緑
        elif hype >= 30:
            color = QColor("#ff9800")   # オレンジ
        else:
            color = QColor("#f44336")   # 赤

        if fill_w > 0:
            painter.fillRect(0, 0, fill_w, h, color)

        # テキスト
        painter.setPen(QColor("#ffffff"))
        font = QFont("Monospace", 10, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter,
                         f"HYPE  {self._hype:.0f} / 100")

        # ボーダー
        painter.setPen(QPen(QColor("#333333"), 1))
        painter.drawRect(0, 0, w - 1, h - 1)


# ─────────────────────────────────────────────
# HypePanel
# ─────────────────────────────────────────────

class HypePanel(QWidget):
    """
    Hype Meter + スコア + Combo + AI 講評を統合表示するパネル（Phase R8.1/R8.3）。

    接続方法（mixer_core の シグナル）:
        mixer.game_score_updated.connect(hype_panel.on_score_updated)
        mixer.commentary_updated.connect(hype_panel.on_commentary)

    ユーザー操作シグナル:
        request_comment  — 「評価して」ボタン押下時（mixer_core が受け取る）
    """

    from PyQt6.QtCore import pyqtSignal
    request_comment = pyqtSignal()     # 「評価して」ボタン → mixer_core へ
    venue_changed   = pyqtSignal(str)  # 都市選択変更 → mixer_core へ

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_venue: Optional[VenueRules] = None
        self._state: Optional[ScoreState] = None
        self._session_active = False

        self._build_ui()

    # ─────────────────────────────────────────
    # UI 構築
    # ─────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── ヘッダー行（会場名 + ランク） ──────────────────
        header = QHBoxLayout()

        self._lbl_title = QLabel("🎯  WORLD TOUR")
        self._lbl_title.setStyleSheet(
            f"color: {COLORS['accent']}; font-weight: bold; font-size: 12px;"
        )
        header.addWidget(self._lbl_title)

        self._lbl_venue = QLabel("—")
        self._lbl_venue.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 11px;"
        )
        header.addWidget(self._lbl_venue, stretch=1)

        self._lbl_rank = QLabel("—")
        self._lbl_rank.setStyleSheet(
            "color: #ffffff; font-size: 20px; font-weight: bold; "
            "background: #333; border-radius: 4px; padding: 2px 8px;"
        )
        self._lbl_rank.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(self._lbl_rank)

        root.addLayout(header)

        # ── セパレータ ──────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        root.addWidget(sep)

        # ── 中段（Hype + スコア） ──────────────────────────
        mid = QHBoxLayout()
        mid.setSpacing(8)

        # 左: HypeMeter + Combo
        left = QVBoxLayout()
        left.setSpacing(4)

        self._hype_bar = HypeMeterBar()
        left.addWidget(self._hype_bar)

        self._lbl_combo = QLabel("COMBO  x1.0   (0.0s)")
        self._lbl_combo.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 10px; font-family: Monospace;"
        )
        left.addWidget(self._lbl_combo)

        self._lbl_beatmatch = QLabel("BPM  —")
        self._lbl_beatmatch.setStyleSheet(
            "color: #888; font-size: 10px; font-family: Monospace;"
        )
        left.addWidget(self._lbl_beatmatch)

        mid.addLayout(left, stretch=2)

        # 右: スコア内訳
        right = QVBoxLayout()
        right.setSpacing(2)

        for label_text, attr in [
            ("TECH", "_lbl_tech"),
            ("VIBE", "_lbl_vibe"),
            ("TOTAL", "_lbl_total"),
        ]:
            row = QHBoxLayout()
            lbl_key = QLabel(label_text)
            lbl_key.setStyleSheet(
                f"color: {COLORS['text_dim']}; font-size: 10px; "
                "font-family: Monospace; min-width: 38px;"
            )
            lbl_val = QLabel("0")
            lbl_val.setStyleSheet(
                "color: #ffffff; font-size: 11px; font-family: Monospace; "
                "font-weight: bold;"
            )
            lbl_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            setattr(self, attr, lbl_val)
            row.addWidget(lbl_key)
            row.addWidget(lbl_val, stretch=1)
            right.addLayout(row)

        mid.addLayout(right, stretch=1)
        root.addLayout(mid)

        # ── AI 講評エリア ──────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("color: #333;")
        root.addWidget(sep2)

        commentary_row = QHBoxLayout()

        self._lbl_comment = QLabel("💬  — ")
        self._lbl_comment.setStyleSheet(
            f"color: {COLORS['text']}; font-size: 11px; padding: 2px;"
        )
        self._lbl_comment.setWordWrap(True)
        commentary_row.addWidget(self._lbl_comment, stretch=1)

        btn_eval = QPushButton("評価して")
        btn_eval.setFixedWidth(72)
        btn_eval.setStyleSheet(
            f"background: {COLORS['surface_hover']}; color: {COLORS['accent']}; "
            "border: 1px solid #555; border-radius: 4px; font-size: 10px; "
            "padding: 3px 6px;"
        )
        btn_eval.clicked.connect(self.request_comment)
        commentary_row.addWidget(btn_eval)

        root.addLayout(commentary_row)

        # ── パネル自体のスタイル ────────────────────────────
        self.setStyleSheet(
            f"background: {COLORS['surface']}; border: 1px solid #333; "
            "border-radius: 6px;"
        )

        # 非アクティブ状態
        self._set_inactive_display()

    # ─────────────────────────────────────────
    # スロット
    # ─────────────────────────────────────────

    @pyqtSlot(dict)
    def on_score_updated(self, data: dict) -> None:
        """
        mixer_core.game_score_updated シグナルを受け取る。

        data 形式:
            {
              "active": bool,
              "hype": float,
              "total_score": float,
              "tech_score": float,
              "vibe_score": float,
              "combo_mult": float,
              "combo_sec": float,
              "beatmatch": str,   # BeatmatchRating.value
              "rank": str,
              "venue_name": str,
              "venue_location": str,
              "venue_flag": str,
            }
        """
        if not data.get("active", False):
            self._set_inactive_display()
            return

        self._session_active = True

        hype        = data.get("hype", 50.0)
        total       = data.get("total_score", 0.0)
        tech        = data.get("tech_score", 0.0)
        vibe        = data.get("vibe_score", 0.0)
        combo_mult  = data.get("combo_mult", 1.0)
        combo_sec   = data.get("combo_sec", 0.0)
        beatmatch   = data.get("beatmatch", "skip")
        rank        = data.get("rank", "—")
        venue_name  = data.get("venue_name", "")
        venue_loc   = data.get("venue_location", "")
        venue_flag  = data.get("venue_flag", "")

        # Hype bar
        self._hype_bar.set_hype(hype)

        # スコア
        self._lbl_tech.setText(f"{tech:,.0f}")
        self._lbl_vibe.setText(f"{vibe:,.0f}")
        self._lbl_total.setText(f"{total:,.0f}")

        # Combo
        self._lbl_combo.setText(
            f"COMBO  x{combo_mult:.1f}   ({combo_sec:.1f}s)"
        )
        combo_color = "#00e5ff" if combo_mult >= 1.5 else COLORS["text_dim"]
        self._lbl_combo.setStyleSheet(
            f"color: {combo_color}; font-size: 10px; font-family: Monospace;"
        )

        # Beatmatch ラベル
        bm_text, bm_color = self._beatmatch_display(beatmatch)
        self._lbl_beatmatch.setText(f"BPM  {bm_text}")
        self._lbl_beatmatch.setStyleSheet(
            f"color: {bm_color}; font-size: 10px; font-family: Monospace;"
        )

        # ランク
        rank_color = self._rank_color(rank)
        self._lbl_rank.setText(rank)
        self._lbl_rank.setStyleSheet(
            f"color: #000; background: {rank_color}; font-size: 20px; "
            "font-weight: bold; border-radius: 4px; padding: 2px 8px;"
        )

        # 会場名
        if venue_name:
            self._lbl_venue.setText(
                f"{venue_flag}  {venue_name}  —  {venue_loc}"
            )

    @pyqtSlot(dict)
    def on_commentary(self, data: dict) -> None:
        """
        mixer_core.commentary_updated シグナルを受け取る。

        data 形式: Commentary.to_dict()
        """
        text   = data.get("text", "")
        source = data.get("source", "fallback")
        icon   = "💬" if source == "gemini" else "🤖"
        self._lbl_comment.setText(f"{icon}  {text}")

    def set_venue(self, venue: VenueRules) -> None:
        """会場が変わったときに呼ぶ（gui_venue_selector から）。"""
        self._current_venue = venue
        self._lbl_venue.setText(
            f"{venue.flag}  {venue.name}  —  {venue.location}"
        )
        self.venue_changed.emit(venue.id)

    # ─────────────────────────────────────────
    # ヘルパ
    # ─────────────────────────────────────────

    def _set_inactive_display(self) -> None:
        self._session_active = False
        self._hype_bar.set_hype(50.0)
        self._lbl_tech.setText("0")
        self._lbl_vibe.setText("0")
        self._lbl_total.setText("0")
        self._lbl_combo.setText("COMBO  x1.0   (0.0s)")
        self._lbl_beatmatch.setText("BPM  —")
        self._lbl_rank.setText("—")
        self._lbl_rank.setStyleSheet(
            "color: #fff; background: #333; font-size: 20px; "
            "font-weight: bold; border-radius: 4px; padding: 2px 8px;"
        )
        self._lbl_comment.setText("💬  —")

    @staticmethod
    def _beatmatch_display(beatmatch: str) -> tuple[str, str]:
        return {
            "perfect": ("PERFECT ●", "#00e5ff"),
            "good":    ("GOOD    ●", "#76ff03"),
            "ok":      ("OK      ○", "#ff9800"),
            "bad":     ("BAD     ✗", "#f44336"),
            "skip":    ("—",         "#888888"),
        }.get(beatmatch, ("—", "#888888"))

    @staticmethod
    def _rank_color(rank: str) -> str:
        return {
            "S": "#ffd700",   # ゴールド
            "A": "#00e5ff",   # シアン
            "B": "#76ff03",   # 黄緑
            "C": "#ff9800",   # オレンジ
            "D": "#f44336",   # 赤
        }.get(rank, "#555555")
