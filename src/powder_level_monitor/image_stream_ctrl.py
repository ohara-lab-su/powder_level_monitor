
"""カメラ画像の継続取得、JPEG符号化、および EventBus 配信を制御する。"""
import threading
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


class ImageStreamDeviceClass:
    """カメラ画像を別スレッドで継続取得し、必要に応じてEventBusへJPEG配信する。"""

    def __init__(
        self,
        camera_id: int = 0,
        topic_name: str = "camera.frame",
        interval_sec: float = 0.1,
        capture_interval_sec: float = 0.03,
        jpeg_quality: int = 85,
        logger: Optional[Any] = None,
    ) -> None:
        """カメラ取得・画像配信の状態と同期オブジェクトを初期化する。
        
        Args:
            camera_id: OpenCVへ渡すカメラデバイス番号。
            topic_name: EventBusへ画像を配信するトピック名。
            interval_sec: 画像配信周期（秒）。
            capture_interval_sec: カメラ取得ループの待機時間（秒）。
            jpeg_quality: JPEG符号化品質。
            logger: 動作ログを出力するロガー。
        """
        if logger is None:
            from x_logger import XLogger

            logger = XLogger(
                log_level="debug",
                logger_name=self.__class__.__name__,
            )

        self._logger = logger
        self._camera_id: int = int(camera_id)
        self._topic_name: str = str(topic_name)
        self._interval_sec: float = float(interval_sec)
        self._capture_interval_sec: float = float(capture_interval_sec)
        self._jpeg_quality: int = int(jpeg_quality)

        self._event_bus: Optional[Any] = None
        self._capture: Optional[cv2.VideoCapture] = None
        self._capture_thread: Optional[threading.Thread] = None
        self._stream_thread: Optional[threading.Thread] = None
        self._capture_stop_event: threading.Event = threading.Event()
        self._stream_stop_event: threading.Event = threading.Event()
        self._frame_lock: threading.Lock = threading.Lock()

        self._capture_running: bool = False
        self._stream_running: bool = False
        self._frame_id: int = 0
        self._latest_frame_id: int = 0
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_frame_time_ns: Optional[int] = None
        self._last_error: Optional[str] = None
        self._last_publish_time_ns: Optional[int] = None

    def _set_event_bus(
        self,
        event_bus: Any,
    ) -> None:
        """grpc_frame から渡された EventBus を画像配信処理へ設定する。
        
        Args:
            event_bus: 画像イベントの配信に使用する EventBus。
        """
        self._event_bus = event_bus

    def connect(self) -> bool:
        """必要なデバイス接続と内部処理ループを開始する。
        
        Returns:
            接続と起動に成功した場合は True、それ以外は False。
        """
        self._logger.info(
            "<IMAGE STREAM ACTION> connect: camera_id={}".format(
                self._camera_id,
            )
        )

        if self._capture is not None:
            if self._capture.isOpened():
                self._start_capture_loop()
                return True

        # カメラは取得スレッドだけが read() し、他処理は最新フレームのコピーを参照する。
        self._capture = cv2.VideoCapture(self._camera_id)

        if not self._capture.isOpened():
            self._last_error = "Failed to open camera."
            self._logger.error(
                "<IMAGE STREAM ACTION> failed to open camera"
            )
            self._capture = None
            return False

        self._last_error = None
        self._start_capture_loop()
        return True

    def disconnect(self) -> bool:
        """内部処理ループを停止し、デバイス接続を解放する。
        
        Returns:
            正常に切断処理を完了した場合は True。
        """
        self._logger.info("<IMAGE STREAM ACTION> disconnect")
        self.stop_stream()
        self._stop_capture_loop()

        if self._capture is not None:
            self._capture.release()

        self._capture = None

        with self._frame_lock:
            self._latest_frame = None
            self._latest_frame_time_ns = None

        return True

    def start_stream(self) -> bool:
        """最新画像を一定周期で EventBus へ配信するスレッドを開始する。
        
        Returns:
            配信を開始できた場合は True。
        
        Raises:
            RuntimeError: EventBus が設定されていない場合。
        """
        self._logger.info("<IMAGE STREAM ACTION> start_stream")

        if self._event_bus is None:
            raise RuntimeError("EventBus is not set.")

        connected: bool = self.connect()
        if not connected:
            return False

        if self._stream_running:
            return True

        self._stream_stop_event.clear()
        self._stream_thread = threading.Thread(
            target=self._stream_loop,
            name="ImageStreamPublishThread",
            daemon=True,
        )
        self._stream_running = True
        self._stream_thread.start()
        return True

    def stop_stream(self) -> bool:
        """画像配信スレッドを停止する。
        
        Returns:
            停止済みまたは正常に停止した場合は True。
        """
        if not self._stream_running:
            return True

        self._logger.info("<IMAGE STREAM ACTION> stop_stream")
        self._stream_stop_event.set()

        if self._stream_thread is not None:
            if self._stream_thread.is_alive():
                self._stream_thread.join(timeout=2.0)

        self._stream_thread = None
        self._stream_running = False
        return True

    def get_latest_frame(
        self,
        copy_frame: bool = True,
    ) -> Optional[np.ndarray]:
        """スレッド間で保護された最新カメラ画像を取得する。
        
        Args:
            copy_frame: Trueの場合は画像のコピーを返し、共有バッファの変更を防ぐ。
        
        Returns:
            最新画像。画像未取得時は None。
        """
        with self._frame_lock:
            if self._latest_frame is None:
                return None

            if copy_frame:
                return self._latest_frame.copy()

            return self._latest_frame

    def capture_once(self) -> Dict[str, Any]:
        """カメラ接続を確保し、最新画像をJPEGペイロードとして取得する。
        
        Returns:
            画像メタデータとJPEGバイト列を格納した辞書。
        
        Raises:
            RuntimeError: 接続失敗または規定時間内に画像を取得できない場合。
        """
        connected: bool = self.connect()
        if not connected:
            raise RuntimeError(str(self._last_error))

        frame: Optional[np.ndarray] = self.get_latest_frame()

        if frame is None:
            timeout_time: float = time.monotonic() + 2.0

            while frame is None:
                if time.monotonic() >= timeout_time:
                    raise RuntimeError("No camera frame is available.")

                time.sleep(0.01)
                frame = self.get_latest_frame()

        return self._encode_frame(frame)

    def publish_once(self) -> bool:
        """最新画像をJPEGへ符号化し、EventBusへ1回だけ配信する。
        
        Returns:
            配信に成功した場合は True。
        
        Raises:
            RuntimeError: EventBusまたは最新画像が利用できない場合。
        """
        if self._event_bus is None:
            raise RuntimeError("EventBus is not set.")

        frame: Optional[np.ndarray] = self.get_latest_frame()
        if frame is None:
            raise RuntimeError("No camera frame is available.")

        # EventBusにはOpenCV配列ではなく、プロセス間転送可能なJPEGバイト列を載せる。
        payload: Dict[str, Any] = self._encode_frame(frame)
        self._event_bus.publish(
            self._topic_name,
            payload,
            source="image_stream_device",
        )
        self._last_publish_time_ns = int(time.time() * 1000000000)
        return True

    def get_status(self) -> Dict[str, Any]:
        """接続、処理ループ、ROI、測定状態をまとめて取得する。
        
        Returns:
            制御対象の状態を格納した辞書。
        """
        capture_opened: bool = False
        if self._capture is not None:
            capture_opened = bool(self._capture.isOpened())

        return {
            "capture_running": self._capture_running,
            "stream_running": self._stream_running,
            "camera_id": self._camera_id,
            "capture_opened": capture_opened,
            "topic_name": self._topic_name,
            "interval_sec": self._interval_sec,
            "capture_interval_sec": self._capture_interval_sec,
            "jpeg_quality": self._jpeg_quality,
            "frame_id": self._latest_frame_id,
            "latest_frame_time_ns": self._latest_frame_time_ns,
            "last_publish_time_ns": self._last_publish_time_ns,
            "last_error": self._last_error,
        }

    def _start_capture_loop(self) -> None:
        """カメラから最新フレームを取得するデーモンスレッドを開始する。"""
        if self._capture_running:
            return

        self._capture_stop_event.clear()
        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="ImageStreamCaptureThread",
            daemon=True,
        )
        self._capture_running = True
        self._capture_thread.start()

    def _stop_capture_loop(self) -> None:
        """カメラ取得スレッドへ停止を通知し、終了を待機する。"""
        self._capture_stop_event.set()

        if self._capture_thread is not None:
            if self._capture_thread.is_alive():
                self._capture_thread.join(timeout=2.0)

        self._capture_thread = None
        self._capture_running = False

    def _capture_loop(self) -> None:
        """カメラフレームを周期取得し、排他制御下で最新画像を更新する。"""
        while not self._capture_stop_event.is_set():
            if self._capture is None:
                self._last_error = "Camera is not connected."
                break

            ok, frame = self._capture.read()

            if not ok:
                self._last_error = "Failed to read frame."
                time.sleep(self._capture_interval_sec)
                continue

            frame_time_ns: int = int(time.time() * 1000000000)

            # 画像本体・ID・時刻を同一ロック内で更新し、組み合わせの不整合を防ぐ。
            with self._frame_lock:
                self._latest_frame_id = self._latest_frame_id + 1
                self._latest_frame = frame.copy()
                self._latest_frame_time_ns = frame_time_ns

            self._last_error = None
            time.sleep(self._capture_interval_sec)

        self._capture_running = False

    def _stream_loop(self) -> None:
        """停止要求まで最新画像を一定周期で配信する。"""
        self._logger.info(
            "<IMAGE STREAM ACTION> publish loop started: topic={}".format(
                self._topic_name,
            )
        )

        while not self._stream_stop_event.is_set():
            try:
                self.publish_once()
            except Exception as exc:
                self._last_error = str(exc)
                self._logger.error(
                    "<IMAGE STREAM ACTION> publish failed: {}".format(
                        exc,
                    )
                )

            self._stream_stop_event.wait(self._interval_sec)

        self._stream_running = False
        self._logger.info("<IMAGE STREAM ACTION> publish loop stopped")

    def _encode_frame(
        self,
        frame: np.ndarray,
    ) -> Dict[str, Any]:
        """OpenCV画像をJPEGへ符号化し、配信用メタデータを付与する。
        
        Args:
            frame: BGR形式のOpenCV画像。
        
        Returns:
            JPEG画像とフレーム識別情報を格納した辞書。
        
        Raises:
            RuntimeError: JPEG符号化に失敗した場合。
        """
        encode_params: List[int] = [
            int(cv2.IMWRITE_JPEG_QUALITY),
            self._jpeg_quality,
        ]

        ok, encoded = cv2.imencode(
            ".jpg",
            frame,
            encode_params,
        )

        if not ok:
            raise RuntimeError("Failed to encode frame.")

        self._frame_id = self._frame_id + 1

        height: int = int(frame.shape[0])
        width: int = int(frame.shape[1])

        return {
            "frame_id": self._frame_id,
            "camera_frame_id": self._latest_frame_id,
            "timestamp_ns": int(time.time() * 1000000000),
            "camera_timestamp_ns": self._latest_frame_time_ns,
            "encoding": "jpg",
            "width": width,
            "height": height,
            "image": encoded.tobytes(),
        }
