import os
from enum import Enum


class Commands(Enum):
    COMMAND_SYMBOL = os.getenv("COMMAND_SYMBOL", "!")

    GENERAL_COMMANDS = {"help": "Prints out commands."}

    CONTENT_COMMANDS = {
        "add_channel": "Add a single channel to the database. Additional args will become tags! Usage: `add_channel CHANNEL tag_1 ... tag_N`.",
        "add_channels": "Add channels to database. Usage: `add_channels CHANNEL_NAME_1 ... CHANNEL_NAME_N`.",
        "add_tags": "Add tags to an existing channel. Usage: `add_tags CHANNEL_NAME TAG_1 ... TAG_N`.",
        "content": "Finds new content from all channels or tagged channels. Usage: `content` or `content TAG`.",
        "current": "Gets the description of the current video.",
        "random": "Get a video based on a search of a random string. Usage: `random` or `random 4` to set the search string to 4 characters.",
        "random_word": "Get a video based on a search of a random word. Usage: `random_word`.",
        "remove_channel": "Alias for remove_channels.",
        "remove_channels": "Remove channels from the database. Usage: `remove_channels CHANNEL_NAME_1 ... CHANNEL_N`",
        "remove_tags": "Remove tags from an existing channel. Usage `remove_tags CHANNEL_NAME TAG_1 ... TAG_N`.",
    }

    BLACKJACK_COMMANDS = {
        "bet": "Place your wager before the round begins. Usage: `bet AMOUNT`.",
        "hit": "Take another card from the dealer. Usage: `hit`.",
        "join": "Join the current blackjack table. Usage: `join`.",
        "split": "Split your hand into two hands when dealt a pair. Usage: `split`.",
        "double": "Double your bet and receive exactly one more card. Usage: `double`.",
        "stand": "Keep your current hand and end your current hand. Usage: `stand`.",
        "init_blackjack": "Initialize the blackjack game system.",
        "start_blackjack": "Start a new blackjack round. Usage: `start_blackjack`.",
        "stop_blackjack": "Stop the current blackjack game. Usage: `stop_blackjack`.",
    }

    @classmethod
    def get_group(cls, name: str) -> dict:
        try:
            return cls[name.upper() + "_COMMANDS"].value
        except KeyError:
            raise ValueError(f"Unknown command group: {name}")
