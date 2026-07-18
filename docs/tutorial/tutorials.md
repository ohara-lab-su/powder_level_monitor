# チュートリアル

このチュートリアルでは、Powder Level Monitor を使用して、カメラ接続、ROI 設定、Baseline 設定、粉面測定を行うまでの手順を説明します。

## 1. 基本構成

gRPC モードでは、サーバー側でカメラ取得と粉面認識を行います。

```text
カメラ
  ↓
PowderLevelGrpcService
  ├── ImageStreamDeviceClass
  └── PowderControlDeviceClass
  ↓
grpc_frame
  ↓
PowderLevelGrpcClient
  ├── CLI
  └── GUI
```

測定処理はサーバープロセス内で完結します。クライアントへ送信する画像は監視表示用であり、認識処理の入力としてサーバーへ送り返すことはありません。

## 2. 接続設定

サーバーおよびクライアントのサンプルでは、次の設定を使用します。

```python
SERVER_IP = "127.0.0.1"
SERVER_PORT = 50051
MAX_MESSAGE_MB = 64
```

別のコンピューターから接続する場合は、クライアント側の `SERVER_IP` をサーバーの IP アドレスへ変更します。

サーバー側は次の設定で全インターフェースに待ち受けます。

```python
GRPC_HOST = "0.0.0.0"
GRPC_PORT = 50051
```

## 3. サーバーを起動する

`run_server.py` を実行します。

```bash
python examples/run_server.py
```

サーバーでは、次の順序で初期化されます。

1. `PowderLevelGrpcService` を生成
2. `EventBus` を生成
3. `create_grpc_server()` で gRPC サーバーを生成
4. `0.0.0.0:50051` で待ち受け
5. カメラ接続
6. 画像取得ループと粉面処理ループを開始

カメラ接続に失敗した場合は、`get_status()` の内容を伴う `RuntimeError` で起動を中止します。

## 4. サーバー状態を確認する

`status_client.py` を実行します。

```bash
python examples/status_client.py
```

クライアントの基本形は次のとおりです。

```python
from powder_level_monitor.server_grpc import PowderLevelGrpcClient
from x_logger import XLogger


logger = XLogger(
    log_level="debug",
    logger_name="status_client",
)

client = PowderLevelGrpcClient(
    server_ip="127.0.0.1",
    grpc_port=50051,
    timeout_sec=5.0,
    logger=logger,
    max_message_mb=64,
)

try:
    status = client.get_status()
    print(status)
finally:
    client.close()
```

`get_status()` の `state` は、おおむね次の状態を返します。

| 状態 | 意味 |
|---|---|
| `DISCONNECTED` | カメラに接続していない |
| `READY_NO_ROI` | 接続済みだが ROI が未設定 |
| `READY_NO_BASELINE` | ROI 設定済みだが Baseline が未設定 |
| `READY` | 測定開始可能 |
| `MEASURING` | 測定中 |

## 5. ROI を設定する

### 5.1 ROI ファイルを用意する

`set_roi_client.py` は、同じディレクトリの `roi.json` を読み込みます。

```json
{
  "points": [
    [100, 80],
    [540, 80],
    [540, 430],
    [100, 430]
  ]
}
```

4点は次の順序で指定します。

```text
左上 → 右上 → 右下 → 左下
```

自己交差する四角形、画像範囲外の点、重複点は使用できません。

### 5.2 ROI を送信する

```bash
python examples/set_roi_client.py
```

実行される処理は次のとおりです。

```python
client.set_roi_points(roi_data["points"])
```

ROI を変更すると、既存の Baseline は無効になります。ROI 変更後は Baseline を再設定してください。

### 5.3 ROI を確認する

```bash
python examples/get_roi_client.py
```

内部では次を呼び出します。

```python
client.get_roi_points()
```

## 6. Baseline を設定する

ROI 設定後、現在検出されている粉面を Baseline として登録します。

```bash
python examples/set_baseline_client.py
```

内部では次を呼び出します。

```python
result = client.set_baseline()
```

粉面を検出できていない場合、`False` が返ります。失敗理由は次で確認できます。

```python
measurement = client.get_measurement()
print(measurement.get("last_error"))
```

Baseline の値を確認するには次を実行します。

```bash
python examples/get_baseline_client.py
```

## 7. 測定を開始する

Baseline 設定後に測定を開始します。

```bash
python examples/start_measurement_client.py
```

内部では次を呼び出します。

```python
result = client.start_measurement()
```

開始できなかった場合は、次で理由を確認できます。

```python
status = client.get_status()
print(status.get("last_error"))
```

測定開始には、少なくとも次の条件が必要です。

- カメラに接続している
- ROI が4点設定されている
- Baseline が設定されている

## 8. 測定結果を取得する

```bash
python examples/measurement_client.py
```

内部では次を呼び出します。

```python
measurement = client.get_measurement()
```

代表的な結果は次の形式です。

```json
{
  "measuring": true,
  "current_detected": true,
  "baseline_set": true,
  "baseline_detected": true,
  "level_y": 310.4,
  "baseline_level_y": 280.2,
  "decrease_px": 30.2,
  "decrease_mm": 4.19,
  "decrease_ratio": 0.0419,
  "last_error": null
}
```

`level_y` と `baseline_level_y` は、透視変換後の縦方向座標です。画像へ線を描画するときは、元画像座標へ逆変換済みの次の値を使用します。

- `line_left`
- `line_right`
- `baseline_line_left`
- `baseline_line_right`

## 9. GUI で操作する

サーバーを起動した状態で、次を実行します。

```bash
python examples/monitor_gui.py
```

GUI 起動時には次の処理が行われます。

1. `camera.frame` の EventBus 購読を開始
2. `start_stream()` を呼び出す
3. JPEG 画像を受信して表示
4. `get_status()` と `get_measurement()` を定期取得

### ROI 設定

1. 「ROI設定開始」を押す
2. 画像上で左上、右上、右下、左下の順に4点をクリック
3. 「ROI送信」を押す
4. Baseline を再設定する

表示色は次のとおりです。

| 表示 | 色 |
|---|---|
| サーバー登録済み ROI | 緑 |
| 編集中 ROI | 黄 |
| Baseline | 赤 |
| 現在粉面 | 青 |

### GUI 終了時

GUI は終了時に次を実行します。

1. `stop_stream()` を呼び出す
2. EventBus 購読スレッドを停止
3. gRPC クライアントを閉じる

これにより、GUI を使用していない間は画像のネットワーク配信が停止します。

## 10. 測定を停止する

停止用クライアントから次を呼び出します。

```python
client.stop_measurement()
```

```bash
python examples/stop_measurement_client.py
```

停止後も ROI と Baseline は保持されます。

## 11. Baseline と ROI を解除する

Baseline を解除する場合は次を呼び出します。

```python
client.clear_baseline()
```

ROI を解除する場合は次を呼び出します。

```python
client.clear_roi_points()
```

ROI を解除すると、測定は停止し、Baseline も無効になります。

## 12. 検出パラメーター

検出パラメーターは `get_detector_params()` で取得し、`set_detector_params()` で変更できます。

```python
params = client.get_detector_params()
print(params)

client.set_detector_params(
    {
        "mode": 0,
        "blur": 5,
        "open_kernel": 3,
        "close_kernel": 5,
        "row_ratio_threshold": 0.2,
        "stable_rows": 4,
        "min_area": 500,
        "margin_x_ratio": 0.05,
        "margin_y_ratio": 0.05,
        "measure_height_mm": 100.0,
    }
)
```

主な項目は次のとおりです。

| 項目 | 内容 |
|---|---|
| `mode` | 二値化方式。0～3 |
| `manual_threshold` | 手動二値化しきい値。0～255 |
| `blur` | Gaussian Blur のカーネルサイズ |
| `open_kernel` | Opening のカーネルサイズ |
| `close_kernel` | Closing のカーネルサイズ |
| `row_ratio_threshold` | 行方向の粉体占有率しきい値 |
| `stable_rows` | 縦方向の連続画素確認数 |
| `min_area` | マスクの最小面積 |
| `margin_x_ratio` | 補正画像左右の除外率 |
| `margin_y_ratio` | 補正画像上下の除外率 |
| `measure_height_mm` | 補正画像全高に対応する実長 |

偶数の `blur`、`open_kernel`、`close_kernel` は、内部で次の奇数へ補正されます。

## 13. ローカルで画像取得だけを使う

`ImageStreamDeviceClass` は、gRPC を使わず直接利用できます。

```python
import time

from powder_level_monitor.image_stream_ctrl import ImageStreamDeviceClass


image_stream = ImageStreamDeviceClass(
    camera_id=0,
)

if not image_stream.connect():
    raise RuntimeError(str(image_stream.get_status()))

try:
    while True:
        frame = image_stream.get_latest_frame()

        if frame is not None:
            print(frame.shape)
            break

        time.sleep(0.01)
finally:
    image_stream.disconnect()
```

## 14. ローカルで粉面測定を使う

`PowderControlDeviceClass` へ `ImageStreamDeviceClass` を渡すことで、gRPC を使わずに測定できます。

```python
from powder_level_monitor.image_stream_ctrl import ImageStreamDeviceClass
from powder_level_monitor.powder_monitor_ctrl import PowderControlDeviceClass


image_stream = ImageStreamDeviceClass(
    camera_id=0,
)

monitor = PowderControlDeviceClass(
    image_source=image_stream,
    measurement_interval_sec=0.1,
)

if not monitor.connect():
    raise RuntimeError(str(monitor.get_status()))

try:
    monitor.set_roi_points(
        [
            [100, 80],
            [540, 80],
            [540, 430],
            [100, 430],
        ]
    )

    if not monitor.set_baseline():
        raise RuntimeError(
            str(monitor.get_measurement().get("last_error"))
        )

    if not monitor.start_measurement():
        raise RuntimeError(
            str(monitor.get_status().get("last_error"))
        )

    measurement = monitor.get_measurement()
    print(measurement)
finally:
    monitor.disconnect()
```

ローカル利用では `PowderLevelGrpcService`、`PowderLevelGrpcClient`、EventBus は不要です。

## 15. 推奨操作順序

```text
1. サーバー起動
2. 状態確認
3. ROI設定
4. ROI確認
5. Baseline設定
6. Baseline確認
7. 測定開始
8. 測定結果取得
9. 測定停止
```

GUI を使用する場合は、ROI 設定から測定開始までを1つの画面で操作できます。
