from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ControlValues:
    """粉体検出の調整値である。

    元の powder_level_monitor.py に定義されていた ControlValues を
    DeviceClass 側から参照するためのデータ定義である。
    変換、検証、補正はこのクラスでは行わない。
    """

    mode: int = 0
    manual_threshold: int = 120
    blur: int = 5
    open_kernel: int = 3
    close_kernel: int = 7
    row_ratio_threshold: float = 0.35
    stable_rows: int = 6
    min_area: int = 500
    margin_x_ratio: float = 0.12
    margin_y_ratio: float = 0.03
    measure_height_mm: float = 100.0
