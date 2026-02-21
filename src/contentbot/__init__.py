import logging
import os
import sys
from typing import List

logger: logging.Logger = logging.getLogger("contentbot")

environment: str = os.getenv("RUNNING_ENVIRONMENT", "UNKNOWN").upper()

stderr: logging.Handler = logging.StreamHandler(sys.stderr)

handlers: List[logging.Handler] = [stderr]

if environment == "DOCKER":
    docker_log: logging.Handler = logging.StreamHandler(open("/proc/1/fd/1", "w"))
    handlers.append(docker_log)

log_level: str = os.getenv("LOG_LEVEL", "DEBUG").upper()
logger.setLevel(log_level)

formatter = logging.Formatter("%(asctime)s %(levelname)s [%(filename)s:%(funcName)s():L%(lineno)d] %(message)s")

for handler in handlers:
    handler.setLevel(log_level)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
