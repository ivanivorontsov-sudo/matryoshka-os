import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from matryoshka_phone import core

HERE = Path(__file__).resolve().parent


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.phone = Path(self.tmp.name) / "phone"
        cam = self.phone / "sdcard/DCIM/Camera"
        (cam / "sub").mkdir(parents=True)
        (cam / "a.jpg").write_bytes(b"A" * 1000)
        (cam / "sub/b.jpg").write_bytes(b"B" * 2000)
        (self.phone / "sdcard/Download").mkdir(parents=True)
        (self.phone / "sdcard/Download/copy-of-a.jpg").write_bytes(b"A" * 1000)
        (self.phone / "sdcard/Download/имя с пробелом.pdf").write_bytes(b"P" * 500)
        os.utime(cam / "a.jpg", (1600000000, 1600000000))
        os.environ["FAKE_PHONE"] = str(self.phone)
        os.environ["MATRYOSHKA_ADB"] = str(HERE / "fake_adb.py")
        os.environ.pop("FAKE_FAIL", None)
        self.dest = Path(self.tmp.name) / "dest"

    def tearDown(self):
        self.tmp.cleanup()

    def files(self):
        return [f for s in ("DCIM/Camera", "Download", "Music") for f in core.list_adb("ABC123", "/sdcard", s)]

    def test_devices(self):
        self.assertEqual(core.adb_devices(), [("ABC123", "device")])

    def test_list_keeps_structure(self):
        rels = sorted(f.rel for f in self.files())
        self.assertIn("DCIM/Camera/sub/b.jpg", rels)
        self.assertIn("Download/имя с пробелом.pdf", rels)

    def test_copy_dates_duplicates_resume(self):
        logs = []
        rep = core.Copier(self.dest, core.adb_fetcher("ABC123"), log=logs.append).run(self.files())
        self.assertEqual(rep.copied, 3)
        self.assertEqual(rep.duplicates, 1)
        self.assertEqual(int((self.dest / "DCIM/Camera/a.jpg").stat().st_mtime), 1600000000)
        self.assertTrue((self.dest / "DCIM/Camera/sub/b.jpg").exists())
        rep2 = core.Copier(self.dest, core.adb_fetcher("ABC123")).run(self.files())
        self.assertEqual(rep2.copied, 0)
        self.assertFalse(list(self.dest.rglob("*.part")))

    def test_failure_then_resume(self):
        os.environ["FAKE_FAIL"] = "b.jpg"
        rep = core.Copier(self.dest, core.adb_fetcher("ABC123")).run(self.files())
        self.assertEqual(len(rep.failed), 1)
        os.environ.pop("FAKE_FAIL")
        rep2 = core.Copier(self.dest, core.adb_fetcher("ABC123")).run(self.files())
        self.assertEqual(rep2.copied, 1)
        self.assertTrue((self.dest / "DCIM/Camera/sub/b.jpg").exists())

    def test_destination_refuses_recovery_source(self):
        with self.assertRaises(core.PhoneError):
            core.check_destination(self.dest, 10, sources={"/dev/nvme0n1p3"}, devfn=lambda p: "/dev/nvme0n1p3")
        core.check_destination(self.dest, 10, sources={"/dev/nvme0n1p3"}, devfn=lambda p: "/dev/sda1")

    def test_destination_space(self):
        with self.assertRaises(core.PhoneError):
            core.check_destination(self.dest, 1 << 60, sources=set(), devfn=lambda p: "")

    def test_apps(self):
        apps = {a.package: a for a in core.list_apps("ABC123")}
        self.assertEqual(apps["org.telegram.messenger"].linux, "org.telegram.desktop")
        self.assertIsNone(apps["com.example.game"].linux)
        self.assertIn("Google Play", apps["com.example.game"].note)
        files = core.pull_apks("ABC123", "com.example.game", self.dest)
        self.assertEqual([f.name for f in files], ["base.apk", "split_config.arm64_v8a.apk"])


if __name__ == "__main__":
    unittest.main()
