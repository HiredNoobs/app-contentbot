import tempfile

import pytest
import yaml

from contentbot.configuration import Configuration
from contentbot.exceptions import ConfigurationError


@pytest.fixture
def config_file():
    """Temporary config YAML file."""
    data = {
        "cytube_url": "https://cytube.example",
        "cytube_channel": "mychannel",
        "db_host": "database",
        "db_port": 5432,
        "db_index": 1,
        "db_ca_cert": "/path/ca",
        "db_cert": "/path/cert",
        "db_key": "/path/key",
        "rabbitmq_host": "rabbit",
        "rabbitmq_port": 5671,
        "rabbitmq_job_queue": "jobs",
        "rabbitmq_result_queue": "results",
        "rabbitmq_ca_cert": "/path/rmq_ca",
        "rabbitmq_cert": "/path/rmq_cert",
        "rabbitmq_key": "/path/rmq_key",
    }

    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        yaml.dump(data, f)
        return f.name


@pytest.fixture
def secrets_file():
    """Temporary secrets YAML file."""
    data = {
        "cytube_user": "user123",
        "cytube_pass": "pass123",
        "db_user": "dbuser",
        "db_pass": "dbpass",
        "rabbitmq_user": "rmquser",
        "rabbitmq_pass": "rmqpass",
    }

    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        yaml.dump(data, f)
        return f.name


class TestConfiguration:
    def test_read_with_domain(self, config_file, secrets_file, monkeypatch):
        """If DOMAIN is set, db_host and rabbitmq_url should include it."""
        monkeypatch.setenv("DOMAIN", "example.net")

        cfg = Configuration(config_file, secrets_file)
        cfg.read()

        # Cytube
        assert cfg.cytube_url == "https://cytube.example"
        assert cfg.cytube_channel == "mychannel"

        # Database
        assert cfg.db_host == "database.example.net"
        assert cfg.db_port == 5432
        assert cfg.db_index == 1

        # Secrets
        assert cfg.cytube_user == "user123"
        assert cfg.cytube_pass == "pass123"
        assert cfg.db_user == "dbuser"
        assert cfg.db_pass == "dbpass"

        # RabbitMQ URL with domain
        assert cfg.rabbitmq_url == ("amqps://rmquser:rmqpass@rabbit.example.net:5671/")

    def test_read_without_domain(self, config_file, secrets_file, monkeypatch):
        """If DOMAIN is not set, db_host and rabbitmq_url should NOT include a domain."""
        monkeypatch.delenv("DOMAIN", raising=False)

        cfg = Configuration(config_file, secrets_file)
        cfg.read()

        assert cfg.db_host == "database"
        assert cfg.rabbitmq_url == ("amqps://rmquser:rmqpass@rabbit:5671/")

    def test_to_dict_excludes_private_fields(self, config_file, secrets_file):
        """to_dict() should return only public attributes."""
        cfg = Configuration(config_file, secrets_file)
        cfg.read()

        d = cfg.to_dict()

        # Private fields removed
        assert "_path" not in d
        assert "_secrets_path" not in d
        assert "_domain" not in d
        assert "_rabbit_host" not in d
        assert "_rabbit_port" not in d

        # Public fields present
        assert "cytube_url" in d
        assert "db_host" in d
        assert "rabbitmq_url" in d

    def test_rabbitmq_credentials_are_quoted(self, config_file, monkeypatch):
        """Special characters in RabbitMQ credentials should be percent-encoded in the URL."""
        monkeypatch.delenv("DOMAIN", raising=False)
        data = {
            "cytube_user": "user123",
            "cytube_pass": "pass123",
            "rabbitmq_user": "rmq@user",
            "rabbitmq_pass": "p@ss:w/rd#1",
        }
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            yaml.dump(data, f)

        cfg = Configuration(config_file, f.name)
        cfg.read()

        assert cfg.rabbitmq_url == "amqps://rmq%40user:p%40ss%3Aw%2Frd%231@rabbit:5671/"


def _config_with(config_file, **changes):
    """A copy of config_file's data with keys changed (None removes one)."""
    with open(config_file) as f:
        data = yaml.safe_load(f)
    for key, value in changes.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        yaml.dump(data, f)
        return f.name


class TestSentinelConfiguration:
    def test_no_sentinels_by_default(self, config_file, secrets_file):
        cfg = Configuration(config_file, secrets_file)
        cfg.read()

        assert cfg.db_sentinels == []
        assert cfg.db_sentinel_master == "redis"

    def test_sentinels_without_db_host(self, config_file, secrets_file, monkeypatch):
        """Sentinels replace db_host and db_port, which can then be left out."""
        monkeypatch.delenv("DOMAIN", raising=False)
        path = _config_with(
            config_file,
            db_host=None,
            db_port=None,
            db_sentinels=["redis-sentinel.redis.svc:26379", "10.0.0.1:26380"],
            db_sentinel_master="mymaster",
        )

        cfg = Configuration(path, secrets_file)
        cfg.read()

        assert cfg.db_host is None
        assert cfg.db_sentinels == [("redis-sentinel.redis.svc", 26379), ("10.0.0.1", 26380)]
        assert cfg.db_sentinel_master == "mymaster"

    def test_sentinels_with_domain(self, config_file, secrets_file, monkeypatch):
        monkeypatch.setenv("DOMAIN", "example.net")
        path = _config_with(config_file, db_sentinels=["sentinel:26379"])

        cfg = Configuration(path, secrets_file)
        cfg.read()

        assert cfg.db_sentinels == [("sentinel.example.net", 26379)]

    @pytest.mark.parametrize("sentinel", ["sentinel", "sentinel:", ":26379", "sentinel:port"])
    def test_sentinel_must_be_host_and_port(self, config_file, secrets_file, sentinel):
        path = _config_with(config_file, db_sentinels=[sentinel])

        with pytest.raises(ConfigurationError):
            Configuration(path, secrets_file).read()

    def test_needs_db_host_or_sentinels(self, config_file, secrets_file):
        path = _config_with(config_file, db_host=None)

        with pytest.raises(ConfigurationError):
            Configuration(path, secrets_file).read()
