import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka"))
import audiodev

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

if __name__ == "__main__":
    unittest.main()
