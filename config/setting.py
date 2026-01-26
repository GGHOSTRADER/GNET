# -----------------------------------------------------------------

# ---- NETWORKING ----

# SAME IPv4 for Redis1 & TCP SERVER  but differnt PORTS
# 127.x.x.x is local loopback address
# 0.0.0.0 means listen on all interfaces (Is risky)

# TCP CONFIGURATION
TCP_HOST = "127.0.0.1"
TCP_PORT = 9009


# REDIS1 CONFIGURATION
REDIS1_HOST = "127.0.0.1"
REDIS1_PORT = 6381  # <------ must match REDIS1
REDIS1_STREAM_NAME = "bars_raw"  # <---- If this does not match, wont transmit either
# -----------------------------------------------------------------
