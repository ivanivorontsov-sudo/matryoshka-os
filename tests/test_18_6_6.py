import json, os, subprocess, sys, tempfile, unittest
from unittest import mock
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INC = os.path.join(ROOT, "config", "includes.chroot_after_packages")
LIB = os.path.join(INC, "usr", "lib", "matryoshka")
sys.path.insert(0, LIB)
import common as C


def read(*p):
    with open(os.path.join(*p), encoding="utf-8") as f:
        return f.read()


class InstallScanSetting(unittest.TestCase):
    def test_default_on_and_off(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(C, "CONF", d):
                self.assertTrue(C.install_scan())
                C.save("settings", {"install_scan": False})
                self.assertFalse(C.install_scan())
                C.save("settings", {"install_scan": True})
                self.assertTrue(C.install_scan())

    def test_center_checkbox(self):
        s = read(LIB, "center.py")
        self.assertIn("Проверять программы антивирусом при установке", s)
        self.assertIn("install_scan=bool(x)", s)


class NoFreeze(unittest.TestCase):
    def test_pkginstall_async(self):
        s = read(LIB, "pkginstall.py")
        self.assertNotIn("scangate.check(", s)
        self.assertIn('scangate.py", "check-full"', s)
        self.assertIn("timeout=SCAN_LIMIT", s)
        self.assertNotIn("processEvents", s)

    def test_run_skips_own_scanners(self):
        s = read(LIB, "run.py")
        self.assertIn('OWN_SCAN = ("deb", "appimage"', s)
        self.assertIn("C.install_scan()", s)

    def test_scangate_cli_full(self):
        import scangate
        fake = {"malicious": False, "activator": False, "clam_ok": False, "clam": [], "yara": []}
        with tempfile.NamedTemporaryFile(suffix=".deb") as f, mock.patch.object(scangate, "check", return_value=dict(fake)) as chk, \
                mock.patch.object(sys, "argv", ["scangate.py", "check-full", f.name, "install"]), mock.patch("builtins.print") as pr:
            with self.assertRaises(SystemExit) as e:
                exec(compile(read(LIB, "scangate.py").split('if __name__ == "__main__":')[1].replace("\n    ", "\n"), "x", "exec"), dict(vars(scangate), __name__="x"))
            self.assertEqual(e.exception.code, 0)
            self.assertEqual(chk.call_args.kwargs.get("wait"), 90)
            out = json.loads(pr.call_args.args[0])
            self.assertFalse(out["clam_ok"])

    def test_archive_scan_timeouts_caught(self):
        s = read(LIB, "archiveinst.py")
        self.assertIn("except (OSError, subprocess.SubprocessError)", s)
        self.assertIn("noscan", s)
        r = read(LIB, "root.sh")
        self.assertIn('case "${4:-}" in ""|noscan) ;; *) exit 2 ;; esac', r)


class Clamd(unittest.TestCase):
    def test_lazy_script(self):
        p = os.path.join(LIB, "clamd-lazy.sh")
        self.assertEqual(subprocess.run(["sh", "-n", p]).returncode, 0)
        s = read(p)
        self.assertIn("preload)", s)
        self.assertIn("big && exit 0", s)

    def test_units(self):
        sd = os.path.join(INC, "etc", "systemd", "system")
        self.assertIn("OnBootSec=2min", read(sd, "matryoshka-clamd-preload.timer"))
        self.assertIn("clamd-lazy.sh preload", read(sd, "matryoshka-clamd-preload.service"))
        self.assertIn("Nice=10", read(sd, "clamav-daemon.service.d", "matryoshka.conf"))
        self.assertIn("matryoshka-clamd-preload.timer", read(ROOT, "config", "hooks", "live", "0600-matryoshka.hook.chroot"))


class Kickoff(unittest.TestCase):
    def test_action_file(self):
        s = read(INC, "usr", "share", "plasma", "kickeractions", "matryoshka-appinfo.desktop")
        self.assertIn("Exec=python3 /usr/lib/matryoshka/appinfo.py --remove %f", s)
        self.assertIn("Name[ru]=Удалить программу…", s)


class Zoom(unittest.TestCase):
    def test_deb_install_block(self):
        r = read(LIB, "root.sh")
        i = r.index("  deb-install)\n")
        b = r[i:r.index("exit $rc ;;", i)]
        self.assertIn("zoomsnitch.py write /opt/zoom >/dev/null || true", b)
        self.assertIn("reload-or-restart opensnitch >/dev/null 2>&1 || true", b)
        self.assertIn("then rc=0; else rc=$?; fi", b)

    def test_repair_deb(self):
        import archiveinst
        with tempfile.TemporaryDirectory() as h:
            real = os.path.isfile
            fake = lambda p: True if p in ("/opt/zoom/ZoomLauncher", "/usr/share/applications/Zoom.desktop", "/usr/lib/matryoshka/zoom-run") else real(p)
            with mock.patch("os.path.isfile", side_effect=fake), mock.patch.object(archiveinst, "register"):
                self.assertTrue(archiveinst.repair_zoom_deb(h))
                dp = os.path.join(h, ".local/share/applications/Zoom.desktop")
                self.assertIn("Exec=/usr/lib/matryoshka/zoom-run /opt/zoom/ZoomLauncher %U", read(dp))
                self.assertEqual(archiveinst.repair_zoom_deb(h), [])
            with mock.patch.object(archiveinst, "register"):
                self.assertEqual(archiveinst.repair_zoom_deb(h), [dp])
                self.assertFalse(os.path.exists(dp))
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            with open(dp, "w") as f:
                f.write("[Desktop Entry]\nExec=my-own\n")
            with mock.patch("os.path.isfile", side_effect=fake), mock.patch.object(archiveinst, "register"):
                self.assertEqual(archiveinst.repair_zoom_deb(h), [])
            self.assertIn("my-own", read(dp))


class Audio(unittest.TestCase):
    def test_hdmi_rule(self):
        s = read(INC, "etc", "wireplumber", "wireplumber.conf.d", "52-matryoshka-hdmi-last.conf")
        self.assertIn('node.name = "~alsa_output.*(hdmi|HDMI|[Dd]isplay[Pp]ort).*"', s)
        self.assertIn("priority.session = 100", s)


if __name__ == "__main__":
    unittest.main()
