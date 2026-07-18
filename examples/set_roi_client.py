#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os

from powder_level_monitor.server_grpc import PowderLevelGrpcClient
from x_logger import XLogger


SERVER_IP = "127.0.0.1"
SERVER_PORT = 50051
MAX_MESSAGE_MB = 64
ROI_FILE = os.path.join(os.path.dirname(__file__), "roi.json")


def main():
    logger = XLogger(
        log_level="debug",
        logger_name="set_roi_client",
    )
    client = PowderLevelGrpcClient(
        server_ip=SERVER_IP,
        grpc_port=SERVER_PORT,
        timeout_sec=5.0,
        logger=logger,
        max_message_mb=MAX_MESSAGE_MB,
    )
    try:
        with open(ROI_FILE, "r", encoding="utf-8") as file_obj:
            roi_data = json.load(file_obj)
        print(client.set_roi_points(roi_data["points"]))
    finally:
        client.close()


if __name__ == "__main__":
    main()
