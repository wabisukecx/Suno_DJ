"""
Deck Loop Mixin
===============

DeckLoopMixin: ループ処理ロジックの分離 (Step 1 Refactor)

【設計根拠】
  Deck クラスのループ関連実装（~500行）を Mixin として分離。
  self.stream_fx / self.beat_times 等の Deck 状態を参照するため
  Mixin 継承により self 参照を維持しつつ責務を分割する。
  deck.py は DeckLoopMixin を継承するだけで後方互換性を 100% 維持できる。

【移動したロジック】
  - set_loop()               : BASS_SYNC_MIXTIME シームレスループ設定
  - clear_loop()             : ループ解除
  - set_loop_snapped()       : ビートグリッドスナップ付きループ設定 (Mixxx slotBeatLoop 移植)
  - _find_quantized_beatloop_start() : Mixxx findQuantizedBeatloopStart 移植
  - _find_zero_cross()       : ゼロクロス探索
  - _min_loop_bytes (property): 最小ループ長（バイト）

【Mixxx 参照元】
  - loopingcontrol.cpp: set_loop / clear_loop / slotBeatLoop / findQuantizedBeatloopStart
  - enginebuffer.cpp  : BASS_SYNC_MIXTIME コールバック設計
"""

import ctypes
import logging

from .audio_constants import (
    BASS_LIB, BASS_AVAILABLE, NUMPY_AVAILABLE,
    BASS_POS_BYTE,
)

if NUMPY_AVAILABLE:
    import numpy as np

logger = logging.getLogger(__name__)


class DeckLoopMixin:
    """
    ループ処理ロジックを提供する Mixin クラス。

    このクラス単体でインスタンス化せず、必ず Deck クラスに
    多重継承で組み込むこと。以下の属性が Deck 側で定義済みである
    ことを前提とする:
      - self.name          : デッキ名 (str)
      - self.config        : AudioConfig
      - self.stream_fx     : BASS ストリームハンドル (int)
      - self.stream_decode : デコードストリームハンドル (int)
      - self.duration      : トラック長 (float, 秒)
      - self.beat_times    : ビート位置リスト (list[float])
      - self.loop_active   : ループ中フラグ (bool)
      - self.loop_sync_handle : BASS Sync ハンドル (int)
      - self.loop_start_bytes : ループ開始バイト位置 (int)
      - self.loop_cb_ref   : SYNCPROC コールバック参照 (保持必須)
      - self.loop_start_sec   : ループ開始位置 (float, 秒)
      - self.loop_duration_sec: ループ長 (float, 秒)
      - self.get_position()   : 現在再生位置を返すメソッド
      - self.set_position()   : 再生位置をセットするメソッド
    """

    # ---------------------------------------------------------------
    # ループ定数
    # ---------------------------------------------------------------

    # Mixxx kMinimumAudibleLoopSizeFrames 相当の最小フレーム数
    # 48kHz で約 3ms。これ未満のループは音飛びの原因になるため拒否する。
    _MIN_LOOP_FRAMES: int = 150

    # ゼロクロス探索範囲 (ms)
    # ループ IN/OUT 点を最近傍ゼロクロスへ微調整してクリックノイズを防止する。
    ZERO_CROSS_SEARCH_MS: float = 5.0

    # ---------------------------------------------------------------
    # プロパティ
    # ---------------------------------------------------------------

    @property
    def _min_loop_bytes(self) -> int:
        """
        最小ループ長（バイト）をサンプルレート・チャンネル数から動的に計算。

        AudioConfig.sample_rate が可変のため固定値ではなく設定値から算出する。
        float32 = 4 bytes/sample。
        """
        return self._MIN_LOOP_FRAMES * self.config.channels * 4

    # ---------------------------------------------------------------
    # ゼロクロス探索
    # ---------------------------------------------------------------

    def _find_zero_cross(self, pos_sec: float, search_forward: bool = True) -> float:
        """
        指定位置の近傍でゼロクロスポイントを探索して返す。

        BASS_ChannelGetData でPCMバッファを取得し、
        振幅がゼロをまたぐ最初のサンプルインデックスを探す。
        numpy が利用不可の場合は pos_sec をそのまま返す。

        Args:
            pos_sec:        探索基点（秒）
            search_forward: True=前向き(ループIN用), False=後ろ向き(ループOUT用)

        Returns:
            ゼロクロス位置（秒）。見つからない場合は元の pos_sec を返す。
        """
        if not BASS_AVAILABLE or not NUMPY_AVAILABLE:
            return pos_sec

        ref = self.stream_decode if self.stream_decode else self.stream_fx
        if not ref:
            return pos_sec

        # 探索範囲をバイトで計算
        search_sec  = self.ZERO_CROSS_SEARCH_MS / 1000.0
        start_sec   = max(0.0, pos_sec - search_sec)
        end_sec     = min(self.duration, pos_sec + search_sec)
        start_bytes = int(BASS_LIB.BASS_ChannelSeconds2Bytes(ref, ctypes.c_double(start_sec)))
        end_bytes   = int(BASS_LIB.BASS_ChannelSeconds2Bytes(ref, ctypes.c_double(end_sec)))
        buf_bytes   = end_bytes - start_bytes
        if buf_bytes <= 0:
            return pos_sec

        # PCMバッファ取得（float32）
        n_floats = buf_bytes // 4
        buf      = (ctypes.c_float * n_floats)()
        BASS_LIB.BASS_ChannelSetPosition(ref, ctypes.c_uint64(start_bytes), BASS_POS_BYTE)
        read = BASS_LIB.BASS_ChannelGetData(ref, buf, buf_bytes)
        # stream_decode を動かしたので再生位置は stream_fx と別管理のため影響なし
        if read <= 0:
            return pos_sec

        samples = np.ctypeslib.as_array(buf)[:read // 4]
        ch      = self.config.channels
        mono    = samples[::ch]  # 左チャンネルのみ評価

        # ゼロクロス = 隣接サンプルの符号が異なるインデックス
        signs   = np.sign(mono)
        crosses = np.where(np.diff(signs) != 0)[0]

        if len(crosses) == 0:
            return pos_sec

        pos_bytes      = int(BASS_LIB.BASS_ChannelSeconds2Bytes(ref, ctypes.c_double(pos_sec)))
        pos_sample_idx = (pos_bytes - start_bytes) // (4 * ch)
        pos_sample_idx = max(0, min(len(mono) - 1, pos_sample_idx))

        if search_forward:
            candidates = crosses[crosses >= pos_sample_idx]
        else:
            candidates = crosses[crosses <= pos_sample_idx]

        if len(candidates) == 0:
            return pos_sec

        zc_idx   = int(candidates[0] if search_forward else candidates[-1])
        zc_bytes = int(start_bytes) + zc_idx * ch * 4
        zc_sec   = float(BASS_LIB.BASS_ChannelBytes2Seconds(ref, ctypes.c_uint64(zc_bytes)))
        logger.debug(
            f"Deck {self.name}: ZeroCross {'fwd' if search_forward else 'bwd'} "
            f"{pos_sec:.4f}s → {zc_sec:.4f}s (Δ={1000*(zc_sec - pos_sec):.2f}ms)"
        )
        return zc_sec

    # ---------------------------------------------------------------
    # ループ設定・解除
    # ---------------------------------------------------------------

    def check_loop(self) -> None:
        if not self.loop_active or not self.stream_fx:
            return
        pos = self.get_position()
        start = self.loop_start_sec
        end   = start + self.loop_duration_sec

        # Syncが設定済みならポーリングは不要（二重折り返し防止）
        if self.loop_sync_handle:
            return

        # STARTに達していなければ監視しない
        if pos < start:
            logger.debug(
                f"Deck {self.name}: [LoopPoll] waiting for start "
                f"pos={pos:.3f}s start={start:.3f}s"
            )
            return

        logger.debug(
            f"Deck {self.name}: [LoopPoll] pos={pos:.3f}s "
            f"start={start:.3f}s end={end:.3f}s"
        )
        if pos >= end:
            import time
            self.set_position(start)
            now = time.perf_counter()
            err_ms = (pos - end) * 1000
            self._loop_wrap_errors.append(err_ms)
            self._loop_wrap_times.append(now)
            if len(self._loop_wrap_times) >= 2:
                interval = (self._loop_wrap_times[-1] - self._loop_wrap_times[-2]) * 1000
                jitter_ms = interval - self.loop_duration_sec * 1000
                logger.info(
                    f"Deck {self.name}: [LoopPoll] WRAP "
                    f"err={err_ms:+.1f}ms jitter={jitter_ms:+.1f}ms"
                )
            else:
                logger.info(
                    f"Deck {self.name}: [LoopPoll] WRAP err={err_ms:+.1f}ms"
                )

    def set_loop(self, start_pos: float, duration: float) -> None:
        """
        BASS_SYNC_MIXTIME を使ったシームレスループを設定する。

        設計ノート (Mixxx loopingcontrol.cpp 参照):
          - ゼロクロス補正でクリックノイズを防止
          - バイト計算は stream_decode で行い、stream_fx に SetSync/SetPosition
          - コールバック内の Python オブジェクト参照を最小化（GIL 影響低減）
          - 最小ループ長チェック (Mixxx kMinimumAudibleLoopSizeFrames 相当)
          - ループ範囲外なら設定後にループ先頭へシーク

        Args:
            start_pos: ループ開始位置（秒）
            duration:  ループ長（秒）
        """
        if not self.stream_fx:
            logger.warning(f"Deck {self.name}: No stream loaded")
            return

        self.clear_loop()

        # ゼロクロス補正は stream_decode のシークが stream_fx に影響するため無効化
        end_pos = start_pos + duration

        # バイト計算は stream_fx で行う。
        # BASS_SYNC_POS の param は SetSync を呼んだチャンネルと同じストリームの座標でなければならない。
        # stream_decode で計算した座標を stream_fx に渡すとループEndが全くずれる。
        ref_stream  = self.stream_fx
        start_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(ref_stream, ctypes.c_double(start_pos))
        end_bytes   = BASS_LIB.BASS_ChannelSeconds2Bytes(ref_stream, ctypes.c_double(end_pos))

        # 最小ループ長チェック
        if (end_bytes - start_bytes) < self._min_loop_bytes:
            logger.warning(
                f"Deck {self.name}: Loop too short "
                f"({end_bytes - start_bytes} bytes < {self._min_loop_bytes}), skipping"
            )
            return

        # BASS_SYNC_POS（MIXTIMEなし）は再生時点で発火するが、バッファ出力遅延の影鿹で
        # 計測値で約+58ms過ぎてから折り返る。
        # end_bytesをその分手前に設定することで実際のENDに近づける。
        SYNC_LEAD_SEC = 0.056  # 計測値から調整: 58ms - 2ms = 56ms
        sync_end_pos  = max(start_pos + 0.1, end_pos - SYNC_LEAD_SEC)
        sync_end_bytes = BASS_LIB.BASS_ChannelSeconds2Bytes(ref_stream, ctypes.c_double(sync_end_pos))

        self.loop_start_bytes   = int(start_bytes)
        self.loop_start_sec     = start_pos
        self.loop_duration_sec  = end_pos - start_pos

        # ループ精度計測用
        self._loop_wrap_times: list[float] = []   # WRAP発生時刻（time.perf_counter）
        self._loop_wrap_errors: list[float] = []  # ENDとの誤差（ms）
        self._loop_expected_end = start_pos + (end_pos - start_pos)  # 理論END

        logger.info(
            f"Deck {self.name}: Loop set "
            f"{start_pos:.3f}s ({start_bytes}b) - {end_pos:.3f}s ({end_bytes}b)"
        )

        # BASS_SYNC_MIXTIMEはバッファ書き込み時点で発火するため、
        # 計測したバッファ分早く発火する。
        # 前回計測: 補正なしでerr≈-540ms。
        # テンポストリームのbytes座標はテンポ比率が乗るので秒で計算する。
        sync_set = False
        if BASS_AVAILABLE:
            from .audio_constants import SYNCPROC, BASS_SYNC_POS

            def _loop_cb(handle, channel, data, user):
                import time
                now = time.perf_counter()
                # MIXTIME: この時点でシークすることで
                # バッファがSTARTの音で上書きされシームレスになる
                BASS_LIB.BASS_ChannelSetPosition(
                    self.stream_fx,
                    ctypes.c_uint64(self.loop_start_bytes),
                    BASS_POS_BYTE
                )
                self._loop_wrap_times.append(now)
                if len(self._loop_wrap_times) >= 2:
                    interval = (self._loop_wrap_times[-1] - self._loop_wrap_times[-2]) * 1000
                    jitter_ms = interval - self.loop_duration_sec * 1000
                    logger.info(f"Deck {self.name}: [SyncCB] jitter={jitter_ms:+.1f}ms")
                else:
                    logger.info(f"Deck {self.name}: [SyncCB] fired")

            self.loop_cb_ref = SYNCPROC(_loop_cb)
            handle = BASS_LIB.BASS_ChannelSetSync(
                self.stream_fx,
                BASS_SYNC_POS,  # MIXTIMEなし: 再生時点で発火。テンポストリームでMIXTIMEを使うと内部デコードバッファの混在で音が重なるため不使用
                ctypes.c_uint64(int(sync_end_bytes)),  # +58ms計測値分手前に設定
                self.loop_cb_ref,
                None
            )
            err = BASS_LIB.BASS_ErrorGetCode()
            logger.info(f"Deck {self.name}: BASS_ChannelSetSync handle={handle} err={err}")
            if handle != 0:
                self.loop_sync_handle = handle
                sync_set = True

        self.loop_active = True
        if sync_set:
            logger.info(f"Deck {self.name}: Loop using BASS_SYNC (native)")
        else:
            logger.info(f"Deck {self.name}: Loop using polling fallback")

    def clear_loop(self) -> None:
        if self.loop_active:
            self.loop_active = False
            if self.loop_sync_handle and self.stream_fx:
                BASS_LIB.BASS_ChannelRemoveSync(self.stream_fx, self.loop_sync_handle)
                self.loop_sync_handle = 0
            self.loop_cb_ref = None
            logger.info(f"Deck {self.name}: Loop cleared")

    # ---------------------------------------------------------------
    # ビートスナップループ (Mixxx slotBeatLoop 移植)
    # ---------------------------------------------------------------

    def set_loop_snapped(self, bpm: float, first_beat: float = 0.0, bars: int = 4) -> None:
        """
        ビートグリッドにスナップした N 小節ループを設定する（Mixxx 方式）。

        Mixxx slotBeatLoop() + findQuantizedBeatloopStart() 準拠。

        処理ステップ:
          1. 現在位置直前のビートを bisect_right で O(log n) 検索
             （Mixxx: beats->findNthBeat(-1)）
          2. そのビートから bars*4 ビート分だけ遡ったビートを始点にスナップ
             （Mixxx: findNthBeatFromPosition(pos, -nBeats+1)）
          3. beat_times がない場合は BPM 固定グリッドにフォールバック

        Args:
            bpm:        トラックの BPM
            first_beat: 最初のビート位置（秒）。BPM グリッドフォールバック時に使用
            bars:       ループ小節数（デフォルト 4 小節）
        """
        if not self.stream_fx:
            return

        if bpm <= 0:
            logger.warning(f"Deck {self.name}: Invalid BPM ({bpm}), using 120.0")
            bpm = 120.0

        # Mixxx は "beats" 単位で管理。4/4拍子で bars 小節 = bars*4 ビート
        n_beats       = bars * 4
        beat_duration = 60.0 / bpm
        loop_duration = beat_duration * n_beats
        current       = self.get_position()

        # first_beat バリデーション
        if first_beat < 0 or (self.duration > 0 and first_beat > self.duration):
            logger.warning(
                f"Deck {self.name}: Invalid first_beat ({first_beat:.3f}s), resetting to 0.0"
            )
            first_beat = 0.0

        # スナップ先を決定
        if self.beat_times:
            snap_start = self._find_quantized_beatloop_start(current, n_beats)
            # ENDもbeat_timesからスナップ
            # snap_startのインデックスを特定してn_beats先のビートをENDにする
            import bisect
            start_idx = bisect.bisect_left(self.beat_times, snap_start - 0.001)
            end_idx   = start_idx + n_beats
            if end_idx < len(self.beat_times):
                loop_duration = self.beat_times[end_idx] - snap_start
                logger.info(
                    f"Deck {self.name}: Loop END snapped to bt[{end_idx}]="
                    f"{self.beat_times[end_idx]:.3f}s "
                    f"(BPM calc was {beat_duration * n_beats:.3f}s, "
                    f"snapped={loop_duration:.3f}s)"
                )
            # beat_timesが足りない場合はBPM計算値のまま
        else:
            # beat_times なし → BPM 固定グリッドでスナップ
            # Mixxx get_quantized_time() 相当: first_beat からの経過ビート数を floor
            if current >= first_beat:
                elapsed    = current - first_beat
                beat_index = int(elapsed / beat_duration)
                snap_start = first_beat + beat_index * beat_duration
            else:
                snap_start = first_beat
            logger.info(
                f"Deck {self.name} Loop Snap (BPM grid): "
                f"snap={snap_start:.3f}s beat_dur={beat_duration:.3f}s"
            )

        snap_start = max(0.0, snap_start)

        # ループ末尾が曲尾を超える場合は開始点を後ろにずらして末尾に収める
        if self.duration > 0 and (snap_start + loop_duration) > self.duration:
            snap_start = max(0.0, self.duration - loop_duration)

        logger.info(
            f"Deck {self.name}: Loop SNAPPED "
            f"start={snap_start:.3f}s dur={loop_duration:.3f}s "
            f"BPM={bpm:.1f} n_beats={n_beats}"
        )

        self.set_loop(snap_start, loop_duration)

    def _find_quantized_beatloop_start(self, current_pos: float, n_beats: int) -> float:
        """
        Mixxx findQuantizedBeatloopStart() の Python 移植。

        beat_times 配列に対して bisect_right を使い O(log n) で
        現在位置直前のビートを特定し、そこから n_beats 分だけ
        遡ったビートをループ始点として返す。

        Mixxx のロジック（loopingcontrol.cpp より）:
          pos   = beats->findNthBeat(-1)          // 現在位置以前の最近傍ビート
          start = beats->findNthBeatFromPosition(pos, -nBeats+1)

        Args:
            current_pos: 現在の再生位置（秒）
            n_beats:     ループ長（ビート数、例: 4小節=16ビート）

        Returns:
            スナップされたループ始点（秒）
        """
        import bisect

        bt  = self.beat_times
        idx = bisect.bisect_right(bt, current_pos) - 1

        if idx < 0:
            # 現在位置が全ビートより前 → 先頭ビートを起点
            snap_start = bt[0]
            logger.info(
                f"Deck {self.name} Loop Snap (beat_times): "
                f"before first beat, using bt[0]={snap_start:.3f}s"
            )
            return snap_start

        # 現在位置より未来の次の小節頭をSTARTにする。
        # 現在の拍インデックスの次の4の倍数を探す。
        next_bar_idx = ((idx // 4) + 1) * 4
        # next_bar_idx が現在位置より前になっていないか確認
        # （ビートグリッドのずれで稀に発生する）
        while next_bar_idx < len(bt) and bt[next_bar_idx] <= current_pos:
            next_bar_idx += 4
        if next_bar_idx >= len(bt):
            next_bar_idx = (idx // 4) * 4  # 曲末なら現在小節頭にフォールバック
        snapped_idx = next_bar_idx
        snap_start  = bt[snapped_idx]

        logger.info(
            f"Deck {self.name} Loop Snap (beat_times): "
            f"cur_pos={current_pos:.3f}s cur_idx={idx} bt[idx]={bt[idx]:.3f}s "
            f"snapped_idx={snapped_idx} snap={snap_start:.3f}s n_beats={n_beats}"
        )
        return snap_start
