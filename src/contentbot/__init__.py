import logging
import os
import sys
from typing import List

logger: logging.Logger = logging.getLogger("contentbot")

environment: str = os.getenv("RUNNING_ENVIRONMENT", "UNKNOWN").upper()

std_out: logging.Handler = logging.StreamHandler(sys.stdout)
log_file: logging.Handler = logging.FileHandler("contentbot.log")

handlers: List[logging.Handler] = [std_out, log_file]

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
