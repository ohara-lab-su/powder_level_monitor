
"""粉体表面の直線検出結果を表すデータ型を定義する。"""
from typing import Tuple

from dataclasses import dataclass


@dataclass
class SurfaceDetection:
    """粉体表面へ当てはめた直線の検出結果。

Attributes:
    center_y: 補正画像中央における表面直線のY座標。
    line_left: 検出領域左端における直線座標。
    line_right: 検出領域右端における直線座標。
    point_count: 直線当てはめに使用した候補点数。"""

    center_y: float
    line_left: Tuple[int, int]
    line_right: Tuple[int, int]
    point_count: int
