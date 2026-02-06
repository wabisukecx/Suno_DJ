# Phase 5: テスト設計書

VCI-100 AI DJ Mixer プロジェクトの包括的なテスト設計書を作成します。

## 1. テスト戦略概要

### 1.1 テスト範囲

- **単体テスト (Unit Tests)**: 個別モジュール・関数の動作検証
- **統合テスト (Integration Tests)**: モジュール間連携の検証
- **システムテスト (System Tests)**: エンドツーエンドの動作検証

### 1.2 テスト環境

- **OS**: Windows 10/11, macOS 12+, Ubuntu 22.04+
- **Python**: 3.9以上
- **ハードウェア**: Vestax VCI-100 (統合/システムテストで使用)
- **テストデータ**: 様々なBPM/キー/ジャンルの音楽ファイル

---

## 2. 単体テスト (Unit Tests)

### 2.1 track_analyzer.py

#### Test Case UT-01: BPM検出精度

```python
def test_bpm_detection_accuracy():
    """
    目的: BPM検出の精度を検証
    入力: 既知のBPMを持つテストトラック (120 BPM, 128 BPM, 140 BPM)
    期待値: 検出BPMが±2 BPM以内の誤差
    """
```

#### Test Case UT-02: キー検出

```python
def test_key_detection():
    """
    目的: 音楽キー検出の正確性
    入力: 既知のキーを持つトラック (C major, A minor等)
    期待値: 正しいキー表記 (Camelot表記含む)
    """
```

#### Test Case UT-03: ジャンル分類

```python
def test_genre_classification():
    """
    目的: ジャンル分類の妥当性
    入力: 明確なジャンル特性を持つトラック
    期待値: 適切なジャンルラベル
    """
```

#### Test Case UT-04: エネルギー計算

```python
def test_energy_calculation():
    """
    目的: エネルギーレベル計算の一貫性
    入力: 静かなトラック、激しいトラック
    期待値: 0.0～1.0の範囲、相対的な差が適切
    """
```

#### Test Case UT-05: 分析キャッシュ

```python
def test_analysis_cache():
    """
    目的: JSONキャッシュの読み書き
    入力: 分析済みトラック
    期待値: 2回目の分析が高速化、データ整合性維持
    """
```

### 2.2 audio_engine.py

#### Test Case UT-06: オーディオ読み込み

```python
def test_audio_loading():
    """
    目的: 各種フォーマットの読み込み
    入力: MP3, WAV, FLAC, AAC
    期待値: エラーなく読み込み完了
    """
```

#### Test Case UT-07: EQフィルター適用

```python
def test_eq_filter_application():
    """
    目的: EQ処理の正確性
    入力: 各バンド (Hi/Mid/Lo) の±12dB調整
    期待値: 周波数応答が期待通り変化
    """
```

#### Test Case UT-08: クロスフェーダーカーブ

```python
def test_crossfader_curve():
    """
    目的: Constant Powerカーブの検証
    入力: クロスフェーダー位置 0.0～1.0
    期待値: √(cos²θ + sin²θ) = 1 (エネルギー保存)
    """
```

#### Test Case UT-09: レイテンシ測定

```python
def test_audio_latency():
    """
    目的: オーディオ処理遅延の測定
    入力: テスト信号
    期待値: <15ms のレイテンシ
    """
```

#### Test Case UT-10: Auto Gain計算

```python
def test_auto_gain_calculation():
    """
    目的: 自動ゲイン調整の正確性
    入力: 様々なラウドネスのトラック
    期待値: -18dBFS ±1dB に正規化
    """
```

### 2.3 prompt_generator.py

#### Test Case UT-11: プロンプト生成

```python
def test_prompt_generation():
    """
    目的: AIプロンプト生成の妥当性
    入力: 現在再生中のトラック情報
    期待値: 構造化されたプロンプト (BPM/Key/Genre/Mood含む)
    """
```

#### Test Case UT-12: API呼び出しエラーハンドリング

```python
def test_api_error_handling():
    """
    目的: API障害時の適切な処理
    入力: 無効なAPIキー、ネットワーク切断
    期待値: 例外を適切にキャッチ、ユーザーへ通知
    """
```

### 2.4 midi_controller.py

#### Test Case UT-13: MIDIメッセージパース

```python
def test_midi_message_parsing():
    """
    目的: MIDIメッセージの正確な解釈
    入力: VCI-100からの各種CCメッセージ
    期待値: 正しいコントロール識別とパラメータ抽出
    """
```

#### Test Case UT-14: コントロールマッピング

```python
def test_control_mapping():
    """
    目的: 物理コントローラーと機能のマッピング
    入力: ノブ/フェーダー操作
    期待値: 対応する内部パラメータが変化
    """
```

---

## 3. 統合テスト (Integration Tests)

### 3.1 Audio Engine × Track Analyzer

#### Test Case IT-01: 分析→再生フロー

```bash
目的: トラック分析結果を使用した再生
手順:
  1. トラックファイルを分析
  2. 分析結果を audio_engine に渡す
  3. 再生開始
期待値: BPM/Key情報が正しく表示され、再生が開始される
```

#### Test Case IT-02: EQ設定の永続化

```bash
目的: EQ設定がトラック切り替え時に保持される
手順:
  1. Deck A で EQ 調整
  2. 別トラックをロード
  3. EQ設定を確認
期待値: デフォルト値にリセットされる (意図通り)
```

### 3.2 MIDI Controller × Audio Engine

#### Test Case IT-03: リアルタイムEQ制御

```bash
目的: VCI-100ノブ操作がEQに即座に反映
手順:
  1. トラック再生中
  2. Hi/Mid/Lo EQノブを回す
  3. 音質変化を確認
期待値: <50ms で音質が変化、GUI表示も連動
```

#### Test Case IT-04: クロスフェーダー制御

```bash
目的: クロスフェーダーによるスムーズなミックス
手順:
  1. Deck A/B で異なるトラック再生
  2. クロスフェーダーを左→右に移動
  3. 音量バランスを確認
期待値: Constant Power カーブでスムーズな音量遷移
```

### 3.3 GUI × Backend

#### Test Case IT-05: デッキウィジェット更新

```bash
目的: バックエンド状態変化がGUIに反映
手順:
  1. トラックをロード
  2. 再生/一時停止/停止操作
  3. GUI表示を確認
期待値: 再生位置、波形表示、BPM/Key情報がリアルタイム更新
```

#### Test Case IT-06: ライブラリ管理

```bash
目的: ライブラリの追加/削除/更新
手順:
  1. 新規トラック追加
  2. 自動分析完了を待つ
  3. ライブラリに表示されることを確認
期待値: メタデータが正しく表示され、ソート可能
```

### 3.4 Prompt Generator × Track Analyzer

#### Test Case IT-07: エネルギーフロー分析

```bash
目的: 現在のトラックから次のトラックのプロンプト生成
手順:
  1. エネルギーレベル高のトラック再生
  2. プロンプト生成リクエスト
  3. 生成されたプロンプトを確認
期待値: エネルギーレベルが相対評価され、適切な次トラック提案
```

---

## 4. システムテスト (System Tests)

### 4.1 エンドツーエンドシナリオ

#### Test Case ST-01: 基本DJセット実行

```bash
シナリオ: 3トラックのDJセット
手順:
  1. アプリ起動、VCI-100接続確認
  2. トラック1をDeck Aにロード、再生開始
  3. トラック2をDeck Bにロード、BPM同期
  4. クロスフェーダーでミックス
  5. トラック3をDeck Aに再ロード
  6. 同様にミックス
期待値: 
  - 音切れなし
  - スムーズなミックス遷移
  - BPM/Key情報が常に正確
```

#### Test Case ST-02: AI支援ワークフロー

```bash
シナリオ: AI提案を使用した4トラックセット
手順:
  1. トラック1再生
  2. 「次のトラック提案」ボタン押下
  3. AIプロンプト確認・編集
  4. Sunoで生成 (手動)
  5. 生成トラックをホットフォルダに保存
  6. 自動分析完了を待つ
  7. 生成トラックでミックス
  8. 上記を3回繰り返す
期待値:
  - プロンプトが現在のトラックと調和
  - 生成トラックが自動検出・分析される
  - BPM/Key互換性が高い
```

### 4.2 負荷テスト

#### Test Case ST-03: 長時間再生

```bash
目的: メモリリーク/安定性検証
手順:
  1. 2時間連続で10トラック以上ミックス
  2. CPU/メモリ使用率をモニタリング
期待値:
  - メモリ使用量が安定
  - CPU使用率 <30%
  - 音質劣化なし
```

#### Test Case ST-04: 大規模ライブラリ

```bash
目的: スケーラビリティ検証
手順:
  1. 500トラック以上のライブラリ作成
  2. 全トラック分析
  3. 検索/フィルター/ソート操作
期待値:
  - GUI応答性維持 (<200ms)
  - 分析キャッシュが有効機能
```

### 4.3 互換性テスト

#### Test Case ST-05: クロスプラットフォーム

```bash
目的: Windows/macOS/Linux での動作確認
手順: 各OS上で ST-01, ST-02 を実行
期待値: 全プラットフォームで同等の動作
```

#### Test Case ST-06: 様々なオーディオフォーマット

```bash
目的: ファイル形式対応確認
入力: MP3 (320kbps/VBR), WAV (16/24bit), FLAC, AAC, OGG
期待値: 全形式で正常再生・分析
```

### 4.4 障害復旧テスト

#### Test Case ST-07: MIDI切断/再接続

```bash
手順:
  1. 再生中にVCI-100 USBケーブル抜く
  2. エラー表示を確認
  3. ケーブル再接続
  4. 操作再開
期待値: 
  - 切断時も再生継続
  - 再接続時に自動復旧
```

#### Test Case ST-08: API障害時の動作

```bash
手順:
  1. ネットワーク切断
  2. プロンプト生成試行
  3. エラーメッセージ確認
期待値: 
  - 適切なエラー通知
  - アプリがクラッシュしない
  - 他機能は正常動作継続
```

---

## 5. テスト実行計画

### 5.1 自動テストスイート構成

```bash
tests/
├── unit/
│   ├── test_track_analyzer.py      # UT-01～UT-05
│   ├── test_audio_engine.py        # UT-06～UT-10
│   ├── test_prompt_generator.py    # UT-11～UT-12
│   └── test_midi_controller.py     # UT-13～UT-14
├── integration/
│   ├── test_audio_analysis.py      # IT-01～IT-02
│   ├── test_midi_audio.py          # IT-03～IT-04
│   ├── test_gui_backend.py         # IT-05～IT-06
│   └── test_ai_workflow.py         # IT-07
└── system/
    ├── test_dj_workflow.py          # ST-01～ST-02
    ├── test_performance.py          # ST-03～ST-04
    └── test_compatibility.py        # ST-05～ST-08
```

### 5.2 テストデータセット

```bash
test_data/
├── audio/
│   ├── known_bpm/
│   │   ├── 120bpm.mp3
│   │   ├── 128bpm.wav
│   │   └── 140bpm.flac
│   ├── known_key/
│   │   ├── c_major.mp3
│   │   ├── a_minor.mp3
│   │   └── g_major.wav
│   └── genre/
│       ├── house.mp3
│       ├── techno.mp3
│       └── trance.mp3
├── midi/
│   └── vci100_test_sequence.mid
└── expected_results/
    └── analysis_results.json
```

### 5.3 実行コマンド

```bash
# 全単体テスト実行
pytest tests/unit/ -v

# 特定モジュールのテスト
pytest tests/unit/test_audio_engine.py -v

# カバレッジ付き実行
pytest --cov=. --cov-report=html tests/

# 統合テスト (VCI-100必要)
pytest tests/integration/ -v --require-hardware

# システムテスト (フルセットアップ必要)
pytest tests/system/ -v --slow
```

---

## 6. 完了基準

### 6.1 Phase 5 完了条件

- ✅ 単体テスト14件すべて作成・実装
- ✅ 統合テスト7件すべて実行可能
- ✅ システムテスト8件の手順書完成
- ✅ テストカバレッジ >80%
- ✅ CI/CD パイプライン構築 (GitHub Actions)

### 6.2 品質ゲート

- 全単体テスト合格
- 統合テスト合格率 >95%
- クリティカルなシステムテスト (ST-01, ST-02) 合格
- メモリリークなし
- レイテンシ要件達成 (<15ms)

---

このテスト設計書に基づいて実装を進めますか?具体的なテストコードの作成が必要であれば、優先順位の高いテストケースから順次実装していきます。
