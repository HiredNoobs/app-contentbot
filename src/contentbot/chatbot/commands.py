import os
from enum import Enum


class Commands(Enum):
    COMMAND_SYMBOL = os.environ.get("COMMAND_SYMBOL", "!")

    STANDARD_COMMANDS = {
        "help": "Prints out all commands.",
        "add": "Add channel to database, use channel username, ID, or URL.",
        "add_tags": "Add tags to an existing channel. Usage: `add_tags CHANNEL_ID TAG1 TAG2`",
        "content": "Finds new content from all channels or tagged channels. Usage: `content` or `content TAG`",
        "current": "",
        "random": "",
        "random_word": "",
        "remove": "",
        "remove_tags": "",
    }

    BLACKJACK_COMMANDS = {
        "bet": "",
        "hit": "",
        "join": "",
        "split": "",
        "double": "",
        "stand": "",
        "init_blackjack": "",
        "start_blackjack": "",
        "stop_blackjack": "",
    }
