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
        """
        Reads the config file(s) supplied to the class on initialisation
        and creates attributes for the known options.
        """
        with open(self._path) as file:
            config: Dict[str, Any] = yaml.safe_load(file)

        domain = os.getenv("DOMAIN", ".com")

        self.cytube_url = config["cytube_url"]
        self.cytube_channel = config["cytube_channel"]

        db_host = config["db_host"]
        self.db_host = f"{db_host}.{domain}"
        self.db_port = config["db_port"]
        self.db_index = config["db_index"]
        self.db_user = config["db_user"]

        self.db_ca_cert = config["db_ca_cert"]
        self.db_cert = config["db_cert"]
        self.db_key = config["db_key"]

        kafka_port = config["kafka_port"]
        kafka_bootstrap_servers = config["kafka_bootstrap_servers"].split(",")
        self.kafka_bootstrap_servers = [f"{server}.{domain}:{kafka_port}" for server in kafka_bootstrap_servers]

        self.kafka_content_topic = config["kafka_content_topic"]
        self.kafka_job_topic = config["kafka_job_topic"]
        self.kafka_consumer_group = config["kafka_consumer_group"]

        self.kafka_ca_cert = config["kafka_ca_cert"]
        self.kafka_cert = config["kafka_cert"]
        self.kafka_key = config["kafka_key"]

        if self._secrets_path:
            with open(self._secrets_path) as file:
                secrets: Dict[str, Any] = yaml.safe_load(file)

            self.cytube_user = secrets["cytube_user"]
            self.cytube_pass = secrets["cytube_pass"]

            self.db_pass = config["db_pass"]

    def to_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items() if not key.startswith("_")}
