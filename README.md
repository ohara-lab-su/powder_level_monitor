# Powder Level Monitor

粉体表面をサーバー側で検出し、画像監視・ROI設定・baseline設定・測定開始停止をgRPC経由で操作するシステムです。

## 通信構成

制御メソッドは `grpc_frame` の完全透過呼び出しを使用します。

```text
GUI / CLI
    -> /ctrl.Control/Call
    -> PowderLevelDeviceClass の public メソッド
```

GUI画像は `grpc_frame` のイベントストリームを使用します。

```text
ImageStreamDeviceClass
    -> EventBus.publish("camera.frame", payload)
    -> /frame.Events/Subscribe
    -> monitor_gui.py
```

## サーバー内部の測定経路

測定処理はgRPCを経由しません。

```text
カメラ
    -> ImageStreamDeviceClass._latest_frame
    -> PowderControlDeviceClass.process_once()
```

`PowderControlDeviceClass` は同一プロセス内で `get_latest_frame()` を直接呼びます。サーバー自身が画像をgRPCで送信して受信し直す処理はありません。

## 画像配信の開始と停止

`run_server.py` 起動時には、カメラ取得とサーバー内部の認識ループだけを開始します。画像publishは開始しません。

`monitor_gui.py` は次の順序で動作します。

1. `camera.frame` のgRPC購読スレッドを開始
2. `start_stream()` を透過RPCで呼び出す
3. サーバーがJPEG画像のpublishを開始
4. GUI終了時に `stop_stream()` を透過RPCで呼び出す
5. gRPCクライアントを閉じる

したがって、GUIを起動していない通常状態では、サーバーはネットワークへ画像を送信し続けません。

## GUI

GUIはQtのPySide6で実装しています。`tkinter` は使用しません。

```bash
python examples/monitor_gui.py
```

主な操作:

- ROI設定開始
- ROI送信
- 画面ROIクリア
- Baseline設定
- Baselineクリア
- 測定開始
- 測定停止

「画面ROIクリア」は未送信のクリック点だけを消します。サーバーに登録済みのROIは変更しません。

## サーバー

```bash
python run_server.py
```

## CLI

各操作は独立したプログラムです。引数による動作切り替えは行いません。

```text
examples/start_measurement_client.py
examples/stop_measurement_client.py
examples/status_client.py
examples/measurement_client.py
examples/set_baseline_client.py
examples/get_baseline_client.py
examples/clear_baseline_client.py
examples/set_roi_client.py
examples/get_roi_client.py
examples/clear_roi_client.py
```

## 依存関係

```bash
pip install -r requirements.txt
```

PythonソースはPython 3.6の構文で検査しています。依存パッケージはPythonバージョン別の条件を `requirements.txt` に記載しています。
