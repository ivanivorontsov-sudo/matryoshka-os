import os, shutil, subprocess, sys, tempfile, unittest, zipfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka"))
import ndk_install as N

def fake_zip(path):
    d = tempfile.mkdtemp()
    base = os.path.join(d, "vendor", "prebuilts")
    for lib in ("lib", "lib64"):
        p = os.path.join(base, lib)
        os.makedirs(p)
        open(os.path.join(p, "libndk_translation.so"), "wb").write(b"fake-" + lib.encode())
    with zipfile.ZipFile(path, "w") as z:
        for root, dirs, files in os.walk(d):
            for name in files:
                full = os.path.join(root, name)
                z.write(full, os.path.relpath(full, d))
    shutil.rmtree(d)

class T(unittest.TestCase):
    def test_apply_idempotent_and_rollback(self):
        root = tempfile.mkdtemp()
        z = os.path.join(root, "n.zip")
        fake_zip(z)
        os.environ["NDK_NO_SYSTEMD"] = "1"
        real = N.SHA
        try:
            N.SHA = N.sha256_file(z)
            self.assertEqual(N.install(root, z), 0)
            self.assertEqual(N.install(root, z), 0)
            so = os.path.join(root, "overlay", "system", "lib64", "libndk_translation.so")
            self.assertTrue(os.path.isfile(so))
            self.assertEqual(N.read_props(os.path.join(root, "waydroid_base.prop"))["ro.dalvik.vm.native.bridge"], "libndk_translation.so")
            os.environ["NDK_FAIL"] = "after-copy"
            open(os.path.join(root, "waydroid_base.prop"), "w").write("ro.dalvik.vm.native.bridge=old\n")
            os.remove(os.path.join(root, ".matryoshka-ndk-user"))
            with self.assertRaises(RuntimeError):
                N.install(root, z)
            self.assertEqual(N.read_props(os.path.join(root, "waydroid_base.prop")).get("ro.dalvik.vm.native.bridge"), "old")
        finally:
            N.SHA = real
            os.environ.pop("NDK_FAIL", None)
            shutil.rmtree(root)

    def test_real_archive_checksum(self):
        src = "/tmp/ndk-src/ndk.zip"
        if not os.path.isfile(src):
            self.skipTest("archive not downloaded")
        self.assertEqual(N.sha256_file(src), N.SHA)
        root = tempfile.mkdtemp()
        try:
            os.environ["NDK_NO_SYSTEMD"] = "1"
            self.assertEqual(N.install(root, src), 0)
            self.assertEqual(N.verify(os.path.join(root, "overlay", "system"), os.path.join(root, "waydroid_base.prop")), [])
            lib = open(os.path.join(root, "overlay", "system", "lib64", "libndk_translation.so"), "rb").read(4)
            self.assertEqual(lib, b"\x7fELF")
        finally:
            shutil.rmtree(root)

if __name__ == "__main__":
    unittest.main()
