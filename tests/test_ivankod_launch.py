import os, subprocess, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WRAP = os.path.join(ROOT, "config", "includes.chroot_after_packages", "usr", "local", "bin", "ivankod")
DESK = os.path.join(ROOT, "config", "includes.chroot_after_packages", "usr", "share", "applications", "ivankod.desktop")


class IvanKodLaunch(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["sh", "-n", WRAP]).returncode, 0)

    def test_wrapper_flags(self):
        with open(WRAP, encoding="utf-8") as f:
            t = f.read()
        self.assertIn("export IVANCODE_PON=/usr/local/bin/ponyatny", t)
        self.assertIn("exec /opt/ivankod/ivankod --ozone-platform=x11 --password-store=basic \"$@\"", t)
        self.assertNotIn("--no-sandbox", t)
        self.assertFalse([l for l in t.splitlines() if l.lstrip().startswith("#") and not l.startswith("#!")])

    def test_desktop_uses_wrapper(self):
        with open(DESK, encoding="utf-8") as f:
            t = f.read()
        self.assertIn("Exec=ivankod %F", t)
        self.assertNotIn("/opt/ivankod/ivankod", t)


if __name__ == "__main__":
    unittest.main()
