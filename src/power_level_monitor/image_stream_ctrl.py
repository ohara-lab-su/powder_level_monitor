import threading
import time
from typing import Any, Dict, List, Optional

import cv2
import numpy as np


class ImageStreamDeviceClass:
    """サーバーローカルのカメラ画像取得と画像配信を行う。"""

    def __init__(
        self,
        camera_id: int = 0,
        topic_name: str = "camera.frame",
        interval_sec: float = 0.1,
        capture_interval_sec: float = 0.03,
        jpeg_quality: int = 85,
        logger: Optional[Any] = None,
    ) -> None:
        self._logger: Optional[Any] = logger
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
        self._event_bus = event_bus

    def connect(self) -> bool:
        if self._capture is not None:
            if self._capture.isOpened():
                self._start_capture_loop()
                return True

        self._capture = cv2.VideoCapture(self._camera_id)

        if not self._capture.isOpened():
            self._last_error = "Failed to open camera."
            self._capture = None
            return False

        self._last_error = None
        self._start_capture_loop()
        return True

    def disconnect(self) -> bool:
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
        with self._frame_lock:
            if self._latest_frame is None:
                return None

            if copy_frame:
                return self._latest_frame.copy()

            return self._latest_frame

    def capture_once(self) -> Dict[str, Any]:
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
        if self._event_bus is None:
            raise RuntimeError("EventBus is not set.")

        payload: Dict[str, Any] = self.capture_once()
        self._event_bus.publish(
            self._topic_name,
            payload,
            source="image_stream_device",
        )
        self._last_publish_time_ns = int(time.time() * 1000000000)
        return True

    def get_status(self) -> Dict[str, Any]:
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
        self._capture_stop_event.set()

        if self._capture_thread is not None:
            if self._capture_thread.is_alive():
                self._capture_thread.join(timeout=2.0)

        self._capture_thread = None
        self._capture_running = False

    def _capture_loop(self) -> None:
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

            with self._frame_lock:
                self._latest_frame_id = self._latest_frame_id + 1
                self._latest_frame = frame.copy()
                self._latest_frame_time_ns = frame_time_ns

            self._last_error = None
            time.sleep(self._capture_interval_sec)

        self._capture_running = False

    def _stream_loop(self) -> None:
        while not self._stream_stop_event.is_set():
            try:
                self.publish_once()
            except Exception as exc:
                self._last_error = str(exc)

            time.sleep(self._interval_sec)

        self._stream_running = False

    def _encode_frame(
        self,
        frame: np.ndarray,
    ) -> Dict[str, Any]:
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
