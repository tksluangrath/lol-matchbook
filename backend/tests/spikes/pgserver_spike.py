"""
Phase 0 spike: validate `pgserver` (embedded Postgres+pgvector) start/stop/
restart/crash-recovery before the data layer depends on it.

See docs/tech-stack.md #4 and docs/build-plan.md Phase 0 for why this spike
exists, and docs/decisions/phase0-pgserver-spike.md for the recorded results.

Each scenario runs in its own subprocess (not just its own connection) so
that "stop the process, start it again" is tested the way a real app
restart would work. This matters: `pgserver.get_server()` caches
PostgresServer handles per pgdata path *within a Python process* and does
not re-verify the server is actually alive on a cache hit -- calling it
twice for the same pgdata inside one long-lived process (e.g. after
killing postgres out from under a still-held handle) silently returns the
stale handle instead of restarting anything. Running each scenario as a
fresh interpreter process sidesteps that and matches how the real app will
behave (a new process on every launch).

Uses a throwaway data directory under the system temp dir (created via
tempfile.mkdtemp, prefix "pgserver_spike_") and deletes it when done,
unless --keep is passed.

Requires the `pgserver` package, which as of this writing only ships wheels
for Python 3.9-3.12 (no 3.13 wheel/sdist on PyPI) -- see the results doc for
what this meant in practice. Run with a Python <=3.12 interpreter that has
`pgserver` and `psycopg[binary]` installed, e.g.:

    python3.12 -m venv .venv312 && source .venv312/bin/activate
    pip install pgserver "psycopg[binary]"
    python backend/tests/spikes/pgserver_spike.py
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

TEST_MSG = "hello-pgserver"


# ---------------------------------------------------------------------------
# Per-scenario worker steps. Each runs in its OWN subprocess (invoked via
# `python pgserver_spike.py <step> <pgdata>`), prints one JSON line to
# stdout as its result, and exits. Keeping these as separate processes is
# the point -- see module docstring.
# ---------------------------------------------------------------------------

def _emit(ok: bool, detail: str) -> None:
    print(json.dumps({"ok": ok, "detail": detail}))


def step_cold_start(pgdata: str) -> None:
    import pgserver
    import psycopg

    srv = pgserver.get_server(pgdata, cleanup_mode="stop")
    try:
        with psycopg.connect(srv.get_uri(), autocommit=True) as conn:
            row = conn.execute("SELECT 1").fetchone()
        _emit(row == (1,), f"SELECT 1 returned {row}")
    finally:
        srv.cleanup()  # graceful `pg_ctl stop -w`


def step_write(pgdata: str) -> None:
    import pgserver
    import psycopg

    srv = pgserver.get_server(pgdata, cleanup_mode="stop")
    try:
        with psycopg.connect(srv.get_uri(), autocommit=True) as conn:
            conn.execute("CREATE TABLE spike_test (id serial primary key, msg text)")
            conn.execute("INSERT INTO spike_test (msg) VALUES (%s)", (TEST_MSG,))
            got = conn.execute(
                "SELECT msg FROM spike_test WHERE msg = %s", (TEST_MSG,)
            ).fetchone()
        _emit(got == (TEST_MSG,), f"wrote {TEST_MSG!r}, read back {got!r}")
    finally:
        srv.cleanup()  # graceful stop, so scenario 3 restarts cleanly


def step_read_check(pgdata: str) -> None:
    import pgserver
    import psycopg

    srv = pgserver.get_server(pgdata, cleanup_mode="stop")
    try:
        with psycopg.connect(srv.get_uri(), autocommit=True) as conn:
            got = conn.execute(
                "SELECT msg FROM spike_test WHERE msg = %s", (TEST_MSG,)
            ).fetchone()
        _emit(got == (TEST_MSG,), f"after graceful stop+restart, read back {got!r}")
    finally:
        srv.cleanup()


def step_crash_write(pgdata: str) -> None:
    """Starts postgres, fires off an in-flight (uncommitted-at-kill-time)
    write, then SIGKILLs the postgres server process itself mid-write.
    Deliberately does NOT call srv.cleanup() -- this is meant to be an
    unclean shutdown, not a graceful one."""
    import pgserver
    import psycopg

    srv = pgserver.get_server(pgdata, cleanup_mode=None)
    pid = srv.get_pid()
    write_outcome = {}

    def do_write():
        try:
            with psycopg.connect(srv.get_uri()) as c:
                cur = c.cursor()
                # pg_sleep inside the statement keeps the write in flight
                # long enough for the SIGKILL below to land before commit.
                cur.execute(
                    "INSERT INTO spike_test (msg) "
                    "SELECT 'inflight-' || pg_sleep(3)::text"
                )
                c.commit()
            write_outcome["committed"] = True
        except Exception as e:
            write_outcome["error"] = repr(e)

    t = threading.Thread(target=do_write)
    t.start()
    time.sleep(1.0)  # let the write start before killing
    os.kill(pid, signal.SIGKILL)
    t.join(timeout=10)
    _emit(True, f"sent SIGKILL to postgres pid {pid} mid-write; write thread outcome: {write_outcome}")
    os._exit(0)  # hard exit, skip any atexit/cleanup handling in this process


def step_recovery_check(pgdata: str) -> None:
    """Fresh process, fresh pgserver handle -- the real test of whether
    postgres recovers on its own after the unclean shutdown in
    step_crash_write, or needs manual intervention."""
    import pgserver
    import psycopg

    log_path = os.path.join(pgdata, "log")

    def tail_log(n=25):
        if not os.path.exists(log_path):
            return "(no log file)"
        with open(log_path) as f:
            return "".join(f.readlines()[-n:])

    try:
        srv = pgserver.get_server(pgdata, cleanup_mode="stop")
    except Exception as e:
        _emit(False, f"restart FAILED, needs manual intervention: {e!r}\n--- log tail ---\n{tail_log()}")
        return

    try:
        with psycopg.connect(srv.get_uri(), autocommit=True) as conn:
            prior_row = conn.execute(
                "SELECT msg FROM spike_test WHERE msg = %s", (TEST_MSG,)
            ).fetchone()
            inflight_rows = conn.execute(
                "SELECT msg FROM spike_test WHERE msg LIKE 'inflight-%'"
            ).fetchall()
        prior_intact = prior_row == (TEST_MSG,)
        _emit(
            prior_intact,
            f"restart after SIGKILL succeeded automatically (no manual repair). "
            f"prior committed row intact: {prior_intact} ({prior_row!r}). "
            f"in-flight/uncommitted rows visible: {inflight_rows!r}.\n"
            f"--- log tail ---\n{tail_log()}",
        )
    finally:
        srv.cleanup()


STEPS = {
    "cold_start": step_cold_start,
    "write": step_write,
    "read_check": step_read_check,
    "crash_write": step_crash_write,
    "recovery_check": step_recovery_check,
}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_step(step: str, pgdata: str) -> tuple[bool, str]:
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), step, pgdata],
        capture_output=True,
        text=True,
        timeout=60,
    )
    last_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else None
    if last_line:
        try:
            result = json.loads(last_line)
            return result["ok"], result["detail"]
        except (json.JSONDecodeError, KeyError):
            pass
    return False, (
        f"subprocess produced no parseable result (exit={proc.returncode})\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


def orchestrate(keep: bool) -> int:
    try:
        import pgserver  # noqa: F401
    except ImportError:
        print("FAIL: `pgserver` is not importable in this interpreter.")
        print("pgserver ships no wheel for this Python version (checked PyPI: "
              "wheels exist only for cp39-cp312 as of 2026-08). Use a Python "
              "<=3.12 venv -- see this file's module docstring.")
        return 1

    pgdata = tempfile.mkdtemp(prefix="pgserver_spike_")
    print(f"pgdata directory: {pgdata}")

    results = {}
    try:
        results["1_cold_start"] = run_step("cold_start", pgdata)
        results["2_write_read"] = run_step("write", pgdata)
        results["3_restart_persistence"] = run_step("read_check", pgdata)
        run_step("crash_write", pgdata)  # kills postgres; result reported via scenario 4
        time.sleep(1.0)  # let the OS fully release the socket/lock files
        results["4_crash_recovery"] = run_step("recovery_check", pgdata)
    finally:
        if keep:
            print(f"--keep passed, leaving pgdata at: {pgdata}")
        else:
            shutil.rmtree(pgdata, ignore_errors=True)

    print("\n=== pgserver spike results ===")
    all_pass = True
    for name in [
        "1_cold_start",
        "2_write_read",
        "3_restart_persistence",
        "4_crash_recovery",
    ]:
        ok, detail = results.get(name, (False, "scenario did not run"))
        all_pass = all_pass and ok
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] in STEPS:
        STEPS[sys.argv[1]](sys.argv[2])
        sys.exit(0)
    else:
        sys.exit(orchestrate(keep="--keep" in sys.argv))
