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

Note: This compose file is untested so it probably won't just work but it should help you get started.

```yaml
services:
  chatbot:
    image: hirednoobs/contentbot:latest
    environment:
      CONFIG_PATH: /etc/contentbot/contentbot.conf
      SECRETS_PATH: /etc/contentbot/contentbot_secrets.conf
      RUNNING_ENVIRONMENT: DOCKER
      LOG_LEVEL: INFO
    volumes:
      - ./configs:/etc/contentbot
    command: chatbot
  worker:
    image: hirednoobs/contentbot:latest
    environment:
      CONFIG_PATH: /etc/contentbot/contentbot.conf
      SECRETS_PATH: /etc/contentbot/contentbot_secrets.conf
      RUNNING_ENVIRONMENT: DOCKER
      LOG_LEVEL: INFO
    volumes:
      - ./configs:/etc/contentbot
    command: worker
  redis:
    image: redis:latest
  rabbitmq:
    image: rabbitmq:latest
```

## Commands

### General commands

``help`` - Prints link to this section of the readme.

### Content commands

``add_channel`` - Add a single channel to the database. Additional args will become tags! Usage: ``add_channel CHANNEL tag_1 ... tag_N``.

``add_channels`` - Add channels to database. Usage: ``add_channels CHANNEL_NAME_1 ... CHANNEL_NAME_N``.

``add_tags`` - Add tags to an existing channel. Usage: ``add_tags CHANNEL_NAME TAG_1 ... TAG_N``.

``content`` - Finds new content from all channels or tagged channels. Usage: ``content`` or ``content TAG``.

``random`` - Get a video based on a search of a random string. Usage: `random` or `random 4` to set the search string to 4 characters.

``random_word`` - Get a video based on a search of a random word. Usage: ``random_word``.

``remove_channel`` - Alias for remove_channels.

``remove_channels`` - Remove channels from the database. Usage: ``remove_channels CHANNEL_NAME_1 ... CHANNEL_N``.

``remove_tags`` - Remove tags from an existing channel. Usage ``remove_tags CHANNEL_NAME TAG_1 ... TAG_N``.

### Blackjack commands

``bet`` - Place your wager before the round begins. Usage: ``bet AMOUNT``.

``hit`` - Take another card from the dealer. Usage: ``hit``.

``join`` - Join the current blackjack table. Usage: ``join``.

``split`` - Split your hand into two hands when dealt a pair. Usage: ``split``.

``double`` - Double your bet and receive exactly one more card. Usage: ``double``.

``stand`` - Keep your current hand and end your current hand. Usage: ``stand``.

``init_blackjack`` - Initialize the blackjack game. Usage: ``init_blackjack``.

``start_blackjack`` - Start a new blackjack round. Usage: ``start_blackjack``.

``stop_blackjack`` - Stop the current blackjack game. Usage: ``stop_blackjack``.
