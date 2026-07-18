#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Powder level monitor gRPC dynamic client."""

from typing import Any, Optional

from grpc_frame import GrpcClient


class PowderLevelGrpcClient(GrpcClient):
    """grpc_frame の完全透過呼び出しと画像購読を使う薄いクライアント。"""

    def __init__(
        self,
        server_ip,
        grpc_port,
        logger=None,
        log_level=None,
        timeout_sec=None,
        max_message_mb=64,
    ):
        # type: (str, int, Optional[Any], Optional[str], Optional[float], int) -> None
        max_message_bytes = int(max_message_mb) * 1024 * 1024
        grpc_options = (
            ("grpc.max_receive_message_length", max_message_bytes),
            ("grpc.max_send_message_length", max_message_bytes),
        )

        super().__init__(
            server_ip=server_ip,
            server_port=grpc_port,
            logger=logger,
            log_level=log_level,
            timeout_sec=timeout_sec,
            grpc_options=grpc_options,
        )
