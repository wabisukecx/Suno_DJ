# VCI-100 AI DJ Mixer

## Legacy Hardware × Generative AI × Modern Audio Engine

Vestaxの名機 **VCI-100** を現代のPC環境で蘇らせる、AI搭載型DJミキシングシステムです。
再生中の楽曲をリアルタイムで解析し、Google **Gemini** と連携して **Suno AI** 用の楽曲生成プロンプト（歌詞・スタイル・タイトル）を自動提案します。

---

## 主な機能 (Features)

### 1. AIクリエイティブ・アシスタント

* **自動プロンプト生成**: 現在の曲（Deck A）から次の曲（Deck B）への展開を読み取り、ミックスに最適な「次の曲」をSunoで生成するためのプロンプトを提案します。
* **コンテキスト認識**: BPM、キー、エネルギー、ジャンルの相性をAIが推論（Reasoning）し、音楽的に妥当なトランジションを設計します。

### 2. 高度なオーディオエンジン

* **Un4seen BASS Powered**: PythonながらC言語ネイティブレベルの低レイテンシ再生と正確なミキシングを実現。
* **Smart Looping**: BPM同期によるパーフェクトな4小節ループ（クリックノイズなし）。
* **High-Res EQ & Filter**: 3バンドEQとアイソレーター仕様のフィルターを搭載。

### 3. 可視化と解析 (Visualization & Analysis)

* **Energy Flow Panel**: 楽曲の「盛り上がり（Energy）」を上下2段で同期表示。ブレイクやドロップのタイミングを一目で把握できます。
* **Automatic Analysis**: 楽曲ロード時にBPM、Key、Energy Profileを自動抽出・キャッシュ化。

### 4. ホットフォルダ連携 (Hot Folder Watcher)

* 指定したダウンロードフォルダを監視し、Sunoなどで生成・DLしたMP3ファイルを自動でライブラリに取り込み、即座に解析します。

---

## 必要要件 (Requirements)

### ハードウェア

* **Controller**: Vestax VCI-100 (Firmware 1.2 / 1.4 推奨)
* **Computer**: Windows 10/11 (Audio Latencyの観点から推奨)

### ソフトウェア / ライブラリ

* **Python**: 3.11 以上
* **BASS Libraries**:
* `bass.dll` (Core Audio)
* `bass_fx.dll` (Effects & BPM Detection)
* ※ プロジェクトルートに配置する必要があります。

---

## インストール手順 (Installation)

### 1. リポジトリのクローン

```bash
git clone https://github.com/your-repo/vci100-ai-mixer.git
cd vci100-ai-mixer

```

### 2. 依存ライブラリのインストール

```bash
pip install -r requirements.txt

```

### 3. BASSライブラリの配置

Un4seen Developments公式サイトから以下をダウンロードし、プロジェクトルート（`app.py`と同じ場所）に配置してください。

* [BASS](https://www.un4seen.com/) -> `bass.dll` (64-bit版推奨)
* [BASS_FX](https://www.google.com/search?q=https://www.un4seen.com/bass_fx.html) -> `bass_fx.dll` (64-bit版推奨)

### 4. 環境変数の設定 (Gemini API)

Google AI Studio で取得したAPIキーを設定します。

**Windows (PowerShell):**

```powershell
$env:GEMINI_API_KEY="AIzaSy..."

```

または、環境変数設定画面で永続的に追加してください。

---

## 使い方 (Usage)

### アプリケーションの起動

```bash
python app.py

```

※ 引数なしで起動すると、カレントディレクトリの `./tracks` フォルダがライブラリとして使用されます。

### 基本操作

1. **楽曲ロード**: ライブラリ（右パネル）からダブルクリック、またはドラッグ＆ドロップでDeck A/Bにロード。
2. **プレイ**: VCI-100の再生ボタン、またはスペースキーで再生開始。
3. **AIプロンプト生成**:

* 「GENERATE PROMPT」ボタンをクリック。
* 右上のパネルに、Suno AI用の Lyrics / Style / Title が表示されます。
* 各項目のコピーボタンを使い、SunoのWeb画面に貼り付けて生成を行ってください。

1. **新規楽曲の追加**:

* 監視対象フォルダ（デフォルト設定を確認）にMP3ファイルを保存すると、自動的に取り込まれます。

---

## 技術スタック (Tech Stack)

| Category | Technology | Usage |
| --- | --- | --- |
| **GUI Framework** | **PyQt6** | メインインターフェース、シグナル処理 |
| **Audio Engine** | **BASS API** | 再生、DSP、ミキシング (ctypes経由) |
| **Analysis** | **Librosa / NumPy** | 波形解析、特徴量抽出 |
| **AI Model** | **Google Gemini 2.0** | 音楽理論に基づくプロンプト推論 |
| **MIDI** | **python-rtmidi** | ハードウェア制御 |

---

## トラブルシューティング

### Q. VCI-100が反応しない

* 起動時にVCI-100がPCに接続されていることを確認してください。
* ログに `MIDI Connected: VCI-100` と表示されているか確認してください。

### Q. `bass.dll not found` エラーが出る

* `bass.dll` および `bass_fx.dll` が `app.py` と同じ階層にあるか、またはPATHが通っているか確認してください。Pythonが64bit版ならDLLも64bit版である必要があります。

### Q. AI生成がエラーになる

* 環境変数 `GEMINI_API_KEY` が正しく設定されているか確認してください。
* APIの無料枠制限（Rate Limit）にかかっている可能性があります。

---

## License

This project is released under the MIT License.

**Credits:**

* BASS Audio Library: (c) Un4seen Developments Ltd.
