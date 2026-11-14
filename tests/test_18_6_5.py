import os, subprocess, sys, tempfile, unittest
from unittest import mock
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INC = os.path.join(ROOT, "config", "includes.chroot_after_packages")
LIB = os.path.join(INC, "usr", "lib", "matryoshka")
sys.path.insert(0, LIB)
import sddm_theme

AUTH = os.path.join(INC, "usr", "sbin", "matryoshka-auth")
BREEZE = os.environ.get("MATRYOSHKA_BREEZE", "/usr/share/sddm/themes/breeze")


def stack(face, finger, have_exec=True):
    sh = r'''
HOWDY=/nonexistent; FP_LOGIN_ARGS="max-tries=3 timeout=15"; EMPTY=/bin/true
mod() { case "$1" in pam_fprintd.so) return 0;; pam_exec.so) [ "$HE" = 1 ];; *) return 1;; esac; }
eval "$(sed -n '/^login_stack()/,/^}/p' "$AUTH")"
login_stack "$1" "$2"
'''
    env = dict(os.environ, AUTH=AUTH, HE="1" if have_exec else "0")
    return subprocess.run(["bash", "-c", sh, "x", str(face), str(finger)], capture_output=True, text=True, env=env).stdout.splitlines()


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


class Pam(unittest.TestCase):
    def test_password_always_first(self):
        for face in (0, 1):
            for fin in (0, 1):
                l = stack(face, fin)
                self.assertIn("pam_unix.so", l[0])
                self.assertIn("pam_deny.so", l[-2])
                self.assertIn("pam_permit.so", l[-1])

    def test_flow(self):
        l = stack(0, 1)
        self.assertTrue(any("pam_exec.so" in x for x in l))
        self.assertTrue(simulate(l, {"pam_unix.so": True, "pam_exec.so": False, "pam_fprintd.so": False}))
        self.assertFalse(simulate(l, {"pam_unix.so": False, "pam_exec.so": False, "pam_fprintd.so": True}))
        self.assertTrue(simulate(l, {"pam_unix.so": False, "pam_exec.so": True, "pam_fprintd.so": True}))
        self.assertFalse(simulate(l, {"pam_unix.so": False, "pam_exec.so": True, "pam_fprintd.so": False}))

    def test_without_pam_exec(self):
        l = stack(0, 1, have_exec=False)
        self.assertFalse(any("pam_exec.so" in x for x in l))
        self.assertTrue(simulate(l, {"pam_unix.so": True, "pam_fprintd.so": False}))
        self.assertTrue(simulate(l, {"pam_unix.so": False, "pam_fprintd.so": True}))
        self.assertFalse(simulate(l, {"pam_unix.so": False, "pam_fprintd.so": False}))

    def test_empty_helper(self):
        h = os.path.join(LIB, "pam-empty-authtok")
        self.assertEqual(subprocess.run(["sh", h], input=b"\0").returncode, 0)
        self.assertEqual(subprocess.run(["sh", h], input=b"").returncode, 0)
        self.assertNotEqual(subprocess.run(["sh", h], input=b"secret\0").returncode, 0)

    def test_safety_hooks(self):
        s = open(AUTH, encoding="utf-8").read()
        self.assertIn('rm -f "$THEME_CONF"', s)
        self.assertIn("zz-matryoshka-finger.conf", s)
        self.assertEqual(subprocess.run(["bash", "-n", AUTH]).returncode, 0)


@unittest.skipUnless(os.path.isfile(os.path.join(BREEZE, "Main.qml")), "нет темы breeze")
class Theme(unittest.TestCase):
    def test_build(self):
        with tempfile.TemporaryDirectory() as t:
            d = os.path.join(t, "m")
            self.assertTrue(sddm_theme.build(BREEZE, d))
            m = open(os.path.join(d, "Main.qml"), encoding="utf-8").read()
            self.assertIn("onInformationMessage", m)
            self.assertIn(sddm_theme.TIP, m)
            self.assertIn("Theme-Id=matryoshka", open(os.path.join(d, "metadata.desktop"), encoding="utf-8").read())
            self.assertTrue(sddm_theme.build(BREEZE, d))

    def test_refuses_unknown(self):
        with tempfile.TemporaryDirectory() as t:
            open(os.path.join(t, "Main.qml"), "w").write("x")
            self.assertFalse(sddm_theme.build(t, os.path.join(t, "out")))
            self.assertFalse(os.path.exists(os.path.join(t, "out")))


class Uninstall(unittest.TestCase):
    def test_outcome(self):
        import appinfo
        cp = subprocess.CompletedProcess
        self.assertTrue(appinfo.outcome("X", cp([], 0, "", ""), True)[0])
        ok, t = appinfo.outcome("X", cp([], 0, "", ""), False)
        self.assertFalse(ok)
        self.assertIn("НЕ удалена", t)
        ok, t = appinfo.outcome("X", cp([], 126, "", ""), False)
        self.assertIn("нет прав", t)
        ok, t = appinfo.outcome("X", cp([], 1, "", ""), False)
        self.assertIn("нет прав", t)
        ok, t = appinfo.outcome("X", cp([], 100, "E: boom", ""), False)
        self.assertIn("код ошибки 100", t)

    def test_root_exit_code(self):
        s = open(os.path.join(LIB, "root.sh"), encoding="utf-8").read()
        i = s.index("  remove-app)\n")
        block = s[i:s.index(";;\n  update-all)", i)]
        self.assertIn("exit $rc", block)
        self.assertNotIn("ufw status", block)
        self.assertIn("done; true)", block)
        sh = "set -e; x=$(printf 'Remv a\\n' | awk '{print $2}' | while read -r q; do if grep -qx \"$q\" /dev/null; then echo \"$q\"; fi; done; true); echo ok"
        self.assertEqual(subprocess.run(["bash", "-c", sh], capture_output=True, text=True).stdout.strip(), "ok")


if __name__ == "__main__":
    unittest.main()
