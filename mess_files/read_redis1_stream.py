# read_redis1_stream.py
from networking.redis_tool import get_redis_connection
from config.setting import REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME
import time
from datetime import datetime


def decode(x):
    if isinstance(x, bytes):
        return x.decode("utf-8", errors="replace")
    return str(x)


def pretty_print(entry_id, fields):
    print("\n" + "-" * 80)
    print(f"{datetime.now().isoformat()} | ID: {decode(entry_id)}")
    for k, v in fields.items():
        print(f"{decode(k):>10s} = {decode(v)}")


def main():
    r = get_redis_connection(REDIS1_HOST, REDIS1_PORT, REDIS1_STREAM_NAME)

    stream = REDIS1_STREAM_NAME
    last_id = "0-0"  # start from beginning (change to "$" for only new messages)

    print(f"[reader] Redis: {REDIS1_HOST}:{REDIS1_PORT}")
    print(f"[reader] Stream: {stream}")
    print("[reader] Reading... Ctrl+C to stop.\n")

    while True:
        # BLOCK waits for new messages up to 5 seconds
        resp = r.xread({stream: last_id}, count=20, block=5000)

        if not resp:
            continue

        for stream_name, messages in resp:
            for entry_id, fields in messages:
                pretty_print(entry_id, fields)
                last_id = entry_id  # advance cursor


if __name__ == "__main__":
    main()
