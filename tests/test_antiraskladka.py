import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka"))
import antiraskladka as A

class T(unittest.TestCase):
    def test_words(self):
        for a, b in (("e[j", "ухо"), ("E{J", "УХО"), ("ghbdtn", "привет"), ("b`;br", "иёжик"), ("ctujlyz", "сегодня"), ("'nj", "это"), ("k.,jdm", "любовь")):
            self.assertEqual(A.conv(a), b, a)
    def test_back(self):
        self.assertEqual(A.conv("привет"), "ghbdtn")
        self.assertEqual(A.conv("ухо"), "e[j")
    def test_email(self):
        self.assertEqual(A.conv('lkgfok"mail.ru'), "lkgfok@mail.ru")
        self.assertEqual(A.conv('ivan.v"yandex.ru'), "ivan.v@yandex.ru")
    def test_punct(self):
        self.assertEqual(A.conv("ghbdtn, vbh."), "привет, мир.")
        self.assertEqual(A.conv("руддщ"), "hello")
    def test_url(self):
        self.assertEqual(A.conv("https://ya.ru"), "https://ya.ru")

if __name__ == "__main__":
    unittest.main()
