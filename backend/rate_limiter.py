import redis
import time
from fastapi import Request, HTTPException

r = redis.Redis(host="redis", port=6379, db=0, decode_responses=True)

RATE_LIMIT = 10
WINDOW = 60  # seconds

async def rate_limiter(request: Request):
    ip = request.client.host
    key = f"rate_limit:{ip}"

    count = r.get(key)

    if count is None:
        r.set(key, 1, ex=WINDOW)
    elif int(count) < RATE_LIMIT:
        r.incr(key)
    else:
        raise HTTPException(status_code=429, detail="Too many requests")