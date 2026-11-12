"""通信なしで検出器の入出力契約を確認する。"""
import numpy as np

from powder_level_monitor.data_control_values import ControlValues
from powder_level_monitor.powder_detector import PowderDetector


def test_detector_output_contract():
    image = np.zeros((720, 360, 3), dtype=np.uint8)
    roi = [[0, 0], [359, 0], [359, 719], [0, 719]]
    result = PowderDetector().detect(image, roi, ControlValues())
    assert len(result) == 4
    if result[0] is not None:
        assert isinstance(result[1], float)
        assert len(result[2]) == len(result[3]) == 2
