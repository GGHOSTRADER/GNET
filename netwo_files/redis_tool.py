import redis


# REDIS -----------------------------------------------------------------------------------------------------
# Connect to Redis1
def get_redis_connection(REDIS_HOST, REDIS_PORT, STREAM_NAME, decode_respon=True):
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=decode_respon)
    if r.ping():
        print(
            f"1) [bar_server] Connected to Redis1 \n-Host:{REDIS_HOST}\n-Port:{REDIS_PORT}\n-Stream Name:{STREAM_NAME}\n"
        )
    else:
        print("1) [bar_server] Failed to connect to Redis1")

    return r
