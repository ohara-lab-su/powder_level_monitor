"""粉体表面認識の交換可能な実装。通信・カメラ取得・測定状態には依存しない。"""
from typing import List, Optional, Tuple

import cv2
import numpy as np

from powder_level_monitor.data_control_values import ControlValues
from powder_level_monitor.data_surface_detection import SurfaceDetection


class PowderDetector:
    """Webカメラ画像から粉面位置を推定する、交換対象の画像認識クラス。

    現行方式（0.0.xから移設した初期実装）:
        1. ROIの四隅を360×720 pxの矩形へ透視変換する。
        2. 矩形の外周を除外して瓶の縁などの影響を抑える。
        3. グレースケール化、CLAHE、GaussianBlurで画像を前処理する。
        4. Otsu法または手動閾値で二値化し、必要に応じて白黒を反転する。
        5. オープニング・クロージングで孤立ノイズやマスクの欠損を処理する。
        6. マスク面積と行方向の白画素占有率で候補を棄却する。
        7. 各列を上から走査し、一定区間に70%以上の白画素が続く
           最初の位置を表面候補点として採用する。
        8. 候補点のY座標について中央値とMADで外れ値を除去する。
        9. 残った点にcv2.fitLine（L2距離）で直線を当てはめる。
       10. 直線の中央Yを補正画像の座標へ戻し、左右端点は逆透視変換で
           原画像座標へ戻して返す。

    この方式は粉面が画像上で概ね一本の境界線として見え、適切な
    二値化によって粉体側が連続した白領域になることを仮定する。
    瓶の反射、背景、照明むら、粉体の色や表面形状によっては成立しない。
    また、マスクの面積・占有率だけでは偽検出を完全には排除できない。

    変更可能な範囲:
        前処理、領域判定、境界抽出、フィッティングなどの認識方式全体。
        既存アルゴリズムの採用は必須ではない。ただし、制御クラスが
        利用するdetect()の入力、返値、座標系を維持する必要がある。

    担当しない処理:
        カメラの接続・切断、測定開始・停止、Baseline・mm換算、gRPC通信。
    """

    RECTIFIED_WIDTH = 360
    RECTIFIED_HEIGHT = 720

    def detect(
        self,
        frame: np.ndarray,
        roi_points: List[List[int]],
        controls: ControlValues,
    ) -> Tuple[
        Optional[SurfaceDetection],
        Optional[float],
        Optional[Tuple[int, int]],
        Optional[Tuple[int, int]],
    ]:
        """画像を解析して粉面位置を返す公開インターフェース。

        Args:
            frame: OpenCVのBGR画像（原画像座標系）。
            roi_points: 左上、右上、右下、左下の順の4点。
            controls: 現行方式の調整値。認識方式変更時は互換性に注意。

        Returns:
            (SurfaceDetection, 補正画像の中央Y, 原画像の左端点,
            原画像の右端点)。検出できない場合は全要素None。
            中央Yは360×720 pxの補正画像上のY座標であり、
            元画像のY座標でも実寸mmでもない。
        """
        return self._process_frame(frame, roi_points, controls)

    def _process_frame(
        self,
        frame: np.ndarray,
        roi_points: List[List[int]],
        controls: ControlValues,
    ) -> Tuple[
        Optional[SurfaceDetection],
        Optional[float],
        Optional[Tuple[int, int]],
        Optional[Tuple[int, int]],
    ]:
        """ROIを矩形へ透視変換し、粉体マスクと表面直線を算出する。
        
        Args:
            frame: 入力となるBGR画像。
            roi_points: 透視変換元となる画像座標系の4点。
            controls: 検出アルゴリズムの調整値。
        
        Returns:
            検出結果、補正画像上の中心Y座標、元画像上の左右端点。検出失敗時は検出結果が None。
        """
        matrix: np.ndarray = self._create_perspective_matrix(roi_points)
        rectified: np.ndarray = cv2.warpPerspective(
            frame,
            matrix,
            (
                self.RECTIFIED_WIDTH,
                self.RECTIFIED_HEIGHT,
            ),
        )

        inner_roi, inner_box = self._crop_inner_roi(
            rectified,
            controls,
        )
        mask: np.ndarray = self._create_powder_mask(
            inner_roi,
            controls,
        )
        surface: Optional[SurfaceDetection] = self._detect_surface(
            mask,
            controls,
        )

        if surface is None:
            return None, None, None, None

        current_level_y: float = inner_box[1] + surface.center_y

        rectified_line = np.array(
            [
                [
                    [
                        inner_box[0] + surface.line_left[0],
                        inner_box[1] + surface.line_left[1],
                    ],
                    [
                        inner_box[0] + surface.line_right[0],
                        inner_box[1] + surface.line_right[1],
                    ],
                ]
            ],
            dtype=np.float32,
        )
        inverse_matrix = np.linalg.inv(matrix)
        source_line = cv2.perspectiveTransform(
            rectified_line,
            inverse_matrix,
        )[0]

        line_left = (
            int(round(float(source_line[0][0]))),
            int(round(float(source_line[0][1]))),
        )
        line_right = (
            int(round(float(source_line[1][0]))),
            int(round(float(source_line[1][1]))),
        )

        return surface, current_level_y, line_left, line_right

    def _create_perspective_matrix(
        self,
        roi_points: List[List[int]],
    ) -> np.ndarray:
        """4点ROIを固定サイズの長方形へ写す透視変換行列を作成する。
        
        Args:
            roi_points: 元画像上の4点。
        
        Returns:
            透視変換行列（3×3）。逆行列はここでは返さない。
        """
        # GUIで指定された4点の順序を維持して、固定寸法の長方形へ対応付ける。
        source_points = np.array(
            roi_points,
            dtype=np.float32,
        )
        destination_points = np.array(
            [
                [0.0, 0.0],
                [self.RECTIFIED_WIDTH - 1.0, 0.0],
                [
                    self.RECTIFIED_WIDTH - 1.0,
                    self.RECTIFIED_HEIGHT - 1.0,
                ],
                [0.0, self.RECTIFIED_HEIGHT - 1.0],
            ],
            dtype=np.float32,
        )

        return cv2.getPerspectiveTransform(
            source_points,
            destination_points,
        )

    def _crop_inner_roi(
        self,
        rectified: np.ndarray,
        controls: ControlValues,
    ) -> Tuple[np.ndarray, Tuple[int, int, int, int]]:
        """補正画像の外周を比率指定で除外し、検出対象領域を切り出す。
        
        Args:
            rectified: 透視補正済み画像。
            controls: 外周除外率を含む調整値。
        
        Returns:
            切り出した画像と補正画像上の矩形座標。
        """
        height, width = rectified.shape[:2]
        margin_x: int = int(width * controls.margin_x_ratio)
        margin_y: int = int(height * controls.margin_y_ratio)

        x1: int = max(0, margin_x)
        y1: int = max(0, margin_y)
        x2: int = min(width, width - margin_x)
        y2: int = min(height, height - margin_y)

        if x2 <= x1:
            x1 = 0
            x2 = width

        if y2 <= y1:
            y1 = 0
            y2 = height

        inner: np.ndarray = rectified[y1:y2, x1:x2]
        return inner, (x1, y1, x2, y2)

    def _create_powder_mask(
        self,
        inner_roi: np.ndarray,
        controls: ControlValues,
    ) -> np.ndarray:
        """輝度補正、平滑化、二値化、モルフォロジー処理で粉体候補マスクを作る。
        
        Args:
            inner_roi: 検出対象として切り出したBGR画像。
            controls: 二値化方式とカーネルサイズを含む調整値。
        
        Returns:
            粉体候補を255とする8ビット二値画像。
        """
        # 色情報を捨て、照明むらをCLAHEで緩和してから二値化する。
        gray: np.ndarray = cv2.cvtColor(
            inner_roi,
            cv2.COLOR_BGR2GRAY,
        )
        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8),
        )
        gray = clahe.apply(gray)
        gray = cv2.GaussianBlur(
            gray,
            (
                controls.blur,
                controls.blur,
            ),
            0,
        )

        if controls.mode == 0:
            _, mask = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY + cv2.THRESH_OTSU,
            )
        elif controls.mode == 1:
            _, mask = cv2.threshold(
                gray,
                0,
                255,
                cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU,
            )
        elif controls.mode == 2:
            _, mask = cv2.threshold(
                gray,
                controls.manual_threshold,
                255,
                cv2.THRESH_BINARY,
            )
        else:
            _, mask = cv2.threshold(
                gray,
                controls.manual_threshold,
                255,
                cv2.THRESH_BINARY_INV,
            )

        if controls.open_kernel > 1:
            open_kernel = np.ones(
                (
                    controls.open_kernel,
                    controls.open_kernel,
                ),
                np.uint8,
            )
            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_OPEN,
                open_kernel,
                iterations=1,
            )

        if controls.close_kernel > 1:
            close_kernel = np.ones(
                (
                    controls.close_kernel,
                    controls.close_kernel,
                ),
                np.uint8,
            )
            mask = cv2.morphologyEx(
                mask,
                cv2.MORPH_CLOSE,
                close_kernel,
                iterations=1,
            )

        return mask

    def _extract_surface_points(
        self,
        mask: np.ndarray,
        controls: ControlValues,
    ) -> np.ndarray:
        """各列を上から走査し、縦方向に連続性がある最上端点を抽出する。
        
        Args:
            mask: 粉体候補の二値画像。
            controls: 連続性判定に使用する行数を含む調整値。
        
        Returns:
            表面候補点のN×2配列。
        """
        height, width = mask.shape[:2]
        points: List[Tuple[int, int]] = []

        # 各列の最上端から、一定行数以上連続する白画素の開始点を表面候補とする。
        for x in range(width):
            column = mask[:, x] > 0
            ys = np.where(column)[0]

            if len(ys) == 0:
                continue

            for y in ys:
                y2: int = min(height, y + controls.stable_rows)
                support: int = int(np.count_nonzero(column[y:y2]))
                required: int = max(1, int((y2 - y) * 0.7))

                if support >= required:
                    points.append((x, int(y)))
                    break

        if len(points) == 0:
            return np.empty((0, 2), dtype=np.float32)

        return np.array(points, dtype=np.float32)

    def _filter_surface_points(
        self,
        points: np.ndarray,
    ) -> np.ndarray:
        """Y座標の中央値とMADを用いて表面候補点の外れ値を除去する。
        
        Args:
            points: 表面候補点のN×2配列。
        
        Returns:
            外れ値を除去した候補点。
        """
        if len(points) < 5:
            return points

        y_values = points[:, 1]
        median_y: float = float(np.median(y_values))
        deviation = np.abs(y_values - median_y)
        mad: float = float(np.median(deviation))

        if mad < 1.0:
            limit: float = 8.0
        else:
            limit = max(8.0, mad * 3.0)

        # 標準偏差より外れ値に頑健なMADを使用し、局所的なノイズを除外する。
        keep = deviation <= limit
        return points[keep]

    def _detect_surface(
        self,
        mask: np.ndarray,
        controls: ControlValues,
    ) -> Optional[SurfaceDetection]:
        """面積、行占有率、点数を検証し、候補点へ直線を当てはめる。
        
        Args:
            mask: 粉体候補の二値画像。
            controls: 検出成立条件を含む調整値。
        
        Returns:
            表面直線の検出結果。成立しない場合は None。
        """
        mask_area: int = int(cv2.countNonZero(mask))

        if mask_area < controls.min_area:
            return None

        height, width = mask.shape[:2]
        row_hit = np.count_nonzero(mask, axis=1) / float(width)

        if np.max(row_hit) < controls.row_ratio_threshold:
            return None

        points: np.ndarray = self._extract_surface_points(
            mask,
            controls,
        )
        points = self._filter_surface_points(points)

        if len(points) < max(12, width * 0.08):
            return None

        # 個々の候補点の凹凸を平均化し、粉面を一本の直線として表現する。
        line = cv2.fitLine(
            points,
            cv2.DIST_L2,
            0,
            0.01,
            0.01,
        )
        vx, vy, x0, y0 = [
            float(value)
            for value in line.flatten()
        ]

        if abs(vx) < 1.0e-6:
            y_left: float = float(np.median(points[:, 1]))
            y_right: float = y_left
        else:
            y_left = y0 + (vy / vx) * (0.0 - x0)
            y_right = y0 + (vy / vx) * ((width - 1.0) - x0)

        y_left = float(np.clip(y_left, 0, height - 1))
        y_right = float(np.clip(y_right, 0, height - 1))
        center_x: float = (width - 1.0) / 2.0

        if abs(vx) < 1.0e-6:
            center_y: float = y_left
        else:
            center_y = y0 + (vy / vx) * (center_x - x0)

        center_y = float(np.clip(center_y, 0, height - 1))

        return SurfaceDetection(
            center_y=center_y,
            line_left=(0, int(round(y_left))),
            line_right=(width - 1, int(round(y_right))),
            point_count=len(points),
        )

