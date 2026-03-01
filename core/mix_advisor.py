"""
Mix Advisor Module (Phase R4)
==============================

Gemini APIを使用したミックスアドバイス生成モジュール。

機能:
- Deck A/B のトラック情報からミックス推奨ポイントを生成
- Camelot Wheel によるキー相性判定を組み込み
- トランジション手法の提案（EQ切り替え、フィルタースイープ等）
- Gemini 利用不可時のルールベースフォールバック

出力形式:
    {
        "mix_point_a": 180.0,        # Deck A の推奨ミックスアウト位置（秒）
        "mix_point_b": 8.0,          # Deck B の推奨ミックスイン位置（秒）
        "technique": "eq_swap",      # トランジション手法
        "technique_label": "EQ切り替え",
        "key_compatibility": {...},  # CamelotWheel の結果
        "bpm_diff": 0.5,             # BPM差
        "advice_text": "...",        # 日本語アドバイス文
        "source": "gemini",          # "gemini" or "rule_based"
    }
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from core.camelot_wheel import CamelotWheel, CompatibilityResult

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# 定数
# ─────────────────────────────────────────────

# BPM差の許容閾値（これ以上は警告）
BPM_WARN_THRESHOLD = 5.0

# Gemini 呼び出し間隔（秒）: 無料枠 15req/min → 4秒間隔
GEMINI_MIN_INTERVAL = 4.0

# トランジション手法定義
TECHNIQUES = {
    "eq_swap":       "EQ切り替え（Low を互い違いに操作）",
    "filter_sweep":  "フィルタースイープ（HPF/LPF でなめらかに入替）",
    "cut_in":        "カットイン（クロスフェーダーで一気に切り替え）",
    "long_blend":    "ロングブレンド（32小節かけてゆっくり移行）",
    "echo_out":      "エコーアウト（エフェクトで自然にフェード）",
}


# ─────────────────────────────────────────────
# データクラス
# ─────────────────────────────────────────────

@dataclass
class MixAdvice:
    """ミックスアドバイス結果"""
    mix_point_a: float          # Deck A ミックスアウト推奨位置（秒）
    mix_point_b: float          # Deck B ミックスイン推奨位置（秒）
    technique: str              # トランジション手法キー
    technique_label: str        # トランジション手法（日本語）
    key_compatibility: dict     # CamelotWheel 結果
    bpm_diff: float             # BPM差
    advice_text: str            # 日本語アドバイス文
    source: str                 # "gemini" or "rule_based"
    generation_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "mix_point_a":      self.mix_point_a,
            "mix_point_b":      self.mix_point_b,
            "technique":        self.technique,
            "technique_label":  self.technique_label,
            "key_compatibility": self.key_compatibility,
            "bpm_diff":         self.bpm_diff,
            "advice_text":      self.advice_text,
            "source":           self.source,
            "generation_time":  self.generation_time,
        }


# ─────────────────────────────────────────────
# MixAdvisor 本体
# ─────────────────────────────────────────────

class MixAdvisor:
    """
    Gemini API を活用したミックスアドバイスエンジン（Phase R4）。

    使い方:
        advisor = MixAdvisor(api_key="YOUR_KEY")

        deck_a = {
            "bpm": 128.0, "key": "C Major", "energy_numeric": 3,
            "genre": "Tech House", "duration": 360.0,
            "energy_flow": [2.1, 2.5, 3.0, 3.8, 4.2, ...],
        }
        deck_b = {
            "bpm": 129.5, "key": "G Major", "energy_numeric": 4,
            "genre": "Tech House", "duration": 390.0,
            "energy_flow": [3.5, 3.8, 4.0, 4.2, 4.5, ...],
        }

        advice = advisor.get_advice(deck_a, deck_b)
        print(advice.advice_text)
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Gemini API キー。None の場合ルールベースのみ使用。
        """
        self._api_key = api_key
        self._camelot = CamelotWheel()
        self._last_gemini_call = 0.0
        self._gemini_model = None

        if api_key:
            self._init_gemini(api_key)

    # ─────────────────────────────────────────
    # 公開 API
    # ─────────────────────────────────────────

    def get_advice(
        self,
        deck_a: dict,
        deck_b: dict,
        use_gemini: bool = True,
    ) -> MixAdvice:
        """
        Deck A/B の情報からミックスアドバイスを生成する。

        Args:
            deck_a: Deck A のトラック情報
            deck_b: Deck B のトラック情報
            use_gemini: Gemini を使用するか（False でルールベース強制）

        Returns:
            MixAdvice
        """
        t0 = time.time()

        # キー相性判定
        camelot_a = self._camelot.to_camelot(deck_a.get("key", ""))
        camelot_b = self._camelot.to_camelot(deck_b.get("key", ""))
        compat: CompatibilityResult = self._camelot.get_compatibility(camelot_a, camelot_b)

        # BPM差
        bpm_a = float(deck_a.get("bpm", 120.0))
        bpm_b = float(deck_b.get("bpm", 120.0))
        bpm_diff = abs(bpm_a - bpm_b)

        # Gemini 呼び出し
        if use_gemini and self._gemini_model and self._can_call_gemini():
            advice = self._get_advice_gemini(deck_a, deck_b, compat, bpm_diff)
        else:
            advice = self._get_advice_rule_based(deck_a, deck_b, compat, bpm_diff)

        advice.generation_time = time.time() - t0
        return advice

    def update_api_key(self, api_key: str) -> bool:
        """実行中に API キーを更新する。"""
        try:
            self._init_gemini(api_key)
            self._api_key = api_key
            return True
        except Exception as e:
            logger.error(f"MixAdvisor: API キー更新失敗: {e}")
            return False

    # ─────────────────────────────────────────
    # Gemini 連携
    # ─────────────────────────────────────────

    def _init_gemini(self, api_key: str) -> None:
        """Gemini クライアントを初期化する。"""
        try:
            import google.generativeai as genai
            genai.configure(api_key=api_key)
            self._gemini_model = genai.GenerativeModel("gemini-2.0-flash")
            logger.info("MixAdvisor: Gemini 初期化完了")
        except ImportError:
            logger.warning("MixAdvisor: google-generativeai 未インストール。ルールベースのみ使用。")
            self._gemini_model = None
        except Exception as e:
            logger.error(f"MixAdvisor: Gemini 初期化エラー: {e}")
            self._gemini_model = None

    def _can_call_gemini(self) -> bool:
        """Gemini 呼び出し間隔チェック（15req/min 制限対応）。"""
        return (time.time() - self._last_gemini_call) >= GEMINI_MIN_INTERVAL

    def _get_advice_gemini(
        self,
        deck_a: dict,
        deck_b: dict,
        compat: CompatibilityResult,
        bpm_diff: float,
    ) -> MixAdvice:
        """Gemini API でアドバイスを生成する。"""
        prompt = self._build_gemini_prompt(deck_a, deck_b, compat, bpm_diff)
        try:
            self._last_gemini_call = time.time()
            response = self._gemini_model.generate_content(prompt)
            raw = response.text.strip()
            logger.debug(f"MixAdvisor Gemini 応答: {raw[:200]}")
            return self._parse_gemini_response(raw, deck_a, deck_b, compat, bpm_diff)
        except Exception as e:
            logger.warning(f"MixAdvisor: Gemini 呼び出し失敗 → ルールベースにフォールバック: {e}")
            return self._get_advice_rule_based(deck_a, deck_b, compat, bpm_diff)

    def _build_gemini_prompt(
        self,
        deck_a: dict,
        deck_b: dict,
        compat: CompatibilityResult,
        bpm_diff: float,
    ) -> str:
        """Gemini に送るプロンプトを構築する。"""
        dur_a = float(deck_a.get("duration", 300.0))
        energy_flow_a = deck_a.get("energy_flow", [])
        energy_flow_b = deck_b.get("energy_flow", [])

        # energy_flow を簡略化（最大10点）
        def _summarize_flow(flow: list) -> str:
            if not flow:
                return "なし"
            step = max(1, len(flow) // 10)
            sampled = flow[::step][:10]
            return ", ".join(f"{v:.1f}" for v in sampled)

        techniques_list = "\n".join(
            f"  - {k}: {v}" for k, v in TECHNIQUES.items()
        )

        return f"""あなたはプロのDJです。以下の2曲の情報からミックスアドバイスを日本語で提供してください。

## Deck A（現在再生中）
- ジャンル: {deck_a.get('genre', '不明')}
- BPM: {deck_a.get('bpm', '?')}
- キー: {deck_a.get('key', '?')} ({compat.camelot_a})
- エネルギー（1-5）: {deck_a.get('energy_numeric', '?')}
- 曲の長さ: {dur_a:.0f}秒
- エネルギーフロー（サンプル）: {_summarize_flow(energy_flow_a)}

## Deck B（次の曲）
- ジャンル: {deck_b.get('genre', '不明')}
- BPM: {deck_b.get('bpm', '?')}
- キー: {deck_b.get('key', '?')} ({compat.camelot_b})
- エネルギー（1-5）: {deck_b.get('energy_numeric', '?')}
- エネルギーフロー（サンプル）: {_summarize_flow(energy_flow_b)}

## キー相性
- 判定: {compat.level}（{compat.description}）

## BPM差
- {bpm_diff:.1f} BPM

## 利用可能なトランジション手法
{techniques_list}

## 回答形式（必ずこの形式で）
MIX_POINT_A: <Deck A のミックスアウト推奨位置（秒、整数）>
MIX_POINT_B: <Deck B のミックスイン推奨位置（秒、整数）>
TECHNIQUE: <上記手法キーのいずれか1つ>
ADVICE: <日本語アドバイス文（2〜3文）>
"""

    def _parse_gemini_response(
        self,
        raw: str,
        deck_a: dict,
        deck_b: dict,
        compat: CompatibilityResult,
        bpm_diff: float,
    ) -> MixAdvice:
        """Gemini の応答テキストをパースして MixAdvice を返す。"""
        values: dict = {}
        for line in raw.splitlines():
            if ":" in line:
                key, _, val = line.partition(":")
                values[key.strip()] = val.strip()

        # MIX_POINT_A
        dur_a = float(deck_a.get("duration", 300.0))
        try:
            mix_a = float(values.get("MIX_POINT_A", dur_a * 0.75))
            mix_a = max(0.0, min(mix_a, dur_a))
        except ValueError:
            mix_a = dur_a * 0.75

        # MIX_POINT_B
        try:
            mix_b = float(values.get("MIX_POINT_B", 8.0))
            mix_b = max(0.0, mix_b)
        except ValueError:
            mix_b = 8.0

        # TECHNIQUE
        technique = values.get("TECHNIQUE", "eq_swap")
        if technique not in TECHNIQUES:
            technique = "eq_swap"

        # ADVICE
        advice_text = values.get("ADVICE", "")
        if not advice_text:
            advice_text = self._build_rule_advice(compat, bpm_diff, technique)

        return MixAdvice(
            mix_point_a=mix_a,
            mix_point_b=mix_b,
            technique=technique,
            technique_label=TECHNIQUES[technique],
            key_compatibility=compat.to_dict(),
            bpm_diff=bpm_diff,
            advice_text=advice_text,
            source="gemini",
        )

    # ─────────────────────────────────────────
    # ルールベース生成
    # ─────────────────────────────────────────

    def _get_advice_rule_based(
        self,
        deck_a: dict,
        deck_b: dict,
        compat: CompatibilityResult,
        bpm_diff: float,
    ) -> MixAdvice:
        """ルールベースでアドバイスを生成する（Gemini 不使用時）。"""
        dur_a = float(deck_a.get("duration", 300.0))

        # ミックスアウト位置: 曲の75%地点（4小節境界に近い位置）
        mix_point_a = self._snap_to_phrase(dur_a * 0.75, deck_a.get("bpm", 128.0))

        # ミックスイン位置: 8小節目（32拍）
        bpm_b = float(deck_b.get("bpm", 128.0))
        beat_b = 60.0 / bpm_b
        mix_point_b = beat_b * 32  # 8小節

        # トランジション手法選択
        technique = self._select_technique(compat, bpm_diff)

        # アドバイス文生成
        advice_text = self._build_rule_advice(compat, bpm_diff, technique)

        return MixAdvice(
            mix_point_a=mix_point_a,
            mix_point_b=mix_point_b,
            technique=technique,
            technique_label=TECHNIQUES[technique],
            key_compatibility=compat.to_dict(),
            bpm_diff=bpm_diff,
            advice_text=advice_text,
            source="rule_based",
        )

    def _select_technique(self, compat: CompatibilityResult, bpm_diff: float) -> str:
        """相性・BPM差からトランジション手法を選択する。"""
        if bpm_diff > BPM_WARN_THRESHOLD:
            # BPM差が大きい → カットイン or エコーアウトで誤魔化す
            return "cut_in"
        if compat.level == "Perfect Match":
            return "long_blend"
        if compat.level == "Compatible":
            return "eq_swap"
        if compat.level == "Energy Boost":
            return "filter_sweep"
        # Avoid
        return "cut_in"

    def _build_rule_advice(
        self, compat: CompatibilityResult, bpm_diff: float, technique: str
    ) -> str:
        """ルールベースのアドバイス文を組み立てる。"""
        parts: list[str] = []

        # キー相性
        if compat.level == "Perfect Match":
            parts.append("同一キーのため、ロングブレンドでシームレスなミックスが可能です。")
        elif compat.level == "Compatible":
            parts.append(f"キー相性は良好（{compat.camelot_a}→{compat.camelot_b}）。自然なトランジションができます。")
        elif compat.level == "Energy Boost":
            parts.append(f"キーが+{compat.interval}段上がりエネルギーが高まります。短めのミックスで勢いを出しましょう。")
        else:
            parts.append("キーが不一致のため、ミックス時間を短くするか、EQで低音を処理してください。")

        # BPM差
        if bpm_diff < 1.0:
            parts.append("BPMはほぼ同一です。")
        elif bpm_diff < BPM_WARN_THRESHOLD:
            parts.append(f"BPM差は{bpm_diff:.1f}。Syncを使うか、テンポを手動で合わせてください。")
        else:
            parts.append(f"BPM差が{bpm_diff:.1f}と大きいため、{TECHNIQUES[technique]}で素早く切り替えることを推奨します。")

        return " ".join(parts)

    # ─────────────────────────────────────────
    # ユーティリティ
    # ─────────────────────────────────────────

    @staticmethod
    def _snap_to_phrase(position_sec: float, bpm: float, phrase_bars: int = 4) -> float:
        """
        指定位置を最寄りの小節境界（デフォルト4小節）にスナップする。

        Args:
            position_sec: スナップ前の位置（秒）
            bpm: BPM
            phrase_bars: フレーズ長（小節数）

        Returns:
            スナップ後の位置（秒）
        """
        if bpm <= 0:
            return position_sec
        beat_sec = 60.0 / bpm
        phrase_sec = beat_sec * 4 * phrase_bars  # 4拍/小節 × phrase_bars
        if phrase_sec <= 0:
            return position_sec
        n = round(position_sec / phrase_sec)
        return n * phrase_sec
