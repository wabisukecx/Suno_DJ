"""
Session Result Dialog (Phase R8.4)
====================================

ゲームセッション終了時に表示するランク結果ダイアログ。

表示内容:
  - ランク（S/A/B/C/D）+ 会場名
  - Total / Tech / Vibe スコア
  - Peak Hype / Max Combo
  - セッション時間
  - Sランク時: 特別メッセージ（将来: Gemini推薦文）

使い方（app.py から）:
    dialog = SessionResultDialog(result_dict, parent=window)
    dialog.exec()
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QWidget,
)

from gui.gui_styles import COLORS


# ランク別カラー（HypePanel と統一）
_RANK_COLOR = {
    "S": "#ffd700",
    "A": "#00e5ff",
    "B": "#76ff03",
    "C": "#ff9800",
    "D": "#f44336",
}

# Sランク特別メッセージ（Gemini未接続時のフォールバック）
_S_RANK_MESSAGES = {
    "tokyo":   "渋谷のフロアを完全に掌握した。プロの域に達している。",
    "berlin":  "Berghain のドアマンも認める完璧なセット。これがテクノだ。",
    "ibiza":   "パチャのテラスが最高潮に達した！あなたは伝説になった！",
    "chicago": "Warehouse の魂を受け継いだ。ハウスの神様が微笑んでいる。",
}


class SessionResultDialog(QDialog):
    """
    セッション終了ランク結果ダイアログ（Phase R8.4）。

    Args:
        result: mixer_core.finish_game_session() の戻り値 dict
                または RankResult.__dict__
        parent: 親ウィジェット
    """

    def __init__(self, result: dict, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._result = result
        self.setWindowTitle("セッション結果")
        self.setMinimumWidth(420)
        self.setModal(True)
        self.setStyleSheet(
            f"background: {COLORS['background']}; color: {COLORS['text']};"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        rank       = self._result.get("rank", "—")
        venue_name = self._result.get("venue_name", "")
        venue_id   = self._result.get("venue_id", "tokyo")
        total      = self._result.get("total_score", 0.0)
        tech       = self._result.get("tech_score", 0.0)
        vibe       = self._result.get("vibe_score", 0.0)
        peak_hype  = self._result.get("peak_hype", 0.0)
        max_combo  = self._result.get("max_combo_sec", 0.0)
        duration   = self._result.get("duration_sec", 0.0)

        rank_color = _RANK_COLOR.get(rank, "#888")
        is_s_rank  = (rank == "S")

        # ── ランク大文字 ───────────────────────────────────────
        rank_lbl = QLabel(rank)
        rank_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rank_lbl.setStyleSheet(
            f"color: {rank_color}; font-size: 72px; font-weight: bold; "
            f"font-family: Monospace; padding: 8px;"
        )
        root.addWidget(rank_lbl)

        # 会場名
        venue_lbl = QLabel(f"@ {venue_name}")
        venue_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        venue_lbl.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 13px;"
        )
        root.addWidget(venue_lbl)

        # ── セパレータ ─────────────────────────────────────────
        root.addWidget(self._sep())

        # ── スコア内訳 ─────────────────────────────────────────
        score_widget = QWidget()
        score_layout = QVBoxLayout(score_widget)
        score_layout.setSpacing(4)
        score_layout.setContentsMargins(0, 0, 0, 0)

        rows = [
            ("TOTAL SCORE", f"{total:,.0f}", "#ffffff", True),
            ("Technical",   f"{tech:,.0f}",  COLORS["text_dim"], False),
            ("Vibe",        f"{vibe:,.0f}",  COLORS["text_dim"], False),
        ]
        for label, value, color, bold in rows:
            row = QHBoxLayout()
            lbl_k = QLabel(label)
            lbl_k.setStyleSheet(
                f"color: {color}; font-size: {'13' if bold else '11'}px; "
                f"font-weight: {'bold' if bold else 'normal'}; font-family: Monospace;"
            )
            lbl_v = QLabel(value)
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl_v.setStyleSheet(
                f"color: {color}; font-size: {'14' if bold else '11'}px; "
                f"font-weight: {'bold' if bold else 'normal'}; font-family: Monospace;"
            )
            row.addWidget(lbl_k)
            row.addWidget(lbl_v)
            score_layout.addLayout(row)

        root.addWidget(score_widget)

        root.addWidget(self._sep())

        # ── サブ統計 ───────────────────────────────────────────
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 0, 0, 0)

        mins = int(duration) // 60
        secs = int(duration) % 60
        stats = [
            ("PEAK HYPE",  f"{peak_hype:.0f}"),
            ("MAX COMBO",  f"{max_combo:.1f}s"),
            ("DURATION",   f"{mins}:{secs:02d}"),
        ]
        for label, value in stats:
            col = QVBoxLayout()
            lbl_v = QLabel(value)
            lbl_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_v.setStyleSheet(
                f"color: #ffffff; font-size: 16px; font-weight: bold; "
                "font-family: Monospace;"
            )
            lbl_k = QLabel(label)
            lbl_k.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_k.setStyleSheet(
                f"color: {COLORS['text_dim']}; font-size: 9px; font-family: Monospace;"
            )
            col.addWidget(lbl_v)
            col.addWidget(lbl_k)
            stats_layout.addLayout(col)

        root.addWidget(stats_widget)

        # ── Sランク特別メッセージ ───────────────────────────────
        if is_s_rank:
            root.addWidget(self._sep())
            msg = _S_RANK_MESSAGES.get(venue_id, "伝説のセットを達成した。")
            msg_lbl = QLabel(f"🏆  {msg}")
            msg_lbl.setWordWrap(True)
            msg_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            msg_lbl.setStyleSheet(
                f"color: {rank_color}; font-size: 12px; font-style: italic; "
                "padding: 4px 8px;"
            )
            root.addWidget(msg_lbl)

        # ── 閉じるボタン ───────────────────────────────────────
        root.addWidget(self._sep())

        btn_close = QPushButton("閉じる")
        btn_close.setStyleSheet(
            f"background: {COLORS['surface_hover']}; color: {COLORS['text']}; "
            "border: 1px solid #555; border-radius: 4px; "
            "padding: 8px 24px; font-size: 12px;"
        )
        btn_close.clicked.connect(self.accept)
        btn_close.setDefault(True)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    @staticmethod
    def _sep() -> QFrame:
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        return sep
