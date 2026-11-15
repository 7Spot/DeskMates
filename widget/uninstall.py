"""Hand uninstall to an independent native helper before the widget exits.

Preparation never deletes anything. The helper only recycles the verified running
bundle after an explicit commit and process exit; user data follows successful
recycling. Source runs use the same handshake, without any application target.
"""
from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import config

BUNDLE_ID = config.BUNDLE_ID
HELPER_NAME = "Deskmate Uninstaller.app"
HELPER_EXE = "DeskmateUninstaller"
READY_TIMEOUT = 15.0


class UninstallError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def validate_bundle(bundle: Path, executable: Path | None = None) -> Path:
    """Accept only this running app, and refuse read-only/translocated copies."""
    bundle = Path(bundle).resolve(strict=True)
    executable = Path(executable or sys.executable).resolve(strict=True)
    try:
        with (bundle / "Contents/Info.plist").open("rb") as stream:
            info = plistlib.load(stream)
        name = info.get("CFBundleExecutable", "")
        if (bundle.suffix != ".app" or info.get("CFBundleIdentifier") != BUNDLE_ID
                or not name or Path(name).name != name
                or (bundle / "Contents/MacOS" / name).resolve(strict=True) != executable):
            raise UninstallError("The running app could not be verified")
        if os.statvfs(bundle).f_flag & os.ST_RDONLY:
            raise UninstallError("Move the app to Applications before uninstalling")
    except UninstallError:
        raise
    except (OSError, ValueError, plistlib.InvalidFileException) as exc:
        raise UninstallError("The running app could not be verified") from exc
    return bundle


def helper_path() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent / "Helpers" / HELPER_NAME
    return config.ROOT / "dist.nosync" / "helpers" / HELPER_NAME


def _write_json(path: Path, value: dict) -> None:
    staging = path.with_suffix(".writing")
    staging.write_text(json.dumps(value), encoding="utf-8")
    staging.replace(path)


@dataclass
class Session:
    folder: Path
    process: subprocess.Popen
    started: float
    committed: bool = False

    def poll(self) -> dict:
        try:
            status = json.loads((self.folder / "status.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            status = {"state": "starting"}
        if status.get("state") in ("error", "cancelled"):
            return status
        if self.process.poll() is not None and not self.committed:
            return {"state": "error", "code": "The uninstall helper could not start"}
        if not self.committed and time.monotonic() - self.started > READY_TIMEOUT:
            self.cancel()
            return {"state": "error", "code": "The uninstall helper could not start"}
        return status

    def commit(self) -> None:
        if self.poll().get("state") != "ready":
            raise UninstallError("The uninstall helper is not ready")
        _write_json(self.folder / "commit.json", {"commit": True})
        self.committed = True

    def cancel(self) -> None:
        """Cancel preparation only; committed recycling belongs to the helper."""
        if not self.committed:
            try:
                (self.folder / "cancel").touch()
            except OSError:
                pass
            # A preflight error panel has stopped its readiness timer. Do not
            # rely on it polling cancel; this is our own uncommitted subprocess.
            try:
                if self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                return  # Keep its private files if it could still be running.
            shutil.rmtree(self.folder, ignore_errors=True)


def start(bundle: Path | None, language: str = "en") -> Session:
    """Create the helper session. Caller waits for ready, commits, then quits."""
    if sys.platform != "darwin":
        raise UninstallError("Automatic uninstall is available on macOS")
    try:
        target = validate_bundle(bundle) if bundle is not None else None
        source = helper_path()
        if not (source / "Contents/MacOS" / HELPER_EXE).is_file():
            raise UninstallError("The uninstall helper could not start")
        folder = Path(tempfile.mkdtemp(prefix="deskmate-uninstall-"))
        try:
            helper = folder / HELPER_NAME
            shutil.copytree(source, helper, symlinks=True)
            st = target.stat() if target is not None else None
            _write_json(folder / "request.json", {
                "pid": os.getpid(), "language": "zh" if language == "zh" else "en",
                "bundle": str(target) if target is not None else "",
                "device": st.st_dev if st is not None else 0,
                "inode": st.st_ino if st is not None else 0,
                "executable": str(Path(sys.executable).resolve()),
            })
            process = subprocess.Popen(
                [str(helper / "Contents/MacOS" / HELPER_EXE), str(folder)],
                start_new_session=True, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
            )
        except Exception:
            shutil.rmtree(folder)
            raise
    except UninstallError:
        raise
    except (OSError, ValueError) as exc:
        raise UninstallError("The uninstall helper could not start") from exc
    return Session(folder, process, time.monotonic())
