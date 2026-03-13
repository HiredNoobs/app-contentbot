import logging
import os
from typing import Any, Dict

import yaml

from contentbot.exceptions import ConfigurationError

logger: logging.Logger = logging.getLogger("contentbot")


class Configuration:
    def __init__(self, path: str, secrets_path: str):
        self._path = path
        self._secrets_path = secrets_path

        self._domain = os.getenv("DOMAIN", None)

    def read(self) -> None:
        if not self._path or not self._secrets_path:
            raise ConfigurationError("Config file or secret config file not set.")

        self._read_conf()
        self._read_secrets_conf()

    def _read_conf(self) -> None:
        with open(self._path) as file:
            config: Dict[str, Any] = yaml.safe_load(file)

        self.dictonary_file = config.get("dictonary_file")

        # Cytube
        self.cytube_url = config["cytube_url"]
        self.cytube_channel = config["cytube_channel"]

        # Database
        db_host = config["db_host"]
        self.db_host = f"{db_host}.{self._domain}" if self._domain else db_host
        self.db_port = config["db_port"]
        self.db_index = config["db_index"]

        self.db_ca_cert = config.get("db_ca_cert")
        self.db_cert = config.get("db_cert")
        self.db_key = config.get("db_key")

        # RabbitMQ
        self._rabbit_host = config["rabbitmq_host"]
        self._rabbit_port = config["rabbitmq_port"]

        self.rabbitmq_job_queue = config["rabbitmq_job_queue"]
        self.rabbitmq_result_queue = config["rabbitmq_result_queue"]

        self.rabbitmq_ca_cert = config.get("rabbitmq_ca_cert")
        self.rabbitmq_cert = config.get("rabbitmq_cert")
        self.rabbitmq_key = config.get("rabbitmq_key")

    def _read_secrets_conf(self) -> None:
        with open(self._secrets_path) as file:
            secrets: Dict[str, Any] = yaml.safe_load(file)

        # Cytube
        self.cytube_user = secrets["cytube_user"]
        self.cytube_pass = secrets["cytube_pass"]

        # Database
        self.db_user = secrets.get("db_user")
        self.db_pass = secrets.get("db_pass")

        # RabbitMQ
        rabbitmq_user = secrets.get("rabbitmq_user", "guest")
        rabbitmq_pass = secrets.get("rabbitmq_pass", "guest")

        if self._domain:
            self.rabbitmq_url = (
                f"amqps://{rabbitmq_user}:{rabbitmq_pass}@{self._rabbit_host}.{self._domain}:{self._rabbit_port}/"
            )
        else:
            self.rabbitmq_url = f"amqps://{rabbitmq_user}:{rabbitmq_pass}@{self._rabbit_host}:{self._rabbit_port}/"

    def to_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if not key.startswith("_")}
