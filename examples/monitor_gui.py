#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""gRPC経由でカメラ画像を購読し、ROI・Baseline・測定開始停止を操作するGUI。

サーバーを別途起動する。画像取得・粉面認識の実装はサーバー側で行う。"""

"""粉体レベル監視サーバーを操作し、画像と測定結果を表示するGUIを提供する。"""

import sys

import cv2
import numpy as np
from PySide6 import QtCore
from PySide6 import QtGui
from PySide6 import QtWidgets

from powder_level_monitor.server_grpc import PowderLevelGrpcClient
from x_logger import XLogger


SERVER_IP = "127.0.0.1"
SERVER_PORT = 50051
MAX_MESSAGE_MB = 64
IMAGE_TOPIC = "camera.frame"
IMAGE_REFRESH_MS = 50
STATUS_REFRESH_MS = 500


class ImageLabel(QtWidgets.QLabel):
    """表示画像上のクリック位置を元画像座標へ変換して通知するQLabel。"""
    image_clicked = QtCore.Signal(int, int)

    def __init__(self, parent=None):
        """クリック座標変換に必要な画像寸法と表示領域を初期化する。
        
        Args:
            parent: 親Qtウィジェット。
        """
        super().__init__(parent)
        self._source_width = 0
        self._source_height = 0
        self._display_rect = QtCore.QRect()
        self.setMinimumSize(640, 480)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("background-color: black;")

    def set_source_size(self, width, height):
        """元画像の画素寸法を設定する。
        
        Args:
            width: 元画像の幅（px）。
            height: 元画像の高さ（px）。
        """
        self._source_width = int(width)
        self._source_height = int(height)

    def set_display_rect(self, rect):
        """アスペクト比維持後の実画像表示領域を設定する。
        
        Args:
            rect: QLabel内でPixmapが実際に描画される矩形。
        """
        self._display_rect = QtCore.QRect(rect)

    def mousePressEvent(self, event):
        """左クリック位置を元画像座標へ変換して通知する。
        
        Args:
            event: Qtのマウス押下イベント。
        """
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return

        if self._source_width <= 0:
            return

        if self._source_height <= 0:
            return

        if not self._display_rect.contains(event.position().toPoint()):
            return

        x_value = event.position().x() - self._display_rect.x()
        y_value = event.position().y() - self._display_rect.y()

        source_x = int(
            x_value
            * self._source_width
            / float(self._display_rect.width())
        )
        source_y = int(
            y_value
            * self._source_height
            / float(self._display_rect.height())
        )

        self.image_clicked.emit(source_x, source_y)


class ImageSubscriptionThread(QtCore.QThread):
    """gRPCのイベント購読をGUIスレッドから分離して実行するQThread。"""
    frame_received = QtCore.Signal(object, object)
    subscription_error = QtCore.Signal(str)

    def __init__(self, client, topic, logger, parent=None):
        """画像イベント購読スレッドを初期化する。
        
        Args:
            client: subscribe_eventsを提供するgRPCクライアント。
            topic: 購読対象の画像トピック名。
            logger: 購読エラーを記録するロガー。
            parent: 親Qtオブジェクト。
        """
        super().__init__(parent)
        self._client = client
        self._topic = topic
        self._logger = logger
        self._running = True

    def stop(self):
        """測定処理を停止する互換API。
        
        Returns:
            測定停止処理を完了した場合は True。
        """
        self._running = False

    def run(self):
        """画像イベントを継続購読し、復号済みフレームをSignalで通知する。"""
        self._logger.info(
            "<POWDER GUI ACTION> subscribe start: topic={}".format(
                self._topic,
            )
        )

        try:
            for payload in self._client.subscribe(topic=self._topic):
                if not self._running:
                    break

                image_bytes = payload.get("image")
                if image_bytes is None:
                    continue

                encoded = np.frombuffer(
                    image_bytes,
                    dtype=np.uint8,
                )
                frame = cv2.imdecode(
                    encoded,
                    cv2.IMREAD_COLOR,
                )

                if frame is None:
                    continue

                self.frame_received.emit(
                    frame,
                    payload.get("frame_id"),
                )
        except Exception as exc:
            if self._running:
                self._logger.error(
                    "<POWDER GUI ACTION> subscribe failed: {}".format(
                        exc,
                    )
                )
                self.subscription_error.emit(str(exc))

        self._logger.info("<POWDER GUI ACTION> subscribe stopped")


class PowderMonitorGui(QtWidgets.QMainWindow):
    """ROI設定、Baseline設定、測定操作、および画像表示を行うメインウィンドウ。"""
    def __init__(self):
        """gRPCクライアント、GUI部品、購読スレッド、および更新タイマーを初期化する。"""
        super().__init__()

        self._logger = XLogger(
            log_level="debug",
            logger_name=self.__class__.__name__,
        )
        self._client = PowderLevelGrpcClient(
            server_ip=SERVER_IP,
            grpc_port=SERVER_PORT,
            timeout_sec=5.0,
            logger=self._logger,
            max_message_mb=MAX_MESSAGE_MB,
        )

        self._latest_frame = None
        self._latest_frame_id = None
        self._latest_measurement = {}
        self._server_roi_points = []
        self._editing_points = []
        self._editing_roi = False
        self._subscription_thread = None

        self._build_gui()
        self._start_image_subscription()

        self._image_timer = QtCore.QTimer(self)
        self._image_timer.timeout.connect(self._refresh_image)
        self._image_timer.start(IMAGE_REFRESH_MS)

        self._status_timer = QtCore.QTimer(self)
        self._status_timer.timeout.connect(self._refresh_status)
        self._status_timer.start(STATUS_REFRESH_MS)

    def _build_gui(self):
        """画像表示、測定状態、ROI操作、測定操作の各ウィジェットを構築する。"""
        self.setWindowTitle("Powder Level Monitor")
        self.resize(1100, 850)

        central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(central_widget)

        main_layout = QtWidgets.QVBoxLayout(central_widget)

        self._image_label = ImageLabel(self)
        self._image_label.image_clicked.connect(self._on_image_click)
        main_layout.addWidget(self._image_label, 1)

        button_layout = QtWidgets.QHBoxLayout()
        main_layout.addLayout(button_layout)

        roi_start_button = QtWidgets.QPushButton("ROI設定開始", self)
        roi_start_button.clicked.connect(self._start_roi_edit)
        button_layout.addWidget(roi_start_button)

        roi_send_button = QtWidgets.QPushButton("ROI送信", self)
        roi_send_button.clicked.connect(self._send_roi)
        button_layout.addWidget(roi_send_button)

        roi_clear_button = QtWidgets.QPushButton("画面ROIクリア", self)
        roi_clear_button.clicked.connect(self._clear_editing_roi)
        button_layout.addWidget(roi_clear_button)

        baseline_set_button = QtWidgets.QPushButton("Baseline設定", self)
        baseline_set_button.clicked.connect(self._set_baseline)
        button_layout.addWidget(baseline_set_button)

        baseline_clear_button = QtWidgets.QPushButton("Baselineクリア", self)
        baseline_clear_button.clicked.connect(self._clear_baseline)
        button_layout.addWidget(baseline_clear_button)

        measurement_start_button = QtWidgets.QPushButton("測定開始", self)
        measurement_start_button.clicked.connect(self._start_measurement)
        button_layout.addWidget(measurement_start_button)

        measurement_stop_button = QtWidgets.QPushButton("測定停止", self)
        measurement_stop_button.clicked.connect(self._stop_measurement)
        button_layout.addWidget(measurement_stop_button)

        self._status_label = QtWidgets.QLabel("接続中", self)
        self._measurement_state_label = QtWidgets.QLabel("測定状態: 未取得", self)
        self._baseline_detection_label = QtWidgets.QLabel("Baseline検出: 未取得", self)
        self._current_detection_label = QtWidgets.QLabel("現在粉面検出: 未取得", self)
        self._baseline_level_label = QtWidgets.QLabel("Baseline位置: 未設定", self)
        self._current_level_label = QtWidgets.QLabel("現在粉面位置: 未取得", self)
        self._decrease_label = QtWidgets.QLabel("減少量: 測定不可", self)
        self._measurement_error_label = QtWidgets.QLabel("測定エラー: なし", self)
        self._roi_label = QtWidgets.QLabel("ROI: 未取得", self)

        main_layout.addWidget(self._status_label)
        main_layout.addWidget(self._measurement_state_label)
        main_layout.addWidget(self._baseline_detection_label)
        main_layout.addWidget(self._current_detection_label)
        main_layout.addWidget(self._baseline_level_label)
        main_layout.addWidget(self._current_level_label)
        main_layout.addWidget(self._decrease_label)
        main_layout.addWidget(self._measurement_error_label)
        main_layout.addWidget(self._roi_label)

    def _start_image_subscription(self):
        """画像購読スレッドを生成し、フレーム受信Signalを接続して開始する。"""
        self._subscription_thread = ImageSubscriptionThread(
            client=self._client,
            topic=IMAGE_TOPIC,
            logger=self._logger,
            parent=self,
        )
        self._subscription_thread.frame_received.connect(
            self._on_frame_received,
        )
        self._subscription_thread.subscription_error.connect(
            self._on_subscription_error,
        )
        self._subscription_thread.start()

        QtCore.QTimer.singleShot(
            100,
            self._request_stream_start,
        )

    def _request_stream_start(self):
        """サーバーへ画像配信開始を要求し、失敗時は画面へ状態を表示する。"""
        try:
            result = self._client.start_stream()
            if result:
                self._status_label.setText("画像配信を開始しました")
            else:
                self._status_label.setText("画像配信を開始できませんでした")
        except Exception as exc:
            self._status_label.setText(
                "画像配信開始失敗: {}".format(exc)
            )

    @QtCore.Slot(object, object)
    def _on_frame_received(self, frame, frame_id):
        """購読スレッドから受け取った最新画像をGUI側へ保存する。
        
        Args:
            frame: JPEGから復号されたBGR画像。
            frame_id: 配信側で付与されたフレームID。
        """
        self._latest_frame = frame
        self._latest_frame_id = frame_id

    @QtCore.Slot(str)
    def _on_subscription_error(self, message):
        """画像購読エラーをステータス表示へ反映する。
        
        Args:
            message: 表示するエラーメッセージ。
        """
        self._status_label.setText(
            "画像受信エラー: {}".format(message)
        )

    def _start_roi_edit(self):
        """ROI編集状態を開始し、既存の編集中座標を消去する。"""
        self._editing_roi = True
        self._editing_points = []
        self._roi_label.setText(
            "ROI設定中: 4点を順にクリックしてください"
        )

    def _clear_editing_roi(self):
        """編集中のROI座標を破棄して編集状態を終了する。"""
        self._editing_points = []
        self._roi_label.setText(
            "画面上の未送信ROIをクリアしました"
        )

    @QtCore.Slot(int, int)
    def _on_image_click(self, x_value, y_value):
        """画像クリック座標をROI頂点として最大4点まで追加する。
        
        Args:
            x_value: 元画像座標系のX座標。
            y_value: 元画像座標系のY座標。
        """
        if not self._editing_roi:
            return

        if len(self._editing_points) >= 4:
            return

        self._editing_points.append(
            [int(x_value), int(y_value)]
        )
        self._roi_label.setText(
            "ROI設定中: {}/4 {}".format(
                len(self._editing_points),
                self._editing_points,
            )
        )

    def _send_roi(self):
        """編集中の4点ROIをサーバーへ送信し、Baseline再設定を促す。"""
        if len(self._editing_points) != 4:
            self._status_label.setText(
                "ROIは4点指定してから送信してください"
            )
            return

        try:
            result = self._client.set_roi_points(
                self._editing_points,
            )
            if result:
                self._server_roi_points = [
                    list(point)
                    for point in self._editing_points
                ]
                self._editing_points = []
                self._editing_roi = False
                self._status_label.setText(
                    "ROIを送信しました。Baselineを再設定してください"
                )
        except Exception as exc:
            self._status_label.setText(
                "ROI送信失敗: {}".format(exc)
            )

    def _set_baseline(self):
        """サーバーの最新検出位置をBaselineとして設定する。"""
        try:
            if self._client.set_baseline():
                self._status_label.setText("Baselineを設定しました")
            else:
                measurement = self._client.get_measurement()
                self._status_label.setText(
                    "Baseline設定失敗: {}".format(
                        measurement.get("last_error"),
                    )
                )
        except Exception as exc:
            self._status_label.setText(
                "Baseline設定失敗: {}".format(exc)
            )

    def _clear_baseline(self):
        """サーバーに保存されたBaselineを消去する。"""
        try:
            self._client.clear_baseline()
            self._status_label.setText("Baselineをクリアしました")
        except Exception as exc:
            self._status_label.setText(
                "Baselineクリア失敗: {}".format(exc)
            )

    def _start_measurement(self):
        """サーバーへ連続測定の開始を要求する。"""
        try:
            if self._client.start_measurement():
                self._status_label.setText("測定を開始しました")
            else:
                status = self._client.get_status()
                self._status_label.setText(
                    "測定開始失敗: {}".format(
                        status.get("last_error"),
                    )
                )
        except Exception as exc:
            self._status_label.setText(
                "測定開始失敗: {}".format(exc)
            )

    def _stop_measurement(self):
        """サーバーへ連続測定の停止を要求する。"""
        try:
            self._client.stop_measurement()
            self._status_label.setText("測定を停止しました")
        except Exception as exc:
            self._status_label.setText(
                "測定停止失敗: {}".format(exc)
            )

    def _refresh_status(self):
        """サーバー状態と最新測定値を取得し、各ラベルへ反映する。"""
        try:
            status = self._client.get_status()
            measurement = self._client.get_measurement()
            self._latest_measurement = measurement
            self._server_roi_points = status.get("roi_points", [])

            if measurement.get("measuring"):
                measurement_state = "測定中"
            else:
                measurement_state = "停止中"

            self._measurement_state_label.setText(
                "測定状態: {} ({})".format(
                    measurement_state,
                    status.get("state"),
                )
            )

            if measurement.get("baseline_detected"):
                baseline_detection = "成功"
            elif measurement.get("baseline_set"):
                baseline_detection = "再設定失敗（既存Baselineあり）"
            else:
                baseline_detection = "未設定または検出失敗"

            self._baseline_detection_label.setText(
                "Baseline検出: {}".format(baseline_detection)
            )

            if measurement.get("current_detected"):
                current_detection = "成功"
            else:
                current_detection = "失敗"

            self._current_detection_label.setText(
                "現在粉面検出: {}".format(current_detection)
            )
            self._baseline_level_label.setText(
                "Baseline位置: {} px".format(
                    measurement.get("baseline_level_y"),
                )
            )
            self._current_level_label.setText(
                "現在粉面位置: {} px".format(
                    measurement.get("level_y"),
                )
            )

            decrease_px = measurement.get("decrease_px")
            decrease_mm = measurement.get("decrease_mm")
            decrease_ratio = measurement.get("decrease_ratio")
            if decrease_ratio is None:
                decrease_percent = None
            else:
                decrease_percent = float(decrease_ratio) * 100.0

            self._decrease_label.setText(
                "Baselineからの減少量: {} px / {} mm / {} %".format(
                    decrease_px,
                    decrease_mm,
                    decrease_percent,
                )
            )

            last_error = measurement.get("last_error")
            if last_error:
                self._measurement_error_label.setText(
                    "測定エラー: {}".format(last_error)
                )
            else:
                self._measurement_error_label.setText("測定エラー: なし")

            if not self._editing_roi:
                self._roi_label.setText(
                    "server ROI: {}".format(
                        self._server_roi_points,
                    )
                )
        except Exception as exc:
            self._status_label.setText(
                "状態取得失敗: {}".format(exc)
            )

    def _refresh_image(self):
        """最新画像へROIと検出線を重ね、表示領域へアスペクト比を維持して描画する。"""
        if self._latest_frame is None:
            return

        frame = self._latest_frame.copy()
        self._draw_roi(
            frame,
            self._server_roi_points,
            (0, 255, 0),
        )
        self._draw_roi(
            frame,
            self._editing_points,
            (0, 255, 255),
        )

        baseline_line_left = self._latest_measurement.get(
            "baseline_line_left",
        )
        baseline_line_right = self._latest_measurement.get(
            "baseline_line_right",
        )

        if baseline_line_left is not None:
            if baseline_line_right is not None:
                cv2.line(
                    frame,
                    (
                        int(baseline_line_left[0]),
                        int(baseline_line_left[1]),
                    ),
                    (
                        int(baseline_line_right[0]),
                        int(baseline_line_right[1]),
                    ),
                    (0, 0, 255),
                    2,
                    cv2.LINE_AA,
                )

        current_line_left = self._latest_measurement.get(
            "line_left",
        )
        current_line_right = self._latest_measurement.get(
            "line_right",
        )

        if current_line_left is not None:
            if current_line_right is not None:
                cv2.line(
                    frame,
                    (
                        int(current_line_left[0]),
                        int(current_line_left[1]),
                    ),
                    (
                        int(current_line_right[0]),
                        int(current_line_right[1]),
                    ),
                    (255, 0, 0),
                    2,
                    cv2.LINE_AA,
                )

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        height = int(rgb.shape[0])
        width = int(rgb.shape[1])
        bytes_per_line = int(rgb.strides[0])

        # NumPyバッファの寿命からQImageを独立させるため、生成直後にcopy()する。
        image = QtGui.QImage(
            rgb.data,
            width,
            height,
            bytes_per_line,
            QtGui.QImage.Format.Format_RGB888,
        ).copy()

        pixmap = QtGui.QPixmap.fromImage(image)
        scaled_pixmap = pixmap.scaled(
            self._image_label.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )

        x_offset = int(
            (self._image_label.width() - scaled_pixmap.width()) / 2
        )
        y_offset = int(
            (self._image_label.height() - scaled_pixmap.height()) / 2
        )

        self._image_label.set_source_size(width, height)
        self._image_label.set_display_rect(
            QtCore.QRect(
                x_offset,
                y_offset,
                scaled_pixmap.width(),
                scaled_pixmap.height(),
            )
        )
        self._image_label.setPixmap(scaled_pixmap)

    def _draw_roi(self, frame, points, color):
        """ROI頂点、頂点番号、および頂点間の線を画像へ描画する。
        
        Args:
            frame: 描画対象のBGR画像。
            points: 描画するROI頂点列。
            color: OpenCVのBGR色。
        """
        if not points:
            return

        draw_points = []

        for index, point in enumerate(points):
            x_value = int(point[0])
            y_value = int(point[1])
            draw_points.append([x_value, y_value])

            cv2.circle(
                frame,
                (x_value, y_value),
                6,
                color,
                -1,
            )
            cv2.putText(
                frame,
                str(index + 1),
                (x_value + 8, y_value - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
                cv2.LINE_AA,
            )

        if len(draw_points) >= 2:
            polyline = np.array(
                draw_points,
                dtype=np.int32,
            ).reshape((-1, 1, 2))
            cv2.polylines(
                frame,
                [polyline],
                len(draw_points) == 4,
                color,
                2,
                cv2.LINE_AA,
            )

    def closeEvent(self, event):
        """ウィンドウ終了時にタイマー、画像配信、購読スレッド、gRPC接続を停止する。
        
        Args:
            event: Qtのウィンドウ終了イベント。
        """
        self._image_timer.stop()
        self._status_timer.stop()

        try:
            self._client.stop_stream()
        except Exception as exc:
            self._logger.error(
                "<POWDER GUI ACTION> stop_stream failed: {}".format(
                    exc,
                )
            )

        if self._subscription_thread is not None:
            self._subscription_thread.stop()

        self._client.close()

        if self._subscription_thread is not None:
            self._subscription_thread.wait(2000)

        event.accept()


def main():
    """エントリーポイントを実行する。"""
    app = QtWidgets.QApplication(sys.argv)
    window = PowderMonitorGui()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
