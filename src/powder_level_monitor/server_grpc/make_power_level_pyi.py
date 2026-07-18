#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import pathlib

import grpc_frame
from grpc_frame.make_pyi import generate_client_pyi


def main() -> None:
    # 現在のディレクトリ
    base = pathlib.Path(__file__).resolve().parent

    # Package 内の GrpcFrame の場所
    grpc_base = pathlib.Path(grpc_frame.__file__).resolve().parent

    # sync
    out = base / "grpc_client.pyi"

    generate_client_pyi(
        ### client
        client_py=base / "grpc_client.py",
        client_class="PowderLevelGrpcClient",
        ### Ctrl
        ctrl_py=base / "../powder_level_device.py",
        ctrl_class="PowderLevelDeviceClass",
        ### Grpc
        base_py=grpc_base / "grpc_client.py",
        base_class="GrpcClient",
        ### Output
        out_path=out,
        ctrl_async=False,
    )


if __name__ == "__main__":
    main()