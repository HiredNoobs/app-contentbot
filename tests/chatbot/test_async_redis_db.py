import pytest
from redis.asyncio.sentinel import SentinelConnectionPool, SentinelManagedSSLConnection

from contentbot.chatbot.db.async_redis_db import CONTENT_BATCH_TTL, VIDEO_PUBLISH_TIME_TTL, AsyncRedisDB


class FakePipeline:
    def __init__(self, redis):
        self._redis = redis
        self._commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def sadd(self, key, value):
        self._commands.append(("sadd", key, str(value)))
        return self

    def scard(self, key):
        self._commands.append(("scard", key))
        return self

    def expire(self, key, ttl):
        self._commands.append(("expire", key, ttl))
        return self

    async def execute(self):
        results = []
        for name, key, *args in self._commands:
            members = self._redis.sets.setdefault(key, set())
            if name == "sadd":
                results.append(0 if args[0] in members else 1)
                members.add(args[0])
            elif name == "scard":
                results.append(len(members))
            elif name == "expire":
                self._redis.ttls[key] = args[0]
                results.append(True)
        return results


class FakeRedis:
    def __init__(self):
        self.sets = {}
        self.values = {}
        self.ttls = {}

    def pipeline(self, transaction=True):
        return FakePipeline(self)

    async def set(self, key, value, ex=None):
        self.values[key] = str(value)
        self.ttls[key] = ex

    async def getex(self, key, ex=None):
        if key in self.values:
            self.ttls[key] = ex
        return self.values.get(key)

    async def expire(self, key, ttl):
        if key not in self.values:
            return False
        self.ttls[key] = ttl
        return True


@pytest.fixture
def db():
    db = AsyncRedisDB("localhost", 6379, 0, "user", "pass", None, None, None)
    db._redis = FakeRedis()
    return db


async def test_complete_batch_job_finishes_on_last_job(db):
    assert await db.complete_batch_job("b", 0, 3) is False
    assert await db.complete_batch_job("b", 2, 3) is False
    assert await db.complete_batch_job("b", 1, 3) is True


async def test_complete_batch_job_ignores_redelivered_jobs(db):
    assert await db.complete_batch_job("b", 0, 2) is False
    # A redelivered job doesn't count again, so it can't finish the batch early.
    assert await db.complete_batch_job("b", 0, 2) is False
    assert await db.complete_batch_job("b", 1, 2) is True
    # Nor report a finished batch a second time.
    assert await db.complete_batch_job("b", 1, 2) is False


async def test_complete_batch_job_single_job_batch(db):
    assert await db.complete_batch_job("b", 0, 1) is True


async def test_complete_batch_job_tracks_batches_separately(db):
    assert await db.complete_batch_job("a", 0, 2) is False
    assert await db.complete_batch_job("b", 0, 1) is True
    assert await db.complete_batch_job("a", 1, 2) is True


async def test_complete_batch_job_sets_expiry(db):
    await db.complete_batch_job("b", 0, 2)

    assert db._redis.ttls == {db._make_content_batch_key("b"): CONTENT_BATCH_TTL}


async def test_get_video_publish_time_refreshes_expiry(db):
    key = db._make_video_publish_time_key("v")
    await db.set_video_publish_time("v", "2026-01-01T00:00:00+00:00")
    db._redis.ttls[key] = 60

    assert await db.get_video_publish_time("v") == "2026-01-01T00:00:00+00:00"
    assert db._redis.ttls[key] == VIDEO_PUBLISH_TIME_TTL


async def test_get_video_publish_time_missing(db):
    assert await db.get_video_publish_time("v") is None
    assert db._redis.ttls == {}


async def test_is_random_video_refreshes_expiry(db):
    key = db._make_random_video_key("v")
    await db.mark_random_video("v")
    db._redis.ttls[key] = 60

    assert await db.is_random_video("v") is True
    assert db._redis.ttls[key] == VIDEO_PUBLISH_TIME_TTL


async def test_is_random_video_missing(db):
    assert await db.is_random_video("v") is False
    assert db._redis.ttls == {}


def test_direct_connection_without_sentinels():
    db = AsyncRedisDB("redis.example", 6379, 2, "user", "pass", "ca.crt", "tls.crt", "tls.key")

    kwargs = db._redis.connection_pool.connection_kwargs
    assert db._sentinel is None
    assert (kwargs["host"], kwargs["port"], kwargs["db"]) == ("redis.example", 6379, 2)
    assert (kwargs["username"], kwargs["password"]) == ("user", "pass")
    assert kwargs["ssl_ca_certs"] == "ca.crt"


def test_master_from_sentinels():
    """The sentinels and the master are both reached over TLS, with the same credentials."""
    db = AsyncRedisDB(
        None,
        None,
        2,
        "user",
        "pass",
        "ca.crt",
        "tls.crt",
        "tls.key",
        sentinels=[("sentinel.example", 26379)],
        sentinel_master="mymaster",
    )

    pool = db._redis.connection_pool
    assert isinstance(pool, SentinelConnectionPool)
    assert pool.service_name == "mymaster"
    assert pool.connection_class is SentinelManagedSSLConnection
    assert pool.connection_kwargs["db"] == 2
    assert (pool.connection_kwargs["username"], pool.connection_kwargs["password"]) == ("user", "pass")
    assert pool.connection_kwargs["ssl_certfile"] == "tls.crt"

    (sentinel,) = db._sentinel.sentinels
    kwargs = sentinel.connection_pool.connection_kwargs
    assert (kwargs["host"], kwargs["port"]) == ("sentinel.example", 26379)
    assert (kwargs["username"], kwargs["password"]) == ("user", "pass")
    assert sentinel.connection_pool.connection_class.__name__ == "SSLConnection"
    assert kwargs["ssl_ca_certs"] == "ca.crt"
