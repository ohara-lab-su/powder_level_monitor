# Powder Level Monitor

[![English](https://img.shields.io/badge/docs-en-blue)](https://ohara-lab-su.github.io/powder_level_monitor/en/index.html) [![日本語](https://img.shields.io/badge/docs-ja-blue)](https://ohara-lab-su.github.io/powder_level_monitor/ja/index.html) [![GitHub](https://img.shields.io/badge/GitHub-repository-black)](https://github.com/ohara-lab-su/powder_level_monitor) [![Pages](https://img.shields.io/badge/GitHub-Pages-blue)](https://ohara-lab-su.github.io/powder_level_monitor/) [![Ohara Lab](https://img.shields.io/badge/Ohara-Lab-green)](https://ohara-lab-su.github.io/)

Powder Level Monitor detects the surface of powder in a container from webcam images and measures displacement relative to a baseline. The same camera acquisition, measurement control and image-recognition implementation is used locally without gRPC and in remote operation through `grpc_frame`.

```{toctree}
:maxdepth: 2
:caption: Contents

tutorials
api/modules
```

## Architecture and responsibilities

`ImageStream` owns camera connection, frame acquisition and image publishing. It is not a control server. `PowderControlDeviceClass` is the single measurement controller; it owns ROI, baseline, measurement lifecycle and measurement values. `PowderDetector` is the replaceable image-recognition implementation and has no camera, gRPC or baseline responsibility. `PowderLevelGrpcService` and `PowderLevelGrpcClient` expose the same control interface for remote operation without changing `grpc_frame`.

## Changes from 0.0.x to 0.1.x

In 0.0.x, `PowderControlDeviceClass` contained the image-recognition pipeline as well as measurement control. In 0.1.x, the recognition pipeline was moved into `PowderDetector`, and `image_stream_ctrl.py` was renamed to `image_stream.py` to reserve `ctrl` for the sole controller. The recognition method itself has not been improved or validated by this refactoring. Version 0.1.0 remains fixed during commissioning; no release tag is implied.

## Current detector algorithm

The input is a BGR frame, four ROI vertices in top-left, top-right, bottom-right, bottom-left order, and `ControlValues`. The ROI is rectified by perspective transformation to 360 × 720 pixels, then cropped by configurable margins. The crop is converted to grayscale, processed by CLAHE and Gaussian blur, thresholded using Otsu or a manual threshold (with optional inversion), and cleaned by morphological opening and closing. The mask is rejected if its white-pixel area or row occupancy is insufficient. For each image column, the first run whose window contains at least 70% white pixels is selected as a candidate surface point. Candidate Y coordinates are filtered by median absolute deviation (MAD), then fitted with a straight line using OpenCV's L2 `fitLine`. The detector returns a `SurfaceDetection`, a center Y in rectified coordinates and two display endpoints in original-camera coordinates; failures return four `None` values.

The algorithm assumes a contiguous thresholdable powder region with a nearly straight upper boundary. Reflections, changing illumination, curved surfaces and background may violate these assumptions. It is intended to be replaced as needed while retaining the external detector result contract and coordinate conventions.

## Local and remote operation

Local tests use the real webcam and call `PowderControlDeviceClass` directly, without communication. Production operation starts one gRPC service, and clients initiate measurement remotely. Neither mode duplicates the detection or measurement logic. See the tutorials for commands and the API reference for the Python interface.
