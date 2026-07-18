
"""粉体表面検出アルゴリズムの調整値を定義する。"""
from dataclasses import dataclass


@dataclass
class ControlValues:
    """粉体表面検出アルゴリズムの調整値。

Attributes:
    mode: 二値化モード。0/1はOtsu、2/3は手動閾値を使用する。
    manual_threshold: 手動二値化に使用する0から255の閾値。
    blur: GaussianBlurのカーネルサイズ。
    open_kernel: オープニング処理のカーネルサイズ。
    close_kernel: クロージング処理のカーネルサイズ。
    row_ratio_threshold: 検出成立に必要な行方向の白画素比率。
    stable_rows: 表面候補点の縦方向連続性を確認する行数。
    min_area: 検出成立に必要なマスクの最小白画素数。
    margin_x_ratio: 補正画像の左右から除外する比率。
    margin_y_ratio: 補正画像の上下から除外する比率。
    measure_height_mm: 補正画像全高に対応する実測高さ。"""

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
