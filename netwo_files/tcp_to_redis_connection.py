# ---------------------------------------------------------------------------------
# TS -- > TCP  ---> Redis Stream
# A TCP server that listens for incoming bar data in CSV format From Tradestation
# Each line received is parsed and appended to a Redis Stream named "bars_raw"

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


def main():

    # READING & CONNECTING

    # REDIS -----------------------------------------------------------------------------------------------------
    # Connect to Redis1
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME)

    # TCP -----------------------------------------------------------------------------------------------------
    # Connect to TCP
    print(f"2) [bar_server] Listening TCP\n-Host:{TCP_HOST}\n-Port:{TCP_PORT} ")
    # Create Server socket
    # AF_INET = IPv4
    # SOCK_STREAM = TCP (reliable byte stream)
    # S is the server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Lets server restart
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind server to the host and port
        s.bind((TCP_HOST, TCP_PORT))
        # Que incoming connectionsS
        s.listen(5)

        # Accepts one Client
        # Conn = New Socket
        # addr = Client Address
        conn, addr = s.accept()
        print(f"[bar_server] Connection from {addr}")

        # Created Empty buffer to recieve
        buf = b""
        with conn:
            # Recieves Data forever of client
            while True:
                # 4096 is maximum bytes per read
                data = conn.recv(4096)
                # If client is gone, it breaks the loop
                if not data:
                    print("[bar_server] Client disconnected")
                    break

                # Appends new data Chunks to buffer
                buf += data

                # If there is a line separator it will proceed
                while b"\n" in buf:
                    # Will split in line sep and leave rest
                    raw_line, buf = buf.split(b"\n", 1)
                    # Convert bytes to String
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue

                    # split by "," so symbol,date,time,open,high,low,close,up,down,barnumber
                    parts = line.split(",")
                    if len(parts) != 11:  # <---------- How many fields are expected
                        print(f"[bar_server] Malformed line: {line}")
                        continue

                    # 🟨 ADD HERE: parse + cast + validate BEFORE redis
                    try:
                        bar = parse_csv_line(line)  # CSV -> typed Bar + validate_bar()
                    except (DecodeError, ContractError) as e:
                        print(
                            f"[bar_server] Decode/Contract violation: {e} | line={line}"
                        )
                        continue

                    # ⬛ TAKE OUT (replaced by fields)
                    # Unpacks the data into the variables
                    # (
                    #    symbol,
                    #    date,
                    #    time_,
                    #    open_,
                    #    high,
                    #    low,
                    #    close,
                    #    up,
                    #    down,
                    #    vwap,
                    #    bar_num,
                    # ) = parts

                    # 🟥 ADD HERE: choose the payload you write to Redis
                    fields = bar_to_redis_fields(bar)  # canonical strings

                    # ⬛ TAKE OUT (replaced by fields)
                    # Append data recieved from TCP and parsed to Redis1 Stream
                    # r.xadd(
                    #    REDIS1_STREAM_NAME,
                    #    {
                    #        "symbol": symbol,
                    #        "date": date,
                    #        "time": time_,
                    #        "open": open_,
                    #        "high": high,
                    #        "low": low,
                    #        "close": close,
                    #        "up": up,
                    #        "down": down,
                    #        "vwap": vwap,
                    #        "bar_num": bar_num,
                    #    },
                    #    maxlen=1_000,  # prevent unbounded growth, max number
                    #    approximate=True,
                    # )

                    # 🟥 ADD HERE: new xadd uses the canonical payload
                    r.xadd(
                        REDIS1_STREAM_NAME,
                        fields,
                        maxlen=1_000,
                        approximate=True,
                    )

                    # Optional: debug output
                    print(f"{datetime.now().isoformat()}  {line}")


if __name__ == "__main__":
    main()
