# プロジェクト構成分析結果

## 1. プロジェクト概要

### プロジェクト名

VCI-100 AI DJ Mixer

### 目的

Vestax VCI-100 MIDIコントローラーを使用したAI搭載DJミキシングシステム。
再生中の楽曲をリアルタイム解析し、Google Gemini経由でSuno AI用の楽曲生成プロンプトを自動提案する。

### 技術スタック

- **言語**: Python 3.11+
- **GUI**: PyQt6
- **オーディオ**: BASS Audio Library (ctypes経由)
- **解析**: librosa, NumPy, SciPy
- **AI**: Google Generative AI (Gemini 2.0 Flash)
- **MIDI**: python-rtmidi
- **可視化**: pyqtgraph

---

## 2. ファイル構成

### 総行数: 5,134行

### コアモジュール (18ファイル)

#### エントリーポイント

- `app.py` (114行) - アプリケーション起動・初期化

#### バックエンド層

- `mixer_core.py` (407行) - ミキサーコア、全体統合
- `audio_engine.py` (466行) - BASS API連携、デッキ制御
- `midi_controller.py` (158行) - VCI-100 MIDIコントローラー連携
- `track_analyzer.py` (292行) - 楽曲解析エンジン
- `prompt_generator.py` (1,341行) - AIプロンプト生成、知識ベース管理
- `hot_folder_watcher.py` (299行) - ホットフォルダ監視
- `prompt_worker.py` (91行) - 非同期プロンプト生成ワーカー

#### GUI層 (PyQt6)

- `gui_main_window.py` (182行) - メインウィンドウ統合
- `gui_deck_widget.py` (282行) - デッキ表示ウィジェット
- `gui_library_panel.py` (115行) - ライブラリパネル
- `gui_energy_panel.py` (244行) - エネルギーフローパネル
- `gui_prompt_panel.py` (182行) - プロンプト表示パネル
- `gui_common_widgets.py` (346行) - 共通ウィジェット群
- `gui_styles.py` (98行) - スタイル定義
- `main_window.py` (205行) - レガシーウィンドウ (※要確認)

#### テスト

- `test_unit_vci100.py` (123行) - VCI-100ユニットテスト
- `test_integration_vc100.py` (189行) - VCI-100統合テスト

#### 設定・データ

- `requirements.txt` - 依存ライブラリ定義
- `knowledge_base.json` - ジャンル・遷移・プロンプトテンプレート知識
- `analysis_cache.json` - 楽曲解析結果キャッシュ (31トラック)
- `README.md` - プロジェクトドキュメント

---

## 3. アーキテクチャ概要

### レイヤー構造

```bash
┌─────────────────────────────────────────────┐
│         GUI Layer (PyQt6)                   │
│  - MainWindow                               │
│  - DeckWidget, LibraryPanel, EnergyPanel    │
│  - PromptPanel                              │
└─────────────────┬───────────────────────────┘
                  │ (Signals/Slots)
┌─────────────────▼───────────────────────────┐
│       Application Core Layer                │
│  - AIVCIMixer (mixer_core.py)               │
│    統合コントローラー                        │
└───┬─────────┬─────────┬──────────┬─────────┘
    │         │         │          │
    ▼         ▼         ▼          ▼
┌────────┐┌────────┐┌────────┐┌──────────┐
│ Audio  ││ MIDI   ││ Track  ││ Prompt   │
│ Engine ││ Ctrl   ││Analyzer││Generator │
└────────┘└────────┘└────────┘└──────────┘
    │                              │
    ▼                              ▼
┌────────────┐              ┌────────────┐
│ BASS       │              │ Gemini API │
│ Library    │              │            │
└────────────┘              └────────────┘
```

### モジュール間依存関係

#### mixer_core.py (中核統合モジュール)

依存先:

- audio_engine (Deck制御)
- midi_controller (VCI-100制御)
- track_analyzer (解析)
- prompt_generator (AI生成)
- hot_folder_watcher (ファイル監視)
- prompt_worker (非同期処理)

#### GUI層の依存

- gui_main_window.py
  - gui_deck_widget
  - gui_prompt_panel
  - gui_energy_panel
  - gui_library_panel
  - gui_styles
  - prompt_generator (データ取得用)

---

## 4. 主要クラス構成

### AIVCIMixer (mixer_core.py)

- **役割**: システム全体の統合コントローラー
- **公開メソッド数**: 15
- **主要メソッド**:
  - `connect_controller()` - MIDIコントローラー接続
  - `on_crossfader(val)` - クロスフェーダー制御
  - `toggle_4bar_loop(deck_id)` - 4小節ループON/OFF
  - `manual_prompt_generate(vocal_enabled)` - プロンプト生成要求
  - `update_track_bpm(filepath, new_bpm)` - BPM手動補正
  - `refresh_library()` - ライブラリ再読み込み
  - `analyze_track(filepath, force)` - 楽曲解析
  - `load_track_by_path(deck_id, filepath)` - トラックロード
  - `process_midi()` - MIDIメッセージ処理ループ

### AudioEngine (audio_engine.py)

- **役割**: BASS API統合、オーディオ再生・DSP制御
- **構成クラス**:
  - `AudioConfig` - 設定データクラス (48kHz, 512サンプル)
  - `Deck` - 個別デッキ制御 (22公開メソッド)
  - `AudioEngine` - デュアルデッキ統合 (4公開メソッド)

#### Deck主要メソッド

- `load(filepath)` - ファイルロード
- `set_eq_low/mid/high(db)` - 3バンドEQ制御
- `set_filter(val)` - アイソレーターフィルター
- `set_tempo(percent)` - テンポ調整
- `enable_4bar_loop()` - ループ制御
- `play()`, `pause()`, `stop()` - 再生制御

### MIDIController (midi_controller.py)

- **役割**: VCI-100 MIDIコントローラーとの通信
- **公開メソッド**: 4
  - `connect()` - デバイス接続
  - `register_callback(event_name, callback)` - イベント登録
  - `get_message()` - MIDIメッセージ取得
  - `close()` - 接続終了

### TrackAnalyzer (track_analyzer.py)

- **役割**: librosaによる楽曲解析
- **公開メソッド**: 3
  - `analyze_track(filepath, force_reanalyze)` - BPM/キー/エネルギー解析
  - `update_bpm(filepath, new_bpm)` - BPM手動補正
  - `recalculate_relative_energy(all_tracks)` - 相対エネルギー再計算

**解析結果データ構造**:

```python
{
    "version": 4,
    "filename": str,
    "filepath": str,
    "bpm": float,
    "key": str,  # "C", "D#" など
    "genre": str,  # "House / Deep House"
    "energy": {
        "max": float,  # 絶対値ピーク
        "median": float,
        "relative": float,  # 1.0-5.0スケール
        "rms_series": List[float]  # 時系列RMS
    },
    "auto_gain": float,  # dB
    "last_analyzed": int  # timestamp
}
```

### PromptGenerator (prompt_generator.py)

- **役割**: Gemini連携、プロンプト生成、知識ベース管理
- **公開メソッド**: 9
  - `generate_prompt(...)` - Sunoプロンプト生成
  - `get_energy_flow_visualization()` - エネルギー可視化データ
  - `record_eq_operation()` - DJスタイルプロファイリング
  - `get_session_stats()` - セッション統計取得

**知識ベース構造** (knowledge_base.json):

- `genres` - 8ジャンル定義
- `transitions` - 遷移ルール
- `song_structures` - 楽曲構造テンプレート
- `prompt_templates` - Sunoプロンプトテンプレート
- `energy_flow_patterns` - エネルギーフローパターン
- `era_specific_tags` - 年代別タグ
- `genre_extensions` - 拡張ジャンル定義 (19種)

---

## 5. GUI構成とシグナル/スロット

### MainWindow (gui_main_window.py)

**定義シグナル**:

- `refresh_library_requested`
- `analyze_track_requested(str)`
- `load_track_requested(str, str)`
- `bpm_update_requested(str, float)`
- `generate_prompt_requested(bool)`

**レイアウト**: 3カラム構成

- 左: DeckWidget x2
- 中央: EnergyFlowPanel
- 右: LibraryPanel + SunoPromptPanel

### LibraryPanel (gui_library_panel.py)

**定義シグナル**:

- `load_track_requested(str, str)` - ダブルクリックでトラックロード
- `analyze_track_requested(str)`
- `bpm_update_requested(str, float)`
- `refresh_requested`

### DeckWidget (gui_deck_widget.py)

- `WaveformWidget` - 波形表示 (未実装)
- デッキ情報表示 (BPM, キー, ジャンル, エネルギー)

### EnergyFlowPanel (gui_energy_panel.py)

- pyqtgraphによるリアルタイムエネルギー可視化
- Deck A/B 同期表示
- 1.0-5.0スケール

### SunoPromptPanel (gui_prompt_panel.py)

- Lyrics, Style, Title 表示
- 各項目コピーボタン (pyperclip連携)

---

## 6. 外部API/ライブラリ統合

### BASS Audio Library

- **モジュール**: audio_engine.py
- **使用機能**:
  - ストリーミング再生 (BASS_StreamCreateFile)
  - DirectX ParamEQ (3バンドEQ)
  - 双2次フィルター (BQF)
  - サンプルレート変換 (48kHz統一)
  - 定電力クロスフェーダー (cos/sin カーブ)
  - セーフスタート機能

### Google Gemini API

- **モジュール**: prompt_generator.py
- **モデル**: gemini-2.0-flash-exp
- **機能**:
  - 音楽理論推論 (Thinking Mode)
  - Sunoプロンプト生成
  - トークン使用量管理
  - 日次クォータ管理 (500リクエスト/日)
  - フォールバック: ルールベース生成

### librosa

- **モジュール**: track_analyzer.py
- **解析項目**:
  - BPM検出 (tempo)
  - キー推定 (chroma_cqt)
  - エネルギープロファイル (RMSエンベロープ)
  - ジャンル推定 (スペクトル特徴量)

---

## 7. データフローダイアグラム

### 楽曲ロードフロー

```bash
User (GUI) 
  → LibraryPanel.itemDoubleClicked
  → MainWindow.load_track_requested(deck_id, filepath)
  → AIVCIMixer.load_track_by_path(deck_id, filepath)
  → TrackAnalyzer.analyze_track(filepath) (未解析の場合)
  → AudioEngine.Deck[deck_id].load(filepath)
  → GUI更新 (DeckWidget, EnergyPanel)
```

### プロンプト生成フロー

```bash
User (Generate Prompt Button)
  → MainWindow.generate_prompt_requested(vocal)
  → AIVCIMixer.manual_prompt_generate(vocal)
  → PromptWorker (QThread起動)
  → PromptGenerator.generate_prompt(...)
    → Gemini API呼び出し (非同期)
    → SunoPrompt生成
  → PromptWorker.prompt_ready Signal
  → SunoPromptPanel.update_prompt(prompt)
```

### MIDI制御フロー

```bash
VCI-100 Hardware
  → MIDIController.get_message()
  → AIVCIMixer.process_midi() (100Hz polling)
  → Event dispatch:
    - "eq_high_a" → Deck[0].set_eq_high(val)
    - "crossfader" → AudioEngine.set_crossfader(val)
    - "play_a" → Deck[0].play()
```

---

## 8. 未実装・部分実装機能

### 確認が必要な項目

#### main_window.py (205行)

- gui_main_window.pyとの重複可能性
- 用途の明確化が必要

#### WaveformWidget (gui_deck_widget.py)

- 波形表示ウィジェットが定義されているが描画ロジック未実装

#### Phase 8B 未完了機能

- UC-10 (BPM手動補正): GUI実装済み、リアルタイムテンポ変更未実装
- F-04 (手動生成ボタン): 一部実装済み

#### Phase 8C 計画中機能

- Sync/Stretch/Loop機能
- BASS_FX統合

---

## 9. キャッシュとデータ永続化

### analysis_cache.json

- **目的**: 楽曲解析結果の永続化
- **キー**: ファイルハッシュ (MD5)
- **キャッシュ数**: 現在31トラック
- **バージョン**: 4

### knowledge_base.json

- **目的**: 音楽理論知識、ジャンル定義、プロンプトテンプレート
- **構造**:
  - genres (8種)
  - transitions (エネルギー遷移、キー互換性、BPM許容範囲)
  - song_structures (3種)
  - prompt_templates (3種)
  - energy_flow_patterns (3種)
  - era_specific_tags (6時代)
  - genre_extensions (19種)

---

## 10. テスト構成

### test_unit_vci100.py (123行)

- VCI-100 MIDI信号マッピングのユニットテスト
- イベント発火検証

### test_integration_vc100.py (189行)

- VCI-100統合テスト
- 実機接続テスト

**テストカバレッジ**: 部分的

- GUI層: 未テスト
- AudioEngine: 未テスト
- TrackAnalyzer: 未テスト
- PromptGenerator: 未テスト

---

## 11. 技術的特記事項

### Python GIL問題の解決

- **問題**: sounddevice使用時のオーディオドロップアウト
- **解決**: BASS Audio Library (C言語ネイティブ) への移行

### サンプルレート統一

- **要件**: 48kHz統一
- **実装**: BASS_StreamCreateFile での自動変換
- **理由**: ミスマッチによるテンポ・周波数レスポンス問題回避

### EQ実装の変遷

- **初期**: BASS_FX プラグイン使用
- **現在**: DirectX ParamEQ (依存関係削減)

### エネルギースケーリング

- **スケール**: 1.0-5.0 (典型的ダンスミュージック)
- **RMS範囲**: 0.05-0.30 (実測ベース)
- **補正**: Evidence-based scaling parameters

### クロスフェーダーカーブ

- **実装**: Constant Power (cos/sin)
- **理由**: リニアカーブでは中央位置でボリューム低下
