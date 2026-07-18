import threading
import tkinter as tk
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
from PIL import Image
from PIL import ImageTk
from power_level_monitor.grpc_client import PowderLevelGrpcClient
from x_logger import XLogger


SERVER_IP = "127.0.0.1"
SERVER_PORT = 50051
IMAGE_TOPIC = "camera.frame"
MAX_MESSAGE_MB = 64
STATUS_REFRESH_MS = 500
IMAGE_REFRESH_MS = 50


class PowderMonitorGui:
    def __init__(self, root):
        self._root = root
        self._logger = XLogger(
            log_level="debug",
            logger_name="PowderMonitorGui",
        )
        self._client = PowderLevelGrpcClient(
            server_ip=SERVER_IP,
            grpc_port=SERVER_PORT,
            timeout_sec=5.0,
            logger=self._logger,
            max_message_mb=MAX_MESSAGE_MB,
        )

        self._frame_lock = threading.Lock()
        self._latest_frame = None
        self._latest_frame_id = None
        self._subscription_thread = None
        self._subscription_running = True

        self._photo = None
        self._source_width = 1
        self._source_height = 1
        self._display_width = 960
        self._display_height = 720
        self._editing_roi = False
        self._editing_points = []
        self._server_roi_points = []

        self._status_var = tk.StringVar(value="接続中")
        self._measurement_var = tk.StringVar(value="")
        self._roi_var = tk.StringVar(value="ROI: 未取得")

        self._build_gui()
        self._start_subscription()
        self._root.after(IMAGE_REFRESH_MS, self._refresh_image)
        self._root.after(STATUS_REFRESH_MS, self._refresh_status)
        self._root.protocol("WM_DELETE_WINDOW", self._close)

    def _build_gui(self):
        self._root.title("Powder Level Monitor")

        self._canvas = tk.Canvas(
            self._root,
            width=self._display_width,
            height=self._display_height,
            background="black",
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)
        self._canvas.bind("<Button-1>", self._on_canvas_click)

        button_frame = tk.Frame(self._root)
        button_frame.pack(fill=tk.X)

        tk.Button(
            button_frame,
            text="ROI設定開始",
            command=self._start_roi_edit,
        ).pack(side=tk.LEFT)
        tk.Button(
            button_frame,
            text="ROI送信",
            command=self._send_roi,
        ).pack(side=tk.LEFT)
        tk.Button(
            button_frame,
            text="画面ROIクリア",
            command=self._clear_editing_roi,
        ).pack(side=tk.LEFT)
        tk.Button(
            button_frame,
            text="Baseline設定",
            command=self._set_baseline,
        ).pack(side=tk.LEFT)
        tk.Button(
            button_frame,
            text="Baselineクリア",
            command=self._clear_baseline,
        ).pack(side=tk.LEFT)
        tk.Button(
            button_frame,
            text="測定開始",
            command=self._start_measurement,
        ).pack(side=tk.LEFT)
        tk.Button(
            button_frame,
            text="測定停止",
            command=self._stop_measurement,
        ).pack(side=tk.LEFT)

        tk.Label(
            self._root,
            textvariable=self._status_var,
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            self._root,
            textvariable=self._measurement_var,
            anchor="w",
        ).pack(fill=tk.X)
        tk.Label(
            self._root,
            textvariable=self._roi_var,
            anchor="w",
        ).pack(fill=tk.X)

    def _start_subscription(self):
        self._subscription_thread = threading.Thread(
            target=self._subscription_loop,
            name="PowderImageSubscriptionThread",
            daemon=True,
        )
        self._subscription_thread.start()

    def _subscription_loop(self):
        try:
            for payload in self._client.subscribe(topic=IMAGE_TOPIC):
                if not self._subscription_running:
                    break
                image_bytes = payload.get("image")
                if image_bytes is None:
                    continue
                encoded = np.frombuffer(image_bytes, dtype=np.uint8)
                frame = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
                if frame is None:
                    continue
                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_frame_id = payload.get("frame_id")
        except Exception as exc:
            self._logger.error("<POWDER GUI ACTION> image subscription failed: {}".format(exc))
            self._status_var.set("画像受信エラー: {}".format(exc))

    def _start_roi_edit(self):
        self._editing_roi = True
        self._editing_points = []
        self._roi_var.set("ROI設定中: 4点を順にクリックしてください")

    def _clear_editing_roi(self):
        self._editing_points = []
        self._roi_var.set("画面上の未送信ROIをクリアしました")

    def _on_canvas_click(self, event):
        if not self._editing_roi:
            return
        if len(self._editing_points) >= 4:
            return
        if self._display_width <= 0 or self._display_height <= 0:
            return

        x_value = int(event.x * self._source_width / float(self._display_width))
        y_value = int(event.y * self._source_height / float(self._display_height))
        self._editing_points.append([x_value, y_value])
        self._roi_var.set(
            "ROI設定中: {}/4 {}".format(
                len(self._editing_points),
                self._editing_points,
            )
        )

    def _send_roi(self):
        if len(self._editing_points) != 4:
            self._status_var.set("ROIは4点指定してから送信してください")
            return
        try:
            result = self._client.set_roi_points(self._editing_points)
            if result:
                self._server_roi_points = [list(point) for point in self._editing_points]
                self._editing_points = []
                self._editing_roi = False
                self._status_var.set("ROIを送信しました。Baselineを再設定してください")
        except Exception as exc:
            self._status_var.set("ROI送信失敗: {}".format(exc))

    def _set_baseline(self):
        try:
            if self._client.set_baseline():
                self._status_var.set("Baselineを設定しました")
            else:
                status = self._client.get_status()
                self._status_var.set(
                    "Baseline設定失敗: {}".format(status.get("last_error"))
                )
        except Exception as exc:
            self._status_var.set("Baseline設定失敗: {}".format(exc))

    def _clear_baseline(self):
        try:
            self._client.clear_baseline()
            self._status_var.set("Baselineをクリアしました")
        except Exception as exc:
            self._status_var.set("Baselineクリア失敗: {}".format(exc))

    def _start_measurement(self):
        try:
            if self._client.start_measurement():
                self._status_var.set("測定を開始しました")
            else:
                status = self._client.get_status()
                self._status_var.set(
                    "測定開始失敗: {}".format(status.get("last_error"))
                )
        except Exception as exc:
            self._status_var.set("測定開始失敗: {}".format(exc))

    def _stop_measurement(self):
        try:
            self._client.stop_measurement()
            self._status_var.set("測定を停止しました")
        except Exception as exc:
            self._status_var.set("測定停止失敗: {}".format(exc))

    def _refresh_status(self):
        try:
            status = self._client.get_status()
            measurement = status.get("measurement", {})
            self._server_roi_points = status.get("roi_points", [])
            self._measurement_var.set(
                "state={} detected={} level_y={} decrease_mm={} baseline={} frame_id={}".format(
                    status.get("state"),
                    measurement.get("detected"),
                    measurement.get("level_y"),
                    measurement.get("decrease_mm"),
                    status.get("baseline_level_y"),
                    self._latest_frame_id,
                )
            )
            if not self._editing_roi:
                self._roi_var.set("server ROI: {}".format(self._server_roi_points))
        except Exception as exc:
            self._status_var.set("状態取得失敗: {}".format(exc))
        self._root.after(STATUS_REFRESH_MS, self._refresh_status)

    def _refresh_image(self):
        with self._frame_lock:
            if self._latest_frame is None:
                frame = None
            else:
                frame = self._latest_frame.copy()

        if frame is not None:
            self._source_height = int(frame.shape[0])
            self._source_width = int(frame.shape[1])
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(rgb)
            image.thumbnail((960, 720))
            self._display_width = image.width
            self._display_height = image.height
            self._canvas.config(
                width=self._display_width,
                height=self._display_height,
            )
            self._photo = ImageTk.PhotoImage(image)
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor=tk.NW, image=self._photo)
            self._draw_points(self._server_roi_points, "lime", "server_roi")
            self._draw_points(self._editing_points, "yellow", "editing_roi")

        self._root.after(IMAGE_REFRESH_MS, self._refresh_image)

    def _draw_points(self, points, color, tag):
        if not points:
            return
        display_points = []
        for index, point in enumerate(points):
            x_value = int(point[0] * self._display_width / float(self._source_width))
            y_value = int(point[1] * self._display_height / float(self._source_height))
            display_points.append((x_value, y_value))
            self._canvas.create_oval(
                x_value - 5,
                y_value - 5,
                x_value + 5,
                y_value + 5,
                fill=color,
                outline=color,
                tags=tag,
            )
            self._canvas.create_text(
                x_value + 12,
                y_value - 12,
                text=str(index + 1),
                fill=color,
                tags=tag,
            )
        if len(display_points) >= 2:
            line_points = list(display_points)
            if len(display_points) == 4:
                line_points.append(display_points[0])
            flat_points = []
            for point in line_points:
                flat_points.extend(point)
            self._canvas.create_line(
                *flat_points,
                fill=color,
                width=2,
                tags=tag,
            )

    def _close(self):
        self._subscription_running = False
        self._client.close()
        self._root.destroy()


def main():
    root = tk.Tk()
    PowderMonitorGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
