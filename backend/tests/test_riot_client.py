import httpx
import pytest

from app.integrations.riot.client import RiotClient
from app.integrations.riot.errors import RiotAuthError, RiotNotConfigured, RiotNotFound, RiotRateLimited, RiotUnavailable
from app.integrations.riot.limiter import RateLimiter


def client(handler, **kw):
    kw.setdefault("limiter", RateLimiter(max_wait=0.1))
    return RiotClient("test-key", transport=httpx.MockTransport(handler), sleep=lambda s: None, **kw)


def test_no_key_means_not_configured():
    with pytest.raises(RiotNotConfigured):
        RiotClient("")


def test_routing_and_key_header():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"puuid": "p", "gameName": "A", "tagLine": "B"})

    c = client(handler)
    c.account_by_riot_id("EUW1", "Some Name", "EUW")
    c.top_mastery("NA1", "p")
    c.league_entries("EUW1", "p")
    assert seen[0].url.host == "europe.api.riotgames.com"
    assert seen[0].url.raw_path.endswith(b"/by-riot-id/Some%20Name/EUW")
    assert seen[0].headers["X-Riot-Token"] == "test-key"
    assert seen[1].url.host == "na1.api.riotgames.com"
    assert seen[2].url.host == "euw1.api.riotgames.com"             # rank is per platform, not per cluster
    assert seen[2].url.path == "/lol/league/v4/entries/by-puuid/p"


@pytest.mark.parametrize("status,error", [(404, RiotNotFound), (401, RiotAuthError), (403, RiotAuthError),
                                          (500, RiotUnavailable), (503, RiotUnavailable)])
def test_error_mapping(status, error):
    with pytest.raises(error):
        client(lambda r: httpx.Response(status)).account_by_riot_id("NA1", "a", "b")


def test_unknown_region_is_rejected_before_any_request():
    called = []
    with pytest.raises(RiotNotFound):
        client(lambda r: called.append(r) or httpx.Response(200, json={})).account_by_riot_id("MARS1", "a", "b")
    assert called == []


def test_short_429_is_retried_once():
    responses = iter([httpx.Response(429, headers={"Retry-After": "1"}), httpx.Response(200, json={"ok": True})])
    assert client(lambda r: next(responses)).match("NA1", "NA1_1") == {"ok": True}


def test_long_or_repeated_429_is_reported():
    with pytest.raises(RiotRateLimited):
        client(lambda r: httpx.Response(429, headers={"Retry-After": "60"})).match("NA1", "NA1_1")
    with pytest.raises(RiotRateLimited):
        client(lambda r: httpx.Response(429, headers={"Retry-After": "1"})).match("NA1", "NA1_1")


def test_network_failure_is_reported():
    def boom(request):
        raise httpx.ConnectError("down")

    with pytest.raises(RiotUnavailable):
        client(boom).match("NA1", "NA1_1")


class FakeTime:
    def __init__(self):
        self.now = 0.0
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def test_limiter_spaces_out_bursts_to_20_per_second():
    t = FakeTime()
    limiter = RateLimiter(max_wait=10, clock=t.clock, sleep=t.sleep)
    for _ in range(20):
        limiter.acquire()
    assert t.slept == []
    limiter.acquire()                 # the 21st request within a second has to wait
    assert t.slept and t.slept[0] == pytest.approx(1.0)


def test_limiter_fails_fast_instead_of_waiting_for_the_two_minute_window():
    t = FakeTime()
    limiter = RateLimiter(max_wait=8, clock=t.clock, sleep=t.sleep)
    for _ in range(100):
        limiter.acquire()
        t.now += 0.1                  # 10 per second: within the per-second limit
    with pytest.raises(RiotRateLimited, match="try again in about"):
        limiter.acquire()
