from contentbot.chatbot.processors.async_event_processor import AsyncEventProcessor
from contentbot.chatbot.sio_data import SIOData


class FakeMessage:
    def __init__(self):
        self.nacked_with = None

    async def nack(self, requeue: bool = True):
        self.nacked_with = requeue


class FakeSocket:
    def __init__(self):
        self.data = SIOData()


async def test_handle_disconnect_requeues_pending_messages():
    sio = FakeSocket()
    msg_a, msg_b = FakeMessage(), FakeMessage()
    sio.data.add_pending("a", msg_a)
    sio.data.add_pending("b", msg_b)

    await AsyncEventProcessor(sio).handle_disconnect()

    assert msg_a.nacked_with is True
    assert msg_b.nacked_with is True
    assert sio.data.get_pending("a") is None
    assert sio.data.get_pending("b") is None
