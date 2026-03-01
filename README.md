# AI DJ Mixer

## Legacy Hardware × Generative AI × Modern Audio Engine

Vestaxの名機 **VCI-100** を現代のPC環境で蘇らせる、AI搭載型DJミキシングシステムです。
再生中の楽曲をリアルタイムで解析し、Google **Gemini** と連携して **Suno AI** 用の楽曲生成プロンプト（歌詞・スタイル・タイトル）を自動提案します。

**コアコンセプト**: 「終わりのない、しかし文脈を持ったDJセット」  
**設計哲学**: AI-Human Co-Creation — AIは「提案」、DJが「選択」

---

## 主な機能 (Features)

### 1. AIクリエイティブ・アシスタント

* **自動プロンプト生成**: 再生中の2デッキのBPM・キー・エネルギー・ジャンルを分析し、次の曲をSunoで生成するためのプロンプトを提案します。
* **Context Aware AI**: DJのEQ/Filter操作傾向をリアルタイムで記録し、プロンプト生成に反映します。エネルギー戦略をHYPNOTIC / STORYの2モードで自動判定。
* **Gemini API フォールバック**: APIレート超過・障害時はルールベース生成に自動切替し、DJセットを継続します。
* **MixAdvisor**: Camelot Wheel × エネルギーフロー分析によるミックスポイント提案。

### 2. 高度なオーディオエンジン

* **BASS Audio Library**: 実測11.6msの低レイテンシ再生をPythonで実現。
* **3バンドEQ**: DJ標準周波数（246Hz / 2.5kHz / 10kHz）のBQF PeakingEQ 3段カスケード（Mixxx参照実装）。各バンド±45dB実効、フラット時に完全透明。
* **Constant Power Crossfader**: cos/sinカーブによる中央音量維持（cos²+sin²=1）。
* **DJ Filter**: LPF/HPF対数スケールマッピング（Mixxx filtereffect.cpp参照）。
* **可変長ループ**: 1〜32バーのビートスナップループ（BPM同期、クリックノイズなし）。
* **BPM Sync**: Mixxx bpmcontrol.cpp L552-627を移植した3段階位相制御（±10ms精度）。
* **HOT CUE**: 8スロット対応（通常CUE / LoopCue）。永続化対応。

### 3. トラック解析 (TrackAnalyzer V10)

* **自動解析**: ライブラリ追加時にBPM・Key・Energy Profileをバックグラウンドで解析・キャッシュ（MD5ハッシュキー）。
* **ビートグリッド**: 先頭60秒librosa実測値 + 60秒以降BPM固定外挿のハイブリッド方式。
* **相対エネルギー評価**: Z-scoreベースの動的閾値（ライブラリ5曲以上で有効）。
* **Auto-Cue検出**: Energy Flow 1階差分から変化点を最大8点検出。
* **Camelot Wheel**: キー互換性スコアリング（Perfect +50 / Compatible +30 / Avoid -20）。

### 4. 可視化

* **波形表示**: PyQtGraphによる高速波形描画（再生位置・ループ範囲・HOT CUE・ビートグリッド）。
* **Energy Flow Panel**: 2デッキのエネルギー曲線を同期表示。ドロップ・ブレイクのタイミングを視認可能。
* **VUメーター**: L/Rリアルタイムレベル表示。

### 5. ゲーミフィケーション (Phase 9)

* **スコアリング**: Beatmatching・Key Compatibility・EQ Mixing・Energy Flowを100msごとに評価。Combo倍率最大2.0x。
* **World Tour モード**: 東京・ベルリン・イビザ・シカゴの4都市、各都市固有のルールとGeminiペルソナ。
* **AI講評**: Hype急変・コンボ達成時にGeminiがリアルタイムでコメント。
* **セッション結果ダイアログ**: 「ゲーム終了」でランク（S/A/B/C/D）・スコア内訳・Peak Hype・Max Comboをダイアログ表示。Sランク達成時は都市別の特別メッセージを表示。

### 6. ホットフォルダ連携

* ダウンロードフォルダを監視し、Sunoで生成したファイルを自動取り込み・解析します（3層防御でダウンロード途中ファイルの誤検知を防止）。

### 7. MIDIマッピング汎用化

* MIXXX形式XMLプリセットのインポート対応。
* `presets/` フォルダのJSONプリセット切り替え。
* MIDIモニターによるデバッグ支援。

---

## 必要要件 (Requirements)

### ハードウェア

* **Controller**: Vestax VCI-100（Firmware 1.2 / 1.4 推奨）
* **OS**: Windows 10/11 64bit

### ソフトウェア

* **Python**: 3.11 以上
* **BASS Libraries**（プロジェクトルートに配置）:
  * `bass.dll` — [un4seen.com](https://www.un4seen.com/) からダウンロード（64bit版）
  * `bass_fx.dll` — 同上

---

## インストール (Installation)

```bash
git clone https://github.com/wabisukecx/Suno_DJ.git
cd Suno_DJ
pip install -r requirements.txt
```

BASSライブラリをプロジェクトルートに配置後、Gemini APIキーを設定します。

```powershell
$env:GEMINI_API_KEY = "AIzaSy..."
```

---

## 起動 (Usage)

```bash
python app.py
```

引数なしで起動すると `./tracks` フォルダがライブラリとして使用されます。

```bash
python app.py C:\path\to\your\music
```

デバッグモードで起動する場合：

```bash
python app.py --debug
```

### 基本操作

1. **楽曲ロード**: ライブラリからダブルクリック、またはVCI-100のCursor左右ボタンで選択してロード。
2. **再生**: VCI-100のPlay/Pauseボタン。
3. **AIプロンプト生成**: 「GENERATE PROMPT」ボタン → Lyrics / Style / Title をSunoに貼り付け。
4. **新規楽曲**: Sunoで生成したファイルをダウンロードフォルダに保存すると自動取り込み。
5. **Sync**: VCI-100のSyncボタン → Deck Aをリーダーとしてビート+位相を自動同期。
6. **World Tour**: `ゲーム(&G)` メニューから都市を選択して「ゲーム開始」。「ゲーム終了」でランク結果ダイアログを表示。

### MIDIマッピング

`設定` メニューからMIXXX形式のXMLプリセットをインポート、または `presets/` フォルダのJSONプリセットを切り替えられます。

### デバッグ

VCI-100が想定通りに動作しない場合は、MIDIモニターで信号を確認できます。

```bash
python midi_monitor.py
```

---

## 技術スタック (Tech Stack)

| Category | Technology | Usage |
|---|---|---|
| GUI | PyQt6 + PyQtGraph | メインインターフェース・波形描画 |
| Audio | BASS Audio Library 2.4 (ctypes) | 低レイテンシ再生・DSP・ミキシング |
| Analysis | Librosa + NumPy | BPM/Key/Beat/Energy解析 |
| AI | Google Gemini API (google-genai) | プロンプト生成・AI講評 |
| MIDI | python-rtmidi | VCI-100制御 |
| Metadata | mutagen | ID3タグ読み込み |

---

## パフォーマンス実測値

| 項目 | 実測値 | 目標値 |
|---|---|---|
| オーディオレイテンシー | 11.6 ms | ≤ 15 ms ✓ |
| MIDI応答時間 | 0.8 ms | ≤ 1 ms ✓ |
| CPU使用率（平均） | 30% | ≤ 50% ✓ |
| メモリ使用量 | 380 MB | — |
| アンダーラン発生 | 0回 / 2時間連続 | — |
| 楽曲解析時間 | 平均 3.2秒 / 曲 | — |

---

## プロジェクト構造 (Project Structure)

```bash
Suno_DJ/
├── app.py                      # エントリーポイント・シグナル配線
├── mixer_core.py               # AIVCIMixer（メインコーディネーター）
├── track_analyzer.py           # 楽曲解析・MD5キャッシュ管理 (V10)
├── midi_controller.py          # VCI-100 MIDI制御
├── midi_monitor.py             # MIDIデバッグツール（単独実行）
├── prompt_worker.py            # バックグラウンドプロンプト生成 (QThread)
├── hot_folder_watcher.py       # ホットフォルダ監視（3層防御）
├── library_manager.py          # ライブラリ管理
├── knowledge_base.json         # ダンスミュージック知識ベース (Gemini入力)
├── analysis_cache.json         # 楽曲解析キャッシュ（MD5ハッシュキー）
├── bass.dll                    # BASS Audio Library（要別途取得）
├── bass_fx.dll                 # BASS FX Library（要別途取得）
│
├── core/                       # コアロジック
│   ├── audio_engine.py         # AudioEngine（デュアルデッキ・クロスフェーダー）
│   ├── audio_constants.py      # BASS定数・ctypes型定義
│   ├── deck.py                 # Deck制御（再生/BQF EQ/Loop/HOT CUE）
│   ├── deck_dsp_mixin.py       # DSPミックスイン（EQ/Filter）
│   ├── deck_loop_mixin.py      # ループミックスイン
│   ├── sync_engine.py          # BPM+位相同期（Mixxx bpmcontrol.cpp移植）
│   ├── camelot_wheel.py        # Camelot Wheelキー互換性判定
│   ├── mix_advisor.py          # Gemini連携ミックスアドバイス
│   ├── midi_mapping.py         # MIDIマッピング管理（XMLインポート対応）
│   ├── hotcue_manager.py       # HOT CUE 8スロット管理・永続化
│   ├── style_logger.py         # DJ操作ログ記録（スタイル学習用）
│   ├── ai/                     # AIロジック
│   │   ├── prompt_coordinator.py   # Gemini API統合・クォータ管理
│   │   ├── prompt_energy.py        # エネルギーフロー分析・戦略判定
│   │   ├── prompt_genre.py         # ジャンル知識管理
│   │   ├── prompt_suno.py          # Suno V5形式プロンプト生成
│   │   └── prompt_base.py          # 共通型定義（EnergyStrategy等）
│   └── gamification/           # ゲーミフィケーション (Phase 9)
│       ├── game_session.py         # GameSession・VenueRules管理
│       ├── score_engine.py         # ScoreEngine（100ms採点）
│       └── ai_commentator.py       # AI講評生成（Gemini）
│
├── gui/                        # GUIコンポーネント (PyQt6)
│   ├── gui_main_window.py      # メインウィンドウ
│   ├── gui_deck_widget.py      # デッキウィジェット（波形・VU・DSP）
│   ├── gui_library_panel.py    # ライブラリパネル
│   ├── gui_energy_panel.py     # Energy Flowパネル
│   ├── gui_prompt_panel.py     # AIプロンプトパネル
│   ├── gui_hype_panel.py       # Hype・スコア表示パネル (Phase 9)
│   ├── gui_venue_selector.py   # World Tour会場選択 (Phase 9)
│   ├── gui_session_result_dialog.py  # セッション結果ダイアログ (Phase 9)
│   ├── gui_vu_meter.py         # VUメーターウィジェット
│   ├── gui_common_widgets.py   # 共通ウィジェット
│   └── gui_styles.py           # CSSスタイル定義（サイバーパンク・ダークテーマ）
│
├── data/
│   └── venues.json             # World Tour会場ルール定義（4都市）
│
├── presets/
│   └── vci100_default.json     # VCI-100デフォルトMIDIマッピング
│
├── tracks/                     # 音楽ファイル格納フォルダ
└── logs/                       # ログファイル（5MB×3世代ローテーション）
```

---

## トラブルシューティング

**VCI-100が反応しない**  
起動前にVCI-100をUSB接続してください。ログに `MIDI Connected` が表示されない場合は `midi_monitor.py` で接続確認を行ってください。MIDI未接続時はUIオンリーモードで起動します。

**`bass.dll not found` エラー**  
`bass.dll` と `bass_fx.dll` が `app.py` と同じ階層にあるか確認してください。Pythonが64bit版の場合はDLLも64bit版が必要です。日本語パスを含む場合は `BASS_UNICODE` フラグが自動適用されます。

**AIプロンプト生成がエラーになる**  
`GEMINI_API_KEY` 環境変数が設定されているか確認してください。APIレート超過（429）やサービス障害（503）時はルールベース生成に自動フォールバックします。

**起動時に音が出ない**  
セーフスタート機能により、起動時は全チャンネルがミュートされます。VCI-100の任意のコントロールを操作するとミュートが解除されます（ログに "Safe start released" と表示）。

---

## License

MIT License

**Credits:**

* BASS Audio Library: © Un4seen Developments Ltd.
* Mixxx: Sync/EQ/Filter アルゴリズム参照 (GPL-2.0)
* Google Gemini API: AI連携
