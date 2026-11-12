[![English](https://img.shields.io/badge/docs-en-blue)](https://ohara-lab-su.github.io/powder_level_monitor/en/index.html) [![日本語](https://img.shields.io/badge/docs-ja-blue)](https://ohara-lab-su.github.io/powder_level_monitor/ja/index.html) [![GitHub](https://img.shields.io/badge/GitHub-repository-black)](https://github.com/ohara-lab-su/powder_level_monitor) [![Pages](https://img.shields.io/badge/GitHub-Pages-blue)](https://ohara-lab-su.github.io/powder_level_monitor/) [![Ohara Lab](https://img.shields.io/badge/Ohara-Lab-green)](https://ohara-lab-su.github.io/)

# Tutorials

## Overview

The server owns the webcam and executes image recognition. A remote client issues measurement commands via `grpc_frame`. Local tests call the same controller directly and require no gRPC server.

## Run the server

```bash
python examples/run_server.py
```

The examples use port `50051`; client examples use `127.0.0.1` by default. Change the client address when connecting from another machine.

## Remote client examples

Run the examples with `python examples/<filename>.py` after starting the server.

- `status_client.py`: inspect connection and measurement state.
- `get_roi_client.py`: read the current ROI.
- `set_roi_client.py`: set the ROI from `examples/roi.json` (must be supplied with camera-specific points).
- `get_baseline_client.py`: read the baseline.
- `set_baseline_client.py`: set the current detected surface as the baseline.
- `start_measurement_client.py`: start measurement.
- `stop_measurement_client.py`: stop measurement without stopping the server.
- `measurement_client.py`: read the latest measurement.
- `monitor_gui.py`: display streamed images and operate the measurement remotely.

## Local test without communication

Connect the webcam and instantiate `ImageStream` and `PowderControlDeviceClass(image_source=...)` in the same process. Call `connect()`, `set_roi_points()`, `process_once()`, `set_baseline()` and `disconnect()` directly. The `powder_monitor_ctrl.py` module also contains an interactive OpenCV example. The image-recognition implementation is the same as in remote operation.

## Recognition and calibration

The ROI must be defined using four vertices in the specified order. Changing the ROI invalidates the baseline. The current detector uses a rectified 360 × 720 pixel coordinate system; the physical scale is set by `measure_height_mm`, not determined automatically by perspective correction. Always verify detections and display endpoints against real camera images.
