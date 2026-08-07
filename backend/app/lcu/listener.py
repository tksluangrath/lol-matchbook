"""
LCU (League Client Update) listener -- reads live champ-select state from the
League client's own local API. This is unofficial/undocumented by Riot (not
part of developer.riotgames.com), separate from the Riot public API pipeline
in app/data_pipeline/. See docs/adr-001-architecture.md Context section and
docs/build-plan.md Phase 4.

Mechanism: the League client writes a `lockfile` to its install directory on
launch, containing a port and password for a local HTTPS server (self-signed
cert, Basic Auth as user "riot"). Poll:
    GET https://127.0.0.1:<port>/lol-champ-select/v1/session
"""
import pathlib


class LCUListener:
    def __init__(self, lockfile_path: pathlib.Path | None = None):
        # TODO(Phase 4): default lockfile_path per-OS. Typically under the
        # League of Legends install directory, e.g.
        # "C:/Riot Games/League of Legends/lockfile" on Windows.
        self.lockfile_path = lockfile_path

    def read_lockfile(self):
        """
        TODO: parse the lockfile (colon-separated fields: name, PID, port,
        password, protocol). Port and password rotate every client launch --
        re-read on every reconnect, never cache across restarts.

        TODO: missing lockfile == client not running. This is a normal idle
        state, not an error -- the UI should fall back to manual champion
        entry, not show an error. See docs/testing-strategy.md LCU resilience
        test cases.
        """
        if self.lockfile_path is None or not self.lockfile_path.exists():
            return None
        raise NotImplementedError

    async def poll_session(self):
        """
        TODO: poll GET /lol-champ-select/v1/session every 1-2s once a lockfile
        is found. Trust the self-signed cert explicitly (don't fail closed on
        the cert error). Push champ_a/champ_b/rank to the frontend over the
        /ask WebSocket or a dedicated push channel when picks change.

        TODO: handle the client closing mid-session (lockfile disappears) --
        stop polling cleanly, notify the frontend to fall back to manual entry.
        """
        raise NotImplementedError
