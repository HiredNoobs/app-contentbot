# content-finder

## Overview

A chatbot for Cytube focusing on automatically tracking and adding new content from YouTube without requiring an API key.

The bot has two parts, functionally each one is a separate arg given to the ``contentbot`` package. There's ``chatbot`` and ``worker``.

``chatbot`` connects to a channel on a Cytube instance and responds to events. It's main function is to wait for the "content" command to be sent in chat, at which point it queues jobs for the ``worker`` to pick up. "Jobs" in this context are a YouTube channel and a timestamp, all content (there are limits to how far back it goes due to avoiding the API) from that channel after the timestamp is collected and added to a queue that the ``chatbot`` picks up and adds to the Cytube queue.

It's safe to leave the bot running 24/7; when alone in a channel (where alone means that either there are no other connected users or all other connected users aren't logged in) the bot will become leader and pause the current video at it's current timestamp.

Requirements:
    - A Cytube user with the moderator role (assuming the channel is using default permissions; otherwise make sure the user has access to the chat, adding items to the queue, and the ability to promote itself to leader)
    - Python 3 (>3.10)
    - RabbitMQ (used to pass jobs between the ``chatbot`` and the ``worker``.)
    - Redis (used as a basic "database" for channels)

A Docker image is available: <https://hub.docker.com/r/hirednoobs/contentbot>

## Usage

### Dev

```bash
$ python3 -m venv venv
$ source venv/bin/activate  # For Windows: .\venv\Scripts\activate
$ python3 -m pip install .[dev]

# Run tests:
$ python3 -m pytest --cov=contentbot tests
$ flake8 src/contentbot
$ mypy src/contentbot
```

### Prod

#### Configuration

The bot is expecting to find two config files, one for general configuration and one for secrets (user/pass for the various services.) These can be set with the following environment variables:

```bash
$ export CONFIG_PATH="/full/path/to/conf"
$ export SECRETS_PATH="/full/path/to/secrets"
```

##### Configuration files

Below are examples of the config and secret config files. Optional values can be removed entirely.

Config file example:

```yaml
cytube_url: https://cytu.be  # Instance base url
cytube_channel: channel_name

# Optionally provide a dictonary of words for the
# `random_word` command. 
dictonary_file: /full/path/to/dict_file.txt

db_host: redis
db_port: 6379
db_index: 0

# Optionally, certs if required
db_ca_cert: /etc/contentbot/tls/redis_ca.crt
db_cert: /etc/contentbot/tls/redis.crt
db_key: /etc/contentbot/tls/redis.key

rabbitmq_host: rabbitmq
rabbitmq_port: 5671

rabbitmq_job_queue: contentbot.channels
rabbitmq_result_queue: contentbot.content

# Optionally, certs if required
rabbitmq_ca_cert: /etc/contentbot/tls/rabbitmq_ca.crt
rabbitmq_cert: /etc/contentbot/tls/rabbitmq.crt
rabbitmq_key: /etc/contentbot/tls/rabbitmq.key
```

Secret config example:

```yaml
cytube_user: username
cytube_pass: "password!123"  # Quote any values with special chars

# Optionally, ACL user if required
db_user: username
db_pass: password123

rabbitmq_user: username
rabbitmq_pass: password123
```

#### Example docker compose file

TODO: Finish this example

Note: I don't use this compose file so it may or may not work...

```yaml
services:
  chatbot:
    image: hirednoobs/contentbot:latest
      environment:
        CONFIG_PATH: /etc/contentbot/contentbot.conf
        SECRETS_PATH: /etc/contentbot/contentbot_secrets.conf
  redis:
    ...
  rabbitmq:
    ...
```
