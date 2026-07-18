#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画像配信と粉体レベル測定を統合して gRPC 公開するサービスを提供する。"""

from powder_level_monitor.image_stream_ctrl import ImageStreamDeviceClass
from powder_level_monitor.powder_monitor_ctrl import PowderControlDeviceClass


class PowderLevelGrpcService:
    """画像取得・配信と粉体表面測定を単一のgRPC制御対象として公開する。"""

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
        """画像配信デバイスと粉体測定デバイスを構築する。
        
        Args:
            camera_id: OpenCVへ渡すカメラデバイス番号。
            image_topic: JPEG画像を配信するEventBusトピック名。
            image_interval_sec: 画像配信周期（秒）。
            capture_interval_sec: カメラ取得周期（秒）。
            measurement_interval_sec: 粉体表面の解析周期（秒）。
            jpeg_quality: JPEG品質。0から100の範囲を想定する。
            logger: 画像配信と測定処理で共有するロガー。
        """
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
        """grpc_frame から渡された EventBus を画像配信処理へ設定する。
        
        Args:
            event_bus: 画像イベントの配信に使用する EventBus。
        """
        self._image_device._set_event_bus(event_bus)

    def connect(self):
        """必要なデバイス接続と内部処理ループを開始する。
        
        Returns:
            接続と起動に成功した場合は True、それ以外は False。
        """
        self._logger.info("<POWDER LEVEL ACTION> connect")
        return self._powder_device.connect()

    def disconnect(self):
        """内部処理ループを停止し、デバイス接続を解放する。
        
        Returns:
            正常に切断処理を完了した場合は True。
        """
        self._logger.info("<POWDER LEVEL ACTION> disconnect")
        self._image_device.stop_stream()
        return self._powder_device.disconnect()

    def start_stream(self):
        """最新画像を一定周期で EventBus へ配信するスレッドを開始する。
        
        Returns:
            配信を開始できた場合は True。
        
        Raises:
            RuntimeError: EventBus が設定されていない場合。
        """
        return self._image_device.start_stream()

    def stop_stream(self):
        """画像配信スレッドを停止する。
        
        Returns:
            停止済みまたは正常に停止した場合は True。
        """
        return self._image_device.stop_stream()

    def publish_once(self):
        """最新画像をJPEGへ符号化し、EventBusへ1回だけ配信する。
        
        Returns:
            配信に成功した場合は True。
        
        Raises:
            RuntimeError: EventBusまたは最新画像が利用できない場合。
        """
        return self._image_device.publish_once()

    def get_image_status(self):
        """画像取得・配信処理の状態を取得する。
        
        Returns:
            画像取得および配信状態を格納した辞書。
        """
        return self._image_device.get_status()

    def start_measurement(self):
        """ROI、Baseline、最新検出結果を確認して連続測定を開始する。
        
        Returns:
            測定開始条件を満たした場合は True。
        """
        return self._powder_device.start_measurement()

    def stop_measurement(self):
        """連続測定フラグを解除する。
        
        Returns:
            常に True。
        """
        return self._powder_device.stop_measurement()

    def is_measuring(self):
        """現在の連続測定状態を取得する。
        
        Returns:
            測定中の場合は True。
        """
        return self._powder_device.is_measuring()

    def process_once(self):
        """最新カメラ画像を1枚処理し、粉体表面と減少量を更新する。
        
        Returns:
            有効な粉体表面を検出できた場合は True。
        """
        return self._powder_device.process_once()

    def set_roi_points(self, points):
        """透視変換に使用する4点のROI座標を設定する。
        
        Args:
            points: 画像座標系の4点。各点は ``[x, y]`` で指定する。
        
        Returns:
            設定に成功した場合は True。
        
        Raises:
            ValueError: 点数が4点でない、または各点が2要素でない場合。
        """
        return self._powder_device.set_roi_points(points)

    def get_roi_points(self):
        """現在設定されているROI座標のコピーを取得する。
        
        Returns:
            画像座標系のROI座標。
        """
        return self._powder_device.get_roi_points()

    def clear_roi_points(self):
        """ROIとROIに依存するBaselineおよび測定結果を消去する。
        
        Returns:
            常に True。
        """
        return self._powder_device.clear_roi_points()

    def set_baseline(self):
        """最新の有効な粉体表面位置をBaselineとして保存する。
        
        Returns:
            Baselineを設定できた場合は True。
        """
        return self._powder_device.set_baseline()

    def get_baseline(self):
        """現在のBaseline位置を取得する。
        
        Returns:
            補正画像座標系のBaselineのY座標。未設定時は None。
        """
        return self._powder_device.get_baseline()

    def clear_baseline(self):
        """BaselineとBaselineに依存する減少量を消去する。
        
        Returns:
            常に True。
        """
        return self._powder_device.clear_baseline()

    def set_detector_params(self, params):
        """粉体表面検出パラメータを検証して更新する。
        
        Args:
            params: 更新するパラメータ名と値の辞書。
        
        Returns:
            更新に成功した場合は True。
        
        Raises:
            KeyError: 未知のパラメータ名が含まれる場合。
            ValueError: 値が許容範囲外の場合。
        """
        return self._powder_device.set_detector_params(params)

    def get_detector_params(self):
        """現在の粉体表面検出パラメータを取得する。
        
        Returns:
            検出パラメータの辞書。
        """
        return self._powder_device.get_detector_params()

    def get_measurement(self):
        """最新の粉体表面検出結果とBaseline差分を取得する。
        
        Returns:
            測定値、検出線、時刻、エラー状態を格納した辞書。
        """
        return self._powder_device.get_measurement()

    def get_status(self):
        """接続、処理ループ、ROI、測定状態をまとめて取得する。
        
        Returns:
            制御対象の状態を格納した辞書。
        """
        status = self._powder_device.get_status()
        status["image_stream"] = self._image_device.get_status()
        return status
