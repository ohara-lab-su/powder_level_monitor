# 変更履歴

## v0.1.0 — 開発中（タグ未作成）

### 0.0.x → 0.1.x の設計変更

0.0.x 系では `PowderControlDeviceClass` が、ROIの透視変換、二値化、候補点抽出、MADによる外れ値除去、直線近似と、Baseline・測定状態・測定結果の管理を同じクラスで行っていた。認識方式を交換するためには測定制御コードの変更が必要だった。

0.1.x 系では画像認識の実装を `PowderDetector.detect()` に移し、`PowderControlDeviceClass` は検出器の呼び出し、Baseline管理、測定状態、変位換算を担当する。現行アルゴリズムは初期状態として移設し、別方式への全面交換を可能にする。検出結果の座標系と返値契約は既存の測定・表示コードとの互換性のため維持する。

従来のローカル直接呼び出しと `grpc_frame` を使うサーバー・クライアント運転は引き続き同一の測定実装を利用する。画像取得とEventBusの責務も変更しない。`set_detector_params()` の検証経路は未定義の `ControlValues.validate()` への呼び出しを避け、既存の `_make_control_values()` を用いる。

### 現行検出アルゴリズムの文書化

`PowderDetector` のクラスDocstringとREADMEに、0.0.xから移設した現行アルゴリズムの処理順序（ROI透視変換、内側領域の切り出し、CLAHE、GaussianBlur、Otsu/手動二値化、モルフォロジー処理、マスクの成立判定、列方向の候補点抽出、MADによる外れ値除去、L2直線近似、逆透視変換）を具体的に記載した。各段階のパラメータ、仮定、返値の座標系、既知の制約も説明した。今回の追加はドキュメントのみで、認識ロジック・公開API・通信処理は変更しない。

### 追加・修正

- `powder_detector.py` に現行画像認識アルゴリズムを**動作を変えずに移設**。
- ローカルWebカメラテストと本運転の責務境界、画像認識変更の境界をREADMEに記載。
- `power_level_monitor` / `powder_level_monitor` のimport名の混在を、添付サービス側の `powder_level_monitor` に統一。
- 旧版のAPI・Baseline計算・補正画像サイズを維持。

### 配布構成の補完（同じ0.1.0の開発版）

- `examples/` に提供されたGUI、サーバー起動、9件のクライアント操作例をすべて収録。
- `src/` にはパッケージコードのみを配置し、`try/` を追加しない。
- GUIの旧importを現行パッケージ名へ修正。`server_grpc/__init__.py` に明示的な公開importを追加。
- 元ファイルが提供されていない `pyproject.toml`、`requirements.txt`、`pytest.ini` は暫定的に新規作成。元の `LICENSE` は再現できないため未収録。
- Framework自体は変更しない。バージョンは0.1.0に固定、タグ未作成。

### ドキュメント

- 既存の `docs/index.md` と `docs/tutorials/tutorials.md` を収録し、ローカル実行とgRPC運転の共通コア、および0.0.x系から0.1.x系への変更点を明記。
- README・CHANGELOGの設計変更説明を表形式から文章形式へ改め、各責務の理由と互換性の境界を明示。
- `docs/conf.py`、API用rst、`LICENSE` 等の未提供ファイルは復元していない。

### 未確認

- 実カメラ、GUI、gRPC、他機器との統合動作は未試験。
- 元リポジトリのパッケージ設定、起動スクリプト、テストは未提供。

# 変更履歴

## v0.0.2

累計fix

## v0.0.1

- マニュアルとコメント整備

## v0.0.0 - 初回リリース

### 追加

- 粉面高さ監視ライブラリの初回リリース
- OpenCV を用いたカメラ画像取得機能
- ROI（監視領域）の設定機能
- 透視変換による粉面検出
- ベースライン登録・解除機能
- 粉面高さ測定機能
- ピクセルから実長（mm）への変換機能
- 粉面減少量・減少率の算出機能
- `grpc_frame` を用いた gRPC サーバ機能
- gRPC クライアントライブラリ
- EventBus を利用した画像ストリーミング機能
- PySide6 による監視 GUI
- ROI 編集機能
- 測定開始・停止操作
- ローカル実行および gRPC サーバ実行に対応
### ローカルテストで判明した既存アルゴリズムの問題

- 真っ黒な画像に対しても、現行のOtsu二値化（`mode=0`）は粉面を検出したと判定する。これは今回の移設で発生した問題ではなく、アルゴリズム自体の偽陽性である。画像認識方式の再検討対象とする。

### 制御プロセスの命名と検証の是正（0.1.0 内での修正）

0.0.x から継承した `image_stream_ctrl.py` は、カメラ取得用コンポーネントであり、サーバーに公開する唯一の制御プロセスを意味する `ctrl` ではなかった。0.1.0 の当初案でも名称を残してしまったため、`image_stream.py` に改名し、クラスを `ImageStream` とした。唯一の `ctrl` は `powder_monitor_ctrl.py` の `PowderControlDeviceClass` とする。サービスは従来通り1つだけ公開し、カメラ取得と測定は同一インスタンスを共有する。

テストはローカル制御とサービス層の直接委譲を対象に追加した。外部 `grpc_frame` を通る実通信と実カメラの検証は未実施であり、構文確認やモックによる検証を実通信確認と混同しない。

### examples/ の互換性確認と説明（0.1.0、開発中）

0.0.x系の実行例10件について、0.1.x系の制御・gRPCサービス・クライアントの公開APIを照合した。公開メソッド名の互換性を確認し、各スクリプトに用途と前提条件を記載した。実行ロジックは変更しない。`set_roi_client.py` が参照する `examples/roi.json` は未収録であり、利用時に実験環境に応じたファイルが必要。gRPC実通信とカメラ実機の動作は未検証。

### Documentation / GitHub Pages (0.1.0, unreleased)

- Replaced the old single-language Sphinx site with the shared bilingual layout: `docs/index.md` (same as `docs/en/index.md`), `docs/en/`, `docs/ja/`, `docs/conf.py`, and `docs/build.sh`.
- English at `/` and `/en/`, Japanese at `/ja/`, including language badges, tutorials and generated API reference.
- Adapted the existing `pages.yml` to call the shared bilingual build script; deployment remains on `main` and publishes `docs/_build/html`.
- No measurement, detection, controller or gRPC implementation was modified by this documentation update.


### ローカルGUIの追加（0.1.0、バージョン変更なし）

- `examples/monitor_gui_local.py` を追加。gRPCを使用せずにカメラ表示、ROI登録、Baseline設定、測定開始・停止、粉面検出線と変化量の表示を行う。
- 既存のgRPC用GUIおよび制御クラスの `__main__` は変更しない。
