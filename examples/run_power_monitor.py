from __future__ import annotations

from ese774_frame.api_server import FastApiServer
from ese774_frame.device_router import DeviceRouter

from src.powder_control_device_class import PowderControlDeviceClass
from src.server_fastapi.api_spec import API_SPEC


HOST = "0.0.0.0"
PORT = 8774


def main() -> None:
    """ese774_frame による粉体制御サーバーを起動する。"""
    server = FastApiServer(
        device_cls=PowderControlDeviceClass,
        router_cls=DeviceRouter,
        config=None,
        api_spec=API_SPEC,
        device_kwargs={},
        logger_name="PowderControlFastApiServer",
        log_level="INFO",
        lifespan_msg_prefix="POWDER_CONTROL",
    )
    server.run(
        host=HOST,
        port=PORT,
        reload=False,
    )


if __name__ == "__main__":
    main()