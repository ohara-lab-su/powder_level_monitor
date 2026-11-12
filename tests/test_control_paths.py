"""通信を使わずにローカル制御とgRPCサービス層の委譲を確認する。"""
import time
from unittest.mock import patch

import numpy as np

from powder_level_monitor.image_stream import ImageStream
from powder_level_monitor.powder_monitor_ctrl import PowderControlDeviceClass
from powder_level_monitor.server_grpc.powder_level_grpc_service import PowderLevelGrpcService


class Logger:
    def info(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def debug(self, *args, **kwargs):
        pass


class FakeCamera:
    def __init__(self, index):
        self.index = index
        self.opened = True
        self.read_count = 0

    def isOpened(self):
        return self.opened

    def read(self):
        self.read_count += 1
        return True, np.zeros((720, 360, 3), dtype=np.uint8)

    def release(self):
        self.opened = False


def wait_frame(stream):
    deadline = time.monotonic() + 2
    while stream.get_latest_frame() is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert stream.get_latest_frame() is not None


def test_local_control_camera_lifecycle():
    logger = Logger()
    with patch('powder_level_monitor.image_stream.cv2.VideoCapture', FakeCamera):
        stream = ImageStream(logger=logger, capture_interval_sec=0.01)
        ctrl = PowderControlDeviceClass(image_source=stream, logger=logger)
        assert ctrl._image_source is stream
        assert ctrl.connect()
        wait_frame(stream)
        assert ctrl.set_roi_points([[0, 0], [359, 0], [359, 719], [0, 719]])
        assert isinstance(ctrl.process_once(), bool)
        assert ctrl.disconnect()
        assert not stream.get_status()['capture_opened']


def test_service_delegates_to_same_control_and_camera():
    logger = Logger()
    with patch('powder_level_monitor.image_stream.cv2.VideoCapture', FakeCamera):
        service = PowderLevelGrpcService(logger=logger, capture_interval_sec=0.01)
        assert service._powder_device._image_source is service._image_device
        assert service.connect()
        wait_frame(service._image_device)
        roi = [[0, 0], [359, 0], [359, 719], [0, 719]]
        assert service.set_roi_points(roi)
        assert service.get_roi_points() == roi
        assert isinstance(service.process_once(), bool)
        assert service.get_measurement() == service._powder_device.get_measurement()
        assert service.disconnect()
