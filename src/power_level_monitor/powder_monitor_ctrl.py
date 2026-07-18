from __future__ import annotations

import threading
import time
from dataclasses import asdict
from dataclasses import fields
from typing import Any

import cv2
import numpy as np

from power_level_monitor.data_control_values import ControlValues
from power_level_monitor.data_surface_detection import SurfaceDetection
from power_level_monitor.image_stream_ctrl import ImageStreamDeviceClass


class PowderControlDeviceClass:
    """サーバーローカル画像を用いて粉体レベルを測定する。"""

    RECTIFIED_WIDTH = 360
    RECTIFIED_HEIGHT = 720

    def __init__(
        self,
        image_source: ImageStreamDeviceClass | None = None,
        measurement_interval_sec: float = 0.1,
        logger: Any | None = None,
    ) -> None:
        self._logger: Any | None = logger
        self._image_source: ImageStreamDeviceClass = image_source
        if self._image_source is None:
            self._image_source = ImageStreamDeviceClass()

        self._measurement_interval_sec: float = float(
            measurement_interval_sec,
        )
        self._roi_points: list[list[int]] = []
        self._baseline_level_y: float | None = None
        self._latest_level_y: float | None = None
        self._latest_decrease_mm: float | None = None
        self._latest_surface: SurfaceDetection | None = None
        self._latest_detected: bool = False
        self._latest_frame_id: int | None = None
        self._latest_frame_time_ns: int | None = None
        self._control_values: ControlValues = ControlValues()
        self._running: bool = False
        self._connected: bool = False
        self._timestamp_ns: int | None = None
        self._last_error: str | None = None

        self._lock: threading.RLock = threading.RLock()
        self._stop_event: threading.Event = threading.Event()
        self._thread: threading.Thread | None = None

    def connect(self) -> bool:
        connected: bool = self._image_source.connect()

        with self._lock:
            self._connected = connected
            self._timestamp_ns = time.time_ns()

            if connected:
                self._last_error = None
            else:
                status: dict[str, Any] = self._image_source.get_status()
                self._last_error = status.get("last_error")

        return connected

    def disconnect(self) -> bool:
        self.stop()
        disconnected: bool = self._image_source.disconnect()

        with self._lock:
            self._connected = False
            self._timestamp_ns = time.time_ns()

        return disconnected

    def start(self) -> bool:
        connected: bool = self.connect()
        if not connected:
            return False

        with self._lock:
            if self._running:
                return True

            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._measurement_loop,
                name="PowderLevelMeasurementThread",
                daemon=True,
            )
            self._running = True
            self._timestamp_ns = time.time_ns()
            self._thread.start()

        return True

    def stop(self) -> bool:
        self._stop_event.set()

        thread: threading.Thread | None = self._thread
        if thread is not None:
            if thread.is_alive():
                thread.join(timeout=2.0)

        with self._lock:
            self._thread = None
            self._running = False
            self._timestamp_ns = time.time_ns()

        return True

    def process_once(self) -> bool:
        frame: np.ndarray | None = self._image_source.get_latest_frame()

        if frame is None:
            with self._lock:
                self._latest_detected = False
                self._last_error = "No camera frame is available."
                self._timestamp_ns = time.time_ns()
            return False

        image_status: dict[str, Any] = self._image_source.get_status()
        frame_id: int | None = image_status.get("frame_id")
        frame_time_ns: int | None = image_status.get("latest_frame_time_ns")

        with self._lock:
            roi_points: list[list[int]] = self.get_roi_points()
            controls: ControlValues = ControlValues(
                **asdict(self._control_values),
            )
            baseline_level_y: float | None = self._baseline_level_y

        if len(roi_points) != 4:
            with self._lock:
                self._latest_detected = False
                self._latest_frame_id = frame_id
                self._latest_frame_time_ns = frame_time_ns
                self._last_error = "ROI points are not set."
                self._timestamp_ns = time.time_ns()
            return False

        try:
            surface, current_level_y = self._process_frame(
                frame,
                roi_points,
                controls,
            )
        except Exception as exc:
            with self._lock:
                self._latest_detected = False
                self._latest_frame_id = frame_id
                self._latest_frame_time_ns = frame_time_ns
                self._last_error = str(exc)
                self._timestamp_ns = time.time_ns()
            return False

        if surface is None:
            with self._lock:
                self._latest_detected = False
                self._latest_surface = None
                self._latest_frame_id = frame_id
                self._latest_frame_time_ns = frame_time_ns
                self._last_error = None
                self._timestamp_ns = time.time_ns()
            return False

        decrease_mm: float | None = None
        if baseline_level_y is not None:
            decrease_mm = self._pixel_delta_to_mm(
                current_level_y=current_level_y,
                baseline_y=baseline_level_y,
                controls=controls,
            )

        self._update_measurement(
            surface=surface,
            level_y=current_level_y,
            decrease_mm=decrease_mm,
            frame_id=frame_id,
            frame_time_ns=frame_time_ns,
        )
        return True

    def set_roi_points(
        self,
        points: list[list[int]],
    ) -> bool:
        if len(points) != 4:
            raise ValueError("ROI points must contain four points.")

        normalized_points: list[list[int]] = []
        for point in points:
            if len(point) != 2:
                raise ValueError("Each ROI point must contain x and y.")

            x_value: int = int(point[0])
            y_value: int = int(point[1])
            normalized_points.append([x_value, y_value])

        with self._lock:
            self._roi_points = normalized_points
            self._baseline_level_y = None
            self._latest_detected = False
            self._latest_surface = None
            self._timestamp_ns = time.time_ns()
            self._last_error = None

        return True

    def get_roi_points(self) -> list[list[int]]:
        copied_points: list[list[int]] = []

        with self._lock:
            for point in self._roi_points:
                copied_point: list[int] = [
                    int(point[0]),
                    int(point[1]),
                ]
                copied_points.append(copied_point)

        return copied_points

    def clear_roi_points(self) -> bool:
        with self._lock:
            self._roi_points = []
            self._baseline_level_y = None
            self._latest_detected = False
            self._latest_surface = None
            self._timestamp_ns = time.time_ns()

        return True

    def set_baseline(self) -> bool:
        with self._lock:
            if not self._latest_detected:
                self._last_error = "No valid measurement is available."
                return False

            if self._latest_level_y is None:
                self._last_error = "No valid measurement is available."
                return False

            self._baseline_level_y = self._latest_level_y
            self._latest_decrease_mm = 0.0
            self._timestamp_ns = time.time_ns()
            self._last_error = None

        return True

    def clear_baseline(self) -> bool:
        with self._lock:
            self._baseline_level_y = None
            self._latest_decrease_mm = None
            self._timestamp_ns = time.time_ns()

        return True

    def get_baseline(self) -> float | None:
        with self._lock:
            return self._baseline_level_y

    def set_detector_params(
        self,
        params: dict[str, Any],
    ) -> bool:
        control_values: ControlValues = self._make_control_values(params)

        with self._lock:
            self._control_values = control_values
            self._timestamp_ns = time.time_ns()
            self._last_error = None

        return True

    def get_detector_params(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._control_values)

    def get_measurement(self) -> dict[str, Any]:
        with self._lock:
            surface_data: dict[str, Any] | None = None

            if self._latest_surface is not None:
                surface_data = {
                    "center_y": self._latest_surface.center_y,
                    "line_left": list(self._latest_surface.line_left),
                    "line_right": list(self._latest_surface.line_right),
                    "point_count": self._latest_surface.point_count,
                }

            return {
                "detected": self._latest_detected,
                "level_y": self._latest_level_y,
                "decrease_mm": self._latest_decrease_mm,
                "baseline_level_y": self._baseline_level_y,
                "surface": surface_data,
                "frame_id": self._latest_frame_id,
                "frame_timestamp_ns": self._latest_frame_time_ns,
                "timestamp_ns": self._timestamp_ns,
                "last_error": self._last_error,
            }

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            running: bool = self._running
            connected: bool = self._connected
            last_error: str | None = self._last_error

        return {
            "connected": connected,
            "running": running,
            "has_roi": len(self.get_roi_points()) == 4,
            "roi_points": self.get_roi_points(),
            "baseline_level_y": self.get_baseline(),
            "detector_params": self.get_detector_params(),
            "measurement": self.get_measurement(),
            "image_source": self._image_source.get_status(),
            "last_error": last_error,
        }

    def _measurement_loop(self) -> None:
        while not self._stop_event.is_set():
            self.process_once()
            time.sleep(self._measurement_interval_sec)

        with self._lock:
            self._running = False

    def _process_frame(
        self,
        frame: np.ndarray,
        roi_points: list[list[int]],
        controls: ControlValues,
    ) -> tuple[SurfaceDetection | None, float | None]:
        matrix: np.ndarray = self._create_perspective_matrix(roi_points)
        rectified: np.ndarray = cv2.warpPerspective(
            frame,
            matrix,
            (
                self.RECTIFIED_WIDTH,
                self.RECTIFIED_HEIGHT,
            ),
        )

        inner_roi, inner_box = self._crop_inner_roi(
            rectified,
            controls,
        )
        mask: np.ndarray = self._create_powder_mask(
            inner_roi,
            controls,
        )
        surface: SurfaceDetection | None = self._detect_surface(
            mask,
            controls,
        )

        if surface is None:
            return None, None

        current_level_y: float = inner_box[1] + surface.center_y
        return surface, current_level_y

    def _create_perspective_matrix(
        self,
        roi_points: list[list[int]],
    ) -> np.ndarray:
        source_points = np.array(
            roi_points,
            dtype=np.float32,
        )
        destination_points = np.array(
            [
                [0.0, 0.0],
                [self.RECTIFIED_WIDTH - 1.0, 0.0],
                [
                    self.RECTIFIED_WIDTH - 1.0,
                    self.RECTIFIED_HEIGHT - 1.0,
                ],
                [0.0, self.RECTIFIED_HEIGHT - 1.0],
            ],
            dtype=np.float32,
        )

        return cv2.getPerspectiveTransform(
            source_points,
            destination_points,
        )

    def _crop_inner_roi(
        self,
        rectified: np.ndarray,
        controls: ControlValues,
    ) -> tuple[np.ndarray, tuple[int, int, int, int]]:
        height, width = rectified.shape[:2]
        margin_x: int = int(width * controls.margin_x_ratio)
        margin_y: int = int(height * controls.margin_y_ratio)

        x1: int = max(0, margin_x)
        y1: int = max(0, margin_y)
        x2: int = min(width, width - margin_x)
        y2: int = min(height, height - margin_y)

        if x2 <= x1:
            x1 = 0
            x2 = width

        if y2 <= y1:
            y1 = 0
            y2 = height

        inner: np.ndarray = rectified[y1:y2, x1:x2]
        return inner, (x1, y1, x2, y2)

    def _create_powder_mask(
        self,
        inner_roi: np.ndarray,
        controls: ControlValues,
    ) -> np.ndarray:
        gray: np.ndarray = cv2.cvtColor(
            inner_roi,
            cv2.COLOR_BGR2GRAY,
        )
        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8),
        )
        gray = clahe.apply(gray)
        gray = cv2.GaussianBlur(
            gray,
            (
                controls.blur,
                controls.blur,
            ),
            0,
        )

        if controls.mode == 0:
            _, mask = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )
        elif controls.mode == 1:
            _, mask = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
            )
        elif controls.mode == 2:
            _, mask = cv2.threshold(
                gray,
                controls.manual_threshold,
                255,
                cv2.THRESH_BINARY,
            )
        else:
            _, mask = cv2.threshold(
                gray,
                controls.manual_threshold,
                255,
                cv2.THRESH_BINARY_INV,
            )

        if controls.open_kernel > 1:
            open_kernel = np.ones(
                (
                    controls.open_kernel,
                    controls.open_kernel,
                ),
                np.uint8,
            )
            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_OPEN,
                open_kernel,
                iterations=1,
            )

        if controls.close_kernel > 1:
            close_kernel = np.ones(
                (
                    controls.close_kernel,
                    controls.close_kernel,
                ),
                np.uint8,
            )
            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_CLOSE,
                close_kernel,
                iterations=1,
            )

        return mask

    def _extract_surface_points(
        self,
        mask: np.ndarray,
        controls: ControlValues,
    ) -> np.ndarray:
        height, width = mask.shape[:2]
        points: list[tuple[int, int]] = []

        for x in range(width):
            column = mask[:, x] > 0
            ys = np.where(column)[0]

            if len(ys) == 0:
                continue

            for y in ys:
                y2: int = min(height, y + controls.stable_rows)
                support: int = int(np.count_nonzero(column[y:y2]))
                required: int = max(1, int((y2 - y) * 0.7))

                if support >= required:
                    points.append((x, int(y)))
                    break

        if len(points) == 0:
            return np.empty((0, 2), dtype=np.float32)

        return np.array(points, dtype=np.float32)

    def _filter_surface_points(
        self,
        points: np.ndarray,
    ) -> np.ndarray:
        if len(points) < 5:
            return points

        y_values = points[:, 1]
        median_y: float = float(np.median(y_values))
        deviation = np.abs(y_values - median_y)
        mad: float = float(np.median(deviation))

        if mad < 1.0:
            limit: float = 8.0
        else:
            limit = max(8.0, mad * 3.0)

        keep = deviation <= limit
        return points[keep]

    def _detect_surface(
        self,
        mask: np.ndarray,
        controls: ControlValues,
    ) -> SurfaceDetection | None:
        mask_area: int = int(cv2.countNonZero(mask))

        if mask_area < controls.min_area:
            return None

        height, width = mask.shape[:2]
        row_hit = np.count_nonzero(mask, axis=1) / float(width)

        if np.max(row_hit) < controls.row_ratio_threshold:
            return None

        points: np.ndarray = self._extract_surface_points(
            mask,
            controls,
        )
        points = self._filter_surface_points(points)

        if len(points) < max(12, width * 0.08):
            return None

        line = cv2.fitLine(
            points,
            cv2.DIST_L2,
            0,
            0.01,
            0.01,
        )
        vx, vy, x0, y0 = [
            float(value)
            for value in line.flatten()
        ]

        if abs(vx) < 1.0e-6:
            y_left: float = float(np.median(points[:, 1]))
            y_right: float = y_left
        else:
            y_left = y0 + (vy / vx) * (0.0 - x0)
            y_right = y0 + (vy / vx) * ((width - 1.0) - x0)

        y_left = float(np.clip(y_left, 0, height - 1))
        y_right = float(np.clip(y_right, 0, height - 1))
        center_x: float = (width - 1.0) / 2.0

        if abs(vx) < 1.0e-6:
            center_y: float = y_left
        else:
            center_y = y0 + (vy / vx) * (center_x - x0)

        center_y = float(np.clip(center_y, 0, height - 1))

        return SurfaceDetection(
            center_y=center_y,
            line_left=(0, int(round(y_left))),
            line_right=(width - 1, int(round(y_right))),
            point_count=len(points),
        )

    def _pixel_delta_to_mm(
        self,
        current_level_y: float,
        baseline_y: float,
        controls: ControlValues,
    ) -> float:
        mm_per_pixel: float = (
            controls.measure_height_mm
            / float(self.RECTIFIED_HEIGHT)
        )
        decrease_mm: float = (
            current_level_y - baseline_y
        ) * mm_per_pixel
        return float(decrease_mm)

    def _update_measurement(
        self,
        surface: SurfaceDetection,
        level_y: float,
        decrease_mm: float | None,
        frame_id: int | None,
        frame_time_ns: int | None,
    ) -> None:
        with self._lock:
            self._latest_surface = surface
            self._latest_level_y = float(level_y)
            self._latest_decrease_mm = decrease_mm
            self._latest_detected = True
            self._latest_frame_id = frame_id
            self._latest_frame_time_ns = frame_time_ns
            self._timestamp_ns = time.time_ns()
            self._last_error = None

    def _make_control_values(
        self,
        params: dict[str, Any],
    ) -> ControlValues:
        with self._lock:
            current_values: dict[str, Any] = asdict(
                self._control_values,
            )

        valid_names: set[str] = self._get_control_value_names()

        for key, value in params.items():
            if key not in valid_names:
                raise KeyError(f"unknown detector parameter: {key}")

            current_values[key] = value

        mode: int = int(current_values["mode"])
        manual_threshold: int = int(
            current_values["manual_threshold"],
        )
        blur: int = self._make_odd(current_values["blur"])
        open_kernel: int = self._make_odd(
            current_values["open_kernel"],
        )
        close_kernel: int = self._make_odd(
            current_values["close_kernel"],
        )
        row_ratio_threshold: float = float(
            current_values["row_ratio_threshold"],
        )
        stable_rows: int = max(
            1,
            int(current_values["stable_rows"]),
        )
        min_area: int = max(
            0,
            int(current_values["min_area"]),
        )
        margin_x_ratio: float = float(
            current_values["margin_x_ratio"],
        )
        margin_y_ratio: float = float(
            current_values["margin_y_ratio"],
        )
        measure_height_mm: float = max(
            1.0,
            float(current_values["measure_height_mm"]),
        )

        if mode < 0 or mode > 3:
            raise ValueError("mode must be between 0 and 3.")

        if manual_threshold < 0 or manual_threshold > 255:
            raise ValueError(
                "manual_threshold must be between 0 and 255.",
            )

        if row_ratio_threshold < 0.0:
            raise ValueError("row_ratio_threshold must be 0.0 or more.")

        if row_ratio_threshold > 1.0:
            raise ValueError("row_ratio_threshold must be 1.0 or less.")

        if margin_x_ratio < 0.0 or margin_x_ratio >= 0.5:
            raise ValueError("margin_x_ratio must be in [0.0, 0.5).")

        if margin_y_ratio < 0.0 or margin_y_ratio >= 0.5:
            raise ValueError("margin_y_ratio must be in [0.0, 0.5).")

        return ControlValues(
            mode=mode,
            manual_threshold=manual_threshold,
            blur=blur,
            open_kernel=open_kernel,
            close_kernel=close_kernel,
            row_ratio_threshold=row_ratio_threshold,
            stable_rows=stable_rows,
            min_area=min_area,
            margin_x_ratio=margin_x_ratio,
            margin_y_ratio=margin_y_ratio,
            measure_height_mm=measure_height_mm,
        )

    def _get_control_value_names(self) -> set[str]:
        control_value_names: set[str] = set()

        for field_info in fields(ControlValues):
            control_value_names.add(field_info.name)

        return control_value_names

    def _make_odd(
        self,
        value: Any,
    ) -> int:
        odd_value: int = max(1, int(value))

        if odd_value % 2 == 0:
            odd_value = odd_value + 1

        return odd_value
