# content-finder

## Overview

A chatbot for Cytube focusing on automatically tracking and adding new content from YouTube without requiring an API key.

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

TODO: Add a generic docker compose file.

Expected env vars:

```bash
CONFIG_PATH="/full/path/to/conf"
SECRETS_PATH="/full/path/to/secrets"
```

Config file example:

```yaml
cytube_url: https://cytu.be  # Instance base url
cytube_channel: channel_name

db_host: redis
db_port: 6379
db_index: 0

# Certs if required. The bot likely breaks if not provided
# regardless of whether they're needed currently...
# TODO: Review that.
db_ca_cert: /etc/contentbot/tls/redis_ca.crt
db_cert: /etc/contentbot/tls/redis.crt
db_key: /etc/contentbot/tls/redis.key

rabbitmq_host: rabbitmq
rabbitmq_port: 5671

rabbitmq_job_queue: contentbot.channels
rabbitmq_result_queue: contentbot.content

# Certs if required. The bot likely breaks if not provided
# regardless of whether they're needed currently...
# TODO: Review that.
rabbitmq_ca_cert: /etc/contentbot/tls/rabbitmq_ca.crt
rabbitmq_cert: /etc/contentbot/tls/rabbitmq.crt
rabbitmq_key: /etc/contentbot/tls/rabbitmq.key
```

Secret config example:

```yaml
cytube_user: username
cytube_pass: "password!123"  # Quote any values with special chars

# The bot is expecting users and ACLs to be setup
# regardless of whether they actually are.
# TODO: Review if that breaks if default user is enabled.
db_user: username
db_pass: password123

rabbitmq_user: username
rabbitmq_pass: password123
```
