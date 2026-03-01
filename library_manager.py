"""
LibraryManager — ライブラリ管理モジュール
==========================================
mixer_core.py から抽出したライブラリ管理ロジック。
Delegation パターンを採用し、AIVCIMixer から分離された純粋な Python クラス。

主な責務:
  - 楽曲フォルダのスキャンと track_list 管理
  - 未解析トラックのバックグラウンド逐次解析
  - HotFolder 経由の新規ファイル受け取りと解析
  - GUI 向けのコールバック通知（シグナル emit）
  - 相対エネルギー Z-score の再計算

設計方針:
  - QObject を継承しない（PyQt6 シグナルは AIVCIMixer 側が保持）
  - コールバックは __init__ で受け取り、シグナルを lambda でラップして渡す
  - track_list へのアクセスは Lock で保護する（スレッドセーフ）
  - 500行ルール遵守・単一責任原則
"""

import os
import logging
from pathlib import Path
from threading import Thread, Lock
from typing import Callable

logger = logging.getLogger(__name__)

# サポートされているオーディオ拡張子（mixer_core.py と同じ定義）
SUPPORTED_AUDIO_EXTENSIONS = (".mp3", ".wav", ".flac", ".ogg", ".m4a")


class LibraryManager:
    """
    楽曲ライブラリのスキャン・解析・更新通知を担当するクラス。

    AIVCIMixer から以下のロジックを抽出:
      - refresh_library()
      - _scan_files()
      - _analyze_unanalyzed_tracks()
      - _emit_library_update()
      - apply_relative_energy_evaluation()
      - analyze_track()
      - on_file_moved()
    """

    def __init__(
        self,
        tracks_folder: str,
        analyzer,
        on_library_updated: Callable[[list], None],
        on_status_updated:  Callable[[str], None],
        on_track_added:     Callable[[str], None],
    ):
        """
        Args:
            tracks_folder:       楽曲フォルダの絶対パス
            analyzer:            TrackAnalyzer インスタンス
            on_library_updated:  ライブラリ更新時コールバック (track_list を渡す)
            on_status_updated:   ステータス文字列通知コールバック
            on_track_added:      新規ファイル追加通知コールバック (filename を渡す)
        """
        self.tracks_folder = tracks_folder
        self.analyzer = analyzer

        # コールバック（AIVCIMixer のシグナルを lambda でラップして渡す）
        self._on_library_updated = on_library_updated
        self._on_status_updated  = on_status_updated
        self._on_track_added     = on_track_added

        # 状態
        self.track_list: list       = []
        self.track_list_lock: Lock  = Lock()
        self._analyzing: bool       = False   # 再帰防止フラグ

    # ─────────────────────────────────────────────────────────────────
    # 公開メソッド（AIVCIMixer から呼ぶ）
    # ─────────────────────────────────────────────────────────────────

    def refresh_library(self) -> None:
        """ライブラリをスキャンし、未解析トラックを自動解析する。"""
        logger.info("LibraryManager.refresh_library: START")
        root = self.tracks_folder
        if not os.path.exists(root):
            os.makedirs(root)
            logger.info(f"Created tracks folder: {root}")

        track_list_copy, unanalyzed = self._scan_files(root)
        self._on_library_updated(track_list_copy)
        logger.info("library_updated callback called")

        if unanalyzed and not self._analyzing:
            count = len(unanalyzed)
            logger.info(f"Found {count} unanalyzed tracks. Starting auto-analysis...")
            self._on_status_updated(f"Analyzing {count} tracks...")
            self._analyze_unanalyzed_tracks(unanalyzed)

    def analyze_track(self, filepath: str, force: bool = False) -> None:
        """単一トラックを強制解析し、完了後にライブラリを更新する（GUI 向け）。"""
        def run():
            filename = os.path.basename(filepath)
            logger.info(f"Analyzing track: {filename}")
            self._on_status_updated(f"Analyzing: {filename}")
            self.analyzer.analyze_track(filepath, force_reanalyze=force)
            self._emit_library_update()
            self._on_status_updated("Analysis complete")

        Thread(target=run, daemon=True).start()

    def apply_relative_energy_evaluation(self) -> None:
        """
        全トラックの相対エネルギーレベルを Z-score で再計算する。

        注意: 呼び出し側で既に track_list_lock を取得済みであること。
        ライブラリが5曲以上の場合に有効。
        """
        if not self.track_list:
            return

        analyzed_tracks = [t for t in self.track_list if t.get('analyzed')]
        if len(analyzed_tracks) < 2:
            return

        self.analyzer.recalculate_relative_energy(analyzed_tracks)

        for track in self.track_list:
            if track.get('analyzed'):
                h = self.analyzer._get_file_hash(track['filepath'])
                cached = self.analyzer.cache.get(h)
                if cached and 'energy' in cached:
                    track['energy'] = cached['energy']

    def on_file_moved(self, src: str, dst: str) -> None:
        """
        HotFolderWatcher.file_moved シグナルのコールバック。
        移動された新規ファイルを解析してライブラリに追加する。
        """
        filename = os.path.basename(dst)
        logger.info(f"HotFolder: File moved to library: {filename}")
        self._on_track_added(filename)

        def run():
            logger.info(f"Auto-analyzing new track: {filename}")
            self._on_status_updated(f"Analyzing new track: {filename}")
            self.analyzer.analyze_track(dst, force_reanalyze=True)
            self._emit_library_update()
            self._on_status_updated(f"New track ready: {filename}")

        Thread(target=run, daemon=True).start()

    def get_track_list_copy(self) -> list:
        """ロックを取得してから track_list のコピーを返す（スレッドセーフ）。"""
        with self.track_list_lock:
            return list(self.track_list)

    # ─────────────────────────────────────────────────────────────────
    # 内部メソッド
    # ─────────────────────────────────────────────────────────────────

    def _scan_files(self, root: str) -> tuple[list, list]:
        """
        root フォルダをスキャンし track_list を再構築する。

        Returns:
            (track_list_copy, unanalyzed):
                GUI通知用リストと未解析パスリストのタプル
        """
        files = [
            f for f in os.listdir(root)
            if f.lower().endswith(SUPPORTED_AUDIO_EXTENSIONS)
        ]
        logger.info(f"Found {len(files)} audio files in {root}")

        unanalyzed = []
        with self.track_list_lock:
            self.track_list = []
            for f in files:
                path = os.path.join(root, f)
                h = self.analyzer._get_file_hash(path)
                cached = self.analyzer.cache.get(h)
                item = {'filename': f, 'filepath': path, 'analyzed': cached is not None}
                if cached:
                    item.update(cached)
                else:
                    unanalyzed.append(path)
                self.track_list.append(item)

            # ロック内で相対エネルギーを再計算（lock 取得済み前提）
            self.apply_relative_energy_evaluation()
            track_list_copy = list(self.track_list)

        return track_list_copy, unanalyzed

    def _analyze_unanalyzed_tracks(self, paths: list) -> None:
        """未解析トラックをバックグラウンドスレッドで順次解析する。"""
        def run():
            self._analyzing = True
            try:
                total = len(paths)
                for i, path in enumerate(paths, 1):
                    filename = os.path.basename(path)
                    logger.info(f"Auto-analyzing ({i}/{total}): {filename}")
                    self._on_status_updated(f"Analyzing ({i}/{total}): {filename}")
                    try:
                        self.analyzer.analyze_track(path)
                    except Exception as e:
                        logger.error(f"Failed to analyze {filename}: {e}")
                logger.info(f"Auto-analysis complete: {total} tracks processed")
                self._on_status_updated(f"Analysis complete: {total} tracks")
                self._emit_library_update()
            finally:
                self._analyzing = False

        Thread(target=run, daemon=True).start()

    def _emit_library_update(self) -> None:
        """解析済みデータでライブラリを再構築してコールバックで通知する。"""
        root = self.tracks_folder
        if not os.path.exists(root):
            return
        track_list_copy, _ = self._scan_files(root)
        self._on_library_updated(track_list_copy)
