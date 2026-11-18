import json, os, random, stat, subprocess, sys, tempfile, unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INC = os.path.join(ROOT, "config", "includes.chroot_after_packages")
LIB = os.path.join(INC, "usr", "lib", "matryoshka")
sys.path.insert(0, LIB)

import avoff, deskicons, facehold, taskmodel, threatscan, vmram, waydroid_net


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as f:
        return f.read()


def simulate(lines, results):
    i = 0
    while i < len(lines):
        parts = lines[i].split("\t")
        ctl, mod = parts[1], parts[2].split()[0]
        if mod == "pam_deny.so":
            return False
        if mod == "pam_permit.so":
            return True
        ok = results[mod]
        if ctl.startswith("["):
            acts = dict(x.split("=") for x in ctl.strip("[]").split())
            act = acts.get("success" if ok else "default", acts.get("default"))
            i += 1 + (int(act) if act.isdigit() else 0)
        else:
            i += 1
    return False


def login_lines(face, finger):
    auth = os.path.join(INC, "usr", "sbin", "matryoshka-auth")
    sh = r'''
HOWDY=/bin/true; FP_LOGIN_ARGS="max-tries=3 timeout=15"; EMPTY=/bin/true
mod() { return 0; }
eval "$(sed -n '/^login_stack()/,/^}/p' "$AUTH")"
login_stack "$1" "$2"
'''
    env = dict(os.environ, AUTH=auth)
    return subprocess.run(["bash", "-c", sh, "x", str(face), str(finger)], capture_output=True, text=True, env=env).stdout.splitlines()


class Threat(unittest.TestCase):
    def test_eicar_and_miner_not_plain_text(self):
        self.assertIn("EICAR", threatscan.scan_bytes(b"xx EICAR-STANDARD-ANTIVIRUS-TEST-FILE yy", "note.txt"))
        self.assertIn("miner-xmrig", threatscan.scan_bytes(b"\0xmrig", "note.txt"))
        self.assertIn("miner-xmrig", threatscan.scan_bytes(b"xmrig", "tool.exe"))
        self.assertEqual(threatscan.scan_bytes(b"this text mentions xmrig", "note.txt"), [])

    def test_quick_launch_does_not_call_clamscan(self):
        import av
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"hello")
            f.flush()
            with mock.patch.object(av, "engine_ping", return_value=False), \
                    mock.patch.object(av, "own_release", return_value=False), \
                    mock.patch.object(av.C, "run", return_value=subprocess.CompletedProcess([], 1, "", "")) as run:
                res = av.scan(f.name, quick=True)
            cmds = [c.args[0][0] for c in run.call_args_list]
            self.assertNotIn("clamscan", cmds)
            self.assertNotIn("clamdscan", cmds)
            self.assertEqual(res["engine"], "fast")
            self.assertFalse(res["malicious"])

    def test_known_string_blocks_without_clam(self):
        import av
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE")
            f.flush()
            with mock.patch.object(av, "engine_ping", return_value=False), \
                    mock.patch.object(av, "own_release", return_value=False), \
                    mock.patch.object(av.C, "run", return_value=subprocess.CompletedProcess([], 1, "", "")):
                res = av.scan(f.name, quick=True)
            self.assertTrue(res["malicious"])
            self.assertIn("EICAR", res["threat"])

    def test_launch_policy_and_no_exec_after_hit(self):
        import av, run, scangate
        self.assertFalse(run.launch_scan("deb", True, False))
        self.assertFalse(run.launch_scan("exe", False, False))
        self.assertFalse(run.launch_scan("exe", True, True))
        self.assertTrue(run.launch_scan("exe", True, False))
        self.assertTrue(run.launch_scan("msi", True, False))
        with mock.patch.object(run, "launch_scan", return_value=True), \
                mock.patch.object(scangate, "check", return_value={"malicious": True, "activator": False}), \
                mock.patch.object(av, "dialog") as dialog, \
                mock.patch("subprocess.Popen") as popen:
            self.assertEqual(run.main("/tmp/pay.exe"), 4)
        dialog.assert_called()
        popen.assert_not_called()


class Face(unittest.TestCase):
    def test_five_minutes(self):
        self.assertFalse(facehold.allow_face(1000, [701]))
        self.assertTrue(facehold.allow_face(1000, [700]))
        self.assertFalse(facehold.allow_face(1000, []))

    def test_pam_writes_stamp_and_respects_wake(self):
        with tempfile.TemporaryDirectory() as d:
            user = os.path.join(d, "face-hold")
            wake = os.path.join(d, "wake")
            self.assertEqual(facehold.pam_exit(1000, user, wake), 1)
            self.assertEqual(facehold.read_stamp(user), 1000)
            self.assertEqual(facehold.pam_exit(1100, user, wake), 1)
            self.assertEqual(facehold.pam_exit(1300, user, wake), 0)
            open(wake, "w").write("2000\n")
            self.assertEqual(facehold.pam_exit(2100, user, wake), 1)
            self.assertEqual(facehold.pam_exit(2300, user, wake), 0)

    def test_scanner_before_face(self):
        lines = login_lines(1, 1)
        mods = [x.split()[-1] if "pam_" not in x else x.split("\t")[-1].split()[0] for x in lines]
        self.assertLess(mods.index("pam_fprintd.so"), mods.index("pam_python.so"))
        self.assertTrue(simulate(lines, {"pam_unix.so": True, "pam_exec.so": False, "pam_fprintd.so": False, "pam_python.so": False}))
        self.assertFalse(simulate(lines, {"pam_unix.so": False, "pam_exec.so": False, "pam_fprintd.so": True, "pam_python.so": True}))
        self.assertTrue(simulate(lines, {"pam_unix.so": False, "pam_exec.so": True, "pam_fprintd.so": True, "pam_python.so": False}))
        self.assertTrue(simulate(lines, {"pam_unix.so": False, "pam_exec.so": True, "pam_fprintd.so": False, "pam_python.so": True}))
        self.assertFalse(simulate(lines, {"pam_unix.so": False, "pam_exec.so": True, "pam_fprintd.so": False, "pam_python.so": False}))
        auth = read(INC, "usr", "sbin", "matryoshka-auth")
        lock = auth.split("apply_lock()", 1)[1].split("admin_file()", 1)[0]
        self.assertLess(lock.index("face-lock-ok"), lock.index("pam_python.so $HOWDY"))
        self.assertEqual(subprocess.run(["bash", "-n", os.path.join(INC, "usr", "sbin", "matryoshka-auth")]).returncode, 0)


class Memory(unittest.TestCase):
    def test_guest_on_eight_gigabytes(self):
        self.assertEqual(vmram.fit_ram("4G", 8192, 6000), 4096)
        self.assertEqual(vmram.fit_ram("4G", 8192, 7000), 4096)
        self.assertEqual(vmram.fit_ram("4G", 8192, 2000), 1280)
        self.assertEqual(vmram.fit_ram("4G", 16384, 12000), 4096)
        text, mb = vmram.rewrite_ram('guest_os="windows"\nram="4G"\n', 8192, 2000)
        self.assertEqual(mb, 1280)
        self.assertIn('ram="1280M"', text)
        self.assertTrue(vmram.should_pause_clam(8192, 3500))
        self.assertFalse(vmram.should_pause_clam(8192, 4096))
        self.assertFalse(vmram.should_pause_clam(16384, 1000))

    def test_task_rows(self):
        stat = "1 (sleep) S 1 1 1 0 -1 4194304 0 0 0 0 5 7"
        self.assertEqual(taskmodel.cpu_jiffies(stat), 12)
        self.assertEqual(taskmodel.row_why("xmrig", 10, "/usr/bin/xmrig"), "майнер")
        self.assertEqual(taskmodel.row_why("bash", 10, "/tmp/a (deleted)"), "файл процесса удалён")
        self.assertEqual(taskmodel.row_why("stress", 95, "/usr/bin/stress"), "высокая загрузка процессора")
        self.assertEqual(taskmodel.row_why("kworker/0", 99, ""), "")
        self.assertTrue(taskmodel.low_mem(399999))
        self.assertFalse(taskmodel.low_mem(400000))
        self.assertIn("подозр", taskmodel.ask_text([{"name": "x", "pid": 1, "cpu": 1, "rss_kb": 0, "why": ""}]).lower())
        self.assertIn("python3 /usr/lib/matryoshka/taskman.py", read(INC, "usr", "share", "applications", "matryoshka-taskmanager.desktop"))


class AvOff(unittest.TestCase):
    def test_phrases_password_and_suspicion(self):
        phrases = avoff.challenge(random.Random(1))
        self.assertIn(avoff.FIXED, phrases)
        self.assertEqual(len({avoff.norm(p) for p in phrases}), 3)
        self.assertTrue(avoff.phrases_ok(phrases, list(phrases)))
        self.assertFalse(avoff.phrases_ok(phrases, [phrases[0], phrases[0], phrases[1]]))
        self.assertTrue(avoff.passwords_ok([True, True, True]))
        self.assertFalse(avoff.passwords_ok([True, True, False]))

        def ok(args, input=None):
            return subprocess.CompletedProcess(args, 0 if input in (b"secret\n", b"secret") else 1)

        self.assertTrue(avoff.password_ok("ivan", "secret", ok))
        self.assertFalse(avoff.password_ok("ivan", "nope", ok))
        self.assertTrue(avoff.is_suspicious(False, ["python /usr/lib/matryoshka/agent.py"]))
        self.assertFalse(avoff.is_suspicious(False, ["plasmashell"]))
        self.assertTrue(avoff.is_suspicious(True, []))
        token = {"kind": "usb", "id": "abcd:1234"}
        self.assertTrue(avoff.token_present(token, [{"kind": "usb", "id": "ABCD:1234"}]))
        self.assertFalse(avoff.token_present(token, avoff.parse_usb("Bus 001 Device 001: ID 1d6b:0002 Linux Foundation 2.0 root hub")))
        wifi = avoff.parse_wifi("yes:AA\\:BB\\:CC\\:DD\\:EE\\:FF:Home")
        self.assertEqual(wifi[0]["id"], "AA:BB:CC:DD:EE:FF")
        with mock.patch.object(avoff, "is_suspicious", return_value=True):
            self.assertEqual(avoff.enroll("usb", "abcd:1234", "key"), 5)
        self.assertEqual(avoff.finish_file("ivan", "/tmp/../etc/passwd"), 2)
        self.assertEqual(avoff.finish_file("ivan", "/etc/passwd"), 2)
        path = avoff.write_payload("{}\n")
        try:
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
        finally:
            os.remove(path)
        root = read(LIB, "root.sh")
        self.assertIn("av-off-finish)", root)
        self.assertIn("waydroid-net)", root)
        self.assertNotRegex(root, r"ufw (allow|default allow)")
        sudo = read(INC, "etc", "sudoers.d", "matryoshka")
        self.assertIn("av-pause", sudo)
        self.assertIn("waydroid-net", sudo)
        self.assertNotIn("av-off", sudo)


class Desktop(unittest.TestCase):
    def test_archive_icon_and_trash(self):
        with tempfile.TemporaryDirectory() as d:
            good = os.path.join(d, "matryoshka-archive-zoom.desktop")
            open(good, "w", encoding="utf-8").write("[Desktop Entry]\nType=Application\nName=Zoom\nExec=zoom\n")
            bad = os.path.join(d, "matryoshka-center.desktop")
            open(bad, "w", encoding="utf-8").write("[Desktop Entry]\nType=Application\nName=C\nExec=c\n")
            self.assertTrue(deskicons.wanted(os.path.basename(good), good))
            self.assertFalse(deskicons.wanted(os.path.basename(bad), bad))
            os.makedirs(os.path.join(d, "Desktop"))
            icon = deskicons.trash_icon(d)
            self.assertTrue(icon.endswith("Корзина.desktop"))
            self.assertIn("trash:/", read(icon))

    def test_cloud_never_home(self):
        src = read(LIB, "cloud.py")
        ns = {}
        start = src.index("def click_action")
        exec(src[start:src.index("\ndef ", start + 1)], ns)
        self.assertEqual(ns["click_action"](True, False), "open")
        self.assertEqual(ns["click_action"](False, True), "mount")
        self.assertEqual(ns["click_action"](False, False), "settings")
        body = src.split("def openf", 1)[1].split("\n    def ", 1)[0]
        self.assertNotIn("C.HOME", body)
        self.assertIn('["xdg-open", MNT]', body)

    def test_session_does_not_suspend_other_user(self):
        s = read(LIB, "session.py")
        body = s.split("def watch_session", 1)[1].split("\ndef ", 1)[0]
        self.assertNotIn("suspend_hw(True)", body)
        self.assertNotIn("ensure_devices", body)
        self.assertIn("nudge_wireplumber()", body)
        self.assertIn("Hidden=true", s)
        self.assertIn("face-hold", s)


class Boot(unittest.TestCase):
    def test_live_menu_is_russian_gfx_with_english(self):
        cfg = read(ROOT, "config", "bootloaders", "grub-pc", "grub.cfg")
        theme = read(ROOT, "config", "bootloaders", "grub-pc", "theme.cfg")
        self.assertIn("Матрёшка", cfg)
        self.assertIn('set mlang="English"', cfg)
        self.assertIn('set mlang="Русский"', cfg)
        self.assertNotIn("--hotkey=e", cfg)
        self.assertIn("terminal_output gfxterm", theme)
        self.assertIn("dejavu_16.pf2", theme)
        self.assertIn("light-gray/blue", theme)
        lang = os.path.join(INC, "etc", "grub.d", "01_matryoshka_lang")
        self.assertEqual(subprocess.run(["sh", "-n", lang]).returncode, 0)
        text = read(lang)
        self.assertIn("lang=ru_RU", text)
        self.assertIn('menuentry "English"', text)
        self.assertIn("unicode.pf2", text)
        self.assertEqual(read(INC, "etc", "default", "grub.d", "matryoshka-lang.cfg").strip(), "GRUB_LANG=ru_RU")
        up = read(LIB, "upgrade.sh")
        self.assertIn("WINBEFORE", up)
        self.assertIn("меню загрузки возвращено", up)
        self.assertIn("01_matryoshka_lang", up)

    def test_net_keeps_bbr_and_drops_server_fastopen(self):
        s = read(INC, "etc", "sysctl.d", "90-matryoshka-net.conf")
        self.assertIn("tcp_congestion_control=bbr", s)
        self.assertIn("default_qdisc=fq", s)
        self.assertIn("tcp_fastopen=1", s)
        self.assertNotIn("tcp_fastopen=3", s)
        self.assertIn("tcp_notsent_lowat=131072", s)
        self.assertIn("rmem_max=16777216", s)

    def test_zoom_and_clamd_and_waydroid(self):
        z = read(LIB, "zoom-run")
        self.assertIn("unset", z)
        self.assertIn("LD_PRELOAD", z)
        self.assertIn('BIN="$DIR/zoom"', z)
        self.assertEqual(subprocess.run(["bash", "-n", os.path.join(LIB, "zoom-run")]).returncode, 0)
        c = read(LIB, "clamd-lazy.sh")
        self.assertIn("KEEP_KB=10485760", c)
        self.assertIn("/etc/matryoshka/av-disabled", c)
        self.assertIn("big && exit 0", c)
        self.assertEqual(subprocess.run(["sh", "-n", os.path.join(LIB, "clamd-lazy.sh")]).returncode, 0)
        w = read(LIB, "waydroid_ctl.py")
        self.assertIn("WindowCloseButtonHint", w)
        self.assertIn("WindowMinimizeButtonHint", w)
        self.assertIn('C.root("waydroid-net"', w)
        calls = []
        seen = set()

        class R:
            def __init__(self, code):
                self.returncode = code

        def run(args):
            calls.append(tuple(args))
            if "-C" in args:
                key = tuple(args)
                if key in seen:
                    return R(0)
                seen.add(key)
                return R(1)
            return R(0)

        self.assertEqual(waydroid_net.apply(run, True, True), 0)
        self.assertEqual(waydroid_net.apply(run, True, True), 0)
        adds = [c for c in calls if "-I" in c or "-A" in c]
        self.assertEqual(len(adds), 3)
        self.assertTrue(any("ip_forward=1" in " ".join(c) for c in calls))
        face = read(INC, "usr", "share", "applications", "kcm_matryoshka_face.desktop")
        self.assertIn("Распознавание лица", face)
        self.assertIn("X-KDE-Weight=51", face)
        self.assertIn("matryoshka-center users", face)


if __name__ == "__main__":
    unittest.main()
