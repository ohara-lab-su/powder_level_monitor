これら#!/usr/bin/env python3
# coding: utf-8
"""
K.NAKADA

Powder Level Measurement

瓶・試験管・透明容器の中に入った粉体の上面位置を検出し、
基準時点から何 mm 減少したかを計算するサンプル。

このサンプルは、単に画像を表示するだけではなく、
調整・確認・基準保存・設定保存を行えるようにしている。

----------------------------------------
目的
----------------------------------------

粉体の残量変化を、画像上の「粉体上面の高さ変化」として測定する。

    baseline時点の粉体上面
        ↓
    現在の粉体上面
        ↓
    pixel差
        ↓
    ROI縦方向の実寸(mm)で換算
        ↓
    decrease_mm

----------------------------------------
基本方針
----------------------------------------

粉体の残量を直接「体積」や「質量」として測るのではなく、
固定カメラ画像上で見える粉体上面の移動量を測る。

そのため、この方式が出す値は：

    ・粉体上面が何 mm 下がったか
    ・見かけ上の高さ変化

である。

----------------------------------------
処理の流れ
----------------------------------------

1. source preview
    元カメラ画像を表示する。
    計測したい瓶の領域を4点クリックする。

2. perspective rectification
    クリックした4点を、正面から見た矩形画像へ射影変換する。
    瓶が少し斜めに写っていても、計測ROIを一定の矩形に揃える。

3. inner ROI crop
    ガラス端・ラベル・背景の影響を避けるため、
    rectified画像の内側だけを測定対象にする。

4. powder mask
    粉体らしい領域を二値化する。
    Otsu / manual threshold と bright / dark を切り替えられる。

5. morphology
    小ノイズ除去と穴埋めを行う。
    粉体maskを、上面検出しやすい形に整える。

6. surface detection
    各列で粉体が最初に現れるY座標を集める。
    外れ値を除去し、cv2.fitLine() で粉体上面の直線を推定する。

7. mm conversion
    baselineとのY差を、measure_height_mm / rectified_height でmm換算する。

----------------------------------------
使うOpenCV関数
----------------------------------------

cv2.VideoCapture()
    カメラ画像を取得する。

cv2.getPerspectiveTransform()
    クリックした4点から射影変換行列を作る。

cv2.warpPerspective()
    瓶ROIを正面矩形に補正する。

cv2.cvtColor()
    BGR画像をGray画像へ変換する。

cv2.createCLAHE()
    局所コントラストを補正し、粉体と背景の差を出しやすくする。

cv2.threshold()
    粉体領域を二値化する。

cv2.morphologyEx()
    maskのノイズ除去・穴埋めをする。

cv2.fitLine()
    粉体上面候補点から代表直線を推定する。

cv2.createTrackbar()
    閾値やmorphology条件を実行中に調整する。

----------------------------------------
操作
----------------------------------------

left click:
    計測ROIの4点を順番に指定する。
    左上、右上、右下、左下。

b:
    現在の粉体上面をbaselineとして設定する。

w:
    ROI、baseline、trackbar設定を保存する。

r:
    ROIクリック点をリセットする。

u:
    最後のクリック点を取り消す。

space:
    pause / resume

h:
    操作説明をterminalに再表示する。

q:
    exit

----------------------------------------
注意
----------------------------------------

measure_height_mm は、クリックしたROIの縦方向に対応する実寸。
瓶全体ではなく、実際に測定したい上下範囲のmmを入れる。

このサンプルは2D画像上の見かけ高さを測る。
粉体の体積、質量、奥行き方向の山形状は直接測らない。
"""

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "powder_level_settings.json"

CAMERA_ID = 0

SOURCE_WINDOW = "powder level source"
RECTIFIED_WINDOW = "powder rectified preview"
MASK_WINDOW = "powder mask preview"
PROFILE_WINDOW = "powder row profile"
CONTROL_WINDOW = "powder controls"

RECTIFIED_WIDTH = 360
RECTIFIED_HEIGHT = 720

# trackbarの初期値。
# 実行中に調整し、wキーで保存できる。
CONTROL_DEFAULTS = {
    "mode": 0,
    "manual_threshold": 120,
    "blur": 5,
    "open_kernel": 3,
    "close_kernel": 7,
    "row_percent": 35,
    "stable_rows": 6,
    "min_area_100": 5,
    "margin_x_percent": 12,
    "margin_y_percent": 3,
    "measure_height_mm": 100,
}

# trackbarの最大値。
# OpenCV trackbar は int のみなので、ratioや面積は後で換算する。
TRACKBAR_MAX = {
    "mode": 3,
    "manual_threshold": 255,
    "blur": 31,
    "open_kernel": 31,
    "close_kernel": 31,
    "row_percent": 100,
    "stable_rows": 30,
    "min_area_100": 200,
    "margin_x_percent": 40,
    "margin_y_percent": 30,
    "measure_height_mm": 500,
}

MODE_NAMES = {
    0: "otsu bright powder",
    1: "otsu dark powder",
    2: "manual bright powder",
    3: "manual dark powder",
}

clicked_points: list[tuple[int, int]] = []
baseline_level_y: float | None = None
paused = False
last_frame: np.ndarray | None = None


@dataclass
class ControlValues:
    """
    trackbarから読んだ現在の調整値。

    trackbarは整数しか扱えないため、
    row_percent や margin_percent は ratio に変換して持つ。
    """

    mode: int
    manual_threshold: int
    blur: int
    open_kernel: int
    close_kernel: int
    row_ratio_threshold: float
    stable_rows: int
    min_area: int
    margin_x_ratio: float
    margin_y_ratio: float
    measure_height_mm: float


@dataclass
class SurfaceDetection:
    """
    粉体上面の検出結果。

    center_y:
        inner ROI 内での粉体上面Y座標。

    line_left / line_right:
        描画用の上面直線の左右端。

    point_count:
        上面推定に使った候補点数。
        少なすぎる場合は検出が不安定。
    """

    center_y: float
    line_left: tuple[int, int]
    line_right: tuple[int, int]
    point_count: int


def noop(value: int) -> None:
    """
    cv2.createTrackbar() に渡す空callback。

    OpenCVのtrackbarはcallbackを要求するが、
    このコードではメインループ側で毎回値を読むため、
    callback内では何もしない。
    """

    pass


def make_odd(value: int) -> int:
    """
    kernel size を奇数に補正する。

    GaussianBlur や morphology kernel は、
    1以上の奇数にしておくと扱いやすい。
    """

    value = max(1, int(value))

    if value % 2 == 0:
        value += 1

    return value


def create_control_panel(defaults: dict) -> None:
    """
    調整用trackbar windowを作成する。

    mode:
        0: Otsuで明るい粉体を抽出
        1: Otsuで暗い粉体を抽出
        2: 手動閾値で明るい粉体を抽出
        3: 手動閾値で暗い粉体を抽出
    """

    cv2.namedWindow(CONTROL_WINDOW)

    for name, default_value in defaults.items():
        cv2.createTrackbar(
            name,
            CONTROL_WINDOW,
            int(default_value),
            TRACKBAR_MAX[name],
            noop,
        )


def read_control_values() -> ControlValues:
    """
    trackbarから現在値を読み取り、計算に使う型へ変換する。

    min_area_100 はUI上の値を100倍してpixel面積にする。
    measure_height_mm は、ROI縦方向の実寸として使う。
    """

    mode = cv2.getTrackbarPos("mode", CONTROL_WINDOW)
    manual_threshold = cv2.getTrackbarPos("manual_threshold", CONTROL_WINDOW)

    blur = make_odd(cv2.getTrackbarPos("blur", CONTROL_WINDOW))
    open_kernel = make_odd(cv2.getTrackbarPos("open_kernel", CONTROL_WINDOW))
    close_kernel = make_odd(cv2.getTrackbarPos("close_kernel", CONTROL_WINDOW))

    row_percent = cv2.getTrackbarPos("row_percent", CONTROL_WINDOW)
    stable_rows = max(1, cv2.getTrackbarPos("stable_rows", CONTROL_WINDOW))
    min_area_100 = cv2.getTrackbarPos("min_area_100", CONTROL_WINDOW)

    margin_x_percent = cv2.getTrackbarPos("margin_x_percent", CONTROL_WINDOW)
    margin_y_percent = cv2.getTrackbarPos("margin_y_percent", CONTROL_WINDOW)

    measure_height_mm = max(
        1,
        cv2.getTrackbarPos("measure_height_mm", CONTROL_WINDOW),
    )

    return ControlValues(
        mode=mode,
        manual_threshold=manual_threshold,
        blur=blur,
        open_kernel=open_kernel,
        close_kernel=close_kernel,
        row_ratio_threshold=row_percent / 100.0,
        stable_rows=stable_rows,
        min_area=min_area_100 * 100,
        margin_x_ratio=margin_x_percent / 100.0,
        margin_y_ratio=margin_y_percent / 100.0,
        measure_height_mm=float(measure_height_mm),
    )


def get_trackbar_state() -> dict:
    """
    現在のtrackbar値を保存用dictとして取得する。
    """

    state = {}

    for name in CONTROL_DEFAULTS:
        state[name] = cv2.getTrackbarPos(name, CONTROL_WINDOW)

    return state


def set_trackbar_state(state: dict) -> None:
    """
    保存済み設定をtrackbarへ反映する。

    古い設定ファイルに存在しないキーは無視する。
    """

    for name, value in state.items():
        if name not in CONTROL_DEFAULTS:
            continue

        cv2.setTrackbarPos(
            name,
            CONTROL_WINDOW,
            int(value),
        )


def load_config() -> dict:
    """
    ROI、baseline、trackbar設定を読み込む。

    設定ファイルがない場合は空dictを返し、
    初期値で起動する。
    """

    if CONFIG_PATH.exists() is False:
        return {}

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def save_config() -> None:
    """
    現在のROI、baseline、trackbar設定をJSONに保存する。
    """

    data = {
        "clicked_points": clicked_points,
        "baseline_level_y": baseline_level_y,
        "rectified_width": RECTIFIED_WIDTH,
        "rectified_height": RECTIFIED_HEIGHT,
        "trackbars": get_trackbar_state(),
    }

    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(f"saved: {CONFIG_PATH}")


def apply_loaded_config(config: dict) -> None:
    """
    JSONから読み込んだ設定を現在状態へ反映する。
    """

    global clicked_points
    global baseline_level_y

    points = config.get("clicked_points", [])

    if len(points) == 4:
        clicked_points = [
            (
                int(point[0]),
                int(point[1]),
            )
            for point in points
        ]

    baseline = config.get("baseline_level_y", None)

    if baseline is not None:
        baseline_level_y = float(baseline)

    trackbars = config.get("trackbars", {})

    if isinstance(trackbars, dict):
        set_trackbar_state(trackbars)


def on_mouse(event, x, y, flags, param) -> None:
    """
    ROI指定用mouse callback。

    4点だけ受け付ける。
    順序は 左上、右上、右下、左下。
    """

    if event != cv2.EVENT_LBUTTONDOWN:
        return

    if len(clicked_points) >= 4:
        return

    clicked_points.append((x, y))
    print(f"clicked {len(clicked_points)}: ({x}, {y})")


def draw_source_overlay(
    frame: np.ndarray,
    controls: ControlValues,
) -> np.ndarray:
    """
    元画像にROI指定状態と操作説明を重ねて表示する。
    """

    display = frame.copy()

    for index, point in enumerate(clicked_points):
        cv2.circle(display, point, 6, (0, 0, 255), -1)

        cv2.putText(
            display,
            str(index + 1),
            (point[0] + 8, point[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
        )

    if len(clicked_points) >= 2:
        for index in range(len(clicked_points) - 1):
            cv2.line(
                display,
                clicked_points[index],
                clicked_points[index + 1],
                (0, 255, 255),
                2,
            )

    if len(clicked_points) == 4:
        cv2.line(
            display,
            clicked_points[3],
            clicked_points[0],
            (0, 255, 255),
            2,
        )

    cv2.putText(
        display,
        "click ROI: LT RT RB LB | b baseline | w save | r reset | u undo | q exit",
        (20, 35),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (0, 255, 0),
        2,
    )

    cv2.putText(
        display,
        f"mode={MODE_NAMES.get(controls.mode, controls.mode)}",
        (20, 65),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (0, 255, 255),
        2,
    )

    return display


def create_perspective_matrix() -> np.ndarray | None:
    """
    ROI 4点から射影変換行列を作成する。

    元画像上の斜めに写った瓶領域を、
    RECTIFIED_WIDTH x RECTIFIED_HEIGHT の正面矩形に変換する。
    """

    if len(clicked_points) != 4:
        return None

    source_points = np.array(clicked_points, dtype=np.float32)

    destination_points = np.array(
        [
            [0.0, 0.0],
            [RECTIFIED_WIDTH - 1.0, 0.0],
            [RECTIFIED_WIDTH - 1.0, RECTIFIED_HEIGHT - 1.0],
            [0.0, RECTIFIED_HEIGHT - 1.0],
        ],
        dtype=np.float32,
    )

    matrix = cv2.getPerspectiveTransform(
        source_points,
        destination_points,
    )

    return matrix


def rectify_roi(
    frame: np.ndarray,
    matrix: np.ndarray,
) -> np.ndarray:
    """
    射影変換によりROIを正面矩形へ補正する。
    """

    return cv2.warpPerspective(
        frame,
        matrix,
        (
            RECTIFIED_WIDTH,
            RECTIFIED_HEIGHT,
        ),
    )


def crop_inner_roi(
    rectified: np.ndarray,
    controls: ControlValues,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    """
    補正後ROIから内側の測定領域だけを切り出す。

    ガラス端、瓶の輪郭、背景、ラベルなどがmaskに混ざると
    粉体面検出が不安定になるため、marginを設ける。
    """

    height, width = rectified.shape[:2]

    margin_x = int(width * controls.margin_x_ratio)
    margin_y = int(height * controls.margin_y_ratio)

    x1 = max(0, margin_x)
    y1 = max(0, margin_y)
    x2 = min(width, width - margin_x)
    y2 = min(height, height - margin_y)

    if x2 <= x1:
        x1 = 0
        x2 = width

    if y2 <= y1:
        y1 = 0
        y2 = height

    inner = rectified[y1:y2, x1:x2]

    return inner, (x1, y1, x2, y2)


def create_powder_mask(
    inner_roi: np.ndarray,
    controls: ControlValues,
) -> np.ndarray:
    """
    粉体領域のmaskを作成する。

    mode 0:
        Otsu threshold で明るい粉体を抽出。

    mode 1:
        Otsu threshold で暗い粉体を抽出。

    mode 2:
        手動thresholdで明るい粉体を抽出。

    mode 3:
        手動thresholdで暗い粉体を抽出。
    """

    gray = cv2.cvtColor(
        inner_roi,
        cv2.COLOR_BGR2GRAY,
    )

    # ガラス反射や照明むらで局所的に暗い/明るい部分が出るため、
    # CLAHEで局所コントラストを補正する。
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

    # open: 小さい白ノイズを除去する。
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

    # close: 粉体領域内部の小さい穴や途切れを埋める。
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


def extract_surface_points(
    mask: np.ndarray,
    controls: ControlValues,
) -> np.ndarray:
    """
    各列から粉体上面候補点を抽出する。

    各x列について上から下に走査し、
    粉体maskが stable_rows 分だけ続く最初の位置を
    その列の粉体上面候補とする。
    """

    height, width = mask.shape[:2]
    points = []

    for x in range(width):
        column = mask[:, x] > 0
        ys = np.where(column)[0]

        if len(ys) == 0:
            continue

        for y in ys:
            y2 = min(height, y + controls.stable_rows)

            support = np.count_nonzero(column[y:y2])
            required = max(1, int((y2 - y) * 0.7))

            if support >= required:
                points.append((x, y))
                break

    if len(points) == 0:
        return np.empty((0, 2), dtype=np.float32)

    return np.array(points, dtype=np.float32)


def filter_surface_points(points: np.ndarray) -> np.ndarray:
    """
    粉体上面候補点から外れ値を除去する。

    ガラス反射、容器内壁への粉付着、maskノイズにより、
    一部の列だけ極端に上または下の点を拾うことがある。
    median absolute deviation を使ってそれを除去する。
    """

    if len(points) < 5:
        return points

    y_values = points[:, 1]
    median_y = float(np.median(y_values))

    deviation = np.abs(y_values - median_y)
    mad = float(np.median(deviation))

    if mad < 1.0:
        limit = 8.0
    else:
        limit = max(8.0, mad * 3.0)

    keep = deviation <= limit

    return points[keep]


def detect_surface(
    mask: np.ndarray,
    controls: ControlValues,
) -> SurfaceDetection | None:
    """
    粉体上面を検出する。

    1. mask面積が小さすぎる場合は無効。
    2. 行方向の粉体比率が閾値未満なら無効。
    3. 各列から上面候補点を取る。
    4. 外れ値を除去する。
    5. cv2.fitLine() で上面直線を推定する。
    """

    mask_area = cv2.countNonZero(mask)

    if mask_area < controls.min_area:
        return None

    height, width = mask.shape[:2]

    row_hit = np.count_nonzero(mask, axis=1) / float(width)

    if np.max(row_hit) < controls.row_ratio_threshold:
        return None

    points = extract_surface_points(mask, controls)
    points = filter_surface_points(points)

    if len(points) < max(12, width * 0.08):
        return None

    line = cv2.fitLine(
        points,
        cv2.DIST_L2,
        0,
        0.01,
        0.01,
    )

    vx, vy, x0, y0 = [float(value) for value in line.flatten()]

    if abs(vx) < 1.0e-6:
        y_left = float(np.median(points[:, 1]))
        y_right = y_left
    else:
        y_left = y0 + (vy / vx) * (0.0 - x0)
        y_right = y0 + (vy / vx) * ((width - 1.0) - x0)

    y_left = float(np.clip(y_left, 0, height - 1))
    y_right = float(np.clip(y_right, 0, height - 1))

    center_x = (width - 1.0) / 2.0

    if abs(vx) < 1.0e-6:
        center_y = y_left
    else:
        center_y = y0 + (vy / vx) * (center_x - x0)

    center_y = float(np.clip(center_y, 0, height - 1))

    return SurfaceDetection(
        center_y=center_y,
        line_left=(0, int(round(y_left))),
        line_right=(width - 1, int(round(y_right))),
        point_count=len(points),
    )


def create_profile_image(
    mask: np.ndarray,
    controls: ControlValues,
    surface: SurfaceDetection | None,
) -> np.ndarray:
    """
    row profile preview を作成する。

    各Y行について、maskが白である画素の割合を横棒で表示する。
    threshold線と、検出された上面位置も重ねる。
    """

    height, width = mask.shape[:2]
    profile_width = 360

    profile = np.zeros(
        (
            height,
            profile_width,
            3,
        ),
        dtype=np.uint8,
    )

    row_ratio = np.count_nonzero(mask, axis=1) / float(width)
    graph_width = profile_width - 60

    threshold_x = int(controls.row_ratio_threshold * graph_width)

    cv2.line(
        profile,
        (threshold_x, 0),
        (threshold_x, height - 1),
        (0, 255, 255),
        1,
    )

    for y, ratio in enumerate(row_ratio):
        x2 = int(np.clip(ratio, 0.0, 1.0) * graph_width)

        cv2.line(
            profile,
            (0, y),
            (x2, y),
            (0, 180, 0),
            1,
        )

    if surface is not None:
        y = int(round(surface.center_y))

        cv2.line(
            profile,
            (0, y),
            (profile_width - 1, y),
            (0, 0, 255),
            2,
        )

    cv2.putText(
        profile,
        "row mask ratio",
        (10, 24),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        1,
    )

    return profile


def pixel_delta_to_mm(
    current_level_y: float,
    baseline_y: float,
    controls: ControlValues,
) -> float:
    """
    baselineからのY差をmmへ変換する。

    画像のY座標は下方向に増える。
    粉体が減ると上面は下がるため、
    current_level_y - baseline_y が正なら減少量も正。
    """

    mm_per_pixel = controls.measure_height_mm / float(RECTIFIED_HEIGHT)

    decrease_mm = (current_level_y - baseline_y) * mm_per_pixel

    return float(decrease_mm)


def draw_rectified_result(
    rectified: np.ndarray,
    inner_box: tuple[int, int, int, int],
    surface: SurfaceDetection | None,
    controls: ControlValues,
) -> np.ndarray:
    """
    rectified preview に測定結果を描画する。
    """

    result = rectified.copy()
    x1, y1, x2, y2 = inner_box

    cv2.rectangle(
        result,
        (x1, y1),
        (x2, y2),
        (255, 0, 0),
        2,
    )

    cv2.putText(
        result,
        f"height={controls.measure_height_mm:.0f}mm mode={MODE_NAMES.get(controls.mode, controls.mode)}",
        (15, 30),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (255, 255, 255),
        2,
    )

    if surface is None:
        cv2.putText(
            result,
            "surface: not detected",
            (15, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )
        return result

    line_left = (
        x1 + surface.line_left[0],
        y1 + surface.line_left[1],
    )

    line_right = (
        x1 + surface.line_right[0],
        y1 + surface.line_right[1],
    )

    level_y = y1 + surface.center_y

    cv2.line(
        result,
        line_left,
        line_right,
        (0, 0, 255),
        3,
    )

    cv2.circle(
        result,
        (
            int((x1 + x2) / 2),
            int(round(level_y)),
        ),
        6,
        (0, 0, 255),
        -1,
    )

    text = f"level_y={level_y:.1f}px points={surface.point_count}"

    if baseline_level_y is not None:
        decrease_mm = pixel_delta_to_mm(
            level_y,
            baseline_level_y,
            controls,
        )

        cv2.line(
            result,
            (x1, int(round(baseline_level_y))),
            (x2, int(round(baseline_level_y))),
            (0, 255, 255),
            2,
        )

        text += f" decrease={decrease_mm:.2f}mm"

    cv2.putText(
        result,
        text,
        (15, 60),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (0, 255, 0),
        2,
    )

    return result


def process_frame(
    frame: np.ndarray,
    controls: ControlValues,
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None, float | None]:
    """
    1 frame分の粉体レベル測定処理を行う。

    ROI未指定の場合は、previewなしとしてNoneを返す。
    """

    matrix = create_perspective_matrix()

    if matrix is None:
        return None, None, None, None

    rectified = rectify_roi(frame, matrix)

    inner_roi, inner_box = crop_inner_roi(
        rectified,
        controls,
    )

    mask = create_powder_mask(
        inner_roi,
        controls,
    )

    surface = detect_surface(
        mask,
        controls,
    )

    profile = create_profile_image(
        mask,
        controls,
        surface,
    )

    result = draw_rectified_result(
        rectified,
        inner_box,
        surface,
        controls,
    )

    current_level_y = None

    if surface is not None:
        current_level_y = inner_box[1] + surface.center_y

    return result, mask, profile, current_level_y


def print_help() -> None:
    """
    操作説明をterminalへ表示する。
    """

    print("keys:")
    print("  left click : ROI point LT, RT, RB, LB")
    print("  b          : save current surface as baseline")
    print("  w          : save ROI, baseline, trackbar settings")
    print("  r          : reset ROI")
    print("  u          : undo last ROI point")
    print("  space      : pause / resume")
    print("  h          : help")
    print("  q          : exit")


def main() -> None:
    """
    メインループ。

    カメラ取得、プレビュー表示、trackbar読み取り、キー操作処理を行う。
    """

    global baseline_level_y
    global clicked_points
    global paused
    global last_frame

    config = load_config()

    create_control_panel(CONTROL_DEFAULTS)
    apply_loaded_config(config)

    cap = cv2.VideoCapture(CAMERA_ID)

    if cap.isOpened() is False:
        print("camera open error")
        return

    cv2.namedWindow(SOURCE_WINDOW)
    cv2.setMouseCallback(SOURCE_WINDOW, on_mouse)

    print_help()

    frame_index = 0

    while True:
        controls = read_control_values()

        if paused is False or last_frame is None:
            ret, frame = cap.read()

            if ret is False:
                print("frame read error")
                break

            last_frame = frame.copy()

        frame = last_frame.copy()

        source_display = draw_source_overlay(
            frame,
            controls,
        )

        result, mask, profile, current_level_y = process_frame(
            frame,
            controls,
        )

        cv2.imshow(SOURCE_WINDOW, source_display)

        if result is not None:
            cv2.imshow(RECTIFIED_WINDOW, result)

        if mask is not None:
            cv2.imshow(MASK_WINDOW, mask)

        if profile is not None:
            cv2.imshow(PROFILE_WINDOW, profile)

        if (
            current_level_y is not None
            and baseline_level_y is not None
            and frame_index % 15 == 0
        ):
            decrease_mm = pixel_delta_to_mm(
                current_level_y,
                baseline_level_y,
                controls,
            )

            print(
                "powder "
                f"level_y={current_level_y:.1f}px "
                f"baseline_y={baseline_level_y:.1f}px "
                f"decrease_mm={decrease_mm:.2f}"
            )

        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

        if key == ord("h"):
            print_help()

        if key == ord("r"):
            clicked_points.clear()
            print("ROI reset")

        if key == ord("u"):
            if clicked_points:
                removed = clicked_points.pop()
                print(f"undo point: {removed}")

        if key == ord(" "):
            paused = not paused
            print(f"paused={paused}")

        if key == ord("b"):
            if current_level_y is None:
                print("surface is not detected. baseline not changed.")
            else:
                baseline_level_y = float(current_level_y)
                print(f"baseline set: {baseline_level_y:.1f}px")

        if key == ord("w"):
            save_config()

        frame_index += 1

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()