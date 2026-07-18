import time

from power_level_monitor.server_fastapi.client import PowderControlClient


SERVER_IP = "127.0.0.1"
SERVER_PORT = 8774


def main() -> None:
    client = PowderControlClient(
        server_ip=SERVER_IP,
        server_port=SERVER_PORT,
    )

    print(client.connect())
    print(client.set_roi_points(
        points=[
            [100, 100],
            [500, 100],
            [500, 900],
            [100, 900],
        ],
    ))
    print(client.start())

    for _ in range(20):
        print(client.get_measurement())
        time.sleep(0.5)

    print(client.set_baseline())
    print(client.get_status())


if __name__ == "__main__":
    main()
