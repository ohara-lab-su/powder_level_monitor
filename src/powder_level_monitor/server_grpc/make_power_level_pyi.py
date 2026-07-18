#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""grpc_frame の動的クライアント用型スタブを生成するスクリプト。"""

from __future__ import annotations

import pathlib

import grpc_frame
from grpc_frame.make_pyi import generate_client_pyi


def main() -> None:
    # 現在のディレクトリ
    """エントリーポイントを実行する。"""
    base = pathlib.Path(__file__).resolve().parent

    # Package 内の GrpcFrame の場所
    grpc_base = pathlib.Path(grpc_frame.__file__).resolve().parent

    # sync
    out = base / "powder_level_grpc_client.pyi"

    generate_client_pyi(
        ### client
        client_py=base / "powder_level_grpc_client.py",
        client_class="PowderLevelGrpcClient",
        ### Ctrl
        ctrl_py=base / "powder_level_grpc_service.py",
        ctrl_class="PowderLevelGrpcService",
        ### Grpc
        base_py=grpc_base / "grpc_client.py",
        base_class="GrpcClient",
        ### Output
        out_path=out,
        ctrl_async=False,
    )


if __name__ == "__main__":
    main()
