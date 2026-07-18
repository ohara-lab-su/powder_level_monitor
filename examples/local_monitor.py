from __future__ import annotations

import time

import cv2

from power_level_monitor.image_stream_ctrl import ImageStreamDeviceClass
from power_level_monitor.powder_monitor_ctrl import PowderControlDeviceClass


WINDOW_NAME = "powder level local"


class RoiSelector:
    def __init__(self) -> None:
        self.points: list[list[int]] = []

    def on_mouse(
        self,
        event: int,
        x: int,
        y: int,
        flags: int,
        param: object,
    ) -> None:
        if event != cv2.EVENT_LBUTTONDOWN:
            return

        if len(self.points) >= 4:
            return

        self.points.append([int(x), int(y)])


def main() -> None:
    image_device = ImageStreamDeviceClass(camera_id=0)
    monitor = PowderControlDeviceClass(
        image_source=image_device,
        measurement_interval_sec=0.1,
    )
    selector = RoiSelector()

    if not monitor.connect():
        raise RuntimeError(str(monitor.get_status().get("last_error")))

    cv2.namedWindow(WINDOW_NAME)
    cv2.setMouseCallback(WINDOW_NAME, selector.on_mouse)

    try:
        while True:
            frame = image_device.get_latest_frame()

            if frame is None:
                time.sleep(0.01)
                continue

            preview = frame.copy()

            for index, point in enumerate(selector.points):
                cv2.circle(
                    preview,
                    (point[0], point[1]),
                    5,
                    (0, 255, 255),
                    -1,
                )
                cv2.putText(
                    preview,
                    str(index + 1),
                    (point[0] + 8, point[1] - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )

            measurement = monitor.get_measurement()
            cv2.putText(
                preview,
                str(measurement),
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1,
            )
            cv2.imshow(WINDOW_NAME, preview)

            key = cv2.waitKey(10) & 0xFF

            if key == ord("q"):
                break

            if key == ord("r"):
                selector.points = []
                monitor.clear_roi_points()

            if key == ord("s"):
                if len(selector.points) == 4:
                    monitor.set_roi_points(selector.points)
                    monitor.start()

            if key == ord("b"):
                monitor.set_baseline()

    finally:
        monitor.disconnect()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
