import json, os, random, shutil, stat, subprocess, sys, tempfile, unittest
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
        self.assertNotIn("Hidden=true", s)
        self.assertIn("loadModule", s)
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
        late = os.path.join(INC, "etc", "grub.d", "99_matryoshka_lang")
        self.assertEqual(subprocess.run(["sh", "-n", lang]).returncode, 0)
        self.assertEqual(subprocess.run(["sh", "-n", late]).returncode, 0)
        text = read(lang)
        self.assertIn("lang=ru_RU", text)
        self.assertNotIn("menuentry", text)
        self.assertIn('set default=0', text)
        self.assertIn("unicode.pf2", text)
        late_text = read(late)
        self.assertIn('menuentry "English"', late_text)
        self.assertIn('menuentry "Русский"', late_text)
        self.assertIn("set default=0", late_text)
        rescue = read(LIB, "rescue.sh")
        self.assertIn('6 "Продолжить загрузку"', rescue)
        self.assertIn('6 "Continue boot"', rescue)
        self.assertIn('9 "English"', rescue)
        self.assertEqual(subprocess.run(["bash", "-n", os.path.join(LIB, "rescue.sh")]).returncode, 0)
        for text in (text, late_text):
            body = text.split("cat <<'EOF'\n", 1)[1].split("\nEOF", 1)[0] + "\n"
            self.assertNotIn("||", body)
            self.assertNotIn("&&", body)
            if shutil.which("grub-script-check"):
                with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".cfg") as f:
                    f.write(body)
                    f.flush()
                    self.assertEqual(subprocess.run(["grub-script-check", f.name]).returncode, 0)
        self.assertEqual(read(INC, "etc", "default", "grub.d", "matryoshka-lang.cfg").strip(), "GRUB_LANG=ru_RU")
        up = read(LIB, "upgrade.sh")
        self.assertIn("WINBEFORE", up)
        self.assertIn("меню загрузки возвращено", up)
        self.assertIn("01_matryoshka_lang", up)
        self.assertIn("99_matryoshka_lang", up)
        self.assertIn("boot-reached", up)
        self.assertIn("FullCyrSlav-Terminus16.psf.gz", rescue)
        self.assertIn("setfont -C", rescue)
        font = os.path.join(INC, "usr", "share", "matryoshka", "fonts", "FullCyrSlav-Terminus16.psf.gz")
        self.assertTrue(os.path.isfile(font))
        ok = read(INC, "etc", "systemd", "system", "matryoshka-bootok.service")
        self.assertIn("bootok.sh", ok)
        self.assertNotIn("After=graphical.target", ok)

    def test_login_screen_shutdown_is_not_a_failed_boot(self):
        script = os.path.join(LIB, "bootcheck.sh")
        mark = os.path.join(LIB, "bootok.sh")
        d = tempfile.mkdtemp()
        fake = os.path.join(d, "systemctl")
        with open(fake, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$MATRYOSHKA_STATE/called\"\n")
        os.chmod(fake, 0o755)
        env = dict(os.environ)
        env["MATRYOSHKA_STATE"] = d
        env["MATRYOSHKA_SYSTEMCTL"] = fake
        for _ in range(4):
            self.assertEqual(subprocess.run(["sh", script], env=env).returncode, 0)
        self.assertEqual(open(os.path.join(d, "booting"), encoding="utf-8").read().strip(), "4")
        self.assertFalse(os.path.exists(os.path.join(d, "called")))
        self.assertEqual(subprocess.run(["sh", script], env=env).returncode, 0)
        self.assertIn("isolate matryoshka-rescue.target", open(os.path.join(d, "called"), encoding="utf-8").read())
        self.assertEqual(subprocess.run(["sh", mark], env=env).returncode, 0)
        self.assertTrue(os.path.isfile(os.path.join(d, "boot-reached")))
        self.assertFalse(os.path.exists(os.path.join(d, "booting")))
        os.remove(os.path.join(d, "called"))
        self.assertEqual(subprocess.run(["sh", script], env=env).returncode, 0)
        self.assertEqual(open(os.path.join(d, "booting"), encoding="utf-8").read().strip(), "1")
        self.assertFalse(os.path.exists(os.path.join(d, "called")))

    def test_net_keeps_bbr_and_drops_server_fastopen(self):
        s = read(INC, "etc", "sysctl.d", "90-matryoshka-net.conf")
        self.assertIn("tcp_congestion_control=bbr", s)
        self.assertIn("default_qdisc=fq", s)
        self.assertIn("tcp_fastopen=1", s)
        self.assertNotIn("tcp_fastopen=3", s)
        self.assertIn("tcp_notsent_lowat=131072", s)
        self.assertIn("rmem_max=16777216", s)
        self.assertIn("tcp_mtu_probing=1", s)
        self.assertNotIn("tcp_mtu_probing=2", s)
        self.assertNotIn("rmem_max=67108864", s)
        wifi = read(INC, "etc", "NetworkManager", "dispatcher.d", "20-matryoshka-wifi")
        self.assertIn("power_save off", wifi)
        self.assertNotIn("qdisc replace", wifi)
        self.assertIn("wifi.powersave=3", wifi)
        self.assertIn("phy80211", wifi)
        hard = read(INC, "etc", "sysctl.d", "80-matryoshka-hardening.conf")
        self.assertIn("rp_filter=2", hard)
        self.assertNotIn("rp_filter=1", hard)

    def test_zoom_and_clamd_and_waydroid(self):
        z = read(LIB, "zoom-run")
        self.assertIn("unset", z)
        self.assertIn("LD_PRELOAD", z)
        self.assertIn('BIN="$DIR/zoom"', z)
        self.assertIn('CLEAN="$HOME/.cache/matryoshka/zoom-bin"', z)
        self.assertIn("xdg-open", z)
        self.assertEqual(subprocess.run(["bash", "-n", os.path.join(LIB, "zoom-run")]).returncode, 0)
        c = read(LIB, "clamd-lazy.sh")
        self.assertIn("KEEP_KB=10485760", c)
        self.assertIn("/etc/matryoshka/av-disabled", c)
        self.assertIn("big && exit 0", c)
        self.assertEqual(subprocess.run(["sh", "-n", os.path.join(LIB, "clamd-lazy.sh")]).returncode, 0)
        w = read(LIB, "waydroid_ctl.py")
        self.assertIn("WindowCloseButtonHint", w)
        self.assertIn("WindowMinimizeButtonHint", w)
        self.assertIn("WindowStaysOnTopHint", w)
        self.assertIn('persist.waydroid.multi_windows", "false"', w)
        self.assertIn('persist.waydroid.width", str(w)', w)
        self.assertIn('persist.waydroid.height", str(h)', w)
        self.assertIn("navigation_mode", w)
        self.assertIn('"Домой"', w)
        self.assertIn('"Приложения"', w)
        self.assertIn('"Закрыть"', w)
        self.assertIn("show_ime_with_hard_keyboard", w)
        self.assertIn("policy_control", w)
        self.assertIn('mtu", "1500"', w)
        rules = read(LIB, "session.py")
        self.assertNotIn('(?i).*waydroid.*', rules)
        self.assertIn('noborderrule": "2"', rules)
        self.assertIn('maximizevertrule": "3"', rules)
        self.assertIn('placementrule": "3"', rules)
        self.assertNotIn('maximizevertrule": "2"', rules)
        self.assertNotIn('maximizehorizrule": "2"', rules)
        self.assertIn("dosbox-x", rules)
        self.assertIn('fullscreenrule": "2"', rules)
        self.assertIn("matryoshka-waydroid", rules)
        self.assertIn("KWIN_DROP", rules)
        self.assertIn("Файлы DOS", rules)
        self.assertIn('sudo", "-n", "/usr/lib/matryoshka/root.sh", "waydroid-net"', w)
        self.assertNotIn("pkexec", w)
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
        ttl = [c for c in adds if "TTL" in c]
        self.assertEqual(len(ttl), 1)
        extra = len(waydroid_net.input_rules()) + len(waydroid_net.mss_clamp_rules())
        self.assertEqual(len(adds) - len(ttl), len(waydroid_net.rules()) + extra)
        self.assertIn("--ttl-set", ttl[0])
        self.assertIn("65", ttl[0])
        self.assertNotIn("128", ttl[0])
        self.assertFalse(any("conntrack" in c for c in adds))
        self.assertTrue(any("--clamp-mss-to-pmtu" in c for c in adds))
        self.assertFalse(any("--set-mss" in c for c in adds))
        self.assertTrue(any("--dport" in c and "53" in c for c in adds))
        self.assertTrue(any("--dport" in c and "67" in c for c in adds))
        self.assertEqual(waydroid_net.HOST_TTL, "65")
        self.assertEqual(waydroid_net.GUEST_TTL, "66")
        self.assertFalse(waydroid_net.guest_ttl("999999"))
        self.assertFalse(any("CHECKSUM" in c for c in adds))
        self.assertTrue(any("TCPMSS" in c and "-D" in c and "1200" in c for c in calls))
        self.assertTrue(any("CHECKSUM" in c and "-D" in c and "tcp" in c for c in calls))
        self.assertTrue(any("CHECKSUM" in c and "-D" in c and "udp" in c for c in calls))
        joined = "\n".join(" ".join(c) for c in calls)
        self.assertIn("ip_forward=1", joined)
        self.assertIn("tcp_mtu_probing=1", joined)
        self.assertNotIn("tcp_mtu_probing=0", joined)
        net = read(LIB, "waydroid_net.py")
        self.assertIn("iptables-legacy", net)
        self.assertIn("net/ipv4/tcp_mtu_probing", net)
        self.assertIn("77.88.8.8", net)
        self.assertIn('disable_ipv6", "0"', net)
        self.assertNotIn('disable_ipv6", "1"', net)
        self.assertIn("accept_ra", net)
        self.assertIn("LimitNPROC=infinity", read(INC, "etc", "systemd", "system", "bluetooth.service.d", "matryoshka.conf"))
        self.assertIn("--noplugin=sap", read(INC, "etc", "systemd", "system", "bluetooth.service.d", "matryoshka.conf"))
        self.assertIn("rfkill unblock bluetooth", read(LIB, "bluetooth-boot.sh"))
        self.assertIn("captive_portal_mode", read(INC, "usr", "local", "bin", "waydroid"))
        self.assertIn("wifi_secret.py", read(INC, "etc", "NetworkManager", "dispatcher.d", "30-matryoshka-wifi-key"))
        self.assertIn("apparmor_restrict_unprivileged_userns=0", read(INC, "etc", "sysctl.d", "82-matryoshka-userns.conf"))
        self.assertIn("disable_ipv6=0", net)
        self.assertNotIn("disable_ipv6=1", net)
        self.assertFalse(waydroid_net.offload_off("nosuch-iface"))
        self.assertEqual(waydroid_net.links("nosuch-iface"), [])
        import ctypes
        self.assertEqual(ctypes.sizeof(waydroid_net._Ifreq), 40)
        self.assertEqual(waydroid_net.usable_nameservers("nameserver 127.0.0.53\nnameserver 192.168.43.1\n"), ["192.168.43.1"])
        stub = "nameserver 127.0.0.53\n"
        real = "nameserver 192.168.43.1\n"
        current = "dnsmasq --interface=waydroid0 --listen-address 192.168.240.1"
        self.assertTrue(waydroid_net.needs_dns(stub, ["192.168.43.1"], current))
        self.assertFalse(waydroid_net.needs_dns(real, ["192.168.43.1"], current))
        self.assertFalse(waydroid_net.needs_dns(stub, ["192.168.43.1"], ""))
        fixed = current + " --no-resolv --no-hosts --server 192.168.43.1"
        self.assertFalse(waydroid_net.needs_dns(stub, ["192.168.43.1"], fixed))
        argv = waydroid_net.dnsmasq_argv(["192.168.43.1"], "nobody")
        self.assertIn("--no-resolv", argv)
        self.assertIn("--no-hosts", argv)
        self.assertNotIn("--strict-order", argv)
        self.assertIn("192.168.43.1", argv)
        self.assertNotIn("127.0.0.53", argv)
        hook = read(INC, "etc", "systemd", "system", "waydroid-container.service.d", "matryoshka-net.conf")
        self.assertIn("waydroid_net.py apply", hook)
        self.assertIn("private_dns_mode", w)
        wrap = read(INC, "usr", "local", "bin", "waydroid")
        self.assertIn("/usr/bin/waydroid", wrap)
        self.assertIn("waydroid-net", wrap)
        self.assertIn("waydroid_ctl.py prepare", wrap)
        self.assertNotIn("waydroid_ctl.py bar", wrap)
        self.assertIn("qemu.hw.mainkeys", wrap)
        import waydroid_ctl
        self.assertTrue(waydroid_ctl.window_is_trap("persist.waydroid.multi_windows = true\npersist.waydroid.width =\n"))
        self.assertFalse(waydroid_ctl.window_is_trap("persist.waydroid.multi_windows = false\npersist.waydroid.width = 1280\n"))
        self.assertFalse(waydroid_ctl.window_is_trap("persist.waydroid.multi_windows = false\npersist.waydroid.width = 1920\n"))
        self.assertEqual(waydroid_ctl.parse_xrandr("  1920x1080  60.00*+"), (1920, 984))
        self.assertIn("navigation_mode", wrap)
        face = read(INC, "usr", "share", "applications", "kcm_matryoshka_face.desktop")
        self.assertIn("Распознавание лица", face)
        self.assertIn("X-KDE-Weight=51", face)
        self.assertIn("matryoshka-center users", face)
        import dosbox
        text = dosbox.session_text("/p", "FESTA.EXE", "/d", "/h", "/s", "/pr")
        self.assertNotIn("ptsize=", text)
        self.assertNotIn("winperc=90", text)
        self.assertNotIn("winperc=100", text)
        self.assertIn("winperc=92", text)
        self.assertIn("stay.start(800)", read(LIB, "dosbox.py"))
        self.assertIn("maximize=false", text)
        self.assertIn("fullscreen=false", text)
        self.assertIn("output=ttf", text)
        self.assertNotIn("output=opengl", text)
        dosbox.LNG = os.path.join(tempfile.mkdtemp(), "ru.lng")
        open(dosbox.LNG, "w").close()
        self.assertEqual(dosbox.command("/tmp/x.conf")[:3], ["dosbox-x", "-lang", dosbox.LNG])
        self.assertIn("Добавить файл", read(LIB, "dosbox.py"))
        self.assertIn("Закрыть DOS", read(LIB, "dosbox.py"))
        run_text = read(LIB, "run.py")
        self.assertIn("MOZ_DISABLE_LAUNCHER_PROCESS", run_text)
        self.assertNotIn("MOZ_DISABLE_CONTENT_SANDBOX", run_text)
        self.assertIn("browser.tabs.inTitlebar", run_text)
        self.assertIn("Graphics", run_text)
        self.assertIn("--disable-dev-shm-usage", run_text)
        import run as runmod
        self.assertEqual(runmod.wine_argv("/tmp/firefox.exe")[-1], "-no-remote")
        self.assertIn("--no-sandbox", runmod.wine_argv("/tmp/chrome.exe"))
        self.assertEqual(runmod.wine_argv("/tmp/notepad.exe")[:3], ["wine", "start", "/unix"])
        external = read(INC, "usr", "share", "plasma", "systemsettings", "externalmodules", "kcm_matryoshka_face.desktop")
        self.assertIn("Type=Service", external)
        self.assertIn("X-KDE-ServiceTypes=SystemSettingsExternalApp", external)
        self.assertIn("system-administration", external)
        self.assertIn("Распознавание лица", external)
        users = read(INC, "usr", "share", "plasma", "systemsettings", "externalmodules", "kcm_matryoshka_users.desktop")
        self.assertIn("Вход по пальцу и лицу", users)
        setup = read(INC, "usr", "share", "applications", "matryoshka-login-setup.desktop")
        self.assertIn("matryoshka-center users", setup)
        so = os.path.join(INC, "usr", "lib", "x86_64-linux-gnu", "qt6", "plugins", "plasma", "kcms", "systemsettings", "kcm_users.so")
        blob = open(so, "rb").read()
        off = blob.find(b"\x28\xb5\x2f\xfd", 221000)
        self.assertGreater(off, 0)
        n = int.from_bytes(blob[off - 4:off], "big")
        frame = os.path.join(tempfile.mkdtemp(), "users.zst")
        open(frame, "wb").write(blob[off:off + n])
        out = frame + ".qml"
        self.assertEqual(subprocess.run(["zstd", "-d", "-f", "-o", out, frame]).returncode, 0)
        page = open(out, encoding="utf-8").read()
        self.assertIn("Записать лицо", page)
        self.assertIn("Записать отпечаток", page)
        self.assertIn("matryoshka-login://enroll", page)
        self.assertNotIn("not yet supported", page)
        self.assertIn("x-scheme-handler/matryoshka-login", setup)
        import zoomdoctor
        self.assertEqual(set(zoomdoctor.DOWNLOADS), {"latest-deb", "latest-tar", "7.2.5", "7.0.5", "6.6.11"})
        home = tempfile.mkdtemp()
        old = zoomdoctor.HOME
        zoomdoctor.HOME = home
        try:
            os.makedirs(os.path.join(home, ".zoom", "data"))
            open(os.path.join(home, ".zoom", "data", "zoomus.db"), "w").write("login")
            os.makedirs(os.path.join(home, ".zoom", "data", "GPUCache"))
            os.makedirs(os.path.join(home, ".cache", "zoom"))
            gone = zoomdoctor.clear_runtime_cache()
            self.assertTrue(os.path.isfile(os.path.join(home, ".zoom", "data", "zoomus.db")))
            self.assertFalse(os.path.isdir(os.path.join(home, ".cache", "zoom")))
            self.assertTrue(any("GPUCache" in p for p in gone))
            self.assertEqual(zoomdoctor.download_zoom("нет такого"), 2)
            browser = os.path.join(home, ".config", "vivaldi", "Default")
            os.makedirs(browser)
            open(os.path.join(browser, "Preferences"), "w", encoding="utf-8").write(json.dumps({"protocol_handler": {"excluded_schemes": {"zoommtg": True}}}))
            ff = os.path.join(home, ".mozilla", "firefox", "abc.default")
            os.makedirs(ff)
            open(os.path.join(ff, "handlers.json"), "w", encoding="utf-8").write("{}")
            changed = zoomdoctor.unblock_protocols(home, running=False)
            self.assertEqual(len(changed), 2)
            prefs = json.load(open(os.path.join(browser, "Preferences"), encoding="utf-8"))
            self.assertFalse(prefs["protocol_handler"]["excluded_schemes"]["zoommtg"])
            handlers = json.load(open(os.path.join(ff, "handlers.json"), encoding="utf-8"))
            self.assertEqual(handlers["schemes"]["zoommtg"]["action"], 4)
            self.assertEqual(zoomdoctor.unblock_protocols(home, running=True), [])
        finally:
            zoomdoctor.HOME = old
        opener = read(LIB, "zoom-open")
        self.assertIn("zoommtg:", opener)
        self.assertIn("zoomprc:", opener)
        self.assertIn("zoom-run", opener)
        desk = read(INC, "usr", "share", "applications", "matryoshka-zoom.desktop")
        self.assertIn("zoom-open %U", desk)
        self.assertIn("x-scheme-handler/zoommtg", desk)
        self.assertIn("x-scheme-handler/zoommtg=matryoshka-zoom.desktop", read(INC, "etc", "xdg", "mimeapps.list"))
        doctor = read(INC, "usr", "share", "applications", "matryoshka-zoom-doctor.desktop")
        self.assertIn("Name=Доктор Zoom", doctor)
        self.assertIn("Exec=matryoshka-zoom-doctor\n", doctor)
        self.assertNotIn("konsole", doctor)
        self.assertNotIn("NoDisplay", doctor)
        self.assertNotIn("--fix", doctor)
        self.assertTrue(zoomdoctor.gui_requested([]))
        self.assertFalse(zoomdoctor.gui_requested(["--fix"]))
        self.assertIn("setWindowTitle(\"Доктор Zoom\")", read(LIB, "zoomdoctor.py"))
        self.assertEqual(runmod.firefox_userjs('user_pref("browser.tabs.inTitlebar", false);\n'), 'user_pref("browser.tabs.inTitlebar", 0);\n')
        self.assertEqual(json.loads(runmod.firefox_policy())["policies"]["Preferences"]["browser.tabs.inTitlebar"], {"Value": 0, "Status": "locked"})
        policy = read(INC, "etc", "vivaldi", "policies", "managed", "matryoshka-zoom.json")
        self.assertIn("zoommtg", policy)
        self.assertIn("google.zoom.us", policy)
        self.assertIn("network.protocol-handler.external.zoommtg", read(INC, "etc", "firefox", "policies", "policies.json"))


class Clone(unittest.TestCase):
    def test_copies_stay_separate(self):
        import clone
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, "Документы"))
            os.makedirs(os.path.join(home, "Desktop"))
            desk = os.path.join(home, "apps")
            os.makedirs(desk)
            open(os.path.join(desk, "note.desktop"), "w", encoding="utf-8").write("[Desktop Entry]\nType=Application\nName[ru]=Блокнот\nExec=gedit %F\nIcon=text-editor\n")
            found = clone.programs(home, [desk])
            self.assertEqual(found[0]["name"], "Блокнот")
            self.assertEqual(found[0]["argv"], ["gedit"])
            made = clone.create(found[0], home)
            self.assertTrue(made["ok"], made)
            script = open(os.path.join(home, ".local/share/matryoshka/clones", made["id"], "run"), encoding="utf-8").read()
            self.assertIn("export HOME=", script)
            self.assertIn("gedit", script)
            self.assertTrue(os.path.islink(os.path.join(home, ".local/share/matryoshka/clones", made["id"], "home", "Документы")))
            again = clone.create(found[0], home)
            self.assertIn("копия 3", again["name"])
            gone = clone.remove(made["id"], home)
            self.assertTrue(gone["ok"])
            self.assertFalse(os.path.exists(os.path.join(home, ".local/share/matryoshka/clones", made["id"])))

    def test_android_user_and_wine_prefix(self):
        import clone
        self.assertEqual(clone.parse_user_id("Success: created user id 10\n"), 10)
        self.assertIsNone(clone.parse_user_id("id 0"))
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, "Desktop"))
            calls = []

            class R:
                def __init__(self, code, out=""):
                    self.returncode = code
                    self.stdout = out
                    self.stderr = ""

            def shell(args):
                calls.append(list(args))
                if "create-user" in args:
                    return R(0, "Success: created user id 12\n")
                return R(0, "")

            made = clone.create_android("com.example.App", "Чат", home, shell=shell)
            self.assertTrue(made["ok"], made)
            self.assertEqual(clone.clones(home)[0]["user"], 12)
            desk = open(made["desktop"], encoding="utf-8").read()
            self.assertIn("--user 12", desk)
            self.assertIn("-p com.example.App", desk)
            prefix = os.path.join(home, "pfx")
            os.makedirs(os.path.join(prefix, "drive_c", "App"))
            open(os.path.join(prefix, "system.reg"), "w").close()
            os.makedirs(os.path.join(prefix, "dosdevices"))
            os.symlink("/", os.path.join(prefix, "dosdevices", "z:"))
            exe = os.path.join(prefix, "drive_c", "App", "app.exe")
            open(exe, "wb").write(b"MZ")
            wine = clone.create_wine(exe, "Блок", home)
            self.assertTrue(wine["ok"], wine)
            copied = os.path.join(home, ".local/share/matryoshka/clones", wine["id"], "wine")
            self.assertTrue(os.path.isfile(os.path.join(copied, "drive_c", "App", "app.exe")))
            self.assertFalse(os.path.exists(os.path.join(copied, "dosdevices")))
            runner = open(os.path.join(home, ".local/share/matryoshka/clones", wine["id"], "run"), encoding="utf-8").read()
            self.assertIn("WINEPREFIX=", runner)
            self.assertIn("Graphics", runner)
            self.assertIn("start /unix", runner)
            self.assertIn("drive_c/App/app.exe", runner)

    def test_dos_copy_is_another_folder(self):
        import clone
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, "Desktop"))
            src = os.path.join(home, "CAD")
            os.makedirs(src)
            open(os.path.join(src, "FESTA.EXE"), "wb").write(b"MZ")
            open(os.path.join(src, "DATA.DAT"), "w").write("1")
            made = clone.create_dos(os.path.join(src, "FESTA.EXE"), home, "FESTA")
            self.assertTrue(made["ok"], made)
            copy = os.path.join(home, "DOS", "Копии", made["id"], "FESTA.EXE")
            self.assertTrue(os.path.isfile(copy))
            self.assertNotEqual(os.path.realpath(copy), os.path.realpath(os.path.join(src, "FESTA.EXE")))
            self.assertIn("dosbox.py", open(made["desktop"], encoding="utf-8").read())
            clone.remove(made["id"], home)
            self.assertFalse(os.path.exists(os.path.join(home, "DOS", "Копии", made["id"])))

    def test_kickoff_keeps_search_for_a_minute(self):
        import kickoff_memory
        self.assertTrue(kickoff_memory.kept(1_000, 61_000))
        self.assertFalse(kickoff_memory.kept(1_000, 61_001))
        plasma = os.path.join(ROOT, "chroot", "usr", "share", "plasma", "plasmoids")
        self.assertTrue(os.path.isdir(plasma), plasma)
        with tempfile.TemporaryDirectory() as tmp:
            for rel, _fn in kickoff_memory.FILES:
                src = os.path.join(plasma, rel)
                dst = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy(src, dst)
            changed, missed = kickoff_memory.patch_tree(tmp)
            self.assertFalse(missed, missed)
            self.assertGreaterEqual(len(changed), 6)
            header = open(os.path.join(tmp, "org.kde.plasma.kickoff/contents/ui/Header.qml"), encoding="utf-8").read()
            footer = open(os.path.join(tmp, "org.kde.plasma.kickoff/contents/ui/Footer.qml"), encoding="utf-8").read()
            self.assertIn("matryoshkaSearch", header)
            self.assertNotIn("searchField.clear()\n", header.split("if (Date.now() - kickoff.matryoshkaMenuClosedAt > 60000)")[0].split("function onExpandedChanged")[-1])
            self.assertIn("60000", header)
            self.assertIn("matryoshkaTab", footer)
            self.assertNotIn("tabBar.currentIndex = 0\n", footer.split("60000")[0])
            again, missed2 = kickoff_memory.patch_tree(tmp)
            self.assertEqual(again, [])
            self.assertFalse(missed2, missed2)
        hook = read(ROOT, "config", "hooks", "live", "0600-matryoshka.hook.chroot")
        self.assertIn("matryoshka-kickoff-memory.service", hook)
        unit = read(INC, "etc", "systemd", "system", "matryoshka-kickoff-memory.service")
        self.assertIn("kickoff_memory.py", unit)
        self.assertIn("netmenu.py", unit)
        import netmenu
        popup = os.path.join(plasma, "org.kde.plasma.networkmanagement/contents/ui/PopupDialog.qml")
        patched = netmenu.patch_popup(open(popup, encoding="utf-8").read())
        self.assertIsNotNone(patched)
        self.assertIn("Отключить бумажник", patched)
        self.assertIn("wallet_menu.py", patched)
        self.assertEqual(netmenu.patch_popup(patched), patched)
        self.assertIn("session.kwallet", read(LIB, "wallet_menu.py"))
        self.assertIn("Before=display-manager.service", unit)

    def test_wallet_switch_writes_disabled(self):
        import session
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "kwalletrc")
            open(path, "w", encoding="utf-8").write("[Wallet]\nEnabled=true\nClose When Idle=false\n[Other]\nKeep=yes\n")
            session.kwallet_write(path, False)
            text = open(path, encoding="utf-8").read()
            self.assertIn("Enabled=true", text)
            self.assertIn("Launch=true", text)
            self.assertIn("SecretServiceEnabled=true", text)
            self.assertIn("Prompt on Open=false", text)
            self.assertNotIn("Enabled=false", text)
            self.assertIn("[Other]", text)
            self.assertIn("Keep=yes", text)
            self.assertNotIn("unloadModule", read(LIB, "session.py"))
            self.assertIn("password-store=basic", read(LIB, "session.py"))
            self.assertNotIn("systemctl", read(LIB, "waydroid_ctl.py"))
            session.kwallet_write(path, True)
            enabled = open(path, encoding="utf-8").read()
            self.assertIn("Enabled=true", enabled)
            self.assertIn("SecretServiceEnabled=true", enabled)
        center = read(LIB, "center.py")
        self.assertIn("Отключить бумажник", center)
        self.assertIn("dos_file_bar", center)
        self.assertIn("dos_file_bar", read(LIB, "common.py"))


if __name__ == "__main__":
    unittest.main()
