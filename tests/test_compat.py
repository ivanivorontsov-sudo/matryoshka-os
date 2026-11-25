import os, sys, io, struct, zipfile, plistlib, tempfile, subprocess, unittest, configparser

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INC = os.path.join(ROOT, "config", "includes.chroot_after_packages")
LIB = os.path.join(INC, "usr", "lib", "matryoshka")
sys.path.insert(0, LIB)
import compat


def macho32(cpu, crypt=None):
    cmds = b""
    n = 0
    if crypt is not None:
        cmds += struct.pack("<IIIII", 0x21, 20, 0x1000, 0x1000, crypt)
        n += 1
    return struct.pack("<IiiIIII", 0xFEEDFACE, cpu, 0, 2, n, len(cmds), 0) + cmds


def macho64(cpu):
    return struct.pack("<IiiIIIII", 0xFEEDFACF, cpu, 0, 2, 0, 0, 0, 0)


def fat(*slices):
    head = struct.pack(">II", 0xCAFEBABE, len(slices))
    off = 4096
    body = b""
    for cpu, data in slices:
        head += struct.pack(">iiIII", cpu, 0, off + len(body), len(data), 12)
        body += data
    return head.ljust(off, b"\0") + body


def ipa(binary, minos="3.0"):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("Payload/Game.app/Info.plist", plistlib.dumps({"CFBundleExecutable": "Game", "MinimumOSVersion": minos}))
        z.writestr("Payload/Game.app/Game", binary)
    f = tempfile.NamedTemporaryFile(suffix=".ipa", delete=False)
    f.write(b.getvalue()); f.close()
    return f.name


class MachO(unittest.TestCase):
    def test_old_armv6(self):
        self.assertEqual(compat.ios_verdict(compat.ipa_info(ipa(macho32(compat.CPU_ARM)))), "ok")

    def test_arm64_only(self):
        self.assertEqual(compat.ios_verdict(compat.ipa_info(ipa(macho64(compat.CPU_ARM64)))), "arm64")

    def test_fat_keeps_32bit(self):
        p = ipa(fat((compat.CPU_ARM, macho32(compat.CPU_ARM)), (compat.CPU_ARM64, macho64(compat.CPU_ARM64))))
        self.assertEqual(compat.ios_verdict(compat.ipa_info(p)), "ok")

    def test_encrypted(self):
        self.assertEqual(compat.ios_verdict(compat.ipa_info(ipa(macho32(compat.CPU_ARM, crypt=1)))), "encrypted")

    def test_decrypted_flag_zero(self):
        self.assertEqual(compat.ios_verdict(compat.ipa_info(ipa(macho32(compat.CPU_ARM, crypt=0)))), "ok")

    def test_new_ios(self):
        self.assertEqual(compat.ios_verdict(compat.ipa_info(ipa(macho32(compat.CPU_ARM), minos="6.0"))), "new")

    def test_macos_app_dir(self):
        d = tempfile.mkdtemp(suffix=".app")
        os.makedirs(os.path.join(d, "Contents", "MacOS"))
        plistlib.dump({"CFBundleExecutable": "Tool"}, open(os.path.join(d, "Contents", "Info.plist"), "wb"))
        open(os.path.join(d, "Contents", "MacOS", "Tool"), "wb").write(macho64(compat.CPU_X86_64))
        m = compat.app_info_dir(d)
        self.assertEqual(m["kind"], "macos")
        self.assertEqual(m["arch"][0]["cpu"], compat.CPU_X86_64)


class Detect(unittest.TestCase):
    def jar(self, manifest):
        f = tempfile.NamedTemporaryFile(suffix=".jar", delete=False); f.close()
        with zipfile.ZipFile(f.name, "w") as z:
            z.writestr("META-INF/MANIFEST.MF", manifest)
        return f.name

    def test_midlet(self):
        self.assertTrue(compat.is_midlet(self.jar("Manifest-Version: 1.0\nMIDlet-1: Game,/i.png,Game\nMIDlet-Name: Game\n")))

    def test_desktop_java(self):
        self.assertFalse(compat.is_midlet(self.jar("Manifest-Version: 1.0\nMain-Class: app.Main\n")))

    def test_jad(self):
        self.assertTrue(compat.is_midlet("/nonexistent/game.jad"))

    def pe(self, machine, subsystem):
        b = bytearray(1024)
        b[0:2] = b"MZ"; b[0x3c:0x40] = (0x80).to_bytes(4, "little")
        b[0x80:0x84] = b"PE\0\0"; b[0x84:0x86] = machine.to_bytes(2, "little")
        b[0x80 + 24 + 68:0x80 + 24 + 70] = subsystem.to_bytes(2, "little")
        f = tempfile.NamedTemporaryFile(suffix=".exe", delete=False); f.write(bytes(b)); f.close()
        return f.name

    def test_wince_arm_exe(self):
        self.assertTrue(compat.is_wince_exe(self.pe(0x01c2, 9)))

    def test_windows_exe_stays_wine(self):
        self.assertFalse(compat.is_wince_exe(self.pe(0x014c, 2)))
        self.assertFalse(compat.is_wince_exe(self.pe(0x8664, 2)))

    def test_cab(self):
        f = tempfile.NamedTemporaryFile(suffix=".cab", delete=False); f.write(b"MSCF\0\0\0\0" + b"x" * 64 + b"GAME.000" + b"_setup.xml"); f.close()
        self.assertTrue(compat.is_wince_cab(f.name))
        g = tempfile.NamedTemporaryFile(suffix=".cab", delete=False); g.write(b"MSCF\0\0\0\0" + b"driver.inf"); g.close()
        self.assertFalse(compat.is_wince_cab(g.name))

    def test_xap(self):
        f = tempfile.NamedTemporaryFile(suffix=".xap", delete=False); f.close()
        with zipfile.ZipFile(f.name, "w") as z:
            z.writestr("WMAppManifest.xml", "<Deployment/>")
            z.writestr("AppManifest.xaml", "<Deployment/>")
        self.assertTrue(compat.is_wp_xap(f.name))
        g = tempfile.NamedTemporaryFile(suffix=".xap", delete=False); g.close()
        with zipfile.ZipFile(g.name, "w") as z:
            z.writestr("AppManifest.xaml", "<Deployment/>")
        self.assertFalse(compat.is_wp_xap(g.name))


class Messages(unittest.TestCase):
    def setUp(self):
        os.environ["MATRYOSHKA_COMPAT_QUIET"] = "1"
        os.environ["MATRYOSHKA_COMPAT"] = tempfile.mkdtemp()
        import importlib
        importlib.reload(compat)

    def tearDown(self):
        os.environ.pop("MATRYOSHKA_COMPAT", None)
        import importlib
        importlib.reload(compat)

    def test_windows_phone_is_honest(self):
        r = subprocess.run([sys.executable, os.path.join(LIB, "compat.py"), "wp"], capture_output=True, text=True, env=dict(os.environ))
        self.assertIn("не существует", r.stdout)

    def test_missing_layer(self):
        r = subprocess.run([sys.executable, os.path.join(LIB, "compat.py"), "j2me"], capture_output=True, text=True, env=dict(os.environ))
        self.assertIn("не установлен", r.stdout)

    def test_status(self):
        ids = [s["id"] for s in compat.status()]
        self.assertEqual(ids, ["macos", "ios", "inferno", "j2me", "symbian", "wm", "wp"])


class Integration(unittest.TestCase):
    def test_no_comments_in_code(self):
        for f in ("compat.py", "compat-setup.sh"):
            for line in open(os.path.join(LIB, f), encoding="utf-8"):
                s = line.strip()
                self.assertFalse(s.startswith("#") and not s.startswith("#!"), f + ": " + s)

    def test_shell_syntax(self):
        self.assertEqual(subprocess.run(["sh", "-n", os.path.join(LIB, "compat-setup.sh")]).returncode, 0)
        self.assertEqual(subprocess.run(["sh", "-n", os.path.join(LIB, "netup.sh")]).returncode, 0)

    def test_desktop_and_mime(self):
        c = configparser.RawConfigParser(); c.optionxform = str
        c.read(os.path.join(INC, "usr", "share", "applications", "matryoshka-compat.desktop"), encoding="utf-8")
        mt = c["Desktop Entry"]["MimeType"]
        for m in ("application/x-ios-app", "application/x-apple-diskimage", "application/vnd.symbian.install", "text/vnd.sun.j2me.app-descriptor", "application/vnd.ms-cab-compressed", "application/x-windows-phone-xap"):
            self.assertIn(m, mt)
        x = open(os.path.join(INC, "usr", "share", "mime", "packages", "matryoshka-compat.xml"), encoding="utf-8").read()
        self.assertIn('glob pattern="*.ipa"', x)
        self.assertIn('glob pattern="*.xap"', x)
        apps = open(os.path.join(INC, "etc", "xdg", "mimeapps.list"), encoding="utf-8").read()
        self.assertIn("application/x-ios-app=matryoshka-compat.desktop", apps)

    def test_service_enabled_by_hook(self):
        h = open(os.path.join(ROOT, "config", "hooks", "live", "0600-matryoshka.hook.chroot"), encoding="utf-8").read()
        self.assertIn("matryoshka-compat-setup.service", h)
        self.assertTrue(os.path.exists(os.path.join(INC, "etc", "systemd", "system", "matryoshka-compat-setup.service")))

    def test_no_firmware_or_store_files(self):
        bad = (".ipsw", ".ipa", ".rpkg", ".rom", ".sis", ".sisx", ".xap", ".cab", ".jar", ".dmg")
        for d, _s, files in os.walk(INC):
            if "/opt/" in d + "/":
                continue
            for f in files:
                self.assertFalse(f.lower().endswith(bad), os.path.join(d, f))

    def test_run_routes_new_types(self):
        t = open(os.path.join(LIB, "run.py"), encoding="utf-8").read()
        self.assertIn("compat.run_jar(path)", t)
        self.assertIn("compat.is_wince_exe(path)", t)


if __name__ == "__main__":
    unittest.main()
