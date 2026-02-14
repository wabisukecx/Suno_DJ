"""
ホットフォルダ監視モジュール（Phase 6）
=====================================

ダウンロードフォルダを監視し、新しいmp3ファイルを
tracksフォルダに自動移動する。

3層防御:
1. ファイルサイズ安定待機（ダウンロード中を掴まない）
2. ファイルロック確認（書き込み中を掴まない）
3. 拡張子・最小サイズチェック（不正ファイル除外）
"""

import time
import shutil
import logging
from pathlib import Path
from typing import Optional, Callable, Set
from threading import Lock

from PyQt6.QtCore import QThread, pyqtSignal

# Supported audio file extensions
SUPPORTED_AUDIO_PATTERNS = ["*.mp3", "*.wav", "*.flac", "*.ogg", "*.m4a"]

logger = logging.getLogger(__name__)


class HotFolderWatcher(QThread):
    """
    ホットフォルダ監視クラス
    
    ダウンロードフォルダの新規mp3を検知し、
    tracksフォルダへ自動移動する。
    """
    
    # シグナル
    file_detected = pyqtSignal(str)      # ファイル検知（ファイル名）
    file_moved = pyqtSignal(str, str)    # 移動完了（元パス、新パス）
    error_occurred = pyqtSignal(str)     # エラー発生
    status_changed = pyqtSignal(str)     # ステータス変更
    
    # 設定
    POLL_INTERVAL = 2.0          # 監視間隔（秒）
    SIZE_STABLE_WAIT = 1.0       # サイズ安定待機（秒）
    SIZE_STABLE_CHECKS = 3       # サイズ安定確認回数
    MIN_FILE_SIZE = 100 * 1024   # 最小ファイルサイズ（100KB）
    LOCK_CHECK_TIMEOUT = 5.0     # ロック確認タイムアウト（秒）
    
    def __init__(
        self,
        watch_folder: str = None,
        destination_folder: str = None,
        parent=None
    ):
        super().__init__(parent)
        
        # 監視フォルダ（デフォルト: ~/Downloads）
        if watch_folder is None:
            watch_folder = str(Path.home() / "Downloads")
        self.watch_folder = Path(watch_folder)
        
        # 移動先フォルダ
        self.destination_folder = Path(destination_folder) if destination_folder else None
        
        # 状態管理
        self._running = False
        self._known_files: Set[str] = set()  # 既知のファイル（起動時に存在したもの）
        self._processing_files: Set[str] = set()  # 処理中のファイル
        self._lock = Lock()
        
        # コールバック（オプション）
        self.on_file_added: Optional[Callable[[str], None]] = None
        
        logger.info(f"HotFolderWatcher initialized")
        logger.info(f"  Watch folder: {self.watch_folder}")
        logger.info(f"  Destination: {self.destination_folder}")
    
    def set_destination(self, folder: str):
        """移動先フォルダを設定"""
        self.destination_folder = Path(folder)
        logger.info(f"Destination folder set: {self.destination_folder}")
    
    def _scan_existing_files(self) -> Set[str]:
        """起動時の既存ファイルをスキャン"""
        existing = set()
        if self.watch_folder.exists():
            for pattern in SUPPORTED_AUDIO_PATTERNS:
                for f in self.watch_folder.glob(pattern):
                    existing.add(str(f))
        return existing
    
    def _is_file_ready(self, filepath: Path) -> bool:
        """
        ファイルが処理可能か確認（3層防御）
        
        1. ファイルサイズ安定待機
        2. ファイルロック確認
        3. 最小サイズチェック
        """
        try:
            # 1. ファイルサイズ安定待機
            prev_size = -1
            stable_count = 0
            
            for _ in range(self.SIZE_STABLE_CHECKS * 2):  # 最大6回チェック
                if not filepath.exists():
                    return False
                
                current_size = filepath.stat().st_size
                
                if current_size == prev_size and current_size > 0:
                    stable_count += 1
                    if stable_count >= self.SIZE_STABLE_CHECKS:
                        break
                else:
                    stable_count = 0
                
                prev_size = current_size
                time.sleep(self.SIZE_STABLE_WAIT)
            
            if stable_count < self.SIZE_STABLE_CHECKS:
                logger.debug(f"File size not stable: {filepath.name}")
                return False
            
            # 2. ファイルロック確認（読み取りオープン試行）
            start_time = time.time()
            while time.time() - start_time < self.LOCK_CHECK_TIMEOUT:
                try:
                    with open(filepath, 'rb') as f:
                        # 先頭を読めれば書き込み完了
                        f.read(1024)
                    break
                except (IOError, PermissionError):
                    time.sleep(0.5)
            else:
                logger.debug(f"File still locked: {filepath.name}")
                return False
            
            # 3. 最小サイズチェック
            if filepath.stat().st_size < self.MIN_FILE_SIZE:
                logger.debug(f"File too small: {filepath.name} ({filepath.stat().st_size} bytes)")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking file readiness: {e}")
            return False
    
    def _move_file(self, source: Path) -> Optional[Path]:
        """
        ファイルを移動先フォルダへ移動
        
        同名ファイルが存在する場合は連番を付与
        """
        if not self.destination_folder:
            logger.error("Destination folder not set")
            return None
        
        if not self.destination_folder.exists():
            self.destination_folder.mkdir(parents=True, exist_ok=True)
        
        # 移動先パスを決定（重複時は連番）
        dest = self.destination_folder / source.name
        
        if dest.exists():
            base = source.stem
            ext = source.suffix
            counter = 1
            while dest.exists():
                dest = self.destination_folder / f"{base}_{counter}{ext}"
                counter += 1
        
        try:
            shutil.move(str(source), str(dest))
            logger.info(f"File moved: {source.name} -> {dest}")
            return dest
        except Exception as e:
            logger.error(f"Failed to move file: {e}")
            return None
    
    def _process_new_file(self, filepath: Path):
        """新規ファイルを処理"""
        filepath_str = str(filepath)
        
        # 重複処理防止
        with self._lock:
            if filepath_str in self._processing_files:
                return
            self._processing_files.add(filepath_str)
        
        try:
            logger.info(f"New mp3 detected: {filepath.name}")
            self.file_detected.emit(filepath.name)
            self.status_changed.emit(f"🎵 Detected: {filepath.name}")
            
            # ファイル準備完了を待機
            if not self._is_file_ready(filepath):
                logger.warning(f"File not ready, skipping: {filepath.name}")
                self.status_changed.emit(f"⏳ Waiting: {filepath.name}")
                return
            
            # ファイル移動
            self.status_changed.emit(f"📂 Moving: {filepath.name}")
            new_path = self._move_file(filepath)
            
            if new_path:
                self.file_moved.emit(str(filepath), str(new_path))
                self.status_changed.emit(f"✅ Added: {new_path.name}")
                
                # コールバック呼び出し
                if self.on_file_added:
                    self.on_file_added(str(new_path))
            else:
                self.error_occurred.emit(f"Failed to move: {filepath.name}")
                self.status_changed.emit(f"❌ Failed: {filepath.name}")
        
        finally:
            with self._lock:
                self._processing_files.discard(filepath_str)
    
    def run(self):
        """監視ループ"""
        logger.info("HotFolderWatcher started")
        self._running = True
        
        # 起動時の既存ファイルを記録（これらは無視）
        self._known_files = self._scan_existing_files()
        logger.info(f"Ignoring {len(self._known_files)} existing mp3 files")
        
        self.status_changed.emit("👁 Watching Downloads folder...")
        
        while self._running:
            try:
                if self.watch_folder.exists() and self.destination_folder:
                    # 新しいmp3ファイルを検索
                    current_files = set()
                    for pattern in SUPPORTED_AUDIO_PATTERNS:
                        for f in self.watch_folder.glob(pattern):
                            filepath_str = str(f)
                            current_files.add(filepath_str)
                            
                            # 新規ファイルを検出
                            if filepath_str not in self._known_files:
                                self._process_new_file(f)
                                self._known_files.add(filepath_str)
                    
                    # 削除されたファイルをknown_filesから除去
                    self._known_files = self._known_files.intersection(current_files)
            
            except Exception as e:
                logger.error(f"Error in watch loop: {e}")
                self.error_occurred.emit(str(e))
            
            time.sleep(self.POLL_INTERVAL)
        
        logger.info("HotFolderWatcher stopped")
        self.status_changed.emit("⏹ Watcher stopped")
    
    def stop(self):
        """監視を停止"""
        self._running = False
        logger.info("Stopping HotFolderWatcher...")
    
    def is_watching(self) -> bool:
        """監視中かどうか"""
        return self._running


# テスト用
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    
    logging.basicConfig(level=logging.INFO)
    
    app = QApplication(sys.argv)
    
    # テスト用の監視先
    test_destination = Path.home() / "test_tracks"
    test_destination.mkdir(exist_ok=True)
    
    watcher = HotFolderWatcher(destination_folder=str(test_destination))
    
    # シグナル接続
    watcher.file_detected.connect(lambda f: print(f"[DETECTED] {f}"))
    watcher.file_moved.connect(lambda s, d: print(f"[MOVED] {s} -> {d}"))
    watcher.error_occurred.connect(lambda e: print(f"[ERROR] {e}"))
    watcher.status_changed.connect(lambda s: print(f"[STATUS] {s}"))
    
    print(f"Watching: {watcher.watch_folder}")
    print(f"Destination: {watcher.destination_folder}")
    print("Drop an mp3 file into Downloads folder to test...")
    print("Press Ctrl+C to stop")
    
    watcher.start()
    
    # 30秒後に自動停止（テスト用）
    QTimer.singleShot(30000, lambda: (watcher.stop(), app.quit()))
    
    sys.exit(app.exec())
