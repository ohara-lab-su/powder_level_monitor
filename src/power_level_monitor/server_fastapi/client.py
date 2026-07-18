from typing import Any, Optional

from ese774_frame.clients.sync_device_client import SyncDeviceClient

from power_level_monitor.server_fastapi.api_spec import API_SPEC
from power_level_monitor.server_fastapi.api_spec import OBJECT_NAME


class PowderControlClient(SyncDeviceClient):
    """ese774_frame 用の粉体測定クライアントである。"""

    def __init__(
        self,
        server_ip: str,
        server_port: int,
        logger: Optional[Any] = None,
    ) -> None:
        super().__init__(
            server_ip=server_ip,
            server_port=server_port,
            api_spec=API_SPEC,
            logger=logger,
            object_name=OBJECT_NAME,
        )
