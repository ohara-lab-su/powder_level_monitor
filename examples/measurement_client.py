#!/usr/bin/env python3
# -*- coding: utf-8 -*-

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
