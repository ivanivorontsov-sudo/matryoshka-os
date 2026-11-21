import os, subprocess, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
ZR = os.path.join(ROOT, "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka", "zoom-run")


class ZoomOsRelease(unittest.TestCase):
    def test_syntax(self):
        self.assertEqual(subprocess.run(["sh", "-n", ZR]).returncode, 0)

    def test_debian_os_release_for_zoom_only(self):
        z = open(ZR, encoding="utf-8").read()
        self.assertIn('--ro-bind $OSR /etc/os-release', z)
        self.assertIn("OSR=/usr/lib/os-release", z)
        self.assertIn('$JAIL "$DIR/ZoomLauncher" "$URL"', z)
        self.assertIn('$JAIL "$BIN" $GPU "$@"', z)
        self.assertIn("LC_ALL=C grep -q '[^ -~]' /etc/os-release", z)

    def test_no_comments(self):
        lines = open(ZR, encoding="utf-8").read().splitlines()
        i = next(n for n, l in enumerate(lines) if l.startswith("OSR="))
        j = next(n for n, l in enumerate(lines) if l.startswith("start=$(date"))
        block = lines[i:j]
        self.assertFalse([l for l in block if l.lstrip().startswith("#")])


if __name__ == "__main__":
    unittest.main()
