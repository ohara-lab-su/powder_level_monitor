# Powder Level Monitor

Python 3.6対応のサーバー側粉体レベル測定システムです。

## 実行プログラム

- `run_server.py`: カメラ取得、grpc_frame画像配信、サーバー側認識、ese774_frame APIを起動します。
- `example/monitor_gui.py`: 通常モニター、ROI編集・送信、baseline設定、測定開始・停止を一画面で操作します。

CLIは、引数で処理を切り替える単一プログラムではありません。操作ごとに独立したクライアントを用意しています。

- `example/connect_client.py`: サーバー側デバイスを接続します。
- `example/disconnect_client.py`: サーバー側デバイスを切断します。
- `example/status_client.py`: 状態を表示します。
- `example/measurement_client.py`: 最新測定値を表示します。
- `example/start_measurement_client.py`: 測定を開始します。
- `example/stop_measurement_client.py`: 測定を停止します。
- `example/set_baseline_client.py`: 現在の検出値をbaselineに設定します。
- `example/get_baseline_client.py`: baselineを表示します。
- `example/clear_baseline_client.py`: baselineを削除します。
- `example/get_roi_client.py`: サーバー側ROIを表示します。
- `example/set_roi_client.py`: `example/roi.json` のROIをサーバーへ送信します。
- `example/clear_roi_client.py`: サーバー側ROIを削除します。

## GUI操作

1. `ROI設定開始` を押します。
2. 画像上を左上、右上、右下、左下の順に4点クリックします。
3. 間違えた場合は `画面ROIクリア` を押します。この操作ではサーバー側ROIは変更されません。
4. `ROI送信` を押して確定します。ROI更新時にはサーバー側で測定を停止し、baselineを無効化します。
5. 検出が安定した状態で `Baseline設定` を押します。
6. `測定開始` を押します。GUIを閉じてもサーバー側測定は継続します。

## CLI実行例

```bash
python example/status_client.py
python example/set_baseline_client.py
python example/start_measurement_client.py
python example/measurement_client.py
python example/stop_measurement_client.py
```

ROIをCLIから送る場合は、先に `example/roi.json` を編集します。

```json
{
  "points": [
    [100, 100],
    [500, 100],
    [500, 900],
    [100, 900]
  ]
}
```

その後、次を実行します。

```bash
python example/set_roi_client.py
```
