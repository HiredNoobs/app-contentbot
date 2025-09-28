import logging
import os
import re
from typing import List

from bs4 import BeautifulSoup as bs

from cytubebot.exceptions import InvalidTagError
from cytubebot.src.cytubebot.commands import Commands
from cytubebot.src.cytubebot.database_wrapper import DatabaseWrapper
from cytubebot.src.cytubebot.socket_wrapper import SocketWrapper
from cytubebot.utils import query_endpoint

VALID_TAGS: List = os.environ.get("VALID_TAGS", "").split()
logger = logging.getLogger(__name__)


# TODO:
# The separate functions have been merged back into here
# making the class a little big. They should be split out
# again but rather than splitting into functions they should
# move to classes that actually make sense i.e. some of the
# random logic can move out to RandomFinder() etc.
class ChatProcessor:
    def __init__(self) -> None:
        self._sio = SocketWrapper("", "")
        self._db = DatabaseWrapper("", 0)

    def process_chat_command(self, command, args, allow_force=False) -> None:
        if self._sio.data.lock and not (allow_force and args and args[0] == "--force"):
            self._sio.send_chat_msg("Already busy, please wait...")
            return

        self._sio.data.lock = True
        try:
            self._process_command(command, args)
        except Exception as err:
            logger.exception(f"Error while processing command {command}: {err}")
            self._sio.send_chat_msg(f"Error processing command: {err}")
        finally:
            self._sio.data.lock = False

    def _process_command(self, command, args) -> None:
        match command:
            case "content":
                tag = args[0].upper() if args else None
                self._handle_content(tag)
            case "random" | "random_word":
                self._handle_random(command, args)
            case "current":
                self._handle_current()
            case "add":
                self._handle_add_user(args)
            case "remove":
                self._handle_remove_user(args)
            case "add_tags" | "remove_tags":
                self._handle_tags(command, args)
            case "christmas" | "xmas":
                self._handle_add_christmas_videos()
            case "help":
                self._handle_help()
            case "kill":
                self._handle_kill()
            case _:
                self._sio.send_chat_msg(f"Unknown command: {command}")

    def _handle_current(self) -> None:
        try:
            self._sio.emit("playerReady")
            self._sio.sleep(1)
            curr = self._sio.data.current_media

            if curr is None:
                raise ValueError("No video id found in current media")

            video_id = curr["id"]
            url = f"https://www.youtube.com/watch?v={video_id}"
            resp = query_endpoint(url)
            resp.raise_for_status()

            soup = bs(resp.text, "lxml")
            script = soup.find("script", string=re.compile("ytInitialPlayerResponse"))
            if script is None:
                raise ValueError("ytInitialPlayerResponse not found in page source.")

            match_obj = re.search('.*"description":{"simpleText":"(.*?)"', script.text)
            if match_obj:
                description = match_obj.group(1).replace("\\n", " ")
                curr["description"] = description
            else:
                curr["description"] = "Description not available"

            logger.info("Current media: %s", curr)
            self._sio.send_chat_msg(f"{curr}")
        except Exception as err:
            logger.exception(f"Error handling 'current' command: {err}")
            self._sio.send_chat_msg(f"Error retrieving current media: {err}")

    def _handle_tags(self, command: str, args: list) -> None:
        try:
            if command == "add_tags":
                self._add_tags(args)
            else:
                self._remove_tags(args)
        except IndexError:
            self._sio.send_chat_msg("Not enough args supplied for !add_tags.")
        except InvalidTagError:
            self._sio.send_chat_msg(f"One or more tags in {args[1:]} is invalid.")

    def _handle_help(self) -> None:
        """
        Provides help information by listing available commands.
        """
        msg = (
            f"Use any of {Commands.COMMAND_SYMBOLS.value} with: "
            f"{Commands.STANDARD_COMMANDS.value}, "
            f"{Commands.ADMIN_COMMANDS.value}, "
            f"{Commands.BLACKJACK_COMMANDS.value}, "
            f"{Commands.BLACKJACK_ADMIN_COMMANDS.value}"
        )
        self._sio.send_chat_msg(msg)

    def _handle_content(self, tag: str) -> None:
        self._sio.send_chat_msg("Requesting content.")
        data = {"tag": tag}
        self._db.add_to_stream("stream:jobs:pending", data)

    def _handle_random(self, command, args) -> None:
        rand_id = None

        if command == "random_word":
            rand_id, search_str = self._random_finder.find_random(use_dict=True)
        elif command == "random":
            try:
                size = int(args[0]) if args else 3
            except ValueError:
                size = 3

            rand_id, search_str = self._random_finder.find_random(size)

        if rand_id:
            self._sio.add_video_to_queue(rand_id)
            self._sio.send_chat_msg(f"Searched: {search_str}, added: {rand_id}")
        else:
            msg = "Found no random videos.. Try again. If giving arg over 5, try reducing."
            self._sio.send_chat_msg(msg)

    def _add_tags(self, args) -> None:
        channel_id = args[0]
        tags = args[1:]
        tags = [x.upper() for x in tags]
        if not all(tag in VALID_TAGS for tag in tags):
            raise InvalidTagError("Invalid tag supplied.")
        self._db.add_tags(channel_id, tags)

    def _remove_tags(self, args) -> None:
        channel_id = args[0]
        tags = args[1:]
        tags = [x.upper() for x in tags]
        if not all(tag in VALID_TAGS for tag in tags):
            raise InvalidTagError("Invalid tag supplied.")
        self._db.remove_tags(channel_id, tags)

    def _handle_add_user(self, args) -> None:
        if not args:
            return

        logger.info(f"{args=}")

        channel_name = "".join(args)
        channel_name = self._cleanse_yt_crap(channel_name)

        # Common request settings.
        cookies = {"CONSENT": "YES+1"}

        def fetch_data(url: str, pattern: str) -> str | None:
            try:
                resp = query_endpoint(url, cookies=cookies)
                soup = bs(resp.text, "lxml")
                script_tag = soup.find("script", string=re.compile("ytInitialData"))
                if script_tag:
                    match = re.search(pattern, script_tag.text)
                    if match:
                        return match.group(1)
            except Exception:
                pass  # Silently ignore errors per URL attempt.
            return None

        channel_id: str | None = ""
        candidate_urls: List[str] = [
            f"https://www.youtube.com/@{channel_name}",
            f"https://www.youtube.com/c/{channel_name}",
        ]
        id_pattern = r'.*"browse_id","value":"(.*?)"'
        for url in candidate_urls:
            channel_id = fetch_data(url, id_pattern)
            if channel_id:
                msg = (
                    f"Found channel ID: {channel_id} for {channel_name}, adding to DB."
                )
                logger.info(msg)
                self._sio.send_chat_msg(msg)
                break

        # If no channel ID was found, try the fallback URL.
        if channel_id is None:
            logger.info(
                f"Failed to find channel_id for {channel_name}. Trying fallback URL."
            )

            channel_id = channel_name
            fallback_url = f"https://www.youtube.com/channel/{channel_id}"
            name_pattern = r'.*"channelMetadataRenderer":{"title":"(.*?)"'
            display_name = fetch_data(fallback_url, name_pattern)
            if display_name:
                channel_name = display_name
                msg = f"Found channel name: {channel_name} for {channel_id}, adding to DB."
                logger.info(msg)
                self._sio.send_chat_msg(msg)
            else:
                msg = f"Couldn't find channel: {fallback_url}"
                logger.error(msg)
                self._sio.send_chat_msg(msg)
                return

        self._db.add_channel(channel_id, channel_name)

    def _cleanse_yt_crap(self, channel_name_or_url: str) -> str:
        if "</a>" in channel_name_or_url:
            cleaned_name = re.search(r".*>(.*?)</a>", channel_name_or_url)
            if cleaned_name:
                channel_name_or_url = cleaned_name.group(1)

        channel_name_or_url = channel_name_or_url.strip()

        channel_name_or_url = channel_name_or_url.replace("/featured", "")
        channel_name_or_url = channel_name_or_url.replace("/videos", "")
        channel_name_or_url = channel_name_or_url.replace("/playlists", "")
        channel_name_or_url = channel_name_or_url.replace("/community", "")
        channel_name_or_url = channel_name_or_url.replace("/channels", "")
        channel_name_or_url = channel_name_or_url.replace("/about", "")

        if channel_name_or_url[-1:] == "/":
            channel_name_or_url = channel_name_or_url[:-1]

        if channel_name_or_url[0] == "@":
            channel_name_or_url = channel_name_or_url[1:]

        channel_name_or_url = channel_name_or_url.rsplit("/", 1)[-1]

        return channel_name_or_url

    def _handle_remove_user(self, args) -> None:
        if not args:
            return

        channel_name = "".join(args)
        channel_name = self._cleanse_yt_crap(channel_name)
        self._sio.send_chat_msg(f"Deleting {channel_name} from DB.")
        self._db.remove_channel(channel_name)

    def _handle_kill(self) -> None:
        try:
            self._sio.send_chat_msg("Bye bye!")
            self._sio.sleep(3)  # Allows time for the chat message to be sent
        except Exception as err:
            logger.exception(f"Error during kill command: {err}")
        finally:
            self._db.shutdown()
            self._sio.disconnect()
