import logging
import os
import sys

logger: logging.Logger = logging.getLogger("contentbot")
environment: str = os.getenv("RUNNING_ENVIRONMENT", "UNKNOWN").upper()

if environment == "DOCKER":
    handler: logging.Handler = logging.StreamHandler(open("/proc/1/fd/1", "w"))
else:
    handler = logging.StreamHandler(sys.stderr)

log_level: str = os.getenv("LOG_LEVEL", "DEBUG").upper()
logger.setLevel(log_level)

formatter = logging.Formatter("%(asctime)s %(levelname)s [%(filename)s:%(funcName)s():L%(lineno)d] %(message)s")

handler.setLevel(log_level)
handler.setFormatter(formatter)
logger.addHandler(handler)
