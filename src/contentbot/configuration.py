import logging
import os
from typing import Any, Dict

import yaml

logger: logging.Logger = logging.getLogger("contentbot")


class Configuration:
    def __init__(self, path: str, secrets_path: None | str = None):
        self._path = path
        self._secrets_path = secrets_path

    def read(self) -> None:
        with open(self._path) as file:
            config: Dict[str, Any] = yaml.safe_load(file)

        domain = os.getenv("DOMAIN", ".com")

        # Cytube
        self.cytube_url = config["cytube_url"]
        self.cytube_channel = config["cytube_channel"]

        # Database
        db_host = config["db_host"]
        self.db_host = f"{db_host}.{domain}"
        self.db_port = config["db_port"]
        self.db_index = config["db_index"]

        self.db_ca_cert = config["db_ca_cert"]
        self.db_cert = config["db_cert"]
        self.db_key = config["db_key"]

        # RabbitMQ
        rabbit_host = config["rabbitmq_host"]
        rabbit_port = config["rabbitmq_port"]

        self.rabbitmq_job_queue = config["rabbitmq_job_queue"]
        self.rabbitmq_result_queue = config["rabbitmq_result_queue"]

        self.rabbitmq_ca_cert = config["rabbitmq_ca_cert"]
        self.rabbitmq_cert = config["rabbitmq_cert"]
        self.rabbitmq_key = config["rabbitmq_key"]

        if self._secrets_path:
            with open(self._secrets_path) as file:
                secrets: Dict[str, Any] = yaml.safe_load(file)

            self.cytube_user = secrets["cytube_user"]
            self.cytube_pass = secrets["cytube_pass"]

            self.db_user = secrets["db_user"]
            self.db_pass = secrets["db_pass"]

            rabbitmq_user = secrets["rabbitmq_user"]
            rabbitmq_pass = secrets["rabbitmq_pass"]

        self.rabbitmq_url = f"amqps://{rabbitmq_user}:{rabbitmq_pass}@{rabbit_host}.{domain}:{rabbit_port}/"

    def to_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if not key.startswith("_")}
