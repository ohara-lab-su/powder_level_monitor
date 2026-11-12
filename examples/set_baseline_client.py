#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""現在検出されている粉面位置をBaselineとしてgRPCサーバーに設定する。

ROIを設定し、粉面検出が成功している状態で実行する。失敗時は測定結果のエラーを表示する。"""

from powder_level_monitor.server_grpc import PowderLevelGrpcClient
from x_logger import XLogger


SERVER_IP = "127.0.0.1"
SERVER_PORT = 50051
MAX_MESSAGE_MB = 64


def main():
    logger = XLogger(
        log_level="debug",
        logger_name="set_baseline_client",
    )
    client = PowderLevelGrpcClient(
        server_ip=SERVER_IP,
        grpc_port=SERVER_PORT,
        timeout_sec=5.0,
        logger=logger,
        max_message_mb=MAX_MESSAGE_MB,
    )
    try:
        result = client.set_baseline()
        print(result)
        if not result:
            measurement = client.get_measurement()
            print(measurement.get("last_error"))
    finally:
        client.close()


if __name__ == "__main__":
    main()
