"""Offline test for OpenRouterClient's proactive rate-limit throttling.
Mocks the clock so it verifies the timing logic without actually sleeping
or touching the network."""

import time

import pytest

from umlregen.perception.openrouter import OpenRouterClient


def _client(requests_per_minute: float = 20.0) -> OpenRouterClient:
    return OpenRouterClient(
        model_id="test/model:free",
        api_key="fake-key-for-offline-test",
        requests_per_minute=requests_per_minute,
    )


def test_first_call_never_sleeps(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", sleep_calls.append)
    monkeypatch.setattr(time, "monotonic", lambda: 1000.0)

    client._throttle()

    assert sleep_calls == []


def test_throttle_sleeps_for_remaining_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(requests_per_minute=20.0)  # 3s minimum gap
    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", sleep_calls.append)

    clock = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    client._throttle()  # first call: no prior request, no sleep
    clock["now"] = 1001.0  # only 1s elapsed; 3s minimum required
    client._throttle()

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(2.0)


def test_no_sleep_once_enough_time_has_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(requests_per_minute=20.0)
    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", sleep_calls.append)

    clock = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    client._throttle()
    clock["now"] = 1005.0  # 5s elapsed, already past the 3s minimum
    client._throttle()

    assert sleep_calls == []


def test_higher_requests_per_minute_shortens_the_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(requests_per_minute=60.0)  # 1s minimum gap
    sleep_calls: list[float] = []
    monkeypatch.setattr(time, "sleep", sleep_calls.append)

    clock = {"now": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["now"])

    client._throttle()
    clock["now"] = 1000.5
    client._throttle()

    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(0.5)
