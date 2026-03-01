"""
GUI Venue Selector (Phase R8.2)
================================

都市選択ダイアログ。venues.json から動的にカードを生成する。

使い方:
    dialog = VenueSelectorDialog(parent=self)
    dialog.venue_selected.connect(hype_panel.set_venue)
    dialog.exec()
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QFrame,
    QSizePolicy,
)

from core.gamification.game_session import VenueRules, GameSession
from gui.gui_styles import COLORS


class VenueCard(QWidget):
    """1都市分のカード表示ウィジェット。"""

    clicked = pyqtSignal(VenueRules)

    def __init__(self, venue: VenueRules, selected: bool = False,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._venue    = venue
        self._selected = selected
        self._build_ui()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        # 国旗 + 都市名
        title_row = QHBoxLayout()
        lbl_flag = QLabel(self._venue.flag)
        lbl_flag.setStyleSheet("font-size: 18px;")
        title_row.addWidget(lbl_flag)

        lbl_name = QLabel(f"{self._venue.location}  /  {self._venue.name}")
        lbl_name.setStyleSheet(
            "color: #ffffff; font-size: 12px; font-weight: bold;"
        )
        title_row.addWidget(lbl_name)
        title_row.addStretch()

        layout.addLayout(title_row)

        # ジャンル
        lbl_genre = QLabel("  ".join(self._venue.genre_tags))
        lbl_genre.setStyleSheet(
            f"color: {COLORS['text_dim']}; font-size: 10px;"
        )
        layout.addWidget(lbl_genre)

        # BPM 範囲 + 難易度
        bpm_lo, bpm_hi = self._venue.bpm_range
        difficulty = self._difficulty_label()
        info_row = QHBoxLayout()
        lbl_bpm = QLabel(f"BPM {bpm_lo}〜{bpm_hi}")
        lbl_bpm.setStyleSheet("color: #aaa; font-size: 10px;")
        info_row.addWidget(lbl_bpm)
        lbl_diff = QLabel(difficulty)
        lbl_diff.setStyleSheet(
            f"color: {self._difficulty_color()}; font-size: 10px; font-weight: bold;"
        )
        info_row.addWidget(lbl_diff)
        info_row.addStretch()
        layout.addLayout(info_row)

        # 枠スタイル
        border_color = COLORS["accent"] if self._selected else "#444"
        self.setStyleSheet(
            f"background: {COLORS['surface_hover'] if self._selected else COLORS['surface']}; "
            f"border: 2px solid {border_color}; border-radius: 6px;"
        )

    def _difficulty_label(self) -> str:
        tw = self._venue.technical_weight
        if tw >= 0.75:
            return "★★★ HARD"
        elif tw >= 0.55:
            return "★★☆ MEDIUM"
        return "★☆☆ EASY"

    def _difficulty_color(self) -> str:
        tw = self._venue.technical_weight
        if tw >= 0.75:
            return "#f44336"
        elif tw >= 0.55:
            return "#ff9800"
        return "#76ff03"

    def mousePressEvent(self, event):  # noqa: N802
        self.clicked.emit(self._venue)


class VenueSelectorDialog(QDialog):
    """
    都市選択ダイアログ（Phase R8.2）。

    venues.json から動的にカードを生成し、選択された VenueRules を
    venue_selected シグナルで通知する。

    使い方:
        dialog = VenueSelectorDialog(parent=self)
        dialog.venue_selected.connect(on_venue_selected)
        dialog.exec()
    """

    venue_selected = pyqtSignal(VenueRules)

    def __init__(self, current_venue_id: str = "tokyo",
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._current_id   = current_venue_id
        self._selected: Optional[VenueRules] = None

        self.setWindowTitle("World Tour — 会場選択")
        self.setMinimumWidth(480)
        self.setModal(True)
        self.setStyleSheet(
            f"background: {COLORS['background']}; color: {COLORS['text']};"
        )

        self._venues = GameSession.available_venues()
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        # タイトル
        lbl_title = QLabel("🌍  会場を選んでください")
        lbl_title.setStyleSheet(
            f"color: {COLORS['accent']}; font-size: 14px; font-weight: bold;"
        )
        root.addWidget(lbl_title)

        lbl_sub = QLabel("各都市のルールと難易度でスコア基準が変わります。")
        lbl_sub.setStyleSheet(f"color: {COLORS['text_dim']}; font-size: 11px;")
        root.addWidget(lbl_sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #333;")
        root.addWidget(sep)

        # スクロールエリア（カード一覧）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("border: none; background: transparent;")

        cards_widget = QWidget()
        cards_widget.setStyleSheet("background: transparent;")
        cards_layout = QVBoxLayout(cards_widget)
        cards_layout.setSpacing(6)

        for venue in self._venues:
            selected = (venue.id == self._current_id)
            card = VenueCard(venue, selected=selected)
            card.clicked.connect(self._on_card_clicked)
            cards_layout.addWidget(card)

        cards_layout.addStretch()
        scroll.setWidget(cards_widget)
        root.addWidget(scroll, stretch=1)

        # ボタン行
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        btn_cancel = QPushButton("キャンセル")
        btn_cancel.setStyleSheet(
            f"background: {COLORS['surface_hover']}; color: {COLORS['text_dim']}; "
            "border: 1px solid #555; border-radius: 4px; padding: 6px 16px;"
        )
        btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(btn_cancel)

        self._btn_ok = QPushButton("この会場でプレイ")
        self._btn_ok.setEnabled(False)
        self._btn_ok.setStyleSheet(
            f"background: {COLORS['accent']}; color: #000; "
            "border-radius: 4px; padding: 6px 16px; font-weight: bold;"
        )
        self._btn_ok.clicked.connect(self._on_ok)
        btn_row.addWidget(self._btn_ok)

        root.addLayout(btn_row)

    def _on_card_clicked(self, venue: VenueRules) -> None:
        self._selected = venue
        self._btn_ok.setEnabled(True)
        self._btn_ok.setText(f"{venue.flag} {venue.name} でプレイ")

        # カードの選択状態を更新（再描画代わりにスタイルを変える）
        # ※ 簡易実装: ダイアログを再構築せず、OK ボタンで完結
        self._current_id = venue.id

    def _on_ok(self) -> None:
        if self._selected:
            self.venue_selected.emit(self._selected)
        self.accept()
