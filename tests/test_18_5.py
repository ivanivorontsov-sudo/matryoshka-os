import os, sys, tempfile, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka"))
import archiveinst
import audiodev
import aveta
import dosbox
import hotkeys
import pkgplan

class T(unittest.TestCase):
    def test_source_default_not_alsa(self):
        self.assertEqual(audiodev.pick_source(["alsa_input.pci", "easyeffects_source"], "zvuk_input"), "zvuk_input")
        self.assertEqual(audiodev.pick_source(["alsa_input.pci.monitor", "alsa_input.pci"], ""), "alsa_input.pci")
        self.assertEqual(audiodev.pick_source(["alsa_input.pci.monitor"], "alsa_input.pci.monitor"), None)

    def test_volume_memory(self):
        sinks = [{"name": "alsa_output.pci", "port": "analog-output-headphones", "volume": "40%"}]
        data = audiodev.remember({"sink": "", "volumes": {}}, sinks, "alsa_output.pci")
        sink, vol = audiodev.restore_plan(data, sinks)
        self.assertEqual(sink, "alsa_output.pci")
        self.assertEqual(vol, "40%")

    def test_eta(self):
        self.assertEqual(aveta.estimate(0, 0, 100, 1, 1, 1), 0)
        self.assertGreater(aveta.estimate(100, 10_000_000, 1_000_000, 0.2, 1, 0.05), 1)
        self.assertEqual(aveta.refine(50, 100, 10, 99), 10)

    def test_archive(self):
        self.assertEqual(archiveinst.classify(["App.AppImage"]), "program")
        self.assertEqual(archiveinst.classify(["Makefile", "main.c"]), "source")
        self.assertEqual(archiveinst.classify([]), "empty")

    def test_dos_conf(self):
        text = dosbox.conf_text("/home/ivan/DOS", "/home/ivan/DOS/CAD", "FESTA.EXE")
        self.assertIn("cycles=max", text)
        self.assertIn("sb16", text)
        self.assertIn("FESTA.EXE", text)
        self.assertNotIn("exit", text.split("[autoexec]")[-1])

    def test_newer(self):
        self.assertFalse(pkgplan.newer("1.0", "1.0"))
        self.assertTrue(pkgplan.newer("1.0", "1.2"))
        self.assertTrue(pkgplan.newer("", "1.0"))
        self.assertFalse(pkgplan.newer("1.0", "(none)"))

    def test_hotkeys(self):
        d = tempfile.mkdtemp()
        hotkeys.FILE = os.path.join(d, "kglobalshortcutsrc")
        hotkeys.apply("windows")
        text = open(hotkeys.FILE, encoding="utf-8").read()
        self.assertIn("Ctrl+Alt+Del,Ctrl+Alt+Del,Меню безопасности", text)
        hotkeys.apply("linux")
        text = open(hotkeys.FILE, encoding="utf-8").read()
        self.assertIn("Meta+Shift+Del,Meta+Shift+Del,Меню безопасности", text)
        self.assertIn("Log Out=Ctrl+Alt+Del,Ctrl+Alt+Del,Выйти из системы", text)

if __name__ == "__main__":
    unittest.main()
