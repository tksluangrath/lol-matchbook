# PyInstaller spec for the packaged desktop app's backend sidecar (Phase 6,
# docs/build-plan.md). Bundles app.main's real uvicorn.run() entry point
# (backend/app/main.py's __main__ guard) into a single executable.
#
# pgserver ships its actual Postgres binaries as package data
# (pginstall/bin, lib, share) -- PyInstaller's import analysis only follows
# Python imports, so these must be listed explicitly or the bundled app
# fails at runtime with a missing-binary error, not an import error.
import pgserver
import os

pgserver_dir = os.path.dirname(pgserver.__file__)

block_cipher = None

a = Analysis(
    ["app/main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        (os.path.join(pgserver_dir, "pginstall"), "pgserver/pginstall"),
    ],
    hiddenimports=[
        "app.routers.advice",
        "app.routers.ask",
        "app.routers.refresh",
        "app.routers.lcu",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="lol-matchbook-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
