import logging
import os
from operator import itemgetter

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
            channels = db.get_channels(tag)
            content = []
            for channel in channels:
                content.extend(content_finder.find_content(channel))

            content = sorted(content, key=itemgetter("datetime"))

            for c in content:
                channel_id = c["channel_id"]
                new_dt = str(c.pop("datetime"))
                db.add_to_stream("stream:jobs:results", c)

                # Having the update here will write to Redis for every
                # video from a given channel. This does keep Redis
                # accurate if the worker crashes half way through.
                db.update_datetime(channel_id, new_dt)

            db.ack_stream_message("stream:jobs:pending", msg_id)


if __name__ == "__main__":
    main()
