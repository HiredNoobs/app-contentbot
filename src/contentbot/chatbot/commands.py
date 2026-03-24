import os
from enum import Enum


class Commands(Enum):
    COMMAND_SYMBOL = os.getenv("COMMAND_SYMBOL", "!")

    GENERAL_COMMANDS = ["help"]

    CONTENT_COMMANDS = [
        "add_channel",
        "add_channels",
        "add_tags",
        "content",
        "current",
        "random",
        "random_word",
        "remove_channel",
        "remove_channels",
        "remove_tags",
    ]

    BLACKJACK_COMMANDS = [
        "bet",
        "hit",
        "join",
        "split",
        "double",
        "stand",
        "init_blackjack",
        "start_blackjack",
        "stop_blackjack",
    ]
