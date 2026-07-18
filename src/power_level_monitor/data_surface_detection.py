from typing import Tuple

from dataclasses import dataclass


@dataclass
class SurfaceDetection:
    """粉体上面の検出結果である。"""

    center_y: float
    line_left: Tuple[int, int]
    line_right: Tuple[int, int]
    point_count: int
