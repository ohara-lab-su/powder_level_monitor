from grpc_frame.event_bus import EventBus
from grpc_frame.grpc_server import create_grpc_server
from x_logger import XLogger

from powder_level_monitor.server_grpc import PowderLevelGrpcService



GRPC_HOST = "0.0.0.0"
GRPC_PORT = 50051
CAMERA_ID = 0
MAX_MESSAGE_MB = 64


def main():
    logger = XLogger(
        log_level="debug",
        logger_name="PowderLevelServer",
    )
    logger.info("<POWDER SERVER ACTION> startup")

    device = PowderLevelGrpcService(
        camera_id=CAMERA_ID,
        image_topic="camera.frame",
        image_interval_sec=0.1,
        capture_interval_sec=0.03,
        measurement_interval_sec=0.1,
        jpeg_quality=85,
        logger=logger,
    )
    event_bus = EventBus()
    max_message_bytes = MAX_MESSAGE_MB * 1024 * 1024
    server = create_grpc_server(
        ctrl_obj=device,
        event_bus=event_bus,
        max_workers=10,
        logger=logger,
        log_level="INFO",
        grpc_options=(
            ("grpc.max_send_message_length", max_message_bytes),
            ("grpc.max_receive_message_length", max_message_bytes),
        ),
    )
    server.add_insecure_port(
        "{}:{}".format(GRPC_HOST, GRPC_PORT),
    )
    server.start()

    try:
        if not device.connect():
            raise RuntimeError(str(device.get_status()))
        logger.info(
            "<POWDER SERVER ACTION> grpc_frame started: {}:{}".format(
                GRPC_HOST,
                GRPC_PORT,
            )
        )
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("<POWDER SERVER ACTION> KeyboardInterrupt")
    finally:
        logger.info("<POWDER SERVER ACTION> shutdown")
        device.disconnect()
        server.stop(grace=1.0)


if __name__ == "__main__":
    main()
