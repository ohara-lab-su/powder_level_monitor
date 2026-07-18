from grpc_frame.grpc_client import SyncGrpcClient
from x_logger import XLogger


SERVER_IP = "127.0.0.1"
SERVER_PORT = 50051
MAX_MESSAGE_MB = 64


def main():
    logger = XLogger(
        log_level="debug",
        logger_name="get_roi_client",
    )
    max_message_bytes = MAX_MESSAGE_MB * 1024 * 1024
    client = SyncGrpcClient(
        server_ip=SERVER_IP,
        server_port=SERVER_PORT,
        timeout_sec=5.0,
        logger=logger,
        grpc_options=(
            ("grpc.max_send_message_length", max_message_bytes),
            ("grpc.max_receive_message_length", max_message_bytes),
        ),
    )
    try:
        print(client.get_roi_points())
    finally:
        client.close()


if __name__ == "__main__":
    main()
