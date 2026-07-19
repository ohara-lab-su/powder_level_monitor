# Powder Level Monitor
view on [github](https://github.com/ohara-lab-su/powder_level_monitor/) / [ohara-lab-su (doc)](https://ohara-lab-su.github.io/)

Powder Level Monitor は、カメラ画像から粉体表面の位置を検出し、基準面（Baseline）からの変化量を測定する Python ライブラリです。

画像取得と粉面測定のコア機能は gRPC に依存せず、ローカル処理として利用できます。リモート運用では、`grpc_frame` を利用した gRPC サービスとクライアントを使用します。

---
```{toctree}
:maxdepth: 2
:caption: Contents:

api/modules
tutorials/tutorials
```
---

## 主な機能

- OpenCV によるカメラ画像取得
- 四角形 ROI の設定と透視変換
- 粉面位置の検出
- Baseline の設定・取得・解除
- 粉面減少量の pixel・mm・比率による取得
- 測定開始・停止と状態取得
- `grpc_frame` による透過 RPC
- EventBus による JPEG 画像ストリーミング
- PySide6 による監視 GUI
- gRPC を使わないローカル実行


## 構成

```text
ローカル処理
    ImageStreamDeviceClass
        └── カメラ接続・画像取得

    PowderControlDeviceClass
        └── ROI・粉面検出・Baseline・測定結果

gRPC 公開層
    PowderLevelGrpcService
        ├── ImageStreamDeviceClass
        └── PowderControlDeviceClass

クライアント
    PowderLevelGrpcClient
        ├── Control.Call による透過 RPC
        └── Events.Subscribe による画像購読
```

## 各クラスの責務

### `ImageStreamDeviceClass`

カメラとの接続、フレーム取得、最新画像の保持、JPEG 変換および EventBus への画像配信を担当します。

カメラ取得自体は gRPC に依存しません。EventBus は `_set_event_bus()` で外部から設定された場合だけ使用されます。

### `PowderControlDeviceClass`

次の粉面測定処理を担当します。

- ROI の保持
- ROI の透視変換
- 粉面検出
- Baseline の保持
- 測定開始・停止
- pixel から mm への換算
- 測定結果およびエラー状態の管理

画像は同一プロセス内の `ImageStreamDeviceClass.get_latest_frame()` から直接取得します。測定処理のために画像を gRPC で送受信することはありません。

### `PowderLevelGrpcService`

`ImageStreamDeviceClass` と `PowderControlDeviceClass` の公開メソッドを gRPC 経由で利用可能にするサービス層です。

このクラスは測定アルゴリズムを持たず、ローカル制御クラスへの委譲と EventBus の接続を担当します。

### `PowderLevelGrpcClient`

`grpc_frame.grpc_client.GrpcClient` を継承する同期クライアントです。

`PowderLevelGrpcService` の公開メソッドは、`grpc_frame` の自動ディスパッチによりクライアントから呼び出せます。

## 測定の流れ

```text
カメラ
  ↓
ImageStreamDeviceClass
  ↓ get_latest_frame()
PowderControlDeviceClass
  ↓
ROI透視変換
  ↓
粉面検出
  ↓
Baselineとの差分計算
  ↓
get_measurement()
```

## 測定結果

`get_measurement()` は辞書を返します。主な項目は次のとおりです。

| キー | 内容 |
|---|---|
| `measuring` | 測定中かどうか |
| `current_detected` | 現在の粉面を検出できたか |
| `baseline_set` | Baseline が保持されているか |
| `baseline_detected` | Baseline の描画座標を保持しているか |
| `level_y` | 透視変換後の現在粉面位置 |
| `baseline_level_y` | 透視変換後の Baseline 位置 |
| `line_left` | 元画像上の現在粉面ライン左端 |
| `line_right` | 元画像上の現在粉面ライン右端 |
| `baseline_line_left` | 元画像上の Baseline ライン左端 |
| `baseline_line_right` | 元画像上の Baseline ライン右端 |
| `decrease_px` | Baseline からの減少量（pixel） |
| `decrease_mm` | Baseline からの減少量（mm） |
| `decrease_ratio` | 補正画像高さに対する減少比 |
| `last_error` | 直近の検出・操作エラー |

## サーバー起動

サーバー設定の既定値は、添付サンプルでは次のとおりです。

```python
GRPC_HOST = "0.0.0.0"
GRPC_PORT = 50051
CAMERA_ID = 0
MAX_MESSAGE_MB = 64
```

サーバーを起動します。

```bash
python examples/run_server.py
```

サーバー起動時にカメラ取得と粉面処理ループが開始されます。画像の EventBus 配信は、クライアントが `start_stream()` を呼ぶまで開始されません。

## GUI 起動

```bash
python examples/monitor_gui.py
```

GUI では次の操作を行えます。

- ROI 設定開始
- ROI 送信
- 未送信 ROI のクリア
- Baseline 設定
- Baseline クリア
- 測定開始
- 測定停止

ROI は、画像上で次の順序に4点を指定します。

```text
左上 → 右上 → 右下 → 左下
```

## CLI

操作ごとに独立したクライアントサンプルを使用します。

```text
status_client.py
measurement_client.py
set_roi_client.py
get_roi_client.py
clear_roi_client.py
set_baseline_client.py
get_baseline_client.py
clear_baseline_client.py
start_measurement_client.py
stop_measurement_client.py
```

詳しい操作手順は [チュートリアル](tutorial/tutorials.md) を参照してください。

## 依存関係

主要な依存パッケージは次のとおりです。

- OpenCV
- NumPy
- grpcio
- grpc_frame
- x_logger
- PySide6（GUI 使用時）

## バージョン

初期リリース: `v0.0.0`
