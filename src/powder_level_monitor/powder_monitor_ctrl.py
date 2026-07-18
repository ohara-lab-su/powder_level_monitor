import threading
import time
from dataclasses import asdict
from dataclasses import fields
from typing import Any, Dict, List, Optional, Set, Tuple

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
        image_source: Optional[ImageStreamDeviceClass] = None,
        measurement_interval_sec: float = 0.1,
        logger: Optional[Any] = None,
    ) -> None:
        if logger is None:
            from x_logger import XLogger
            logger = XLogger(
                log_level="debug",
                logger_name=self.__class__.__name__,
            )

        self._logger = logger
        self._image_source = image_source
        if self._image_source is None:
            self._image_source = ImageStreamDeviceClass(logger=logger)

        self._measurement_interval_sec = float(measurement_interval_sec)
        self._roi_points = []
        self._baseline_level_y = None
        self._baseline_line_left = None
        self._baseline_line_right = None
        self._latest_level_y = None
        self._latest_line_left = None
        self._latest_line_right = None
        self._latest_decrease_mm = None
        self._latest_surface = None
        self._latest_detected = False
        self._latest_frame_id = None
        self._latest_frame_time_ns = None
        self._control_values = ControlValues()
        self._processing_running = False
        self._measuring = False
        self._connected = False
        self._timestamp_ns = None
        self._last_error = None

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread = None

        image_status = self._image_source.get_status()
        if image_status.get("capture_opened"):
            self._connected = True
            self._start_processing_loop()

        self._logger.info("<POWDER ACTION> PowderControlDeviceClass initialized")

    def connect(self) -> bool:
        self._logger.info("<POWDER ACTION> connect")
        connected = self._image_source.connect()

        with self._lock:
            self._connected = connected
            self._timestamp_ns = int(time.time() * 1000000000)
            if connected:
                self._last_error = None
            else:
                status = self._image_source.get_status()
                self._last_error = status.get("last_error")

        if connected:
            self._start_processing_loop()
        return connected

    def disconnect(self) -> bool:
        self._logger.info("<POWDER ACTION> disconnect")
        self.stop_measurement()
        self._stop_processing_loop()
        disconnected = self._image_source.disconnect()
        with self._lock:
            self._connected = False
            self._timestamp_ns = int(time.time() * 1000000000)
        return disconnected

    def start(self) -> bool:
        return self.start_measurement()

    def stop(self) -> bool:
        return self.stop_measurement()

    def start_measurement(self) -> bool:
        self._logger.info("<POWDER ACTION> start_measurement")
        if not self.connect():
            return False

        self.process_once()

        with self._lock:
            if self._measuring:
                return True
            if len(self._roi_points) != 4:
                self._last_error = "ROI points are not set."
                self._logger.error("<POWDER ACTION> start_measurement failed: ROI points are not set")
                return False
            if self._baseline_level_y is None:
                self._last_error = "Baseline is not set."
                self._logger.error("<POWDER ACTION> start_measurement failed: baseline is not set")
                return False
            if not self._latest_detected:
                self._last_error = "No valid surface detection is available."
                self._logger.error("<POWDER ACTION> start_measurement failed: no valid detection")
                return False

            self._measuring = True
            self._timestamp_ns = int(time.time() * 1000000000)
            self._last_error = None

        self._logger.info("<POWDER ACTION> measurement started")
        return True

    def stop_measurement(self) -> bool:
        self._logger.info("<POWDER ACTION> stop_measurement")
        with self._lock:
            self._measuring = False
            self._timestamp_ns = int(time.time() * 1000000000)
        return True

    def is_measuring(self) -> bool:
        with self._lock:
            return bool(self._measuring)

    def process_once(self) -> bool:
        frame = self._image_source.get_latest_frame()
        if frame is None:
            with self._lock:
                self._latest_detected = False
                self._last_error = "No camera frame is available."
                self._timestamp_ns = int(time.time() * 1000000000)
            return False

        image_status = self._image_source.get_status()
        frame_id = image_status.get("frame_id")
        frame_time_ns = image_status.get("latest_frame_time_ns")

        with self._lock:
            roi_points = self.get_roi_points()
            controls = ControlValues(**asdict(self._control_values))
            baseline_level_y = self._baseline_level_y

        if len(roi_points) != 4:
            with self._lock:
                self._latest_detected = False
                self._latest_frame_id = frame_id
                self._latest_frame_time_ns = frame_time_ns
                self._last_error = "ROI points are not set."
                self._timestamp_ns = int(time.time() * 1000000000)
            return False

        try:
            (
                surface,
                current_level_y,
                line_left,
                line_right,
            ) = self._process_frame(
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
                self._timestamp_ns = int(time.time() * 1000000000)
            self._logger.error("<POWDER ACTION> process_once failed: {}".format(exc))
            return False

        if surface is None:
            with self._lock:
                self._latest_detected = False
                self._latest_surface = None
                self._latest_frame_id = frame_id
                self._latest_frame_time_ns = frame_time_ns
                self._last_error = None
                self._timestamp_ns = int(time.time() * 1000000000)
            return False

        decrease_mm = None
        if baseline_level_y is not None:
            decrease_mm = self._pixel_delta_to_mm(
                current_level_y=current_level_y,
                baseline_y=baseline_level_y,
                controls=controls,
            )

        self._update_measurement(
            surface=surface,
            level_y=current_level_y,
            line_left=line_left,
            line_right=line_right,
            decrease_mm=decrease_mm,
            frame_id=frame_id,
            frame_time_ns=frame_time_ns,
        )
        return True

    def set_roi_points(self, points: List[List[int]]) -> bool:
        self._logger.info("<POWDER ACTION> set_roi_points: {}".format(points))
        if len(points) != 4:
            raise ValueError("ROI points must contain four points.")

        normalized_points = []
        for point in points:
            if len(point) != 2:
                raise ValueError("Each ROI point must contain x and y.")
            normalized_points.append([int(point[0]), int(point[1])])

        with self._lock:
            self._roi_points = normalized_points
            self._baseline_level_y = None
            self._baseline_line_left = None
            self._baseline_line_right = None
            self._latest_line_left = None
            self._latest_line_right = None
            self._latest_decrease_mm = None
            self._latest_detected = False
            self._latest_surface = None
            self._measuring = False
            self._timestamp_ns = int(time.time() * 1000000000)
            self._last_error = None
        return True

    def get_roi_points(self) -> List[List[int]]:
        copied_points = []
        with self._lock:
            for point in self._roi_points:
                copied_points.append([int(point[0]), int(point[1])])
        return copied_points

    def clear_roi_points(self) -> bool:
        self._logger.info("<POWDER ACTION> clear_roi_points")
        with self._lock:
            self._roi_points = []
            self._baseline_level_y = None
            self._baseline_line_left = None
            self._baseline_line_right = None
            self._latest_line_left = None
            self._latest_line_right = None
            self._latest_decrease_mm = None
            self._latest_detected = False
            self._latest_surface = None
            self._measuring = False
            self._timestamp_ns = int(time.time() * 1000000000)
        return True

    def set_baseline(self) -> bool:
        self._logger.info("<POWDER ACTION> set_baseline")
        self.process_once()
        with self._lock:
            if not self._latest_detected:
                self._last_error = "No valid measurement is available."
                return False
            if self._latest_level_y is None:
                self._last_error = "No valid measurement is available."
                return False
            self._baseline_level_y = self._latest_level_y
            self._baseline_line_left = self._latest_line_left
            self._baseline_line_right = self._latest_line_right
            self._latest_decrease_mm = 0.0
            self._timestamp_ns = int(time.time() * 1000000000)
            self._last_error = None
        return True

    def clear_baseline(self) -> bool:
        self._logger.info("<POWDER ACTION> clear_baseline")
        with self._lock:
            self._baseline_level_y = None
            self._baseline_line_left = None
            self._baseline_line_right = None
            self._latest_decrease_mm = None
            self._measuring = False
            self._timestamp_ns = int(time.time() * 1000000000)
        return True

    def get_baseline(self) -> Optional[float]:
        with self._lock:
            return self._baseline_level_y

    def set_detector_params(self, params: Dict[str, Any]) -> bool:
        valid_names = set()
        for field in fields(ControlValues):
            valid_names.add(field.name)
        unknown_names = set(params.keys()) - valid_names
        if unknown_names:
            raise ValueError("Unknown detector parameter(s): {}".format(sorted(unknown_names)))

        current = self.get_detector_params()
        current.update(params)
        controls = ControlValues(**current)
        controls.validate()
        with self._lock:
            self._control_values = controls
            self._last_error = None
        self._logger.info("<POWDER ACTION> set_detector_params: {}".format(params))
        return True

    def get_detector_params(self) -> Dict[str, Any]:
        with self._lock:
            return asdict(self._control_values)

    def get_measurement(self) -> Dict[str, Any]:
        with self._lock:
            surface_data = None
            if self._latest_surface is not None:
                surface_data = {
                    "center_y": self._latest_surface.center_y,
                    "line_left": list(self._latest_surface.line_left),
                    "line_right": list(self._latest_surface.line_right),
                    "point_count": self._latest_surface.point_count,
                }

            line_left = None
            if self._latest_line_left is not None:
                line_left = list(self._latest_line_left)

            line_right = None
            if self._latest_line_right is not None:
                line_right = list(self._latest_line_right)

            baseline_line_left = None
            if self._baseline_line_left is not None:
                baseline_line_left = list(self._baseline_line_left)

            baseline_line_right = None
            if self._baseline_line_right is not None:
                baseline_line_right = list(self._baseline_line_right)

            decrease_px = None
            decrease_ratio = None
            if self._baseline_level_y is not None:
                if self._latest_level_y is not None:
                    decrease_px = (
                        self._latest_level_y
                        - self._baseline_level_y
                    )
                    decrease_ratio = (
                        decrease_px
                        / float(self.RECTIFIED_HEIGHT)
                    )

            baseline_set = self._baseline_level_y is not None
            baseline_detected = (
                baseline_set
                and baseline_line_left is not None
                and baseline_line_right is not None
            )

            return {
                "measuring": self._measuring,
                "detected": self._latest_detected,
                "current_detected": self._latest_detected,
                "baseline_set": baseline_set,
                "baseline_detected": baseline_detected,
                "level_y": self._latest_level_y,
                "line_left": line_left,
                "line_right": line_right,
                "decrease_px": decrease_px,
                "decrease_mm": self._latest_decrease_mm,
                "decrease_ratio": decrease_ratio,
                "baseline_level_y": self._baseline_level_y,
                "baseline_line_left": baseline_line_left,
                "baseline_line_right": baseline_line_right,
                "surface": surface_data,
                "frame_id": self._latest_frame_id,
                "frame_timestamp_ns": self._latest_frame_time_ns,
                "timestamp_ns": self._timestamp_ns,
                "last_error": self._last_error,
            }

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            connected = self._connected
            processing_running = self._processing_running
            measuring = self._measuring
            last_error = self._last_error
        if not connected:
            image_status = self._image_source.get_status()
            connected = bool(image_status.get("capture_opened"))
        if not connected:
            state = "DISCONNECTED"
        elif len(self.get_roi_points()) != 4:
            state = "READY_NO_ROI"
        elif self.get_baseline() is None:
            state = "READY_NO_BASELINE"
        elif measuring:
            state = "MEASURING"
        else:
            state = "READY"
        return {
            "state": state,
            "connected": connected,
            "processing_running": processing_running,
            "measuring": measuring,
            "has_roi": len(self.get_roi_points()) == 4,
            "roi_points": self.get_roi_points(),
            "baseline_level_y": self.get_baseline(),
            "detector_params": self.get_detector_params(),
            "measurement": self.get_measurement(),
            "image_source": self._image_source.get_status(),
            "last_error": last_error,
        }

    def _start_processing_loop(self) -> bool:
        with self._lock:
            if self._processing_running:
                return True
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._measurement_loop,
                name="PowderLevelProcessingThread",
                daemon=True,
            )
            self._processing_running = True
            self._thread.start()
        self._logger.info("<POWDER ACTION> processing loop started")
        return True

    def _stop_processing_loop(self) -> bool:
        self._stop_event.set()
        thread = self._thread
        if thread is not None:
            if thread.is_alive():
                thread.join(timeout=2.0)
        with self._lock:
            self._thread = None
            self._processing_running = False
        self._logger.info("<POWDER ACTION> processing loop stopped")
        return True

    def _measurement_loop(self) -> None:
        while not self._stop_event.is_set():
            self.process_once()
            time.sleep(self._measurement_interval_sec)
        with self._lock:
            self._processing_running = False
    def _process_frame(
        self,
        frame: np.ndarray,
        roi_points: List[List[int]],
        controls: ControlValues,
    ) -> Tuple[
        Optional[SurfaceDetection],
        Optional[float],
        Optional[Tuple[int, int]],
        Optional[Tuple[int, int]],
    ]:
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
        surface: Optional[SurfaceDetection] = self._detect_surface(
            mask,
            controls,
        )

        if surface is None:
            return None, None, None, None

        current_level_y: float = inner_box[1] + surface.center_y

        rectified_line = np.array(
            [
                [
                    [
                        inner_box[0] + surface.line_left[0],
                        inner_box[1] + surface.line_left[1],
                    ],
                    [
                        inner_box[0] + surface.line_right[0],
                        inner_box[1] + surface.line_right[1],
                    ],
                ]
            ],
            dtype=np.float32,
        )
        inverse_matrix = np.linalg.inv(matrix)
        source_line = cv2.perspectiveTransform(
            rectified_line,
            inverse_matrix,
        )[0]

        line_left = (
            int(round(float(source_line[0][0]))),
            int(round(float(source_line[0][1]))),
        )
        line_right = (
            int(round(float(source_line[1][0]))),
            int(round(float(source_line[1][1]))),
        )

        return surface, current_level_y, line_left, line_right

    def _create_perspective_matrix(
        self,
        roi_points: List[List[int]],
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
    ) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
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
        points: List[Tuple[int, int]] = []

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
    ) -> Optional[SurfaceDetection]:
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
        line_left: Tuple[int, int],
        line_right: Tuple[int, int],
        decrease_mm: Optional[float],
        frame_id: Optional[int],
        frame_time_ns: Optional[int],
    ) -> None:
        with self._lock:
            self._latest_surface = surface
            self._latest_level_y = float(level_y)
            self._latest_line_left = line_left
            self._latest_line_right = line_right
            self._latest_decrease_mm = decrease_mm
            self._latest_detected = True
            self._latest_frame_id = frame_id
            self._latest_frame_time_ns = frame_time_ns
            self._timestamp_ns = int(time.time() * 1000000000)
            self._last_error = None

    def _make_control_values(
        self,
        params: Dict[str, Any],
    ) -> ControlValues:
        with self._lock:
            current_values: Dict[str, Any] = asdict(
                self._control_values,
            )

        valid_names: Set[str] = self._get_control_value_names()

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

    def _get_control_value_names(self) -> Set[str]:
        control_value_names: Set[str] = set()

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
