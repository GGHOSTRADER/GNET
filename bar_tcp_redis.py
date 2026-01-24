# ---------------------------------------------------------------------------------
# TS -- > TCP  ---> Redis Stream
# A TCP server that listens for incoming bar data in CSV format From Tradestation
# Each line received is parsed and appended to a Redis Stream named "bars_raw"
# ---------------------------------------------------------------------------------

import socket
from datetime import datetime
import redis


# -----------------------------------------------------------------
# SAME IPv4 for Redis1 & TCP SERVER  but differnt PORTS
# 127.x.x.x is local loopback address
# 0.0.0.0 means listen on all interfaces (Is risky)
HOST = "127.0.0.1"
PORT = 9009

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6381  # <------ must match REDIS1
STREAM_NAME = "bars_raw"  # <---- If this does not match, wont transmit either
# -----------------------------------------------------------------


def main():

    # READING & CONNECTING

    # REDIS -----------------------------------------------------------------------------------------------------
    # Connect to Redis1
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    if r.ping():
        print(
            f"1) [bar_server] Connected to Redis1 \n-Host:{REDIS_HOST}\n-Port:{REDIS_PORT}\n-Stream Name:{STREAM_NAME}\n"
        )
    else:
        print("1) [bar_server] Failed to connect to Redis1")

    # TCP -----------------------------------------------------------------------------------------------------
    # Connect to TCP
    print(f"2) [bar_server] Listening TCP\n-Host:{HOST}\n-Port:{PORT} ")
    # Create Server socket
    # AF_INET = IPv4
    # SOCK_STREAM = TCP (reliable byte stream)
    # S is the server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Lets server restart
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind server to the host and port
        s.bind((HOST, PORT))
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

                    # Unpacks the data into the variables
                    (
                        symbol,
                        date,
                        time_,
                        open_,
                        high,
                        low,
                        close,
                        up,
                        down,
                        vwap,
                        bar_num,
                    ) = parts

                    # Append data recieved from TCP and parsed to Redis1 Stream
                    r.xadd(
                        STREAM_NAME,
                        {
                            "symbol": symbol,
                            "date": date,
                            "time": time_,
                            "open": open_,
                            "high": high,
                            "low": low,
                            "close": close,
                            "up": up,
                            "down": down,
                            "vwap": vwap,
                            "bar_num": bar_num,
                        },
                        maxlen=1_000,  # prevent unbounded growth, max number
                        approximate=True,
                    )

                    # Optional: debug output
                    print(f"{datetime.now().isoformat()}  {line}")


if __name__ == "__main__":
    main()
