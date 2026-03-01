"""
Camelot Wheel Module (Phase R4)
================================
Harmonic Mixing対応のCamelot Wheel実装。

キー相性判定:
- Perfect Match: 同一キー              (+0)  → +50点 (Phase R8)
- Compatible:    隣接 (±1)、平行調    (+1/-1) → +30点
- Energy Boost:  エネルギー変化 (+2/+3) → +20点
- Avoid:         それ以外              → -20点

利用例:
    from core.camelot_wheel import CamelotWheel

    wheel = CamelotWheel()
    camelot_a = wheel.to_camelot("C Major")   # -> "8B"
    camelot_b = wheel.to_camelot("G Major")   # -> "9B"
    compat    = wheel.get_compatibility("8B", "9B")
    # -> {"level": "Compatible", "description": "...", "score": 30}
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

# ─────────────────────────────────────────────
# Camelot変換テーブル
# ─────────────────────────────────────────────

# pitch_class (0=C, 1=C#, ..., 11=B) × scale → Camelot番号
_MAJOR_TABLE: dict[str, str] = {
    "C":  "8B",  "C#": "3B",  "Db": "3B",
    "D":  "10B", "D#": "5B",  "Eb": "5B",
    "E":  "12B", "F":  "7B",
    "F#": "2B",  "Gb": "2B",
    "G":  "9B",  "G#": "4B",  "Ab": "4B",
    "A":  "11B", "A#": "6B",  "Bb": "6B",
    "B":  "1B",
}

_MINOR_TABLE: dict[str, str] = {
    "C":  "5A",  "C#": "12A", "Db": "12A",
    "D":  "7A",  "D#": "2A",  "Eb": "2A",
    "E":  "9A",  "F":  "4A",
    "F#": "11A", "Gb": "11A",
    "G":  "6A",  "G#": "1A",  "Ab": "1A",
    "A":  "8A",  "A#": "3A",  "Bb": "3A",
    "B":  "10A",
}

# librosa出力キー文字列 → (root, scale)
# 例: "C Maj (8B)" → ("C", "major")
#     "A# Min (3A)" → ("A#", "minor")
_SCALE_ALIASES = {
    "Maj": "major", "Major": "major",
    "Min": "minor", "Minor": "minor",
    "maj": "major", "min": "minor",
}


@dataclass
class CompatibilityResult:
    level: str            # "Perfect Match" / "Compatible" / "Energy Boost" / "Avoid"
    description: str      # 人間が読める説明
    score: int            # R8スコアリング用 (50/30/20/-20)
    interval: int         # Camelotホイール上の距離 (0=same, 1=adjacent, etc.)
    camelot_a: str
    camelot_b: str

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "description": self.description,
            "score": self.score,
            "interval": self.interval,
            "camelot_a": self.camelot_a,
            "camelot_b": self.camelot_b,
        }


class CamelotWheel:
    """
    Camelot Wheel — Harmonic Mixing判定エンジン。

    Attributes:
        WHEEL_SIZE (int): ホイールサイズ（12）
    """

    WHEEL_SIZE: int = 12

    # ─────────────────────────────────────────
    # 公開 API
    # ─────────────────────────────────────────

    def to_camelot(self, key_str: str) -> str:
        """
        キー文字列をCamelot表記に変換。

        対応フォーマット:
          - "C Major"  / "C Maj"  → "8B"
          - "A Minor"  / "A Min"  → "8A"
          - "C Maj (8B)"          → "8B"  (既にCamelot付き)
          - "8B"                  → "8B"  (そのまま返す)

        Args:
            key_str: キー文字列

        Returns:
            Camelot表記。不明なら "8B"（C Major デフォルト）
        """
        if not key_str:
            return "8B"

        key_str = key_str.strip()

        # 既にCamelot形式なら即返す
        if self._is_camelot(key_str):
            return key_str

        # "(8B)" のような括弧内Camelotを抽出
        if "(" in key_str and ")" in key_str:
            start = key_str.index("(") + 1
            end   = key_str.index(")")
            candidate = key_str[start:end].strip()
            if self._is_camelot(candidate):
                return candidate

        # "C Major" / "C Maj" / "C Min" を解析
        root, scale = self._parse_key_str(key_str)
        if root is None:
            return "8B"

        if scale == "major":
            return _MAJOR_TABLE.get(root, "8B")
        else:
            return _MINOR_TABLE.get(root, "8A")

    def get_compatibility(
        self,
        camelot_a: str,
        camelot_b: str,
    ) -> CompatibilityResult:
        """
        2つのCamelot表記間の相性を判定。

        Args:
            camelot_a: Deck A の Camelot 表記
            camelot_b: Deck B の Camelot 表記

        Returns:
            CompatibilityResult
        """
        a = self._normalize_camelot(camelot_a)
        b = self._normalize_camelot(camelot_b)

        if a is None or b is None:
            return CompatibilityResult(
                level="Unknown",
                description="キー情報が取得できません",
                score=0,
                interval=-1,
                camelot_a=camelot_a,
                camelot_b=camelot_b,
            )

        num_a, letter_a = a
        num_b, letter_b = b

        # ── 同一キー ──────────────────────────
        if num_a == num_b and letter_a == letter_b:
            return CompatibilityResult(
                level="Perfect Match",
                description=f"{camelot_a} → {camelot_b}：同一キー。シームレスにミックス可能",
                score=50,
                interval=0,
                camelot_a=camelot_a,
                camelot_b=camelot_b,
            )

        # ── 平行調 (A ↔ B, 同番号) ────────────
        if num_a == num_b and letter_a != letter_b:
            return CompatibilityResult(
                level="Compatible",
                description=f"{camelot_a} → {camelot_b}：平行調。明るさ/暗さが変化",
                score=30,
                interval=1,
                camelot_a=camelot_a,
                camelot_b=camelot_b,
            )

        # ── 数字の距離を計算 ──────────────────
        diff = self._min_interval(num_a, num_b)

        # ── 隣接 (±1, 同スケール) ─────────────
        if diff == 1 and letter_a == letter_b:
            direction = "+" if self._forward_distance(num_a, num_b) == 1 else "-"
            return CompatibilityResult(
                level="Compatible",
                description=f"{camelot_a} → {camelot_b}：隣接キー ({direction}1)。自然な移行",
                score=30,
                interval=1,
                camelot_a=camelot_a,
                camelot_b=camelot_b,
            )

        # ── エネルギーブースト (+2/+3, 同スケール) ─
        fwd = self._forward_distance(num_a, num_b)
        if letter_a == letter_b and fwd in (2, 3):
            return CompatibilityResult(
                level="Energy Boost",
                description=f"{camelot_a} → {camelot_b}：+{fwd}キー。エネルギー急上昇の演出に",
                score=20,
                interval=fwd,
                camelot_a=camelot_a,
                camelot_b=camelot_b,
            )

        # ── Perfect Fifth (7半音差, 異なるスケール) ─
        if diff == 7 and letter_a != letter_b:
            return CompatibilityResult(
                level="Compatible",
                description=f"{camelot_a} → {camelot_b}：完全5度転調。クラシックなハーモニック",
                score=30,
                interval=diff,
                camelot_a=camelot_a,
                camelot_b=camelot_b,
            )

        # ── その他: Avoid ─────────────────────
        return CompatibilityResult(
            level="Avoid",
            description=f"{camelot_a} → {camelot_b}：キー不一致。クロスフェードは短くするか、EQ処理で対処",
            score=-20,
            interval=diff,
            camelot_a=camelot_a,
            camelot_b=camelot_b,
        )

    def get_compatible_keys(self, camelot: str) -> list[str]:
        """
        指定キーと相性の良いキー一覧を返す（Perfect / Compatible のみ）。

        Args:
            camelot: 基準 Camelot 表記

        Returns:
            相性の良い Camelot 表記のリスト
        """
        norm = self._normalize_camelot(camelot)
        if norm is None:
            return []

        num, letter = norm
        results: list[str] = []

        # 同一
        results.append(f"{num}{letter}")

        # 平行調
        opposite = "B" if letter == "A" else "A"
        results.append(f"{num}{opposite}")

        # ±1 同スケール
        prev_num = (num - 2) % self.WHEEL_SIZE + 1
        next_num = (num % self.WHEEL_SIZE) + 1
        results.append(f"{prev_num}{letter}")
        results.append(f"{next_num}{letter}")

        return list(dict.fromkeys(results))  # 重複除去・順序維持

    # ─────────────────────────────────────────
    # プロンプト用テキスト生成
    # ─────────────────────────────────────────

    def format_for_prompt(
        self,
        camelot_a: str,
        camelot_b: str,
        key_a: str = "",
        key_b: str = "",
    ) -> str:
        """
        Geminiプロンプトに組み込む相性テキストを生成。

        Returns:
            日本語テキスト例:
            "キー相性: C Major (8B) → G Major (9B) = Compatible (+1). 自然な移行。"
        """
        compat = self.get_compatibility(camelot_a, camelot_b)
        a_label = f"{key_a} ({camelot_a})" if key_a else camelot_a
        b_label = f"{key_b} ({camelot_b})" if key_b else camelot_b
        return (
            f"キー相性: {a_label} → {b_label} = "
            f"{compat.level} (interval={compat.interval}). "
            f"{compat.description}"
        )

    # ─────────────────────────────────────────
    # 内部ユーティリティ
    # ─────────────────────────────────────────

    @staticmethod
    def _is_camelot(s: str) -> bool:
        """"8B" や "12A" のようなCamelot形式かどうか判定"""
        import re
        return bool(re.fullmatch(r"([1-9]|1[0-2])[AB]", s.strip()))

    @staticmethod
    def _normalize_camelot(s: str) -> Optional[tuple[int, str]]:
        """Camelot表記を (number, letter) に分解。失敗でNone"""
        s = s.strip()
        if not s:
            return None
        letter = s[-1].upper()
        if letter not in ("A", "B"):
            return None
        try:
            num = int(s[:-1])
            if 1 <= num <= 12:
                return num, letter
        except ValueError:
            pass
        return None

    @staticmethod
    def _parse_key_str(key_str: str) -> tuple[Optional[str], str]:
        """
        "C Major" / "C# Min" などを (root, scale) に解析。

        Returns:
            (root, scale): root は None の場合解析失敗
        """
        parts = key_str.split()
        if len(parts) < 2:
            return None, "major"

        root  = parts[0]  # "C", "C#", "Bb", etc.
        scale_token = parts[1]

        scale = _SCALE_ALIASES.get(scale_token, "major")
        return root, scale

    def _min_interval(self, a: int, b: int) -> int:
        """ホイール上の最短距離（0〜6）"""
        diff = abs(a - b)
        return min(diff, self.WHEEL_SIZE - diff)

    def _forward_distance(self, a: int, b: int) -> int:
        """a → b の時計回り距離（1〜12）"""
        return (b - a) % self.WHEEL_SIZE or self.WHEEL_SIZE
