import os
from enum import Enum


class Commands(Enum):
    COMMAND_SYMBOLS = os.environ.get("COMMAND_SYMBOLS", "!").split(",")

    STANDARD_COMMANDS = {"help": "Prints out all commands."}

    ADMIN_COMMANDS = {
        "add": "Add channel to database, use channel username, ID, or URL.",
        "add_tags": "Add tags to an existing channel. Usage: `add_tags CHANNEL_ID TAG1 TAG2`",
        "content": "Finds new content from all channels or tagged channels. Usage: `content` or `content TAG`",
        "current": "",
        "christmas": "",
        "kill": "Kills the chat bot and the DB. Usage: `kill`",
        "random": "",
        "random_word": "",
        "remove": "",
        "remove_tags": "",
        "xmas": "",
    }

    BLACKJACK_COMMANDS = {
        "bet": "",
        "hit": "",
        "hold": "",
        "join": "",
        "split": "",
        "double": "",
        "stand": "",
    }

    BLACKJACK_ADMIN_COMMANDS = {
        "init_blackjack": "",
        "start_blackjack": "",
        "stop_blackjack": "",
    }
