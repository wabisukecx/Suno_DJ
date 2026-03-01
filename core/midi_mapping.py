"""
MIDI Mapping Data Layer
=======================

MIDIマッピングのデータクラスとJSON入出力を管理するモジュール。

設計方針:
- MIDIエントリはイミュータブルなdataclassで表現
- JSON保存/読込のI/Oはこのモジュールに集約
- mixer_core.pyが依存するイベント名（event_name）は変更しない
"""

from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# デフォルトプリセットのパス
DEFAULT_PRESET_DIR = Path(__file__).parent.parent / "presets"
DEFAULT_PRESET_PATH = DEFAULT_PRESET_DIR / "vci100_default.json"  # 後方互換（存在する場合はこちらを優先）
DEFAULT_XML_PATH = DEFAULT_PRESET_DIR / "Vestax_PC-CONTROLLER.midi.xml"

# マッピングバージョン（後方互換管理用）
MAPPING_VERSION = 1


@dataclass
class MIDIEntry:
    """
    単一MIDI機能のマッピングエントリ

    Attributes:
        event_name: mixer_core.pyのregister_callbackと対応するイベント識別子
        msg_type:   'cc'（フェーダー/ノブ）または 'note'（ボタン）
        control:    MIDI CCナンバーまたはNoteナンバー
        label:      ウィザードGUIに表示するユーザー向けラベル
    """
    event_name: str
    msg_type: str   # 'cc' or 'note'
    control: int
    label: str


@dataclass
class MIDIMapping:
    """
    コントローラー1台分のMIDIマッピング定義

    Attributes:
        preset_name: プリセット名（例: 'VCI-100 Default'）
        device_name: 対象MIDIデバイス名（部分一致で接続時に使用）
        entries:     MIDIEntryのリスト
        version:     データバージョン（互換性管理）
    """
    preset_name: str
    device_name: str
    entries: list[MIDIEntry] = field(default_factory=list)
    version: int = MAPPING_VERSION

    # ---- ルックアップテーブル（ランタイム用、JSON非保存） ----

    def build_lookup(self) -> tuple[dict[int, str], dict[int, str]]:
        """
        cc_map / note_map を構築して返す。
        MIDIController._handle_cc / _handle_note が使用する。

        Returns:
            (cc_map, note_map): {control: event_name} の辞書ペア
        """
        cc_map: dict[int, str] = {}
        note_map: dict[int, str] = {}
        for entry in self.entries:
            if entry.msg_type == 'cc':
                cc_map[entry.control] = entry.event_name
            elif entry.msg_type == 'note':
                note_map[entry.control] = entry.event_name
        return cc_map, note_map

    # ---- JSON I/O ----

    def save(self, path: Path) -> bool:
        """
        マッピングをJSONファイルに保存する。

        Args:
            path: 保存先ファイルパス

        Returns:
            成功時True、失敗時False
        """
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "version": self.version,
                "preset_name": self.preset_name,
                "device_name": self.device_name,
                "entries": [asdict(e) for e in self.entries],
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"MIDIMapping saved: {path}")
            return True
        except Exception as e:
            logger.error(f"MIDIMapping save failed: {e}")
            return False

    @classmethod
    def load(cls, path: Path) -> Optional[MIDIMapping]:
        """
        JSONファイルからマッピングを読み込む。

        Args:
            path: 読み込むJSONファイルパス

        Returns:
            MIDIMappingインスタンス、失敗時None
        """
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            entries = [MIDIEntry(**e) for e in data.get("entries", [])]
            return cls(
                preset_name=data.get("preset_name", "Unknown"),
                device_name=data.get("device_name", ""),
                entries=entries,
                version=data.get("version", 1),
            )
        except Exception as e:
            logger.error(f"MIDIMapping load failed ({path}): {e}")
            return None

    @classmethod
    def load_default(cls) -> Optional["MIDIMapping"]:
        """
        デフォルトプリセットを読み込む。

        優先順位:
        1. presets/vci100_default.json（後方互換、存在する場合）
        2. presets/Vestax_PC-CONTROLLER.midi.xml（MIXXX XML）

        Returns:
            MIDIMappingインスタンス、両方存在しない場合None
        """
        if DEFAULT_PRESET_PATH.exists():
            return cls.load(DEFAULT_PRESET_PATH)
        if DEFAULT_XML_PATH.exists():
            logger.info(f"Loading default mapping from XML: {DEFAULT_XML_PATH}")
            return load_from_mixxx_xml(DEFAULT_XML_PATH)
        logger.warning(
            f"Default preset not found. "
            f"Tried: {DEFAULT_PRESET_PATH}, {DEFAULT_XML_PATH}"
        )
        return None


# MIXXX key → event_name 変換テーブル
# XMLの <group>/<key> の組み合わせを本システムの event_name にマッピングする
_MIXXX_KEY_MAP: dict[tuple[str, str], str] = {
    ("[Master]",    "crossfader"):        "crossfader",
    ("[Master]",    "volume"):             "master_volume",
    ("[Channel1]",  "volume"):             "deck_a_volume",
    ("[Channel1]",  "pregain"):            "deck_a_trim",
    ("[Channel1]",  "filterHigh"):         "deck_a_eq_high",
    ("[Channel1]",  "filterMid"):          "deck_a_eq_mid",
    ("[Channel1]",  "filterLow"):          "deck_a_eq_low",
    ("[Channel1]",  "rate"):               "deck_a_tempo",
    ("[Channel2]",  "volume"):             "deck_b_volume",
    ("[Channel2]",  "pregain"):            "deck_b_trim",
    ("[Channel2]",  "filterHigh"):         "deck_b_eq_high",
    ("[Channel2]",  "filterMid"):          "deck_b_eq_mid",
    ("[Channel2]",  "filterLow"):          "deck_b_eq_low",
    ("[Channel2]",  "rate"):               "deck_b_tempo",
    ("[Channel1]",  "play"):               "play_a",
    ("[Channel1]",  "cue_goto"):           "cue_a",
    ("[Channel1]",  "LoadSelectedTrack"): "load_a",
    ("[Channel2]",  "play"):               "play_b",
    ("[Channel2]",  "cue_goto"):           "cue_b",
    ("[Channel2]",  "LoadSelectedTrack"): "load_b",
    ("[Playlist]",  "SelectPrevTrack"):   "prev_track",
    ("[Playlist]",  "SelectNextTrack"):   "next_track",
    ("[Channel1]",  "hotcue_1_activate"): "loop_a",
    ("[Channel2]",  "hotcue_1_activate"): "loop_b",
    ("[Channel1]",  "sync_enabled"):       "sync_a",  # SW24 Note 107
    ("[Channel2]",  "sync_enabled"):       "sync_b",  # SW37 Note 108
}

# event_name のラベル（日本語）
_EVENT_LABELS: dict[str, str] = {
    "crossfader":     "クロスフェーダー",
    "master_volume":  "マスターボリューム",
    "deck_a_volume":  "Deck A: チャンネルボリューム",
    "deck_a_trim":    "Deck A: トリム (pregain)",
    "deck_a_eq_high": "Deck A: EQ High",
    "deck_a_eq_mid":  "Deck A: EQ Mid",
    "deck_a_eq_low":  "Deck A: EQ Low",
    "deck_a_tempo":   "Deck A: テンポ",
    "deck_b_volume":  "Deck B: チャンネルボリューム",
    "deck_b_trim":    "Deck B: トリム (pregain)",
    "deck_b_eq_high": "Deck B: EQ High",
    "deck_b_eq_mid":  "Deck B: EQ Mid",
    "deck_b_eq_low":  "Deck B: EQ Low",
    "deck_b_tempo":   "Deck B: テンポ",
    "play_a":         "Deck A: Play/Pause",
    "cue_a":          "Deck A: Cue Goto",
    "load_a":         "Deck A: ロード",
    "play_b":         "Deck B: Play/Pause",
    "cue_b":          "Deck B: Cue Goto",
    "load_b":         "Deck B: ロード",
    "prev_track":     "前のトラック",
    "next_track":     "次のトラック",
    "loop_a":         "Deck A: ループ",
    "loop_b":         "Deck B: ループ",
    "sync_a":         "Deck A: Sync",
    "sync_b":         "Deck B: Sync",
    "beat_grid_fwd_a": "Deck A: Beat Grid +1",
    "beat_grid_bwd_a": "Deck A: Beat Grid -1",
    "beat_grid_fwd_b": "Deck B: Beat Grid +1",
    "beat_grid_bwd_b": "Deck B: Beat Grid -1",
}


def load_from_mixxx_xml(xml_path: Path, preset_name: str = "") -> Optional["MIDIMapping"]:
    """
    MIXXX XML形式のコントローラープリセットを読み込み、MIDIMappingに変換する。

    変換ルール:
    - status 0xB0 (CC)  → msg_type='cc'
    - status 0x90 (NoteOn) → msg_type='note'
    - status 0x80 (NoteOff) はスキップ（0x90と同一コントロールが存在するため）
    - script-binding の <options> はスキップ
    - 同一 event_name が複数ある場合は最初のものを採用

    Args:
        xml_path:    MIXXXのXMLプリセットファイルパス
        preset_name: プリセット名（省略時はXMLの<n>タグを使用）

    Returns:
        MIDIMappingインスタンス、失敗時None
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
    except Exception as e:
        logger.error(f"load_from_mixxx_xml: XMLパースエラー: {e}")
        return None

    # プリセット名・デバイス名を取得
    info = root.find("info")
    if not preset_name:
        preset_name = info.findtext("n", default="Imported") if info else "Imported"
    controller_el = root.find("controller")
    device_name = controller_el.get("id", "") if controller_el is not None else ""

    entries: list[MIDIEntry] = []
    seen_events: set[str] = set()

    for ctrl in root.iter("control"):
        # script-binding はスキップ
        options = ctrl.find("options")
        if options is not None and options.find("script-binding") is not None:
            continue

        group = ctrl.findtext("group", default="").strip()
        key   = ctrl.findtext("key",   default="").strip()
        status_str = ctrl.findtext("status", default="0x00").strip()
        midino_str = ctrl.findtext("midino", default="0x00").strip()

        try:
            status = int(status_str, 16)
            midino = int(midino_str, 16)
        except ValueError:
            continue

        # NoteOff (0x80) はスキップ
        if status == 0x80:
            continue

        # msg_type 判定
        if status == 0xB0:
            msg_type = "cc"
        elif status == 0x90:
            msg_type = "note"
        else:
            continue

        # event_name 変換
        event_name = _MIXXX_KEY_MAP.get((group, key))
        if not event_name:
            continue

        # 重複スキップ
        if event_name in seen_events:
            continue
        seen_events.add(event_name)

        label = _EVENT_LABELS.get(event_name, event_name)
        entries.append(MIDIEntry(
            event_name=event_name,
            msg_type=msg_type,
            control=midino,
            label=label,
        ))

    if not entries:
        logger.warning(f"load_from_mixxx_xml: 有効なエントリが0件 ({xml_path})")
        return None

    logger.info(f"load_from_mixxx_xml: {len(entries)}件のエントリを読み込みました")
    return MIDIMapping(
        preset_name=preset_name,
        device_name=device_name,
        entries=entries,
    )


def list_presets() -> list[Path]:
    """
    presetsディレクトリ内の全JSONプリセットファイルを返す。

    Returns:
        Pathのリスト（存在しない場合は空リスト）
    """
    if not DEFAULT_PRESET_DIR.exists():
        return []
    return sorted(DEFAULT_PRESET_DIR.glob("*.json"))
