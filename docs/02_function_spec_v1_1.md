# VCI-100 AI DJ Mixer - 基本設計書

**バージョン**: 2.0  
**最終更新日**: 2026-02-02  
**前提ドキュメント**: 要件定義書 v2.0  
**ステータス**: Phase 9G (Auto-Analysis) + Phase 8L (4-Bar Loop) 実装完了版

---

## 1. システム構成

### 1.1 システム構成図

```
┌──────────────────────────────────────────────────────────┐
│                    User Environment                      │
│  ┌─────────────┐         ┌──────────────┐               │
│  │ VCI-100     │◄────────┤ PC (Win/Mac) │               │
│  │ MIDI Ctrl   │ USB     │              │               │
│  └─────────────┘         │  ┌────────┐  │               │
│                          │  │ VCI100 │  │               │
│  ┌─────────────┐         │  │   AI   │  │               │
│  │ Speakers /  │◄────────┤  │  Mixer │  │               │
│  │ Headphones  │ Audio   │  └────┬───┘  │               │
│  └─────────────┘         │       │      │               │
│                          │  ┌────▼───┐  │               │
│  ┌─────────────┐         │  │  BASS  │  │               │
│  │ Downloads   │────────►│  │+ FX    │  │               │
│  │  Folder     │ Monitor │  └────────┘  │               │
│  └─────────────┘         └──────┬───────┘               │
└─────────────────────────────────┼───────────────────────┘
                                  │ HTTPS
                        ┌─────────▼─────────┐
                        │   Internet        │
                        │ ┌───────────────┐ │
                        │ │ Google Gemini │ │
                        │ │  2.0 Flash    │ │
                        │ └───────────────┘ │
                        │ ┌───────────────┐ │
                        │ │   Suno AI     │ │
                        │ │  (Manual Use) │ │
                        │ └───────────────┘ │
                        └───────────────────┘
```

### 1.2 デプロイメント構成

| コンポーネント | 配置場所 | サイズ | 役割 |
| ------------ | --------- | ------ | ---- |
| app.py | プロジェクトルート | 4KB | エントリーポイント |
| mixer_core.py | プロジェクトルート | 20KB | コアコントローラー |
| audio_engine.py | プロジェクトルート | 19KB | BASS Audio統合 |
| bass.dll | プロジェクトルート | ~120KB | オーディオライブラリ (v2.4.18) |
| bass_fx.dll | プロジェクトルート | ~90KB | Tempo/FXエクステンション |
| tracks/ | プロジェクトルート | - | 楽曲ライブラリフォルダ |
| analysis_cache.json | プロジェクトルート | ~500KB | 解析結果キャッシュ (v4) |
| knowledge_base.json | プロジェクトルート | 18KB | AI知識ベース |

---

## 2. アーキテクチャ設計

### 2.1 レイヤーアーキテクチャ

```
┌─────────────────────────────────────────────────┐
│         Presentation Layer (GUI)                │
│  PyQt6 Widgets, Signals/Slots                   │
│  - gui_main_window, gui_deck_widget,            │
│  - gui_energy_panel, gui_library_panel,         │
│  - gui_prompt_panel, gui_common_widgets         │
└────────────────┬────────────────────────────────┘
                 │ pyqtSignal/pyqtSlot
┌────────────────▼────────────────────────────────┐
│       Application Layer (Core Logic)            │
│  - AIVCIMixer (mixer_core.py)                   │
│    └─ MIDIイベント集約                          │
│    └─ オーディオエンジン制御                     │
│    └─ 解析・プロンプト生成統括                   │
│  - PromptGeneratorWorker (QThread)              │
│  - HotFolderWatcher (QThread)                   │
└────────────────┬────────────────────────────────┘
                 │ メソッド呼び出し
┌────────────────▼────────────────────────────────┐
│       Domain Layer (Business Logic)             │
│  - AudioEngine (audio_engine.py)                │
│    └─ Deck A/B 管理                             │
│    └─ クロスフェーダー制御                       │
│  - TrackAnalyzer (track_analyzer.py)            │
│    └─ BPM/Key/Energy解析                        │
│    └─ キャッシュ管理 (v4)                       │
│  - PromptGenerator (prompt_generator.py)        │
│    └─ Gemini API統合                            │
│    └─ フォールバックロジック                     │
└────────────────┬────────────────────────────────┘
                 │ FFI/API呼び出し
┌────────────────▼────────────────────────────────┐
│       Infrastructure Layer                      │
│  - BASS Library (ctypes経由)                    │
│  - Librosa/Essentia (音楽解析)                  │
│  - Google Gemini API (REST)                     │
│  - python-rtmidi (MIDIドライバー)               │
└─────────────────────────────────────────────────┘
```

### 2.2 MVCパターン適用

| 層 | 実装箇所 | 責務 |
| - | ------- | ---- |
| **Model** | audio_engine, track_analyzer, prompt_generator | ドメインロジック・状態管理 |
| **View** | gui_*.py (PyQt6 Widgets) | UI描画・ユーザー入力受付 |
| **Controller** | mixer_core.AIVCIMixer | Model⇔View間のデータ仲介 |

---

## 3. モジュール設計

### 3.1 モジュール構成

```
vci-100-ai-mixer/
├── app.py                      # アプリケーションエントリーポイント
├── mixer_core.py               # コアコントローラー (407行)
├── audio_engine.py             # BASS統合 (472行)
├── track_analyzer.py           # 楽曲解析 (292行)
├── prompt_generator.py         # Gemini API統合 (1341行)
├── prompt_worker.py            # Prompt生成QThread (91行)
├── hot_folder_watcher.py       # HotFolder監視 (299行)
├── midi_controller.py          # MIDI入力処理 (158行)
├── gui_main_window.py          # メインウィンドウ (182行)
├── gui_deck_widget.py          # デッキUI (282行)
├── gui_energy_panel.py         # Energyフロー表示 (244行)
├── gui_library_panel.py        # ライブラリテーブル (115行)
├── gui_prompt_panel.py         # Prompt表示 (182行)
├── gui_common_widgets.py       # 共通Widget (346行)
├── gui_styles.py               # スタイル定数 (105行)
├── bass.dll / bass_fx.dll      # Audioライブラリ
├── tracks/                     # 楽曲フォルダ
├── analysis_cache.json         # 解析キャッシュ
└── knowledge_base.json         # AI知識ベース
```

### 3.2 主要モジュール詳細

#### 3.2.1 mixer_core.py (AIVCIMixer)

**役割**: システム全体の統合コントローラー

**主要メソッド**:
- `start()`: システム起動
- `load_track_by_path(deck, path)`: トラックロード + 解析
- `toggle_4bar_loop(deck_id)`: 4小節ループ制御
- `manual_prompt_generate(vocal)`: AI Prompt生成トリガー
- `update_track_bpm(filepath, new_bpm)`: BPM手動修正
- `refresh_library()`: ライブラリスキャン + 自動解析
- `_analyze_unanalyzed_tracks(paths)`: バックグラウンド解析

**接続**:
- MIDIController → コールバック登録
- AudioEngine → play/pause/EQ制御
- TrackAnalyzer → analyze_track呼び出し
- PromptWorker → QThread起動
- HotFolderWatcher → file_moved signal受信

#### 3.2.2 audio_engine.py (AudioEngine / Deck)

**役割**: オーディオ再生・エフェクト処理

**Deck クラス**:
- `load(filepath)`: BASS Stream生成 + FX Setup
- `set_loop(start, duration)`: ループ設定 (BASS_SYNC_MIXTIME)
- `clear_loop()`: ループ解除
- `set_eq_low/mid/high(db)`: 3バンドEQ制御
- `set_filter(val)`: LPF/HPFフィルター
- `set_tempo(percent)`: Tempo変更 (-50% ~ +50%)
- `set_pitch(semitones)`: Pitch変更 (-12 ~ +12)

**AudioEngine クラス**:
- `set_crossfader(v)`: 等電力カーブ適用
- `_update_mix()`: cos/sin係数計算

#### 3.2.3 track_analyzer.py (TrackAnalyzer)

**役割**: 楽曲メタデータ・エネルギー解析

**主要メソッド**:
- `analyze_track(filepath)`: フル解析実行
- `update_bpm(filepath, new_bpm)`: BPM手動修正
- `apply_relative_energy_evaluation(tracks)`: Z-Score正規化
- `_get_file_hash(filepath)`: MD5ハッシュ生成

**キャッシュ形式 (v4)**:
```json
{
  "hash": {
    "version": 4,
    "bpm": 128.0,
    "key": "Am",
    "genre": "Techno",
    "energy": {
      "mean": 0.45,
      "max": 0.8,
      "numeric": 4.2,
      "profile": [{"time": 0.0, "level": 0.1}, ...]
    }
  }
}
```

#### 3.2.4 prompt_generator.py (PromptGenerator)

**役割**: Gemini API経由でSunoプロンプト生成

**主要メソッド**:
- `generate_next_track_prompt(...)`: AI生成実行
- `_generate_fallback_prompt(...)`: ルールベース生成

**出力形式**:
```json
{
  "suno": {
    "title": "Generated Title",
    "styles": "Genre, BPM, Mood",
    "lyrics": "[Intro]\n[Verse]\n..."
  },
  "reasoning": {
    "harmonic_mixing": "Am to Fm (Relative key)",
    "energy_strategy": "Maintain high energy",
    "genre_transition": "Techno to Progressive House"
  }
}
```

---

## 4. データ設計

### 4.1 データフロー

```
User操作 (MIDI/GUI)
    ↓
mixer_core (AIVCIMixer)
    ↓
┌───────────┬────────────┬─────────────┐
│           │            │             │
audio_engine  track_analyzer  prompt_generator
│           │            │             │
BASS DLL  Librosa/Essentia  Gemini API
│           │            │             │
再生出力   Cache更新   Prompt返却
```

### 4.2 永続化データ

| データ | ファイル名 | 形式 | サイズ | 更新タイミング |
| ----- | --------- | ---- | ----- | ------------ |
| 解析結果 | analysis_cache.json | JSON | ~500KB | トラック解析時 |
| AI知識 | knowledge_base.json | JSON | 18KB | 手動更新 |
| 設定 | (未実装) | INI/JSON | - | 設定変更時 |

### 4.3 データ構造詳細

#### Track Metadata

```python
{
    "filename": "track.mp3",
    "filepath": "/path/to/track.mp3",
    "analyzed": True,
    "bpm": 128.0,
    "key": "Am",
    "genre": "Techno",
    "energy": {
        "mean": 0.45,        # 生RMS平均
        "max": 0.8,          # 生RMS最大
        "numeric": 4.2,      # 相対評価スコア (1.0-5.0)
        "profile": [...]     # 1秒間隔のレベル配列
    }
}
```

#### Deck State

```python
{
    "stream_decode": int,      # BASSデコードストリームハンドル
    "stream_fx": int,          # BASS FXストリームハンドル
    "duration": float,         # 秒数
    "channel_volume": float,   # 0.0-1.0
    "mix_volume": float,       # クロスフェーダー係数
    "eq_low/mid/high": float,  # -15 ~ +15 dB
    "filter_val": float,       # -1.0 ~ +1.0
    "tempo_percent": float,    # -50 ~ +50 %
    "pitch_semitones": float,  # -12 ~ +12
    "loop_active": bool,       # ループ状態
    "loop_sync_handle": int    # BASSシンクハンドル
}
```

---

## 5. 外部インターフェース設計

### 5.1 MIDI入力 (VCI-100)

**プロトコル**: MIDI over USB (Class-Compliant)

**メッセージ形式**: MIDI CC (Control Change)

**主要マッピング**:

| 物理コントロール | CC番号 | 用途 | 値域 |
| -------------- | ------ | ---- | ---- |
| Crossfader | 8 | Deck A/B Mix | 0-127 |
| Master Volume | 24 | 出力レベル | 0-127 |
| CH1 Volume | 12 | Deck A Volume | 0-127 |
| CH1 EQ High | 20 | Deck A High EQ | 0-127 |
| CH1 EQ Mid | 21 | Deck A Mid EQ | 0-127 |
| CH1 EQ Low | 22 | Deck A Low EQ | 0-127 |
| CH1 Filter | 23 | Deck A LPF/HPF | 0-127 |
| CH1 Tempo | 14 | Deck A Tempo Fader | 0-127 |
| CH1 Loop | 66 | 4-Bar Loop Toggle | 127 (on press) |
| Play A | 52 | Deck A Play/Pause | 127 (on press) |
| Cue A | 54 | Deck A Cue | 127 (on press) |
| Load A | 64 | Library→Deck A | 127 (on press) |
| Prev Track | 62 | Library Cursor Up | 127 (on press) |
| Next Track | 63 | Library Cursor Down | 127 (on press) |

**注意**: Deck B (CH2)は同様のマッピング (CCナンバー異なる)

### 5.2 Google Gemini API

**エンドポイント**: `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent`

**認証**: Bearer Token (API Key)

**リクエスト形式** (JSON):
```json
{
  "contents": [{
    "role": "user",
    "parts": [{"text": "System Prompt + User Query"}]
  }],
  "generationConfig": {
    "responseMimeType": "application/json",
    "responseSchema": {...}
  }
}
```

**レスポンス形式**:
```json
{
  "candidates": [{
    "content": {
      "parts": [{"text": "{\"suno\": {...}, \"reasoning\": {...}}"}]
    }
  }]
}
```

**エラーハンドリング**:
- HTTP 429 (Rate Limit) → フォールバック生成
- HTTP 500 (Server Error) → フォールバック生成
- Timeout (30s) → フォールバック生成

### 5.3 BASS Audio Library

**API種別**: C Library (DLL) → ctypes経由で呼び出し

**主要関数**:
- `BASS_Init(device, freq, flags, hwnd, clsid)`
- `BASS_StreamCreateFile(mem, file, offset, length, flags)`
- `BASS_ChannelPlay(handle, restart)`
- `BASS_ChannelSetAttribute(handle, attrib, value)`
- `BASS_ChannelSetFX(handle, type, priority)`
- `BASS_ChannelSetSync(handle, type, param, proc, user)`

**BASS_FX 拡張**:
- `BASS_FX_TempoCreate(chan, flags)`: Tempo/Pitch処理ストリーム生成
- `BASS_FX_GetVersion()`: バージョン確認

---

## 6. 画面設計

### 6.1 メインウィンドウレイアウト

```
┌────────────────────────────────────────────────┐
│  VCI-100 AI DJ Mixer               [−][□][×] │
├────────────────────────────────────────────────┤
│ ┌─────────────┐     ┌─────────────┐           │
│ │  Deck A     │     │  Deck B     │           │
│ │ ┌─────────┐ │     │ ┌─────────┐ │           │
│ │ │Waveform │ │     │ │Waveform │ │           │
│ │ └─────────┘ │     │ └─────────┘ │           │
│ │ BPM: 128    │     │ BPM: 130    │           │
│ │ Key: Am     │     │ Key: Cm     │           │
│ │ [LOOP: OFF] │     │ [LOOP: ON ] │           │
│ └─────────────┘     └─────────────┘           │
│                                                │
│ ┌──────────────────────────────────────────┐  │
│ │  Energy Flow Panel                       │  │
│ │  ┌────────────────────────────────────┐  │  │
│ │  │  Deck A (上向き波形)              │  │  │
│ │  ├────────────────────────────────────┤  │  │
│ │  │  Deck B (下向き波形)              │  │  │
│ │  └────────────────────────────────────┘  │  │
│ └──────────────────────────────────────────┘  │
│                                                │
│ ┌──────────────┐  ┌──────────────────────┐   │
│ │ Library      │  │ AI Prompt Generator  │   │
│ │ ┌──────────┐ │  │ ┌──────────────────┐ │   │
│ │ │Track List│ │  │ │Title:            │ │   │
│ │ │          │ │  │ │Styles:           │ │   │
│ │ │          │ │  │ │Lyrics: ...       │ │   │
│ │ └──────────┘ │  │ │                  │ │   │
│ │ [▲][▼]      │  │ │[Generate] [Vocal]│ │   │
│ └──────────────┘  │ └──────────────────┘ │   │
│                   │ Reasoning:           │   │
│                   │ - Harmonic: ...      │   │
│                   │ - Energy: ...        │   │
│                   └──────────────────────┘   │
├────────────────────────────────────────────────┤
│ Status: Ready | DSP: DX8 EQ | Latency: 11.6ms │
└────────────────────────────────────────────────┘
```

### 6.2 カラースキーム (gui_styles.py)

```python
COLORS = {
    'deck_a': '#ff1744',        # Red A400
    'deck_b': '#00e5ff',        # Cyan A400
    'background': '#121212',    # Dark Background
    'surface': '#1e1e1e',       # Panel Background
    'text_primary': '#ffffff',  # White
    'text_secondary': '#b0b0b0',# Gray
    'accent': '#bb86fc',        # Purple
    'warning': '#ffab00',       # Amber
    'error': '#cf6679'          # Red
}
```

---

## 7. エラーハンドリング設計

### 7.1 エラーカテゴリ

| カテゴリ | 重要度 | 対応方針 |
| ------- | ------ | ------- |
| **Critical** | システム停止 | ログ記録 + ユーザー通知 + 終了 |
| **High** | 機能停止 | フォールバック + ユーザー通知 |
| **Medium** | 一部機能制限 | ログ記録 + 継続動作 |
| **Low** | 無視可能 | ログ記録のみ |

### 7.2 具体的エラーハンドリング

| エラー | カテゴリ | 検知箇所 | 対応 |
| ----- | ------- | ------- | ---- |
| BASS初期化失敗 | Critical | audio_engine.py | アプリ終了 + エラーダイアログ |
| BASS_FX読み込み失敗 | High | audio_engine.py | DX8 ParamEQにフォールバック |
| MIDI切断 | Medium | midi_controller.py | キーボード操作モード継続 |
| トラック解析失敗 | Medium | track_analyzer.py | ダミーデータ返却 (BPM=120) |
| Gemini API Error | Medium | prompt_generator.py | ルールベース生成に切り替え |
| HotFolder移動失敗 | Low | hot_folder_watcher.py | 次回ポーリングでリトライ |
| キャッシュ破損 | Low | track_analyzer.py | キャッシュ削除 + 再解析 |

---

## 8. パフォーマンス要件

### 8.1 レスポンスタイム

| 操作 | 目標 | 実測値 |
| ---- | ---- | ------ |
| トラック再生開始 | < 200ms | ~150ms |
| MIDI入力反映 | < 50ms | ~30ms |
| クロスフェーダー応答 | < 20ms | ~12ms |
| 波形描画更新 | < 16ms (60fps) | ~8ms |
| トラック解析 (Cache Hit) | < 10ms | ~5ms |
| トラック解析 (Cache Miss) | < 30s | ~20s |

### 8.2 リソース使用量

| リソース | 目標 | 実測値 (Phase 9G) |
| ------- | ---- | ---------------- |
| CPU使用率 (Idle) | < 5% | ~3% |
| CPU使用率 (再生中) | < 15% | ~8% |
| メモリ使用量 | < 200MB | ~150MB |
| ディスク I/O | < 10MB/s | ~5MB/s (解析時) |

---

## 9. セキュリティ設計

### 9.1 API Key管理

- 環境変数 `GEMINI_API_KEY` から読み込み
- コード内にハードコード禁止
- `.env` ファイルを `.gitignore` に追加

### 9.2 ファイルアクセス制御

- トラックフォルダ: `tracks/` のみ読み込み許可
- キャッシュ: プロジェクトルートのみ書き込み許可
- HotFolder: ユーザー指定フォルダ (Downloads等) の読み取り専用

### 9.3 ネットワーク通信

- Gemini API: HTTPS (TLS 1.2+) 必須
- タイムアウト設定: 30秒
- リトライ制御: 最大3回 (Exponential Backoff)

---

## 10. テスト戦略

### 10.1 単体テスト

- 対象: track_analyzer, prompt_generator
- ツール: pytest
- カバレッジ目標: 80%以上

### 10.2 統合テスト

- 対象: mixer_core ⇔ audio_engine/track_analyzer
- 手法: モック + 実機テスト

### 10.3 システムテスト

- VCI-100実機接続テスト
- 長時間動作テスト (8時間以上)
- メモリリーク検証

---

## 11. デプロイメント

### 11.1 動作環境

| 項目 | 要件 |
| ---- | ---- |
| OS | Windows 10/11 (64-bit), macOS 11+ |
| Python | 3.10+ |
| RAM | 4GB以上 |
| ディスク | 2GB以上空き容量 |
| MIDI | VCI-100 (USB接続) |

### 11.2 インストール手順

```bash
# 1. リポジトリクローン
git clone https://github.com/user/vci-100-ai-mixer.git
cd vci-100-ai-mixer

# 2. 仮想環境作成
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. 依存関係インストール
pip install -r requirements.txt

# 4. BASS DLLコピー (Windows)
# bass.dll, bass_fx.dll をプロジェクトルートに配置

# 5. 環境変数設定
export GEMINI_API_KEY="your-api-key-here"

# 6. 起動
python app.py
```

---

## 12. 保守・運用

### 12.1 ログ管理

- ログレベル: DEBUG/INFO/WARNING/ERROR
- 出力先: 標準出力 + ファイル (`logs/mixer.log`)
- ローテーション: 日次 (最大7日分保持)

### 12.2 バックアップ対象

- `analysis_cache.json`
- `knowledge_base.json`
- `tracks/` フォルダ

### 12.3 トラブルシューティング

| 症状 | 原因 | 対処法 |
| ---- | ---- | ------ |
| 音が出ない | BASS初期化失敗 | デバイス確認、DLL再配置 |
| MIDIが反応しない | VCI-100未接続 | USB接続確認、ドライバ再インストール |
| Promptが生成されない | API Key未設定 | 環境変数確認 |
| 解析が遅い | Librosa処理時間 | SSD使用、Python最適化 |

---

**End of Document**
