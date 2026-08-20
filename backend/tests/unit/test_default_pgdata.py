"""
Unit test for app.db_migrate._default_pgdata()'s frozen-vs-source split.

Real bug this guards against, found during Phase 6's fresh-install smoke
test: a PyInstaller onefile bundle extracts to a fresh, randomly-named temp
dir every launch. The old __file__-relative default resolved pgdata inside
that ephemeral tree for the frozen binary -- confirmed live by finding the
packaged app's real Postgres process running with `-D $TMPDIR/.pgdata`, a
location macOS/Windows periodically clear. The fix branches on
sys.frozen (set by PyInstaller) to use a stable per-user app-data dir
instead.
"""
import sys

from app.db_migrate import _default_pgdata


def test_source_mode_is_repo_relative(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    result = _default_pgdata()
    assert result.endswith(".pgdata")
    assert "Application Support" not in result


def test_frozen_macos_avoids_application_support_space(monkeypatch):
    # Real bug found during Phase 6's fresh-install smoke test: pgserver's
    # own socket-dir handling breaks on a space in the pgdata path (embeds
    # it in a `pg_ctl -o "-k <dir>"` string that gets re-split on
    # whitespace) -- "~/Library/Application Support" is the normal macOS
    # convention but not usable here for that reason.
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    result = _default_pgdata()
    assert " " not in result
    assert result.endswith(".lol-matchbook/pgdata")


def test_frozen_windows_uses_appdata(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    result = _default_pgdata()
    assert result == str(tmp_path / "lol-matchbook" / "pgdata")


def test_frozen_linux_uses_home_dotdir(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    result = _default_pgdata()
    assert " " not in result
    assert result.endswith(".lol-matchbook/pgdata")
