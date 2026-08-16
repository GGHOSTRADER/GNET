# -----------------------------------------------------------------

# ---- NETWORKING ----

# SAME IPv4 for Redis1 & TCP SERVER  but differnt PORTS
# 127.x.x.x is local loopback address
# 0.0.0.0 means listen on all interfaces (Is risky)

# TCP CONFIGURATION - BAR DATA
TCP_HOST = "127.0.0.1"
TCP_PORT = 9009

# TCP CONFIGURATION - TICK DATA
TCP_TICK_HOST = "127.0.0.1"
TCP_TICK_PORT = 9010

# TCP CONFIGURATION - STRATEGY CANDIDATES (TradeStation -> Python)
TCP_CANDIDATE_HOST = "127.0.0.1"
TCP_CANDIDATE_PORT = 9012

# REDIS1 CONFIGURATION
REDIS1_HOST = "127.0.0.1"
REDIS1_PORT = 6381
REDIS1_STREAM_NAME = "validated_bar"
REDIS1_TICK_RAW_STREAM = "tick_data_raw"
REDIS1_TICK_VALIDATED_STREAM = "tick_data_validated"
REDIS1_FEATURES_TRANSFORMER_STREAM = "features_transformer"
REDIS1_FEATURES_VP_STREAM = "features_volume_profile"
REDIS1_SIGNAL_STREAM = "trade_signal"
REDIS1_CANDIDATE_STREAM = "trade_candidates"
REDIS1_DECISION_STREAM = "trade_decisions"
REDIS1_ROUTER_READY_KEY = "gnet:strategy_router:ready"
REDIS1_ROUTER_CANDIDATE_GROUP = "gnet-router"
REDIS1_ROUTER_CONSUMER = "router-1"
REDIS1_SIGNAL_DECISION_GROUP = "gnet-signal-server"
REDIS1_SIGNAL_CONSUMER = "signal-server-1"

# TCP CONFIGURATION - SIGNAL (Python -> TradeStation)
TCP_SIGNAL_HOST = "127.0.0.1"
TCP_SIGNAL_PORT = 9011
# -----------------------------------------------------------------
