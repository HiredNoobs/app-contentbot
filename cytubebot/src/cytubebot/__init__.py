import logging
import os

config_level = os.environ.get("LOG_LEVEL", "INFO").upper()

if not config_level.isnumeric():
    try:
        logging_level = getattr(logging, config_level)
    except AttributeError:
        logging_level = logging.INFO
else:
    logging_level = int(config_level)

logging.basicConfig(
    format="%(asctime)s, %(levelname)s [%(threadName)-8s] [%(filename)s:%(funcName)s:L%(lineno)d] %(message)s",
    handlers=[logging.StreamHandler()],
)
logging.getLogger(__name__).setLevel(logging_level)
logging.getLogger(__name__).addHandler(logging.NullHandler())
