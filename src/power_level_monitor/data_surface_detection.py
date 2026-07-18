from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SurfaceDetection:
    """粉体上面の検出結果である。"""

    center_y: float
    line_left: tuple[int, int]
    line_right: tuple[int, int]
    point_count: int
