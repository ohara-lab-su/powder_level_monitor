from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SurfaceDetection:
    """粉体上面の検出結果である。

    元の powder_level_monitor.py に定義されていた SurfaceDetection を
    DeviceClass 側から参照するためのデータ定義である。
    変換、検証、描画処理はこのクラスでは行わない。
    """

    center_y: float
    line_left: tuple[int, int]
    line_right: tuple[int, int]
    point_count: int
