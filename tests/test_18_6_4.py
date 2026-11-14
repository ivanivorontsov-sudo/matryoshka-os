import json, os, re, subprocess, sys, tempfile, unittest
from unittest import mock
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LIB = os.path.join(ROOT, "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka")
sys.path.insert(0, LIB)
import audiodev
import av
import dosbox
import zoomsnitch


def text(*p):
    with open(os.path.join(ROOT, *p), encoding="utf-8") as f:
        return f.read()


class Antivirus(unittest.TestCase):
    def test_ready_when_ping_ok(self):
        with mock.patch.object(av, "engine_ping", return_value=True):
            self.assertTrue(av.engine_ready(5))

    def test_starts_service_and_waits(self):
        pings = iter([False, False, True])
        calls = []
        with mock.patch.object(av, "engine_ping", side_effect=lambda: next(pings)), \
             mock.patch.object(av.C, "root_argv", return_value=["sudo", "-n", "x", "av-start"]), \
             mock.patch.object(av.C, "run", side_effect=lambda *a, **k: calls.append(a[0]) or subprocess.CompletedProcess(a[0], 0, "active\n", "")), \
             mock.patch("time.sleep"):
            self.assertTrue(av.engine_ready(30))
        self.assertTrue(any("av-start" in c for c in calls))

    def test_root_action_and_sudoers(self):
        self.assertIn("av-start)", text("config/includes.chroot_after_packages/usr/lib/matryoshka/root.sh"))
        self.assertIn("av-start", text("config/includes.chroot_after_packages/etc/sudoers.d/matryoshka"))


class Zoom(unittest.TestCase):
    def test_rules_only_zoom(self):
        with tempfile.TemporaryDirectory() as t:
            zoomsnitch.DIR = t
            names = zoomsnitch.write("/home/и/zoom")
            self.assertEqual(len(names), 2)
            for n in names:
                with open(os.path.join(t, n + ".json")) as f:
                    r = json.load(f)
                ops = r["operator"]["list"]
                self.assertEqual(r["action"], "allow")
                self.assertEqual(ops[0]["operand"], "process.path")
                self.assertTrue(re.match(ops[0]["data"], "/home/и/zoom/zoom"))
                self.assertFalse(re.match(ops[0]["data"], "/usr/bin/curl"))
                self.assertIn("dest.port", [o["operand"] for o in ops])
        h = re.compile(zoomsnitch.DOMAINS)
        self.assertTrue(h.match("us05web.zoom.us") and h.match("zoom.com") and h.match("x.zoomgov.com"))
        self.assertFalse(h.match("evilzoom.us") or h.match("zoom.us.evil.com"))
        p = re.compile(zoomsnitch.PORTS)
        self.assertTrue(p.match("443") and p.match("8801") and p.match("8810") and p.match("3478"))
        self.assertFalse(p.match("80") or p.match("22") or p.match("8811"))

    def test_no_global_firewall_holes(self):
        s = text("config/includes.chroot_after_packages/usr/lib/matryoshka/root.sh")
        self.assertNotRegex(s, r"ufw (allow|default allow)")
        self.assertIn("zoomsnitch.py write", s)
        self.assertIn("zoom-migrate.sh", text("config/includes.chroot_after_packages/usr/lib/matryoshka/apply-look.sh"))
        self.assertIn("zoomsnitch.py migrate", text("config/includes.chroot_after_packages/usr/lib/matryoshka/zoom-migrate.sh"))

    def test_wrapper(self):
        s = text("config/includes.chroot_after_packages/usr/lib/matryoshka/zoom-run")
        self.assertIn("unset", s)
        self.assertIn("LD_PRELOAD", s)
        self.assertEqual(subprocess.run(["bash", "-n", os.path.join(LIB, "zoom-run")]).returncode, 0)


class FreeDOS(unittest.TestCase):
    def test_mount_when_present(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "BIN"))
            open(os.path.join(t, "BIN", "EDIT.EXE"), "w").close()
            with mock.patch.object(dosbox, "FREEDOS", t):
                s = dosbox.session_text("/p", "", "/d", "/h", "/s", "/pr")
        self.assertIn('mount -q h "%s" -ro' % t, s)
        self.assertIn(";h:\\bin", s)
        self.assertIn("set LANG=RU", s)

    def test_absent(self):
        with mock.patch.object(dosbox, "FREEDOS", "/nonexistent"):
            s = dosbox.session_text("/p", "", "/d", "/h", "/s", "/pr")
        self.assertNotIn("mount -q h", s)

    def test_no_keyrus_bundled(self):
        self.assertIn("KeyRus is not included", text("packaging/matryoshka-freedos/copyright"))


class Fingerprint(unittest.TestCase):
    def test_session_and_boot_hooks(self):
        s = text("packaging/matryoshka-gxfp/root/usr/sbin/matryoshka-gxfp")
        self.assertIn("ActiveSession", s)
        self.assertIn("PrepareForSleep", s)
        self.assertIn("/run/matryoshka-gxfp-boot", s)
        self.assertEqual(subprocess.run(["sh", "-n", os.path.join(ROOT, "packaging/matryoshka-gxfp/root/usr/sbin/matryoshka-gxfp")]).returncode, 0)


class Headphones(unittest.TestCase):
    def test_dev_key(self):
        self.assertEqual(audiodev.dev_key("bluez_output.aa_bb_cc_dd_ee_ff.1"), "bt:AA_BB_CC_DD_EE_FF")
        self.assertEqual(audiodev.dev_key("alsa_output.usb-Kenshi_H2-00.analog-stereo"), "usb:Kenshi_H2-00")
        self.assertIsNone(audiodev.dev_key("alsa_output.pci-0000_00_1f.3.analog-stereo"))

    def test_remember_per_device(self):
        d = {"sink": "", "volumes": {}}
        sinks = [{"name": "alsa_output.usb-Kenshi_H2-00.analog-stereo", "port": "analog-output", "volume": "35%"},
                 {"name": "alsa_output.pci-x.analog-stereo", "port": "analog-output-speaker", "volume": "70%"}]
        audiodev.remember(d, sinks, sinks[1]["name"])
        self.assertEqual(audiodev.saved_volume(d, "alsa_output.usb-Kenshi_H2-00.iec958-stereo", "analog-output"), "35%")
        self.assertEqual(audiodev.saved_volume(d, sinks[1]["name"], sinks[1]["port"]), "70%")
        sinks[0]["volume"] = "100%"
        audiodev.remember(d, sinks, sinks[1]["name"], hold=(sinks[0]["name"],))
        self.assertEqual(audiodev.saved_volume(d, sinks[0]["name"], "analog-output"), "35%")

    def test_reapply_only_foreign(self):
        self.assertTrue(audiodev.needs_reapply("100%", "35%", "60%"))
        self.assertTrue(audiodev.needs_reapply("60%", "35%", "60%"))
        self.assertFalse(audiodev.needs_reapply("50%", "35%", "60%"))
        self.assertFalse(audiodev.needs_reapply("35%", "35%", "60%"))

    def test_new_sinks(self):
        self.assertEqual(audiodev.new_sinks({"a": "x"}, {"a": "x", "b": ""}), ["b"])
        self.assertEqual(audiodev.new_sinks(None, {"a": "x"}), [])


class Tiho(unittest.TestCase):
    def test_repack(self):
        s = text("packaging/tiho-browser/repack.sh")
        self.assertIn("StartupWMClass", s)
        self.assertIn("--class", s)
        self.assertIn("MPL", text("packaging/tiho-browser/copyright.in"))


if __name__ == "__main__":
    unittest.main()
