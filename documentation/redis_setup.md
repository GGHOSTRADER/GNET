# Redis Services Documentation
> **What:** How Redis is set up and run on this machine — Docker commands, port config, and original Linux/systemd reference.

## Objective

Transport data between scripts locally using RAM memory.

## Technology Stack

- `redis`
- Docker (Windows)
- Previously: Ubuntu + systemd (Linux)

## Structure

1. Build Redis server by binding it to a host and port
2. Create a stream channel
3. Producer pushes data
4. Consumer pulls data

---

## Servers

| Server | Host | Port |
|---|---|---|
| Redis 1 | `127.0.0.1` | `6381` |
| Redis 2 | `127.0.0.1` | `6380` |

> **Note:** Redis 2 is planned but not yet configured. Only Redis 1 is active.

---

## Kernel TCP Receive Buffer

`tcp_to_redis_ticks.py` sets `SO_RCVBUF = 1MB` on the port 9010 listening socket:

```python
s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024 * 1024)
```

**Why:** The tick pipeline receives 100–400 ticks/s at the open. During fast markets, TradeStation can burst 50+ ticks in a single millisecond. The kernel buffers incoming bytes between `recv()` calls — if the buffer fills up, the OS starts dropping data silently.

| | Default (Windows) | After change |
|---|---|---|
| Buffer size | ~64 KB | 1 MB |
| Backlog at 400 ticks/s × 50 bytes | ~3 seconds | ~50 seconds |

Zero CPU cost — purely RAM reserved in the kernel. The actual `recv()` loop and Redis `xadd` path are unchanged.

---

## Streams on Redis 1

All active streams live on Redis 1 (`127.0.0.1:6381`).

| Stream | Producer | Consumer(s) | maxlen | Frequency |
|---|---|---|---|---|
| `validated_bar` | `tcp_to_redis_connection.py` | `feat_eng_1.py`, `transformer_features.py` | 1,000 | 1 per bar close |
| `tick_data_raw` | `tcp_to_redis_ticks.py` | `tick_validator.py` | 50,000 | every tick |
| `tick_data_validated` | `tick_validator.py` | `volume_profile.py` | 50,000 | every tick |
| `features_transformer` | `transformer_features.py` | `consolidator.py` | 1,000 | 1 per bar close |
| `features_volume_profile` | `volume_profile.py` | `consolidator.py` | 50,000 | 1 per bar (1s before close) |

**maxlen policy:**
- Tick streams (`tick_data_raw`, `tick_data_validated`) → **50,000** entries: high-frequency, need a large buffer.
- Bar streams (`validated_bar`, `features_transformer`) → **1,000** entries: 1 per bar close, low-frequency, small buffer is enough.
- `features_volume_profile` is now bar-frequency (snapshot gated by `tick.time_s % snapshot_interval_s == snapshot_interval_s - 1`) but keeps the larger **50,000** maxlen inherited from its tick-frequency origin — oversized but harmless.
- All `xadd` calls use `approximate=True` so Redis trims lazily without blocking the write path.

---

## Running on Windows (Docker)

```bash
# First time
docker run -d --name redis1 -p 6381:6379 redis

# After first run
docker start redis1

# Stop
docker stop redis1

# Check status
docker ps
```

---

## Original Linux / systemd Setup (reference)

Both servers were managed by systemd — started automatically on boot, restarted on crash.

### systemd Service Files
```
/etc/systemd/system/redis-server1.service
/etc/systemd/system/redis-server2.service
```

### Redis Config Files
```
/etc/redis/redis1/redis.conf
/etc/redis/redis2/redis.conf
```

### Runtime Files (created at service start)
```
/var/run/redis/redis-server1.pid
/var/run/redis/redis-server2.pid
```

### Log Files
```
/var/log/redis/redis1/redis.log
/var/log/redis/redis2/redis.log
```

### Data Persistence Files
```
/var/lib/redis/redis1/
/var/lib/redis/redis2/
```

### Useful Commands

```bash
# Check service status
systemctl status redis-server1

# Check all config locations at once
sudo egrep -n '^(port|bind|daemonize|pidfile|logfile|dir|appendonly|appendfilename|dbfilename)' /etc/redis/redis1/redis.conf
sudo egrep -n '^(port|bind|daemonize|pidfile|logfile|dir|appendonly|appendfilename|dbfilename)' /etc/redis/redis2/redis.conf
```

---

## Potential Improvements

### Unix Domain Socket (Linux only)

On Linux without Docker, Redis can be configured to accept connections over a Unix socket instead of TCP. This bypasses the TCP/IP stack entirely — no headers, no checksums, no port state machine — cutting per-`xadd` latency roughly in half (~25µs vs ~50µs).

**Why it matters on the tick path:** at 400 ticks/s the tick pipeline does 400 `xadd` calls per second. TCP loopback costs ~20ms/s of wall clock time; UDS cuts that to ~10ms/s. Not a bottleneck at current volumes, but a free win on Linux.

**How to enable (Linux native Redis, no Docker):**

1. Add to `redis.conf`:
```
unixsocket /tmp/redis1.sock
unixsocketperm 777
```

2. Change the redis-py connection in `netwo_files/redis_tool.py`:
```python
# instead of redis.Redis(host=host, port=port)
redis.Redis(unix_socket_path="/tmp/redis1.sock")
```

**Why not now:** Redis runs inside a Docker container on Windows. The socket file lives inside the Linux VM (WSL2/Hyper-V) and cannot be directly accessed from the Windows host. Move to Linux native Redis and this becomes a 3-line change.

---

### Tick Batching Before Redis Write

Currently `tick_validator.py` does one `xadd` per tick — 400 GIL lock/unlock cycles per second on the open. An alternative is to accumulate a small batch of validated ticks in a Python list and flush them to Redis in a single **pipeline** call:

```python
# instead of one xadd per tick:
pipe = r.pipeline(transaction=False)
for tick in validated_batch:
    pipe.xadd(REDIS1_TICK_VALIDATED_STREAM, tick_to_redis_fields(tick), maxlen=50_000, approximate=True)
pipe.execute()  # one round trip, one GIL lock for the whole batch
```

**Trade-off:** batching introduces a small latency — ticks are held in memory until the batch is full or a timeout fires. For a 10-tick batch at 400 ticks/s, the extra delay is ~25ms. Acceptable for volume profile (stateful, doesn't care about per-tick freshness) but would matter for any consumer that needs tick-level real-time response.

**When to apply:** if GIL contention in the validator becomes measurable — i.e. the validator falls behind the raw stream during fast markets. At current volumes (400 ticks/s) it is not necessary.

---

## Quick Command Reference

| Command | Description |
|---|---|
| `cat file` | Show entire file |
| `grep something file` | Show lines containing "something" |
| `grep -E` / `egrep` | grep with more powerful patterns |
