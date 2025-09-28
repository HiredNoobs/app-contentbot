import logging
import os

from worker.content_finder import ContentFinder
from worker.database_wrapper import DatabaseWrapper
from worker.exceptions import MissingEnvVar

logger = logging.getLogger(__name__)


def main() -> None:
    db_host = os.getenv("REDIS_HOST", "localhost")
    db_port = int(os.getenv("REDIS_PORT", 6379))

    if not db_host and not db_port:
        raise MissingEnvVar("One/some of the env variables are missing.")

    db = DatabaseWrapper(db_host, db_port)

    content_finder = ContentFinder()

    logger.info("Worker ready.")

    while True:
        resp = db.read_stream("stream:jobs:pending")
        if not resp:
            continue

        _, messages = resp[0]
        for msg_id, data in messages:
            tag = data["tag"]
            content = content_finder.find_content(tag=tag)

            for c in content:
                channel_id = c["channel_id"]
                new_dt = c["datetime"]
                db.add_to_stream("stream:jobs:results", c)
                db.update_datetime(channel_id, new_dt)

            db.ack_stream_message("stream:jobs:pending", msg_id)


if __name__ == "__main__":
    main()
