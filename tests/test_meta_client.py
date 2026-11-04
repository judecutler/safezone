import json

import pytest

from safezone.meta_client import BudgetExceeded, MetaClient, OfflineCacheMiss


class FakeTransport:
    def __init__(self):
        self.calls = 0

    def __call__(self, path, payload):
        self.calls += 1
        return {"echo": payload}


def make(tmp_path, transport, **kwargs):
    return MetaClient(cache_dir=tmp_path, transport=transport, **kwargs)


def test_identical_request_is_paid_for_once(tmp_path):
    transport = FakeTransport()
    client = make(tmp_path, transport, max_calls=5, offline=False)
    first = client.post("/responses", {"q": "bookshelf"})
    second = client.post("/responses", {"q": "bookshelf"})
    assert first == second
    assert transport.calls == 1


def test_distinct_requests_are_each_paid_for(tmp_path):
    transport = FakeTransport()
    client = make(tmp_path, transport, max_calls=5, offline=False)
    client.post("/responses", {"q": "bookshelf"})
    client.post("/responses", {"q": "window"})
    assert transport.calls == 2


def test_budget_blocks_before_any_network_call(tmp_path):
    transport = FakeTransport()
    client = make(tmp_path, transport, max_calls=2, offline=False)
    client.post("/responses", {"q": 1})
    client.post("/responses", {"q": 2})
    with pytest.raises(BudgetExceeded):
        client.post("/responses", {"q": 3})
    assert transport.calls == 2


def test_budget_survives_a_restart(tmp_path):
    first = make(tmp_path, FakeTransport(), max_calls=1, offline=False)
    first.post("/responses", {"q": 1})
    transport = FakeTransport()
    restarted = make(tmp_path, transport, max_calls=1, offline=False)
    with pytest.raises(BudgetExceeded):
        restarted.post("/responses", {"q": 2})
    assert transport.calls == 0


def test_offline_serves_cache_and_refuses_misses(tmp_path):
    online = make(tmp_path, FakeTransport(), max_calls=5, offline=False)
    online.post("/responses", {"q": "cached"})
    transport = FakeTransport()
    offline = make(tmp_path, transport, max_calls=5, offline=True)
    assert offline.post("/responses", {"q": "cached"}) == {"echo": {"q": "cached"}}
    with pytest.raises(OfflineCacheMiss):
        offline.post("/responses", {"q": "new"})
    assert transport.calls == 0


def test_cache_files_hold_only_responses(tmp_path):
    client = make(tmp_path, FakeTransport(), max_calls=5, offline=False)
    client.post("/responses", {"q": "x"})
    for path in tmp_path.glob("*.json"):
        assert set(json.loads(path.read_text())) == {"echo"}


def test_missing_key_costs_nothing(tmp_path, monkeypatch):
    from safezone import config

    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    monkeypatch.setattr(config, "ENV_PATH", tmp_path / "absent.env")
    monkeypatch.setattr(config, "load_env", lambda path=None: None)
    client = MetaClient(cache_dir=tmp_path, max_calls=5, offline=False)
    with pytest.raises(RuntimeError, match="MODEL_API_KEY"):
        client.post("/responses", {"q": 1})
    assert client.calls_used() == 0
