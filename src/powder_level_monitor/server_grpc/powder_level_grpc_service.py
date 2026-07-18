#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Camera streaming and powder measurement device."""

from powder_level_monitor.image_stream_ctrl import ImageStreamDeviceClass
from powder_level_monitor.powder_monitor_ctrl import PowderControlDeviceClass


class PowderLevelGrpcService:
    """画像取得・gRPC画像配信・粉体測定を一つの制御対象として公開する。"""

    def __init__(
        self,
        camera_id=0,
        image_topic="camera.frame",
        image_interval_sec=0.1,
        capture_interval_sec=0.03,
        measurement_interval_sec=0.1,
        jpeg_quality=85,
        logger=None,
    ):
        if logger is None:
            from x_logger import XLogger

            logger = XLogger(
                log_level="debug",
                logger_name=self.__class__.__name__,
            )

        self._logger = logger
        self._image_device = ImageStreamDeviceClass(
            camera_id=camera_id,
            topic_name=image_topic,
            interval_sec=image_interval_sec,
            capture_interval_sec=capture_interval_sec,
            jpeg_quality=jpeg_quality,
            logger=logger,
        )
        self._powder_device = PowderControlDeviceClass(
            image_source=self._image_device,
            measurement_interval_sec=measurement_interval_sec,
            logger=logger,
        )

    def _set_event_bus(self, event_bus):
        """grpc_frame から注入された EventBus を画像配信クラスへ渡す。"""
        self._image_device._set_event_bus(event_bus)

    def connect(self):
        """カメラ取得とサーバー内部の認識ループを開始する。"""
        self._logger.info("<POWDER LEVEL ACTION> connect")
        return self._powder_device.connect()

    def disconnect(self):
        """測定、認識ループ、画像配信、カメラ接続を停止する。"""
        self._logger.info("<POWDER LEVEL ACTION> disconnect")
        self._image_device.stop_stream()
        return self._powder_device.disconnect()

    def start_stream(self):
        return self._image_device.start_stream()

    def stop_stream(self):
        return self._image_device.stop_stream()

    def publish_once(self):
        return self._image_device.publish_once()

    def get_image_status(self):
        return self._image_device.get_status()

    def start_measurement(self):
        return self._powder_device.start_measurement()

    def stop_measurement(self):
        return self._powder_device.stop_measurement()

    def is_measuring(self):
        return self._powder_device.is_measuring()

    def process_once(self):
        return self._powder_device.process_once()

    def set_roi_points(self, points):
        return self._powder_device.set_roi_points(points)

    def get_roi_points(self):
        return self._powder_device.get_roi_points()

    def clear_roi_points(self):
        return self._powder_device.clear_roi_points()

    def set_baseline(self):
        return self._powder_device.set_baseline()

    def get_baseline(self):
        return self._powder_device.get_baseline()

    def clear_baseline(self):
        return self._powder_device.clear_baseline()

    def set_detector_params(self, params):
        return self._powder_device.set_detector_params(params)

    def get_detector_params(self):
        return self._powder_device.get_detector_params()

    def get_measurement(self):
        return self._powder_device.get_measurement()

    def get_status(self):
        status = self._powder_device.get_status()
        status["image_stream"] = self._image_device.get_status()
        return status
