#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""gRPCサーバーから最新の粉面測定結果を取得し、JSON形式で表示する。

測定を開始するスクリプトではない。測定の有効性は結果の検出状態を確認する。"""

import json

from powder_level_monitor.server_grpc import PowderLevelGrpcClient
from x_logger import XLogger


SERVER_IP = "127.0.0.1"
SERVER_PORT = 50051
MAX_MESSAGE_MB = 64


def main():
    logger = XLogger(
        log_level="debug",
        logger_name="measurement_client",
    )
    client = PowderLevelGrpcClient(
        server_ip=SERVER_IP,
        grpc_port=SERVER_PORT,
        timeout_sec=5.0,
        logger=logger,
        max_message_mb=MAX_MESSAGE_MB,
    )
    try:
        print(json.dumps(client.get_measurement(), ensure_ascii=False, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
