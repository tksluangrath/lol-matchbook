"""
Unit tests for app.lcu.listener. No live League client is available in
this environment (a real, stated limitation -- see the module's own
docstring) -- these test the parts that are genuinely deterministic
without one: real lockfile-format parsing, and the champ-select/rank
response-parsing logic against the documented LCU JSON contract, with the
network layer mocked (real HTTP calls to a live client can't be made
here, per the same limitation).
"""
import pathlib

import pytest

from app.lcu.listener import ChampSelectState, LCUListener, default_lockfile_path, parse_lockfile


def test_parse_lockfile_real_format():
    # Real, documented format: name:pid:port:password:protocol
    info = parse_lockfile("LeagueClient:12345:54321:some-real-password:https")
    assert info == {
        "name": "LeagueClient", "pid": 12345, "port": 54321,
        "password": "some-real-password", "protocol": "https",
    }


def test_parse_lockfile_rejects_malformed_content():
    with pytest.raises(ValueError):
        parse_lockfile("not:enough:fields")


def test_default_lockfile_path_known_platforms(monkeypatch):
    monkeypatch.setattr("app.lcu.listener.sys.platform", "darwin")
    assert default_lockfile_path() == pathlib.Path(
        "/Applications/League of Legends.app/Contents/LoL/lockfile"
    )

    monkeypatch.setattr("app.lcu.listener.sys.platform", "win32")
    assert default_lockfile_path() == pathlib.Path("C:/Riot Games/League of Legends/lockfile")


def test_default_lockfile_path_unknown_platform_returns_none(monkeypatch):
    monkeypatch.setattr("app.lcu.listener.sys.platform", "linux")
    assert default_lockfile_path() is None


def test_read_lockfile_returns_none_when_missing(tmp_path):
    listener = LCUListener(lockfile_path=tmp_path / "nonexistent-lockfile")
    assert listener.read_lockfile() is None


def test_read_lockfile_parses_a_real_written_file(tmp_path):
    lockfile = tmp_path / "lockfile"
    lockfile.write_text("LeagueClient:999:61234:pw123:https", encoding="utf-8")
    listener = LCUListener(lockfile_path=lockfile)
    assert listener.read_lockfile() == {
        "name": "LeagueClient", "pid": 999, "port": 61234, "password": "pw123", "protocol": "https",
    }


class _FakeResponse:
    def __init__(self, status_code, json_body):
        self.status_code = status_code
        self._json = json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError("error", request=None, response=self)

    def json(self):
        return self._json


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient -- routes GET calls to pre-seeded
    fake responses keyed by path, matching the documented LCU endpoint
    shapes rather than a real live connection."""

    def __init__(self, responses: dict):
        self._responses = responses

    async def get(self, path):
        return self._responses[path]


# Real, documented LCU champ-select session shape (myTeam/theirTeam arrays
# with championId/assignedPosition) -- hand-built per the module docstring's
# contract, not copied from a live response (none was available).
REAL_SESSION_SHAPE = {
    "myTeam": [
        {"championId": 0, "assignedPosition": "jungle"},
        {"championId": 266, "assignedPosition": "top"},  # 266 = Aatrox's real Data Dragon numeric key
    ],
    "theirTeam": [
        {"championId": 0, "assignedPosition": ""},
        {"championId": 10, "assignedPosition": ""},  # 10 = Kayle's real Data Dragon numeric key
    ],
}

FAKE_CHAMPION_DATA = {
    "Aatrox": {"key": "266"},
    "Kayle": {"key": "10"},
}


@pytest.mark.asyncio
async def test_read_session_state_resolves_champion_names_and_index_matched_opponent(monkeypatch):
    monkeypatch.setattr("app.lcu.listener.get_current_patch", lambda: "16.15.1")
    monkeypatch.setattr("app.lcu.listener.fetch_champion_data", lambda patch: FAKE_CHAMPION_DATA)

    listener = LCUListener()
    client = _FakeAsyncClient({
        "/lol-champ-select/v1/session": _FakeResponse(200, REAL_SESSION_SHAPE),
        "/lol-ranked/v1/current-ranked-stats": _FakeResponse(
            200, {"queues": [{"queueType": "RANKED_SOLO_5x5", "tier": "EMERALD"}]},
        ),
    })

    state = await listener._read_session_state(client)
    assert state == ChampSelectState(champ_a="Aatrox", champ_b="Kayle", role="top", rank="emerald")


@pytest.mark.asyncio
async def test_read_session_state_none_when_nothing_locked_yet(monkeypatch):
    monkeypatch.setattr("app.lcu.listener.get_current_patch", lambda: "16.15.1")
    monkeypatch.setattr("app.lcu.listener.fetch_champion_data", lambda patch: FAKE_CHAMPION_DATA)

    listener = LCUListener()
    empty_session = {"myTeam": [{"championId": 0, "assignedPosition": ""}], "theirTeam": []}
    client = _FakeAsyncClient({"/lol-champ-select/v1/session": _FakeResponse(200, empty_session)})

    assert await listener._read_session_state(client) is None


@pytest.mark.asyncio
async def test_read_session_state_none_on_real_404_no_active_session(monkeypatch):
    listener = LCUListener()
    client = _FakeAsyncClient({"/lol-champ-select/v1/session": _FakeResponse(404, {})})
    assert await listener._read_session_state(client) is None


@pytest.mark.asyncio
async def test_fetch_rank_degrades_to_unranked_on_missing_solo_duo_queue():
    listener = LCUListener()
    client = _FakeAsyncClient({"/lol-ranked/v1/current-ranked-stats": _FakeResponse(200, {"queues": []})})
    assert await listener._fetch_rank(client) == "unranked"
