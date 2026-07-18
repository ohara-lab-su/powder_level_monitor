# Powder Level Monitor (grpc_frame)

粉体表面をサーバー側で継続認識し、GUIへカメラ画像をgRPC streamingで転送する構成です。

## 通信経路

画像転送は次の実経路を通ります。

```text
ImageStreamDeviceClass._stream_loop()
  -> EventBus.publish("camera.frame", payload)
  -> /frame.Events/Subscribe
  -> PowderLevelGrpcClient.subscribe(topic="camera.frame")
  -> GUIでJPEG bytesをOpenCV画像へdecode
```

ROI、baseline、測定開始・停止、状態・測定値は `grpc_frame` の完全透過呼び出しです。

```text
PowderLevelGrpcClient.start_measurement()
  -> /ctrl.Control/Call
  -> PowderLevelDeviceClass.start_measurement()
```

専用proto、FastAPI、Base64画像APIは使用しません。

## 起動

サーバー:

```bash
python run_server.py
```

GUI:

```bash
python example/monitor_gui.py
```

GUIは通常時には画像モニターです。必要時に同じ画面で次を操作します。

- ROI設定開始
- ROI送信
- 画面ROIクリア
- Baseline設定
- Baselineクリア
- 測定開始
- 測定停止

`画面ROIクリア` は未送信の編集点だけを消し、サーバー側ROIには影響しません。

## 独立クライアント

各ファイルは引数で動作を切り替えず、1ファイル1操作です。

```text
start_measurement_client.py
stop_measurement_client.py
status_client.py
measurement_client.py
set_baseline_client.py
get_baseline_client.py
clear_baseline_client.py
set_roi_client.py
get_roi_client.py
clear_roi_client.py
```

`set_roi_client.py` は同じディレクトリの `roi.json` を読みます。

## grpc_frame

サーバーは `create_grpc_server()` を使い、同じポートへ以下の2サービスを登録します。

- `/ctrl.Control/Describe`, `/ctrl.Control/Call`
- `/frame.Events/Subscribe`

クライアントはN10W02の例と同様に `GrpcClient` を継承した薄いクラスだけを使います。
