# ---------------------------------------------------------------------------------
# TS -- > TCP  ---> Redis Stream
# A TCP server that listens for incoming bar data in CSV format From Tradestation
# Each line received is parsed and appended to a Redis Stream named "validated_bar"

# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
# TO RUN AS A MODULE INSTEAD OF A SCRIPT (for better imports):
# python -m netwo_files.tcp_to_redis_connection
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

# ---------------------------------------------------------------------------------

from netwo_files.redis_tool import get_redis_connection
from config.setting import (
    TCP_HOST,
    TCP_PORT,
    REDIS1_HOST,
    REDIS1_PORT,
    REDIS1_STREAM_NAME,
)
import socket
from datetime import datetime
import redis

# 🟦 ADD HERE (imports): you need the codec/validator at the boundary
from netwo_files.bar_codec import parse_csv_line, bar_to_redis_fields
from netwo_files.bar_contract import validate_sequence, ContractError
from netwo_files.bar_codec import DecodeError


def _handle_client(conn, redis_client) -> None:
    """Drain one bar-DLL connection until it closes."""
    buf = b""
    with conn:
        while True:
            data = conn.recv(4096)
            if not data:
                return
            buf += data

            while b"\n" in buf:
                raw_line, buf = buf.split(b"\n", 1)
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                if len(line.split(",")) != 11:
                    print(f"[bar_server] Malformed line: {line}")
                    continue

                try:
                    bar = parse_csv_line(line)
                except (DecodeError, ContractError) as exc:
                    print(
                        f"[bar_server] Decode/Contract violation: {exc} | line={line}"
                    )
                    continue

                redis_client.xadd(
                    REDIS1_STREAM_NAME,
                    bar_to_redis_fields(bar),
                    maxlen=1_000,
                    approximate=True,
                )
                print(f"{datetime.now().isoformat()}  {line}")


def _accept_forever(server, redis_client) -> None:
    """Accept replacement DLL clients without terminating this process."""
    while True:
        conn, addr = server.accept()
        print(f"[bar_server] Connection from {addr}")
        try:
            _handle_client(conn, redis_client)
            print("[bar_server] Client disconnected")
        except OSError as exc:
            print(f"[bar_server] Client connection lost: {exc}")
        print("[bar_server] Waiting for TradeStation to reconnect...")


def main() -> None:
    redis_client = get_redis_connection(
        REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME
    )
    print(f"2) [bar_server] Listening TCP\n-Host:{TCP_HOST}\n-Port:{TCP_PORT} ")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((TCP_HOST, TCP_PORT))
        server.listen(5)
        _accept_forever(server, redis_client)


if __name__ == "__main__":
    main()
