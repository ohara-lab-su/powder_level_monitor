#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""粉体レベル監視サーバーへ接続する gRPC クライアントを提供する。"""

from typing import Any, Optional

from grpc_frame import GrpcClient


class PowderLevelGrpcClient(GrpcClient):
    """粉体レベル監視サービス用の薄いgRPCクライアント。

GrpcClientの動的メソッド転送を利用しつつ、大容量JPEG画像を送受信できるようメッセージ上限を設定する。"""

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
        """gRPCクライアントを初期化する。
        
        Args:
            server_ip: 接続先サーバーのIPアドレスまたはホスト名。
            grpc_port: 接続先gRPCポート番号。
            logger: 使用するロガー。省略時は基底クラスの既定値を使用する。
            log_level: ログレベル。
            timeout_sec: RPC呼び出しのタイムアウト秒数。
            max_message_mb: 送受信可能なgRPCメッセージの最大容量（MiB）。
        """
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
