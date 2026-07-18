#!/usr/bin/env python
# from __future__ import annotations

import time
from dataclasses import asdict
from dataclasses import fields
from typing import Any

from power_level_monitor.data_control_values import ControlValues


class PowderControlDeviceClass:
    """粉体レベル制御用のローカル DeviceClass である。

    ese774_frame の FastAPI サーバーに載せる実体である。
    画像転送は扱わない。
    ROI、baseline、検出パラメータ、測定状態を保持する。
    """

    def __init__(
        self,
        logger: Any | None = None,
    ) -> None:
        self._logger: Any | None = logger
        self._roi_points: list[list[int]] = []
        self._baseline_level_y: float | None = None
        self._latest_level_y: float | None = None
        self._latest_decrease_mm: float | None = None
        self._control_values: ControlValues = ControlValues()
        self._running: bool = False
        self._timestamp_ns: int | None = None

    def connect(self) -> bool:
        """接続処理を行う。

        Returns:
            bool: 接続処理の結果である。
        """
        self._running = False
        self._timestamp_ns = time.time_ns()
        return True

    def disconnect(self) -> bool:
        """切断処理を行う。

        Returns:
            bool: 切断処理の結果である。
        """
        self._running = False
        self._timestamp_ns = time.time_ns()
        return True

    def start(self) -> bool:
        """測定制御を開始する。

        Returns:
            bool: 開始処理の結果である。
        """
        self._running = True
        self._timestamp_ns = time.time_ns()
        return True

    def stop(self) -> bool:
        """測定制御を停止する。

        Returns:
            bool: 停止処理の結果である。
        """
        self._running = False
        self._timestamp_ns = time.time_ns()
        return True

    def set_roi_points(
        self,
        points: list[list[int]],
    ) -> bool:
        """ROI 4点を設定する。

        Args:
            points: 画像座標系の ROI 点列である。

        Returns:
            bool: 設定処理の結果である。
        """
        if len(points) != 4:
            raise ValueError("ROI points must contain four points.")

        normalized_points: list[list[int]] = []
        for point in points:
            if len(point) != 2:
                raise ValueError("Each ROI point must contain x and y.")

            x_value: int = int(point[0])
            y_value: int = int(point[1])
            normalized_points.append([x_value, y_value])

        self._roi_points = normalized_points
        self._timestamp_ns = time.time_ns()
        return True

    def get_roi_points(self) -> list[list[int]]:
        """ROI 4点を取得する。

        Returns:
            list[list[int]]: ROI 点列である。
        """
        copied_points: list[list[int]] = []
        for point in self._roi_points:
            copied_point: list[int] = [int(point[0]), int(point[1])]
            copied_points.append(copied_point)

        return copied_points

    def clear_roi_points(self) -> bool:
        """ROI 4点を消去する。

        Returns:
            bool: 消去処理の結果である。
        """
        self._roi_points = []
        self._timestamp_ns = time.time_ns()
        return True

    def set_baseline(
        self,
        level_y: float,
    ) -> bool:
        """baseline の y 座標を設定する。

        Args:
            level_y: baseline の y 座標である。

        Returns:
            bool: 設定処理の結果である。
        """
        self._baseline_level_y = float(level_y)
        self._timestamp_ns = time.time_ns()
        return True

    def get_baseline(self) -> float | None:
        """baseline の y 座標を取得する。

        Returns:
            float | None: baseline の y 座標である。
        """
        return self._baseline_level_y

    def set_detector_params(
        self,
        params: dict[str, Any],
    ) -> bool:
        """検出パラメータを設定する。

        Args:
            params: 検出パラメータである。

        Returns:
            bool: 設定処理の結果である。
        """
        self._control_values = self._make_control_values(params)
        self._timestamp_ns = time.time_ns()
        return True

    def get_detector_params(self) -> dict[str, Any]:
        """検出パラメータを取得する。

        Returns:
            dict[str, Any]: 検出パラメータである。
        """
        return asdict(self._control_values)

    def update_measurement(
        self,
        level_y: float,
        decrease_mm: float | None,
    ) -> bool:
        """測定値を更新する。

        Args:
            level_y: 粉体上面の y 座標である。
            decrease_mm: baseline からの変化量である。

        Returns:
            bool: 更新処理の結果である。
        """
        self._latest_level_y = float(level_y)
        self._latest_decrease_mm = decrease_mm
        self._timestamp_ns = time.time_ns()
        return True

    def get_measurement(self) -> dict[str, Any]:
        """測定値を取得する。

        Returns:
            dict[str, Any]: 測定状態である。
        """
        return {
            "level_y": self._latest_level_y,
            "decrease_mm": self._latest_decrease_mm,
            "baseline_level_y": self._baseline_level_y,
            "timestamp_ns": self._timestamp_ns,
        }

    def get_status(self) -> dict[str, Any]:
        """制御 DeviceClass の状態を取得する。

        Returns:
            dict[str, Any]: 状態である。
        """
        has_roi: bool = False
        if len(self._roi_points) == 4:
            has_roi = True

        return {
            "running": self._running,
            "has_roi": has_roi,
            "roi_points": self.get_roi_points(),
            "baseline_level_y": self._baseline_level_y,
            "detector_params": self.get_detector_params(),
            "measurement": self.get_measurement(),
        }

    def _make_control_values(
        self,
        params: dict[str, Any],
    ) -> ControlValues:
        """API入力辞書から ControlValues を作る。

        Args:
            params: API 経由で受け取った検出パラメータである。

        Returns:
            ControlValues: 正規化後の検出パラメータである。
        """
        current_values: dict[str, Any] = asdict(self._control_values)
        valid_names: set[str] = self._get_control_value_names()

        for key, value in params.items():
            if key not in valid_names:
                raise KeyError(f"unknown detector parameter: {key}")

            current_values[key] = value

        mode: int = int(current_values["mode"])
        manual_threshold: int = int(current_values["manual_threshold"])
        blur: int = self._make_odd(current_values["blur"])
        open_kernel: int = self._make_odd(current_values["open_kernel"])
        close_kernel: int = self._make_odd(current_values["close_kernel"])
        row_ratio_threshold: float = float(current_values["row_ratio_threshold"])
        stable_rows: int = max(1, int(current_values["stable_rows"]))
        min_area: int = max(0, int(current_values["min_area"]))
        margin_x_ratio: float = float(current_values["margin_x_ratio"])
        margin_y_ratio: float = float(current_values["margin_y_ratio"])
        measure_height_mm: float = max(
            1.0,
            float(current_values["measure_height_mm"]),
        )

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
        """ControlValues のフィールド名を取得する。

        Returns:
            set[str]: ControlValues のフィールド名である。
        """
        control_value_names: set[str] = set()
        for field_info in fields(ControlValues):
            control_value_names.add(field_info.name)

        return control_value_names

    def _make_odd(
        self,
        value: Any,
    ) -> int:
        """kernel size を1以上の奇数へ補正する。

        Args:
            value: 入力値である。

        Returns:
            int: 1以上の奇数である。
        """
        odd_value: int = max(1, int(value))

        if odd_value % 2 == 0:
            odd_value = odd_value + 1

        return odd_value
