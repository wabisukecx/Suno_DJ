"""
Prompt Generator Worker
=======================

非同期プロンプト生成を担当するQThreadワーカー。
GUIをブロックせずにGemini APIを呼び出す。
"""

import logging
from PyQt6.QtCore import QThread, pyqtSignal
from core.prompt_generator import PromptGenerator

logger = logging.getLogger(__name__)


class PromptGeneratorWorker(QThread):
    """
    非同期プロンプト生成ワーカー
    
    GUIをブロックせずにGemini APIを呼び出す実装
    """
    
    # シグナル
    finished = pyqtSignal(dict)       # 生成完了
    error = pyqtSignal(str)           # エラー発生
    status_changed = pyqtSignal(str)  # ステータス変更
    
    def __init__(self, generator: PromptGenerator, parent=None):
        super().__init__(parent)
        self.generator = generator
        self.current_analysis = None
        self.deck_a_analysis = None
        self.deck_b_analysis = None
        self.energy_target = None
        self.preferred_genre = None
        self.vocal = True
        self._should_run = False
    
    def setup(
        self,
        current_analysis: dict,
        deck_a_analysis: dict = None,
        deck_b_analysis: dict = None,
        energy_target: int = None,
        preferred_genre: str = None,
        vocal: bool = True
    ):
        """生成パラメータを設定"""
        self.current_analysis = current_analysis
        self.deck_a_analysis = deck_a_analysis
        self.deck_b_analysis = deck_b_analysis
        self.energy_target = energy_target
        self.preferred_genre = preferred_genre
        self.vocal = vocal
        self._should_run = True
    
    def run(self):
        """バックグラウンドでプロンプト生成を実行"""
        # データチェック
        if not self._should_run:
            return
            
        if not self.current_analysis:
            # 【重要】データ不足を通知
            error_msg = "No track analysis data provided for generation."
            logger.error(error_msg)
            self.error.emit(error_msg)
            self.status_changed.emit("⚠️ No Track Data")
            return
        
        try:
            self.status_changed.emit("⏳ Generating...")
            
            result = self.generator.generate_prompt(
                current_track_analysis=self.current_analysis,
                deck_a_analysis=self.deck_a_analysis,
                deck_b_analysis=self.deck_b_analysis,
                energy_target=self.energy_target,
                preferred_genre=self.preferred_genre,
                vocal=self.vocal
            )
            
            self.status_changed.emit("✓ Prompt Ready")
            self.finished.emit(result)
            
        except Exception as e:
            logger.error(f"Worker error: {e}", exc_info=True)
            self.error.emit(str(e))
            self.status_changed.emit("✗ Generation Failed")
        
        finally:
            self._should_run = False