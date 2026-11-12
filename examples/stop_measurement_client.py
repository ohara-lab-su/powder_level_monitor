#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""gRPCサーバーに粉面測定の停止を指示する。

サーバーやカメラを停止する操作ではなく、測定処理の停止指示である。"""

from powder_level_monitor.server_grpc import PowderLevelGrpcClient
from x_logger import XLogger


SERVER_IP = "127.0.0.1"
SERVER_PORT = 50051
MAX_MESSAGE_MB = 64


def main():
    logger = XLogger(
        log_level="debug",
        logger_name="stop_measurement",
    )
    client = PowderLevelGrpcClient(
        server_ip=SERVER_IP,
        grpc_port=SERVER_PORT,
        timeout_sec=5.0,
        logger=logger,
        max_message_mb=MAX_MESSAGE_MB,
    )
    try:
        print(client.stop_measurement())
    finally:
        client.close()


if __name__ == "__main__":
    main()
