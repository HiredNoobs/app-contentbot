import tempfile

import pytest
import yaml

from contentbot.configuration import Configuration


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

        # db_host unchanged
        assert cfg.db_host == "database"

        # RabbitMQ URL without domain
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
