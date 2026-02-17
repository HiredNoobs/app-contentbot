import json
import string
from typing import Any, Dict, List

import pytest
import requests

from worker.random_finder import RandomFinder


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text: str = text


class FakeFile:
    def __init__(self, lines: List[str]) -> None:
        self._lines: List[str] = lines

    def read(self) -> str:
        return "\n".join(self._lines)

    def __enter__(self) -> "FakeFile":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, traceback: Any) -> None:
        pass


@pytest.fixture
def fake_video_data() -> Dict[str, Any]:
    return {
        "contents": {
            "twoColumnSearchResultsRenderer": {
                "primaryContents": {
                    "sectionListRenderer": {
                        "contents": [
                            {
                                "itemSectionRenderer": {
                                    "contents": [
                                        {"videoRenderer": {"videoId": "testid1"}},
                                        {"videoRenderer": {"videoId": "testid2"}},
                                    ]
                                }
                            }
                        ]
                    }
                }
            }
        }
    }


class TestRandomFinder:
    def test_rand_str(self) -> None:
        """
        Test the _rand_str helper to ensure it returns a string of the correct
        length and that every character is a lowercase letter or digit.
        """
        rf = RandomFinder()
        allowed_chars: str = string.ascii_lowercase + string.digits
        for size in [0, 5, 10]:
            result: str = rf._rand_str(size)
            assert isinstance(result, str), "Result should be a string."
            assert len(result) == size, f"Result should be of length {size}."
            for ch in result:
                assert ch in allowed_chars, f"Character {ch} is not allowed."

    def test_find_random_default(
        self, monkeypatch: pytest.MonkeyPatch, fake_video_data: Dict[str, Any]
    ) -> None:
        fake_text: str = "ytInitialData = " + json.dumps(fake_video_data) + ";</script>"

        def fake_get(url: str, timeout: int, cookies: None | Dict) -> FakeResponse:
            return FakeResponse(fake_text)

        monkeypatch.setattr(requests, "get", fake_get)
        rf = RandomFinder()
        size: int = 5
        video_id, query_str = rf.find_random(size=size, use_dict=False)

        assert video_id in [
            "testid1",
            "testid2",
        ], "Video ID should be one of the expected test IDs."
        assert isinstance(query_str, str), "Query string should be a string."
        assert len(query_str) == size, f"Query string should be of length {size}."

    def test_find_random_no_videos(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fake_data_no_videos: Dict[str, Any] = {
            "contents": {
                "twoColumnSearchResultsRenderer": {
                    "primaryContents": {
                        "sectionListRenderer": {
                            "contents": [{"itemSectionRenderer": {"contents": []}}]
                        }
                    }
                }
            }
        }

        fake_text: str = (
            "ytInitialData = " + json.dumps(fake_data_no_videos) + ";</script>"
        )

        def fake_get(url: str, timeout: int, cookies: None | Dict) -> FakeResponse:
            return FakeResponse(fake_text)

        monkeypatch.setattr(requests, "get", fake_get)
        rf = RandomFinder()
        video_id, query_str = rf.find_random(size=5, use_dict=False)

        assert video_id is None, "Video ID should be None when no videos are found."
        assert (
            query_str is None
        ), "Query string should be None when no videos are found."

    def test_find_random_with_use_dict(
        self, monkeypatch: pytest.MonkeyPatch, fake_video_data: Dict[str, Any]
    ) -> None:
        fake_file_lines: List[str] = ["dictword1", "dictword2", "dictword3"]

        def fake_open(
            filepath: str, mode: str = "r", *args: Any, **kwargs: Any
        ) -> FakeFile:
            return FakeFile(fake_file_lines)

        monkeypatch.setattr("builtins.open", fake_open)

        fake_text: str = "ytInitialData = " + json.dumps(fake_video_data) + ";</script>"

        def fake_get(url: str, timeout: int, cookies: None | Dict) -> FakeResponse:
            return FakeResponse(fake_text)

        monkeypatch.setattr(requests, "get", fake_get)
        rf = RandomFinder()
        video_id, query_str = rf.find_random(size=8, use_dict=True)
        assert (
            query_str in fake_file_lines
        ), "Query string should be one of the words from the fake file."
        assert video_id in [
            "testid1",
            "testid2",
        ], "Video ID should be an expected test ID."

    def test_find_random_negative_size(
        self, monkeypatch: pytest.MonkeyPatch, fake_video_data: Dict[str, Any]
    ) -> None:
        fake_text: str = "ytInitialData = " + json.dumps(fake_video_data) + ";</script>"

        def fake_get(url: str, timeout: int, cookies: None | Dict) -> FakeResponse:
            return FakeResponse(fake_text)

        monkeypatch.setattr(requests, "get", fake_get)
        rf = RandomFinder()
        video_id, query_str = rf.find_random(size=-5, use_dict=False)
        assert (
            query_str == ""
        ), "Query string should be empty when a negative size is provided."
        assert video_id in [
            "testid1",
            "testid2",
        ], "Video ID should be an expected test ID."
