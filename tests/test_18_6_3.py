import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka"))
import audiodev
import quickshot

class Audio(unittest.TestCase):
    def test_virtual_mic_replaced(self):
        data = {"sink": "", "volumes": {}}
        srcs = ["alsa_input.pci-0000_00_1f.3.analog-stereo", "easyeffects_source", "alsa_output.pci.monitor"]
        self.assertEqual(audiodev.source_fix(data, srcs, "easyeffects_source", False), srcs[0])

    def test_saved_real_mic_kept(self):
        data = {"sink": "", "volumes": {}}
        srcs = ["alsa_input.usb-mic", "alsa_input.pci-x", "easyeffects_source"]
        self.assertIsNone(audiodev.source_fix(data, srcs, "alsa_input.usb-mic", False))
        self.assertEqual(data["source"], "alsa_input.usb-mic")
        self.assertEqual(audiodev.source_fix(data, srcs, "easyeffects_source", False), "alsa_input.usb-mic")

    def test_user_choice_of_virtual_respected(self):
        data = {"sink": "", "volumes": {}}
        srcs = ["alsa_input.pci-x", "easyeffects_source"]
        self.assertIsNone(audiodev.source_fix(data, srcs, "easyeffects_source", True))
        self.assertIsNone(audiodev.source_fix(data, srcs, "easyeffects_source", False))

    def test_unplug(self):
        a = {"alsa_output.pci": "analog-output-headphones"}
        b = {"alsa_output.pci": "analog-output-speaker"}
        changed, unplugged = audiodev.route_events(a, b)
        self.assertEqual(changed, ["alsa_output.pci"])
        self.assertTrue(unplugged)
        changed, unplugged = audiodev.route_events(b, a)
        self.assertFalse(unplugged)
        bt = dict(b, **{"bluez_output.AA": "headset-output"})
        self.assertTrue(audiodev.route_events(bt, b)[1])
        self.assertEqual(audiodev.route_events(None, b), ([], False))

    def test_hw(self):
        self.assertTrue(audiodev.has_hw_sink(["easyeffects_sink", "alsa_output.pci"]))
        self.assertFalse(audiodev.has_hw_sink(["easyeffects_sink", "auto_null"]))


class Shot(unittest.TestCase):
    def test_edges_snap(self):
        import quickshot
        self.assertEqual(quickshot.norm_rect((2, 1), (1918, 1078), 1920, 1080), (0, 0, 1920, 1080))
        self.assertEqual(quickshot.norm_rect((500, 400), (100, 100), 1920, 1080), (100, 100, 400, 300))

    def test_overlay_crop(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import quickshot
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtGui import QPixmap, QColor
        app = QApplication.instance() or QApplication([])
        pix = QPixmap(200, 100); pix.fill(QColor("red"))
        w = quickshot.Overlay(pix, dict(quickshot.DEFAULTS, mode="tools"), "/tmp")
        w.resize(100, 50)
        w.a, w.b = (0, 0), (199, 99)
        w.done_rect = w.sel()
        self.assertEqual(w.crop().width(), 200)
        self.assertEqual(w.crop().height(), 100)

if __name__ == "__main__":
    unittest.main()
