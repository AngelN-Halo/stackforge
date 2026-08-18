from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import redis


REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
QUEUE_NAME = "stackforge:jobs"


def process_job(job: dict) -> None:
    print(json.dumps({"event": "job_received", "job": job, "ts": datetime.now(timezone.utc).isoformat()}), flush=True)


def main() -> None:
    client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
    while True:
        item = client.blpop(QUEUE_NAME, timeout=5)
        if not item:
            time.sleep(1)
            continue
        _, raw = item
        process_job(json.loads(raw))


if __name__ == "__main__":
    main()
