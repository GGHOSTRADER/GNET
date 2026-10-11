"""Quote-independent interpreter identity probe; no market data or imports."""
import json
import platform
import struct


def identity():
    return {"version": platform.python_version(), "bits": struct.calcsize("P") * 8}


if __name__ == "__main__":
    print(json.dumps(identity(), sort_keys=True))
