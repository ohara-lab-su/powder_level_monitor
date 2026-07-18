# Powder Level Monitor (grpc_frame)

画像配信、ROI、baseline、測定開始・停止、状態・測定値取得を `grpc_frame` に統一した構成です。

- `run_server.py`: gRPCサーバー、カメラ取得、画像イベント配信、粉体認識
- `example/monitor_gui.py`: gRPC画像モニター兼ROI・baseline・測定操作GUI
- `example/*_client.py`: 操作ごとの独立CLIクライアント

## 起動

```bash
python run_server.py
python example/monitor_gui.py
```

画像は `camera.frame` を `Events/Subscribe` で受信します。ROI等の制御は、同じ `SyncGrpcClient` がDescribeで透過取得したpublicメソッドを直接呼び出します。専用proto、専用RPCクライアント、FastAPIは使用しません。
