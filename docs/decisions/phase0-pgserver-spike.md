# Phase 0 spike result: `pgserver` start/stop/restart/crash-recovery

Ran the four scenarios from [build-plan.md](../build-plan.md) Phase 0 ("`pgserver` spike"), per [tech-stack.md](../tech-stack.md) #4. Script: `backend/tests/spikes/pgserver_spike.py`. Run 2026-08-06, macOS arm64 (Apple Silicon), Postgres 16.2 (bundled by `pgserver` 0.1.4).

**Overall: proceed with `pgserver`.** All four scenarios pass, repeatably (ran the full sequence 4 times back to back, identical outcome each time). One real environment gotcha found along the way (see below) that affects the Phase 6 packaging plan, not the Phase 1 decision to use `pgserver` itself.

## Environment note (found before scenario 1 could even run)

`pip install pgserver` failed on this machine's default interpreter with "No matching distribution found for pgserver" and no useful reason given. Root cause, confirmed via `pip index`/PyPI JSON API: **`pgserver` (up to and including the current 0.1.4) ships wheels only for CPython 3.9-3.12, no 3.13 wheel and no sdist.** This machine's default `python3` (via pyenv) is 3.13.7. Installed a Python 3.12.5 venv (already present via pyenv: `~/.pyenv/versions/3.12.5`) and `pgserver` installed cleanly there.

Action item for later phases: `backend/requirements.txt` should pin the backend to Python <=3.12 (or this gets re-checked when 3.13 wheels ship), and the Phase 6 PyInstaller bundling step needs to build with that interpreter. Not a blocker, just needs to be consistent everywhere the backend gets built/run.

## Scenario 1 — Cold start: PASS

Fresh `tempfile.mkdtemp()` pgdata directory, no prior state. `pgserver.get_server(pgdata)` ran `initdb` then `pg_ctl start`, came up, and a `SELECT 1` over a `psycopg` connection returned `(1,)`. Observed in the postgres log:
```
starting PostgreSQL 16.2 on aarch64-apple-darwin23.5.0...
database system was shut down at ...
database system is ready to accept connections
```
Startup (initdb + pg_ctl start + first connection) took well under a second in every run.

## Scenario 2 — Write + read: PASS

`CREATE TABLE spike_test (id serial primary key, msg text)`, `INSERT INTO spike_test (msg) VALUES ('hello-pgserver')`, then `SELECT msg FROM spike_test WHERE msg = 'hello-pgserver'` in the same process. Read back `('hello-pgserver',)` — exact match.

## Scenario 3 — Graceful restart + persistence: PASS

Stopped the server gracefully (`srv.cleanup()` with `cleanup_mode='stop'`, which internally runs `pg_ctl stop -w`, i.e. a fast/clean shutdown — confirmed in the log as `received fast shutdown request` / `database system is shut down`), then started a **new process** against the same pgdata directory. `SELECT msg FROM spike_test WHERE msg = 'hello-pgserver'` still returned `('hello-pgserver',)`.

Note on methodology: this scenario (and scenario 4) run the "start it again" step as a genuinely separate OS process (`subprocess.run([sys.executable, ...])`), not just a second Python object in the same process. That distinction turned out to matter — see the design note in the spike script's module docstring: `pgserver.get_server()` caches `PostgresServer` handles per pgdata path *within a single Python process* and does not re-verify the underlying postgres process is still alive on a cache hit. Calling it twice for the same pgdata from one long-lived process after the server died out from under you silently hands back the stale, dead handle instead of restarting anything — first attempt at this spike hit exactly that and produced a false "connection refused" failure that had nothing to do with Postgres's actual crash recovery. Running every "start it again" step as a fresh subprocess (which is what a real app restart looks like anyway) avoids this and is the accurate test.

## Scenario 4 — Unclean shutdown + recovery: PASS (automatic recovery, no manual intervention needed)

Procedure: started postgres, opened a connection, issued `INSERT INTO spike_test (msg) SELECT 'inflight-' || pg_sleep(3)::text` (deliberately slow so it's still in flight, uncommitted), waited 1 second, then sent `SIGKILL` directly to the postgres server process (`os.kill(pid, signal.SIGKILL)` — not `pg_ctl stop`, not a signal to the Python wrapper process). Confirmed via `psutil` that the killed pid was actually gone before proceeding. Then, in a **fresh subprocess**, called `pgserver.get_server(pgdata)` again against the same data directory.

Observed: it came back up automatically, with no manual repair step, no corrupted-data-directory error, no refusal to start. Actual log output from the restart attempt (unedited, one representative run):
```
starting PostgreSQL 16.2 on aarch64-apple-darwin23.5.0...
database system was interrupted; last known up at 2026-08-06 16:26:56 EDT
database system was not properly shut down; automatic recovery in progress
invalid record length at 0/14CA718: expected at least 24, got 0
redo is not required
checkpoint starting: end-of-recovery immediate wait
checkpoint complete: wrote 3 buffers (0.0%); 0 WAL file(s) added, 0 removed, 0 recycled; ...
database system is ready to accept connections
```
The whole restart (initdb-skip, WAL scan, "redo is not required", ready) completed in well under a second (log timestamps ~30-330ms apart across runs).

After restart: the row written and committed in scenario 2 (`'hello-pgserver'`) was still present. The in-flight `INSERT ... SELECT 'inflight-' || pg_sleep(3)` — which was still sleeping (uncommitted) at the moment of SIGKILL — was **not** present after recovery (0 rows matching `'inflight-%'`), i.e. Postgres correctly discarded the incomplete transaction rather than partially applying it. This matches "redo is not required" in the log: no committed WAL record existed for that transaction to replay.

Ran this exact sequence 4 times end to end; identical outcome (PASS) every time — no flakiness observed.

**Separately confirmed** (ad hoc, not in the checked-in script) that a transaction which *did* commit immediately before the `SIGKILL` also survived recovery: inserted and committed a row, `SIGKILL`ed the server pid directly afterward, restarted in a fresh process, and the row was present. So both directions hold — committed work survives an unclean kill, uncommitted work is cleanly rolled back — consistent with normal Postgres WAL-based crash recovery, actually observed here rather than assumed.

## Bottom line

- `pgserver` cold-starts fast, persists correctly across a graceful stop/start, and recovers automatically from a hard `SIGKILL` mid-write with no manual intervention, at least under this failure mode (server process killed directly) on macOS arm64.
- The one real friction point is Python-version support (3.9-3.12 only) — plan the backend's Python version around that now rather than discovering it at packaging time.
- The `get_server()` per-process caching behavior (not re-checking liveness on cache hit) is worth knowing about for the real backend code: if the FastAPI process is going to hold a long-lived `pgserver` handle, it should not assume calling `get_server()` again mid-process will recover a server that died unexpectedly — that only works via a real process restart. Not a blocker, just something `backend/app/db.py` should be aware of when it's built in Phase 1.
