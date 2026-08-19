"""
LCU (League Client Update) listener -- reads live champ-select state from the
League client's own local API. This is unofficial/undocumented by Riot (not
part of developer.riotgames.com), separate from the Riot public API pipeline
in app/data_pipeline/. See docs/adr-001-architecture.md Context section and
docs/system-design.md ("LCU listener" component).

Mechanism: the League client writes a `lockfile` to its install directory on
launch, containing `name:pid:port:password:protocol` (colon-separated).
Connects to `https://127.0.0.1:<port>` with Basic Auth (user "riot", the
lockfile password) and a self-signed cert the client generates fresh per
launch -- verification is deliberately disabled for this, not a security
bug: it's a loopback-only connection to a process this same machine's user
already launched, the same trust model every community LCU tool (Blitz,
Porofessor, op.gg) uses.

Real, honest limitation, not papered over: `/lol-champ-select/v1/session`'s
`theirTeam` entries frequently have an empty `assignedPosition` for the
enemy team in solo/duo queue (only `myTeam`'s own assigned position is
reliably populated) -- there is no fully-documented, guaranteed way to know
exactly which enemy pick is "my lane opponent" from this endpoint alone.
This module resolves it the same way community overlay tools do: matching
`myTeam`/`theirTeam` by list index, on the (usually true, not guaranteed)
assumption both teams' picks are ordered by the same role sequence. Verified
against the documented API contract only -- no live League client was
available in this environment to confirm real champ-select session JSON
shapes/behavior end to end.

Rank comes from a separate LCU endpoint entirely
(`/lol-ranked/v1/current-ranked-stats`), not champ-select session -- polled
alongside it, best-effort (missing/errored ranked data degrades to "unranked"
rather than failing the whole champ-select push).
"""
import asyncio
import pathlib
import sys
from typing import AsyncIterator, TypedDict

import httpx

from app.data_pipeline.data_dragon import fetch_champion_data, get_current_patch

CHAMP_SELECT_SESSION_PATH = "/lol-champ-select/v1/session"
RANKED_STATS_PATH = "/lol-ranked/v1/current-ranked-stats"
SOLO_DUO_QUEUE_TYPE = "RANKED_SOLO_5x5"

# Real, documented per-OS League install locations. Windows/macOS are the
# two Riot officially ships a client for; no Linux client exists to default
# a path for.
_DEFAULT_LOCKFILE_PATHS = {
    "win32": pathlib.Path("C:/Riot Games/League of Legends/lockfile"),
    "darwin": pathlib.Path("/Applications/League of Legends.app/Contents/LoL/lockfile"),
}


def default_lockfile_path() -> pathlib.Path | None:
    """None on a platform with no known default (e.g. Linux, no official
    client) -- caller must pass lockfile_path explicitly there, this isn't
    a hard failure."""
    return _DEFAULT_LOCKFILE_PATHS.get(sys.platform)


class LockfileInfo(TypedDict):
    name: str
    pid: int
    port: int
    password: str
    protocol: str


def parse_lockfile(content: str) -> LockfileInfo:
    """Parses the real, documented lockfile format:
    `name:pid:port:password:protocol`. Raises ValueError on malformed
    content rather than silently returning a partial/wrong result."""
    parts = content.strip().split(":")
    if len(parts) != 5:
        raise ValueError(f"malformed lockfile content: expected 5 colon-separated fields, got {len(parts)}")
    name, pid, port, password, protocol = parts
    return LockfileInfo(name=name, pid=int(pid), port=int(port), password=password, protocol=protocol)


class ChampSelectState(TypedDict):
    champ_a: str
    champ_b: str | None
    role: str
    rank: str


class LCUListener:
    def __init__(self, lockfile_path: pathlib.Path | None = None, poll_interval_s: float = 1.5):
        self.lockfile_path = lockfile_path or default_lockfile_path()
        self.poll_interval_s = poll_interval_s
        self._champion_by_id: dict[int, str] | None = None

    def read_lockfile(self) -> LockfileInfo | None:
        """None if the client isn't running (missing lockfile) -- a normal
        idle state per docs/system-design.md, not an error. Re-read on every
        call rather than cached: port/password rotate on every client
        launch, and this project established re-checking liveness rather
        than trusting a stale cached handle (same reasoning as
        db_migrate.py's start_pgserver, per docs/decisions/
        phase0-pgserver-spike.md)."""
        if self.lockfile_path is None or not self.lockfile_path.exists():
            return None
        return parse_lockfile(self.lockfile_path.read_text(encoding="utf-8"))

    async def _champion_name(self, champion_id: int) -> str | None:
        """Numeric LCU championId -> real Data Dragon champion key (e.g.
        266 -> "Aatrox"). Cached for this listener's lifetime -- the
        champion roster doesn't change mid-session."""
        if champion_id == 0:  # LCU's real "not picked yet" sentinel
            return None
        if self._champion_by_id is None:
            patch = get_current_patch()
            champs = fetch_champion_data(patch)
            self._champion_by_id = {int(data["key"]): key for key, data in champs.items()}
        return self._champion_by_id.get(champion_id)

    async def _fetch_rank(self, client: httpx.AsyncClient) -> str:
        """Best-effort: a missing/errored ranked-stats call degrades to
        "unranked" rather than dropping the whole champ-select push -- rank
        genuinely may not exist yet (a fresh account, or this queue type
        never played)."""
        try:
            resp = await client.get(RANKED_STATS_PATH)
            resp.raise_for_status()
            queues = resp.json().get("queues", [])
            solo_duo = next((q for q in queues if q.get("queueType") == SOLO_DUO_QUEUE_TYPE), None)
            tier = solo_duo.get("tier") if solo_duo else None
            return tier.lower() if tier else "unranked"
        except (httpx.HTTPError, ValueError, KeyError):
            return "unranked"

    async def _read_session_state(self, client: httpx.AsyncClient) -> ChampSelectState | None:
        resp = await client.get(CHAMP_SELECT_SESSION_PATH)
        if resp.status_code == 404:  # real LCU response when no champ-select session is active
            return None
        resp.raise_for_status()
        session = resp.json()

        my_team = session.get("myTeam", [])
        their_team = session.get("theirTeam", [])
        my_pick = next((p for p in my_team if p.get("championId")), None)
        if my_pick is None:
            return None  # I haven't locked/hovered anything yet -- nothing real to report

        champ_a = await self._champion_name(my_pick["championId"])
        if champ_a is None:
            return None

        # Index-match fallback for the enemy laner -- see module docstring's
        # real, documented limitation on theirTeam.assignedPosition.
        my_index = my_team.index(my_pick)
        champ_b = None
        if my_index < len(their_team):
            enemy_champion_id = their_team[my_index].get("championId", 0)
            champ_b = await self._champion_name(enemy_champion_id)

        role = my_pick.get("assignedPosition") or "unknown"
        rank = await self._fetch_rank(client)
        return ChampSelectState(champ_a=champ_a, champ_b=champ_b, role=role, rank=rank)

    async def poll_session(self) -> AsyncIterator[ChampSelectState | None]:
        """Polls at self.poll_interval_s and yields the current state on
        every tick -- None whenever the client isn't running, no lockfile
        exists, or no active pick exists yet (caller falls back to manual
        entry in all three cases, they're not distinguished downstream).
        Runs until cancelled (e.g. the frontend's WebSocket disconnects) --
        callers own their own asyncio.sleep loop around this generator, this
        method does not loop internally beyond re-reading the lockfile and
        emitting one value per real poll tick, per this project's async-
        generator convention (app.llm.serve.stream_tokens)."""
        while True:
            lock = self.read_lockfile()
            if lock is None:
                yield None
            else:
                async with httpx.AsyncClient(
                    base_url=f"https://127.0.0.1:{lock['port']}",
                    auth=("riot", lock["password"]),
                    verify=False,  # self-signed cert -- see module docstring's trust-model note
                    timeout=5.0,
                ) as client:
                    try:
                        yield await self._read_session_state(client)
                    except httpx.HTTPError:
                        yield None  # client mid-restart / transient -- normal degraded state, not fatal
            await asyncio.sleep(self.poll_interval_s)
