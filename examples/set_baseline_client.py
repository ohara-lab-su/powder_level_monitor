#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from power_level_monitor.grpc_client import PowderLevelGrpcClient
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
