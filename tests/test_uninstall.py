"""Uninstall preparation is harmless; only the independent helper deletes data.

Opt-in native tests compile a separate helper with a compulsory /private/tmp
data root. They never access real settings or any installed Deskmate application.
"""
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import config
from widget import uninstall


def fake_bundle(root, fixture=None):
    bundle = root / "Uninstall Fixture.app"
    binary = bundle / "Contents/MacOS/Fixture"
    binary.parent.mkdir(parents=True)
    if fixture is None:
        binary.write_bytes(b"non-executable bundle identity fixture")
    else:
        shutil.copy(fixture, binary)
    with (bundle / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump({"CFBundleIdentifier": uninstall.BUNDLE_ID, "CFBundleExecutable": "Fixture"}, stream)
    if fixture is not None:
        subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(bundle)], check=True)
    return bundle, binary


def build_fixture(folder):
    """Own signed executable: never relocate a protected Apple platform binary."""
    source = folder / "fixture.c"
    binary = folder / "DeskmateTestParent"
    source.write_text("#include <signal.h>\n#include <unistd.h>\n#include <stdio.h>\n"
                      "static volatile sig_atomic_t alive = 1;\n"
                      "static void stop(int signo) { alive = 0; }\n"
                      "int main(void) { signal(SIGTERM, stop); puts(\"ready\"); fflush(stdout); "
                      "while (alive) pause(); return 0; }\n")
    subprocess.run(["xcrun", "clang", "-O2", str(source), "-o", str(binary)], check=True)
    subprocess.run(["/usr/bin/codesign", "--force", "--sign", "-", str(binary)], check=True)
    return binary


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bundle, self.executable = fake_bundle(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_accepts_only_the_running_bundle(self):
        self.assertEqual(uninstall.validate_bundle(self.bundle, self.executable), self.bundle.resolve())
        with self.assertRaises(uninstall.UninstallError):
            uninstall.validate_bundle(self.bundle, Path(sys.executable))

    def test_rejects_wrong_identity_and_executable_traversal(self):
        info = self.bundle / "Contents/Info.plist"
        for data in ({"CFBundleIdentifier": "another.app", "CFBundleExecutable": "Fixture"},
                     {"CFBundleIdentifier": uninstall.BUNDLE_ID, "CFBundleExecutable": "../Fixture"}):
            with info.open("wb") as stream:
                plistlib.dump(data, stream)
            with self.assertRaises(uninstall.UninstallError):
                uninstall.validate_bundle(self.bundle, self.executable)

    def test_refuses_read_only_volume_before_spawning(self):
        with mock.patch.object(uninstall.os, "statvfs", return_value=mock.Mock(f_flag=os.ST_RDONLY)):
            with self.assertRaisesRegex(uninstall.UninstallError, "Applications"):
                uninstall.validate_bundle(self.bundle, self.executable)

    def test_start_fails_without_launching_if_helper_missing(self):
        with mock.patch.object(uninstall, "helper_path", return_value=self.root / "missing"), \
             mock.patch.object(uninstall.subprocess, "Popen") as spawn:
            with self.assertRaises(uninstall.UninstallError):
                uninstall.start(None)
            spawn.assert_not_called()

    def test_copy_outside_bundle_and_never_delete_data_in_preparation(self):
        helper = self.root / "helper.app"
        binary = helper / "Contents/MacOS/DeskmateUninstaller"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"fixture")
        with mock.patch.object(uninstall, "helper_path", return_value=helper), \
             mock.patch.object(uninstall.subprocess, "Popen") as spawn:
            session = uninstall.start(None, "zh")
        try:
            request = json.loads((session.folder / "request.json").read_text())
            self.assertEqual(request["bundle"], "")
            self.assertEqual(request["language"], "zh")
            self.assertFalse((session.folder / "commit.json").exists())
            self.assertTrue(Path(spawn.call_args.args[0][0]).is_file())
            self.assertTrue(spawn.call_args.kwargs["start_new_session"])
            self.assertNotIn("home", request)
            self.assertNotIn("cache", request)
        finally:
            shutil.rmtree(session.folder)

    def test_handshake_requires_live_ready_helper(self):
        process = mock.Mock()
        process.poll.return_value = None
        session = uninstall.Session(self.root, process, time.monotonic())
        with self.assertRaises(uninstall.UninstallError):
            session.commit()
        uninstall._write_json(self.root / "status.json", {"state": "ready"})
        process.poll.return_value = 2
        with self.assertRaises(uninstall.UninstallError):
            session.commit()
        self.assertFalse((self.root / "commit.json").exists())
        process.poll.return_value = None
        session.commit()
        self.assertTrue(session.committed)
        self.assertTrue((self.root / "commit.json").exists())
        session.cancel()
        self.assertFalse((self.root / "cancel").exists(), "a committed operation is owned by the helper")

    def test_readiness_timeout_cancels_without_commit(self):
        process = mock.Mock()
        process.poll.return_value = None
        session = uninstall.Session(self.root, process, time.monotonic() - 100)
        self.assertEqual(session.poll()["state"], "error")
        process.terminate.assert_called_once()
        self.assertFalse(self.root.exists(), "uncommitted helper session is cleaned")

    def test_cancel_preflight_error_stops_helper_even_if_it_stopped_polling(self):
        process = mock.Mock()
        process.poll.return_value = None
        uninstall._write_json(self.root / "status.json", {"state": "error"})
        session = uninstall.Session(self.root, process, time.monotonic())
        session.cancel()
        process.terminate.assert_called_once()
        process.wait.assert_called_once_with(timeout=1)
        self.assertFalse(self.root.exists())

    def test_preflight_error_keeps_message(self):
        uninstall._write_json(self.root / "status.json", {"state": "error", "message": "permission denied"})
        session = uninstall.Session(self.root, mock.Mock(), time.monotonic())
        self.assertEqual(session.poll()["message"], "permission denied")


@unittest.skipUnless(os.environ.get("DESKMATE_NATIVE_UNINSTALL_TESTS") == "1" and sys.platform == "darwin",
                     "opt-in AppKit test, with an isolated disposable app and data root")
class NativeUninstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix="deskmate-uninstall-test-build-", dir="/private/tmp")
        cls.helper = Path(cls.build.name) / uninstall.HELPER_NAME
        cls.fixture = build_fixture(Path(cls.build.name))
        subprocess.run(["zsh", "tools/build_uninstaller.sh", str(cls.helper), "--test"], cwd=config.ROOT, check=True)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="deskmate-uninstall-test-", dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.bundle, self.binary = fake_bundle(self.root, self.fixture)
        self.parent = subprocess.Popen([str(self.binary)], stdout=subprocess.PIPE, text=True)
        self.assertEqual(self.parent.stdout.readline(), "ready\n")
        self.files = [self.root / p for p in ("Library/Preferences/com.deskmate.Companion.plist",
                     "Library/Logs/Deskmate.log", "Library/Caches/Deskmate/fixture")]
        for path in self.files:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("keep until confirmed recycle")
        self.folder = Path(tempfile.mkdtemp(prefix="deskmate-uninstall-", dir="/private/tmp"))
        helper = self.folder / uninstall.HELPER_NAME
        shutil.copytree(self.helper, helper)
        st = self.bundle.stat()
        self.bundle_identity = (st.st_dev, st.st_ino)
        self.request = {"pid": self.parent.pid, "bundle": str(self.bundle), "device": st.st_dev,
                        "inode": st.st_ino, "executable": str(self.binary), "language": "en",
                        "testDataRoot": str(self.root)}
        self.process = None
        self.trash = None

    def launch(self):
        uninstall._write_json(self.folder / "request.json", self.request)
        self.process = subprocess.Popen([str(self.folder / uninstall.HELPER_NAME / "Contents/MacOS/DeskmateUninstaller"), str(self.folder)])
        return self.wait_state("ready", "error")

    def wait_state(self, *states, timeout=15):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = json.loads((self.folder / "status.json").read_text())
                if last.get("trash"):
                    self.trash = Path(last["trash"])
                if last.get("state") in states:
                    return last
            except (OSError, ValueError):
                pass
            if self.process.poll() is not None:
                self.fail(f"helper exited {self.process.returncode}, last status {last}")
            time.sleep(.05)
        self.fail(f"helper did not reach {states}: {last}")

    def tearDown(self):
        for process in (self.process, self.parent):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()
        self.parent.stdout.close()
        if self.trash is not None and self.trash.exists():
            st = self.trash.stat()
            self.assertEqual((st.st_dev, st.st_ino), self.bundle_identity)
            shutil.rmtree(self.trash)  # Only the exact disposable fixture inode.
        shutil.rmtree(self.folder, ignore_errors=True)
        self.tmp.cleanup()

    def test_ready_then_cancel_preserves_app_and_all_data(self):
        self.assertEqual(self.launch()["state"], "ready")
        (self.folder / "cancel").touch()
        self.process.wait(timeout=5)
        self.assertTrue(self.bundle.exists())
        self.assertTrue(all(path.exists() for path in self.files))
        self.assertFalse(self.folder.exists())

    def test_identity_mismatch_never_becomes_ready(self):
        self.request["inode"] += 1
        self.assertEqual(self.launch()["state"], "error")
        self.assertTrue(self.bundle.exists())
        self.assertTrue(all(path.exists() for path in self.files))

    def test_recycle_then_clean_only_after_commit_and_process_exit(self):
        self.assertEqual(self.launch()["state"], "ready")
        uninstall._write_json(self.folder / "commit.json", {"commit": True})
        self.wait_state("waiting")
        self.assertTrue(self.bundle.exists())
        self.assertTrue(all(path.exists() for path in self.files))
        self.parent.terminate(); self.parent.wait()
        result = self.wait_state("done", "error", "partial", timeout=30)
        self.assertEqual(result["state"], "done", result)
        self.assertFalse(self.bundle.exists())
        self.assertTrue(all(not path.exists() for path in self.files))

    def test_failed_recycle_keeps_data(self):
        status = self.launch()
        self.assertEqual(status["state"], "ready", status)
        # Replace the verified bundle before committing: preflight must refuse it.
        moved = self.root / "Kept Fixture.app"
        self.bundle.rename(moved)
        fake_bundle(self.root, self.fixture)
        uninstall._write_json(self.folder / "commit.json", {"commit": True})
        self.parent.terminate(); self.parent.wait()
        self.assertEqual(self.wait_state("error")["state"], "error")
        self.assertTrue(moved.exists())
        self.assertTrue(self.bundle.exists())
        self.assertTrue(all(path.exists() for path in self.files))

    def test_source_mode_cleans_only_test_data_without_source_deletion(self):
        self.request["bundle"] = ""
        self.request["device"] = self.request["inode"] = 0
        self.assertEqual(self.launch()["state"], "ready")
        uninstall._write_json(self.folder / "commit.json", {"commit": True})
        self.parent.terminate(); self.parent.wait()
        self.assertEqual(self.wait_state("done", "error")["state"], "done")
        self.assertTrue(self.bundle.exists())
        self.assertTrue(all(not path.exists() for path in self.files))

    def test_symlinked_parent_is_preserved_and_reported_as_partial(self):
        self.request["bundle"] = ""
        cache_parent = self.root / "Library/Caches"
        outside = self.root / "unrelated-data"
        cache_parent.rename(outside)
        cache_parent.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.launch()["state"], "ready")
        uninstall._write_json(self.folder / "commit.json", {"commit": True})
        self.parent.terminate(); self.parent.wait()
        result = self.wait_state("partial", "done", "error")
        self.assertEqual(result["state"], "partial", result)
        self.assertTrue((outside / "Deskmate/fixture").exists())
        self.assertTrue(cache_parent.is_symlink())
        self.assertTrue(self.bundle.exists())

    def test_preferences_symlink_cannot_modify_its_destination(self):
        self.request["bundle"] = ""
        external = self.root / "unrelated-settings.plist"
        external.write_text("must remain")
        self.files[0].unlink()
        self.files[0].symlink_to(external)
        self.assertEqual(self.launch()["state"], "ready")
        uninstall._write_json(self.folder / "commit.json", {"commit": True})
        self.parent.terminate(); self.parent.wait()
        result = self.wait_state("partial", "done", "error")
        self.assertEqual(result["state"], "partial", result)
        self.assertEqual(external.read_text(), "must remain")
        self.assertTrue(self.files[0].is_symlink())


if __name__ == "__main__":
    unittest.main()
