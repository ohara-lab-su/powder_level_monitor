from ese774_frame.api_server import FastApiServer
from ese774_frame.routers.device_router import DeviceRouter
from grpc_frame.event_bus import EventBus
from grpc_frame.grpc_server import create_grpc_server

from power_level_monitor.image_stream_ctrl import ImageStreamDeviceClass
from power_level_monitor.powder_monitor_ctrl import PowderControlDeviceClass
from power_level_monitor.server_fastapi.api_spec import API_SPEC


FASTAPI_HOST = "0.0.0.0"
FASTAPI_PORT = 8774
GRPC_HOST = "0.0.0.0"
GRPC_PORT = 50051
CAMERA_ID = 0


def main() -> None:
    image_device = ImageStreamDeviceClass(
        camera_id=CAMERA_ID,
        topic_name="camera.frame",
        interval_sec=0.1,
        capture_interval_sec=0.03,
        jpeg_quality=85,
    )

    event_bus = EventBus()
    grpc_server = create_grpc_server(
        ctrl_obj=image_device,
        event_bus=event_bus,
        max_workers=10,
        log_level="INFO",
    )
    grpc_server.add_insecure_port(
        f"{GRPC_HOST}:{GRPC_PORT}",
    )
    grpc_server.start()

    if not image_device.connect():
        status = image_device.get_status()
        grpc_server.stop(grace=1.0)
        raise RuntimeError(str(status.get("last_error")))

    image_device.start_stream()

    fastapi_server = FastApiServer(
        device_cls=PowderControlDeviceClass,
        router_cls=DeviceRouter,
        config=None,
        api_spec=API_SPEC,
        device_kwargs={
            "image_source": image_device,
            "measurement_interval_sec": 0.1,
        },
        logger_name="PowderControlFastApiServer",
        log_level="INFO",
        lifespan_msg_prefix="POWDER_CONTROL",
    )

    try:
        fastapi_server.run(
            host=FASTAPI_HOST,
            port=FASTAPI_PORT,
            reload=False,
        )
    finally:
        image_device.disconnect()
        grpc_server.stop(grace=1.0)


if __name__ == "__main__":
    main()
