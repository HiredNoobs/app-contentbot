import asyncio
import json
from datetime import datetime, timedelta

import pytest

from contentbot.chatbot.processors import async_content_processor
from contentbot.chatbot.processors.async_content_processor import AsyncContentProcessor
from contentbot.chatbot.sio_data import SIOData

PLAYLIST = [{"uid": 1, "temp": True, "media": {"id": "vid1", "type": "yt"}}]


class FakeMessage:
    def __init__(self, body):
        self.body = json.dumps(body).encode()
        self.acked = False
        self.nacked_with = None

    async def ack(self):
        self.acked = True

    async def nack(self, requeue: bool = True):
        self.nacked_with = requeue


class FakeSocket:
    def __init__(self):
        self.data = SIOData()
        self.data.add_or_update_user("mod", 2)
        self.chat = []
        self.playlist_requests = 0

    async def send_chat_msg(self, message):
        self.chat.append(message)

    async def request_playlist(self):
        self.playlist_requests += 1
        self.data.last_playlist_request = datetime.now()
        return PLAYLIST


class FakeDB:
    def __init__(self, channels):
        self._channels = channels

    async def get_channels(self, tag=""):
        return self._channels


class FakeJobQueue:
    def __init__(self):
        self.sent = []

    async def send(self, data):
        self.sent.append(data)

    def sort_jobs(self):
        return [job for job in self.sent if job["type"] == "sort_queue"]


@pytest.fixture
def sio():
    return FakeSocket()


@pytest.fixture
def job_queue():
    return FakeJobQueue()


@pytest.fixture
def processor(sio, job_queue):
    channels = [{"channel_id": "c1"}, {"channel_id": "c2"}]
    return AsyncContentProcessor(sio, FakeDB(channels), job_queue)


async def settle(processor):
    """Wait for the processor's background tasks."""
    await asyncio.gather(*processor._tasks)


async def run_content_command(processor, job_queue):
    await processor._handle_command("mod", "content", [])
    return job_queue.sent[0]["batch_id"]


async def job_done(processor, batch_id):
    msg = FakeMessage({"type": "job_done", "batch_id": batch_id})
    await processor.handle_job_done(msg)
    return msg


async def test_content_command_sends_jobs_in_one_batch(processor, job_queue):
    batch_id = await run_content_command(processor, job_queue)

    assert len(job_queue.sent) == 2
    assert all(job["batch_id"] == batch_id for job in job_queue.sent)


async def test_content_command_without_channels_starts_no_batch(sio, job_queue):
    processor = AsyncContentProcessor(sio, FakeDB([]), job_queue)
    await processor._handle_command("mod", "content", [])

    assert sio.data._content_batches == {}


async def test_sorts_after_last_job_done(processor, job_queue):
    batch_id = await run_content_command(processor, job_queue)

    msg = await job_done(processor, batch_id)
    await settle(processor)
    assert msg.acked
    assert job_queue.sort_jobs() == []

    await job_done(processor, batch_id)
    await settle(processor)

    assert len(job_queue.sort_jobs()) == 1


async def test_job_done_for_unknown_batch_ignored(processor, job_queue):
    # e.g. the chatbot restarted after sending the jobs.
    msg = await job_done(processor, "unknown")
    await settle(processor)

    assert msg.acked
    assert job_queue.sort_jobs() == []


async def test_sort_waits_for_playlist_cooldown(processor, sio, job_queue, monkeypatch):
    sleeps = []

    async def fake_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(async_content_processor.asyncio, "sleep", fake_sleep)
    sio.data.last_playlist_request = datetime.now() - timedelta(seconds=45)

    batch_id = await run_content_command(processor, job_queue)
    await job_done(processor, batch_id)
    await job_done(processor, batch_id)
    await settle(processor)

    assert any(14 < delay <= 15 for delay in sleeps)
    assert len(job_queue.sort_jobs()) == 1


async def test_sorts_waiting_for_cooldown_are_combined(processor, sio, job_queue):
    sio.data.last_playlist_request = datetime.now()

    assert processor._schedule_sort() > 0
    assert processor._schedule_sort() is None

    for task in processor._tasks:
        task.cancel()


async def test_manual_sort_during_cooldown_reports_delay(processor, sio):
    sio.data.last_playlist_request = datetime.now()

    await processor._handle_command("mod", "sort_queue", [])
    await processor._handle_command("mod", "sort_queue", [])

    assert sio.chat[0].startswith("The queue was fetched recently, sorting in")
    assert sio.chat[1] == "A queue sort is already scheduled."

    for task in processor._tasks:
        task.cancel()
