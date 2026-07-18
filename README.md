# Powder Level Monitor

## 概要

Powder Level Monitor は、OpenCV により取得したカメラ画像から粉面位置を検出し、粉面高さや減少量を測定するためのライブラリです。

コアとなる画像処理部は gRPC に依存しておらず、ローカルライブラリとして利用できます。また、`grpc_frame` を利用した gRPC サーバとして公開することもできます。

## 主な機能

- カメラ画像取得
- ROI 設定
- 粉面検出
- ベースライン登録
- 粉面高さ測定
- 減少量・減少率算出
- GUI による監視
- gRPC によるリモート制御

## システム構成

```
                 GUI / CLI
                     │
                     ▼
        PowderLevelGrpcService
               │
      ┌────────┴────────┐
      ▼                 ▼
ImageStreamDeviceClass  PowderControlDeviceClass
```

## クラス構成

### ImageStreamDeviceClass

カメラとの接続、画像取得、および画像ストリーム管理を行います。

### PowderControlDeviceClass

ROI 管理、粉面検出、ベースライン管理、粉面高さ計算などの画像解析処理を担当します。

### PowderLevelGrpcService

`grpc_frame` を利用した gRPC 公開クラスです。

`ImageStreamDeviceClass` および `PowderControlDeviceClass` を組み合わせ、各機能を gRPC 経由で公開します。

## 動作モード

### ローカルモード

```
Application
      │
      ├── ImageStreamDeviceClass
      └── PowderControlDeviceClass
```

gRPC を使用せず、ライブラリとして直接利用します。

### gRPC モード

```
Client
   │
gRPC
   │
PowderLevelGrpcService
   │
├── ImageStreamDeviceClass
└── PowderControlDeviceClass
```

リモートから画像取得や粉面測定を実行できます。

## 必要ライブラリ

- Python 3.10 以上
- OpenCV
- NumPy
- PySide6（GUI 使用時）
- grpc_frame（gRPC 使用時）

## ライセンス

MIT License