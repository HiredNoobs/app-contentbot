# content-finder

## Overview
A chatbot for Cytube focusing on automatically tracking and adding new content from YouTube without requiring an API key. Also includes various other features such as chat based blackjack.

## Requirements
Docker & docker compose v2, Windows users may need to manually create a volume for Redis. Note: I have not tested this on Windows.

Or Python 3.10+ and a Redis instance. If not using Docker then install with ``python -m pip install -e .`` or ``python -m pip install -e ".[dev]"``.

## Usage
Simply run ``docker compose up -d``. The compose file is expecting a number of environment variables to either be in the environmnet or in a ``.env`` file at the top level directory.

env vars (some may have preset defaults in either the compose file or in the code or both):
```bash
CYTUBE_URL_CHANNEL_NAME="CHANNEL_NAME"
CYTUBE_USERNAME="BOTNAME"
CYTUBE_PASSWORD="PASSWORD"

REDIS_HOST="redis"
REDIS_PORT=6379

VALID_TAGS="tag1 tag2 tag3"

BASE_RETRY_BACKOFF=4
RETRY_BACKOFF_FACTOR=2
MAX_RETRY_BACKOFF=20
RETRY_COOLOFF_PERIOD=10
```

## Redis
The ``redis`` directory contains a helper script (``redis_client.py``) for pushing and pulling data manually into Redis - mainly for backing up and seeding new data if messing with the volume.

Usage:

```bash
# FILENAME must include a path to the file if not in your current directory
python3 redis_client.py push FILENAME

# PATH is optional, by default the file will be dropped into redis/ next to the script
python3 redis_client.py pull PATH
```
