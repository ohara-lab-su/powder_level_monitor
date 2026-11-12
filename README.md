# Powder Level Monitor — 0.1.0（開発中）

Webカメラで瓶内の粉面を認識し、設定したBaselineからの変位を測定する。**0.1.0は動作確認前の開発版**であり、タグはまだ作成しない。

## 0.0.x 系から 0.1.x 系への変更

0.0.x 系では、`PowderControlDeviceClass` が測定制御に加え、透視変換、二値化、粉面候補点の抽出、外れ値除去、直線近似などの画像認識処理を直接実装していた。このため、認識方式を全面的に変更する場合には、Baseline管理、測定状態、単位換算、公開メソッドを含む制御コードを編集する必要があった。

0.1.x 系では、これらの画像認識処理を `powder_detector.py` の `PowderDetector` に分離した。`PowderControlDeviceClass` は画像取得元からフレームを受け取り、検出器を呼び出して得られた結果を、既存の測定状態・Baseline・変位計算へ接続する。画像認識方式の変更による影響を測定制御から切り離すことが目的であり、検出アルゴリズムの精度向上を保証する変更ではない。

制御プロセスとは独立した機能部品として画像取得を担当する `ImageStream`、gRPC公開を担当する `PowderLevelGrpcService`、クライアントの `PowderLevelGrpcClient` は引き続き既存の役割を担う。通信基盤 `grpc_frame` は変更しない。ローカル処理と本運転では同じ画像取得・測定制御・認識コードを使用し、呼び出し経路のみが異なる。

0.1.0 は開発途中の固定バージョンであり、最低限の動作確認後にタグを作成する。それまではバージョン番号を変更しない。

## 責務と依存関係

```text
ローカル: 直接呼び出し ─┐
                       ├─> PowderControlDeviceClass ─> PowderDetector
本運転: gRPCクライアント ─> PowderLevelGrpcService ─┘           ↑
                                       │                       │
                                       └─> ImageStream ─> Webカメラ
```

- `ImageStream` (`image_stream.py`): `ctrl` ではなくカメラ入出力の内部コンポーネント。 Webカメラの接続、取得、最新画像保持、画像配信。**画像認識を実装しない**。
- `PowderControlDeviceClass` (`powder_monitor_ctrl.py`): ROI・Baseline・測定状態・変位換算・最新測定結果を管理し、検出器を呼ぶ。**二値化等のアルゴリズムを実装しない**。
- `PowderDetector` (`powder_detector.py`): BGR画像とROIから粉面を検出する。**カメラ接続、gRPC、測定開始停止、Baselineを扱わない**。画像認識方式を独立して変更するための実装境界。
- `ControlValues` (`data_control_values.py`): 現行アルゴリズムの調整値。新方式で不要になるパラメータがある場合、公開APIとの互換性を確認する。
- `SurfaceDetection` (`data_surface_detection.py`): 現行直線検出の詳細結果。アルゴリズムを直線以外に変更するときは返値契約との整合性を検討する。
- `PowderLevelGrpcService` / `PowderLevelGrpcClient`: 本運転用の既存公開層。**Framework (`grpc_frame`) は変更しない**。

## 検出器の入出力契約

`PowderDetector.detect(frame, roi_points, controls)` は、BGRのNumPy画像、原画像上のROI四隅（左上→右上→右下→左下）、`ControlValues` を受け取り、
`(SurfaceDetection | None, 補正画像上の中心Y | None, 元画像上の左端点 | None, 元画像上の右端点 | None)` を返す。検出失敗時は `(None, None, None, None)` とする。

**現在の測定系は補正画像の高さ720 pxを実寸 `measure_height_mm` に対応させる。** 粉面が下がると変位が正となる。アルゴリズム内部の二値化・フィッティング方式は自由だが、この座標契約を壊すとBaseline・mm換算・GUI描画が破綻する。曲線や領域ベースの検出でも、外部にはこの契約に合わせた代表位置と表示用端点を返す。

## 現行 `PowderDetector` の画像認識アルゴリズム

0.1.0で分離した検出器は、0.0.xの処理を初期実装として引き継いでいる。**現行方式は暫定的な選択であり、認識精度を保証するものでも、変更時に維持すべき方式でもない。** 実際の瓶と粉体をWebカメラで撮影し、検出結果と画像を比較しながら方式自体を再検討する。

### 画像座標の補正と解析範囲

`detect(frame, roi_points, controls)` にBGR画像と原画像上のROI四隅を渡す。ROIは左上、右上、右下、左下の順とし、OpenCVの `getPerspectiveTransform()` と `warpPerspective()` で **幅360 px、高さ720 px** の矩形画像へ変換する。これはROI内を一定の解析座標系にそろえるためであり、透視変換だけで実寸の校正が完了するわけではない。さらに `margin_x_ratio`、`margin_y_ratio` に従って周囲を切り落とす。瓶の縁などを解析から外す狙いだが、実際の粉面が除外される可能性もある。

### 粉体候補領域の二値化

切り出したBGR画像をグレースケールへ変換し、CLAHE（局所ヒストグラム均等化）で局所コントラストを補正する。続いてGaussianBlurで平滑化する。`mode=0` はOtsu法の通常二値化、`mode=1` はOtsu法の反転二値化、`mode=2` は手動閾値の通常二値化、`mode=3` は手動閾値の反転二値化である。手動閾値は `manual_threshold`、平滑化カーネルは `blur` で設定する。

二値化した画像では、白（255）を粉体候補とみなす。`open_kernel` によるモルフォロジーのオープニングは小さな白ノイズの除去、`close_kernel` によるクロージングは白領域内の小さな欠損の補完を意図している。いずれもカーネル値が1以下なら適用しない。

### 粉面候補点の抽出と直線近似

まず、白画素の総数が `min_area` 未満なら棄却する。また、各行の白画素占有率の最大値が `row_ratio_threshold` 未満なら棄却する。次に各列を上から走査し、ある白画素を起点に最大 `stable_rows` 行の区間を調べ、そのうち**70%以上が白画素**なら最初の該当Y座標を候補点とする。これは「粉体領域の上端が粉面」という仮定に基づく。70%は現行コードに直接記載された固定値である。

候補点が5点以上ある場合は、Y座標の中央値とMAD（median absolute deviation）で外れ値を除く。除外境界はMADが1未満なら8 px、それ以外は `max(8, 3×MAD)` である。残存点数が `max(12, 解析領域の幅×0.08)` 未満なら棄却する。最後に `cv2.fitLine()` のL2距離で候補点へ一本の直線を当てはめ、左右端点と中央Y座標を求める。中央Yは切り出し前の補正画像座標に戻し、表示用左右端点は逆透視変換で原画像座標へ戻す。

### 返値、測定制御との境界、制限

`detect()` は `(SurfaceDetection, current_level_y, line_left, line_right)` を返す。`SurfaceDetection.center_y` は**切り出した解析領域内**の座標、`current_level_y` は**360×720 pxの補正画像内**の中央Y、`line_left` と `line_right` は**元のカメラ画像内**の表示用端点である。異なる座標系を混同しないこと。検出不成立時は4要素とも `None` とする。Baselineとの比較、mmへの換算、測定状態の更新は検出器ではなく `PowderControlDeviceClass` の責務である。

現行方式は粉面を一本の直線で近似する。湾曲した粉面、透明容器の反射、背景の誤検出、白黒極性の不一致、照明変化に弱い可能性がある。**白画素が十分存在することは粉面の存在証明ではない。** 検出成功を真値として扱わず、実画像と照合する必要がある。方式を全面的に置換してもよいが、`detect()` の外部契約を変更する場合は制御・GUI・公開APIへの影響を明示して整合させる。

## ローカルテストと本運転

ローカルではWebカメラをPCに接続し、`ImageStream` を `PowderControlDeviceClass(image_source=...)` に渡して直接 `connect()`、`set_roi_points()`、`process_once()`、`set_baseline()` 等を呼ぶ。`powder_monitor_ctrl.py` の `main()` はOpenCVの対話操作例（B:Baseline、S:開始停止、R:ROIリセット、Q:終了）。**通信もgRPCサーバーも不要**。

本運転では同じ2クラスを `PowderLevelGrpcService` が構築し、外部のgRPCクライアントが測定を指示する。検出処理と測定処理はローカルと共通で、通信のために認識コードを複製しない。画像配信はEventBusを利用する。

## 画像認識アルゴリズムの変更範囲

画像認識方式の変更では、まず `powder_detector.py` を変更する。**現在の二値化・CLAHE・MAD・直線フィットの採用は確定仕様ではない**。照明、瓶の反射、粉体の色・形状に応じて方式全体を置換してよい。ただし `detect()` の入力・返値・座標系を維持し、`grpc_frame`、`server_grpc/`、カメラ取得、測定制御には触れない。設定の変更が必要な場合は、外部APIとの互換性を先に確認する。

検証は**Webカメラを使ったローカル接続**で行い、実際の瓶・粉体・照明条件でROI設定、Baseline設定、検出の成功・失敗、粉面低下時の正の変位、表示端点を確認する。その後、本運転のサーバー・クライアントと他機器の連携を確認する。

## 配布ディレクトリと開発の境界

`src/powder_level_monitor/` はインストールされるPythonパッケージのみを置く。実験用の `try/` やサンプルスクリプトは置かない。`examples/` にGUI、サーバー起動、既存のgRPCクライアント操作例を配置する。`tests/` はパッケージ外のローカルテスト用である。

既存の `examples/monitor_gui.py` にあった旧パッケージ名 `power_level_monitor.grpc_client` は、現行の `powder_level_monitor.server_grpc` に統一した。`server_grpc/__init__.py` からクライアント・サービスを明示的に公開する。Frameworkのコードは収録・改変しない。

`pyproject.toml` と `requirements.txt` は今回提供された元ファイルがないため、添付コードのimportと既存READMEに基づいて**新規作成した暫定設定**である。依存ライブラリの正式な配布名・バージョン制約、ライセンス本文は元リポジトリとの照合が必要である。元の `LICENSE` は提供されていないため、推測して新しいライセンス本文を作成していない。

## 制限と確認事項

- 添付ソースから構成した開発版。GUI、起動スクリプト、既存のクライアント操作例を追加収録した。ただし元のパッケージ設定・ライセンス・既存テスト一式は未提供であり、完全な配布・統合試験は未実施。
- 検出失敗時に以前の測定値が残る場合がある。`detected` を必ず確認すること。
- 画像とフレームIDは現行コードでは別取得であり、厳密な同一性は保証されない。
- README旧版の「減少率」について、提供されたコードに対応する計算を確認できないため、0.1.0の実装済み機能とは記載しない。

## 必要環境

Python 3.10以上、OpenCV、NumPy。カメラ制御・ロギングに既存の `x_logger`、本運転に既存の `grpc_frame` 等を利用する。元の `pyproject.toml` が未提供のため、依存パッケージの正式な配布名・バージョン制約は要確認。

## 現行アルゴリズムの既知の課題

真っ黒な入力画像に対してもデフォルトの二値化モードでは粉面検出が成功することを確認した。これは「画像認識アルゴリズムの選定を再検討する」理由の一例であり、0.1.0の初期移植では挙動を変更していない。

## ドキュメントと運用手順

`docs/index.md` はSphinxのドキュメント入口、`docs/tutorials/tutorials.md` は操作手順である。ローカルでのWebカメラ接続・粉面測定と、gRPCサーバーを介した本運転の両方を扱う。ローカルテストは通信を使用せず、同じ測定クラスを直接呼び出す。本運転はクライアントから認識・測定を指示し、他機器との連携を行う。

既存の `docs/conf.py`、`docs/build.sh`、API用rst、`LICENSE` は今回の提供ファイルに含まれていないため、この配布物には復元していない。既存ディレクトリを完全に削除する前に、これらの原本を別途確保する必要がある。`build/` と `docs/_build/` は生成物であり、ソースの正本として扱わない。

## 0.1.0 の検証状況と実行環境

`powder_monitor_ctrl.py` の `PowderControlDeviceClass` のみを制御対象とする。`image_stream.py` の `ImageStream` はカメラ取得と配信の機能部品であり、独立した制御サーバーではない。gRPC の公開対象は `PowderLevelGrpcService` 1個である。

カメラを差し替えたローカル制御テストと、サービス層から同じ制御オブジェクトを呼び出すテストを `tests/test_control_paths.py` に設けた。実機カメラおよび外部 `grpc_frame` のサーバー・クライアント間通信は、この実行環境で確認できていない。従ってこれらを検証済みとは扱わない。

元の `LICENSE`、Sphinx設定一式、元の `pyproject.toml` はこの作業環境に存在しない。これらの原本を提供されない限り、配布物は元リポジトリの完全な代替にはならない。


## `examples/` の役割と0.0.x系からの互換性

`examples/` は、0.0.x系で利用していたgRPCサーバー起動・クライアント操作の実行例である。0.1.x系でも同じ公開操作を利用する。これらは**通信を利用する本運転の例**であり、gRPCを使わないローカルテストとは区別する。ローカルテストでは `PowderControlDeviceClass` を直接呼び出す。

`run_server.py` は `PowderLevelGrpcService` を単一のgRPC制御対象として起動し、Webカメラを接続する。`monitor_gui.py` は画像イベントを購読し、ROI指定、Baseline設定、測定開始・停止、状態と画像の表示を行う。どちらも実際のカメラ・通信環境が必要である。

`get_roi_client.py` は現在のROI四隅を取得する。`set_roi_client.py` は `examples/roi.json` の `points` に指定された四隅をサーバーへ設定する。**`roi.json` は現行配布物には含まれない**ため、実際のカメラ画像に合わせて作成する必要がある。座標は左上、右上、右下、左下の順である。

`get_baseline_client.py` は設定済みBaselineを取得する。`set_baseline_client.py` は現在検出されている粉面位置をBaselineに登録する。Baseline設定にはROIと有効な粉面検出結果が必要となる。

`start_measurement_client.py` と `stop_measurement_client.py` は測定処理の開始・停止を指示する。`measurement_client.py` は最新の測定結果を取得する。`status_client.py` は制御状態を取得する。結果取得と測定開始は異なる操作である。

0.0.x系と0.1.x系の `PowderControlDeviceClass` の公開メソッド名17件をソース上で照合し、一致することを確認した。また、両版の `PowderLevelGrpcService` の公開メソッドは同一であり、変更点は内部で使用する画像取得クラスのimportと生成に限られる。`PowderLevelGrpcClient` のコンストラクタも同一である。このため、これらのサンプルが利用する**公開APIについてはソース上の互換性がある**。ただし、`grpc_frame` を通した実通信・画像イベント購読・実カメラ動作は未検証であり、動作保証とは区別する。

各ファイルの先頭Docstringにも用途と前提条件を記載した。
