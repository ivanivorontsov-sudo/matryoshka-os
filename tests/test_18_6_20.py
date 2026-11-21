import json, os, sys, tempfile, unittest
from unittest import mock
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
LIB = os.path.join(ROOT, "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka")
sys.path.insert(0, LIB)
sys.path.insert(0, HERE)

import common as C
import agent_models
import agent_websearch
import krunner_match


def score(name, kw, q):
    q = (q or "").lower()
    blob = (name + " " + (kw or "")).lower()
    return 80 if q and q in blob else 0


class KrunnerAi(unittest.TestCase):
    def test_offers_naiti_when_nothing_found(self):
        apps = [{"name": "Калькулятор", "kw": "calc", "file": "/x/calc.desktop", "icon": "calc"}]
        found = krunner_match.find_matches("погода во владивостоке", apps, score, (("kcm_keyboard", "клавиатура", "keyboard"),))
        out = krunner_match.with_ai_search("погода во владивостоке", found)
        self.assertEqual(found, [])
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0][0], "ai:погода во владивостоке")
        self.assertEqual(out[0][1], "Найти «погода во владивостоке»")

    def test_no_naiti_when_app_matches(self):
        apps = [{"name": "Калькулятор", "kw": "calc", "file": "/x/calc.desktop", "icon": "calc"}]
        found = krunner_match.find_matches("калькулятор", apps, score, ())
        out = krunner_match.with_ai_search("калькулятор", found)
        self.assertTrue(any(m[0].startswith("app:") for m in out))
        self.assertFalse(any(m[0].startswith("ai:") for m in out))

    def test_short_query_empty(self):
        self.assertEqual(krunner_match.with_ai_search("я", []), [])


class Models(unittest.TestCase):
    def test_name_ok(self):
        self.assertTrue(agent_models.name_ok("qwen2.5:3b"))
        self.assertTrue(agent_models.name_ok("hf.co/Qwen/Qwen2.5-3B-Instruct-GGUF"))
        self.assertFalse(agent_models.name_ok(""))
        self.assertFalse(agent_models.name_ok("../etc/passwd"))
        self.assertFalse(agent_models.name_ok("qwen;rm -rf /"))
        self.assertFalse(agent_models.name_ok("qwen && id"))

    def test_desktop_file(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(agent_models, "appdir", return_value=d), mock.patch.object(os.path, "expanduser", return_value=d):
                path = agent_models.write_desktop("qwen2.5:3b")
                self.assertTrue(os.path.isfile(path))
                self.assertTrue(os.path.basename(path).startswith("matryoshka-ai-"))
                with open(path, encoding="utf-8") as f:
                    text = f.read()
                self.assertIn("Name=Чат: qwen2.5:3b", text)
                self.assertIn("Exec=matryoshka-agent --model", text)
                self.assertIn("qwen2.5:3b", text)
                self.assertTrue(agent_models.remove_desktop("qwen2.5:3b"))
                self.assertFalse(os.path.isfile(path))


class WebSearch(unittest.TestCase):
    def test_format_and_engines(self):
        items = [{"title": "Пример", "url": "https://example.com/x", "snippet": "текст"}]
        t = agent_websearch.format_items("yandex", items)
        self.assertIn("Яндекс", t)
        self.assertIn("https://example.com/x", t)
        self.assertIn("Пример", t)
        self.assertEqual(agent_websearch.engines_of({}), ["yandex", "google"])
        self.assertEqual(agent_websearch.engines_of({"search_engines": "google"}), ["google"])

    def test_redacts_keys(self):
        s = {"google_search_key": "SECRETKEY99", "yandex_search_key": "YANKEY11"}
        t = agent_websearch._redact("url?key=SECRETKEY99 and YANKEY11", s)
        self.assertNotIn("SECRETKEY99", t)
        self.assertNotIn("YANKEY11", t)

    def test_net_off(self):
        with mock.patch.object(C, "net_on", return_value=False):
            self.assertIn("Сеть выключена", agent_websearch.search("погода", {}))

    def test_google_api_used_when_keys(self):
        s = {"search_engines": "google", "google_search_key": "gk", "google_search_cx": "cx1"}
        payload = {"items": [{"title": "A", "link": "https://a.example/", "snippet": "s"}]}
        def fake_open(url, s2, timeout=25, headers=None):
            self.assertIn("googleapis.com/customsearch/v1", url)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            self.assertEqual(q["q"][0], "кошки")
            return json.dumps(payload).encode(), "application/json"
        with mock.patch.object(C, "net_on", return_value=True), mock.patch.object(agent_websearch, "_open", fake_open):
            out = agent_websearch.search("кошки", s)
        self.assertIn("Google", out)
        self.assertIn("https://a.example/", out)
        self.assertNotIn("googleapis.com", out)

    def test_empty_query(self):
        self.assertEqual(agent_websearch.search("  ", {}), "пустой запрос")


class AgentHooks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_agent
        cls.agent = test_agent.load_agent()

    def test_web_search_tool_and_confirm(self):
        self.assertIn("web_search", self.agent.TOOLS)
        self.assertIn("web_search", self.agent.CONFIRM)
        self.assertIn("web_search", self.agent.SYSTEM)

    def test_settings_hide_search_keys(self):
        s = {"theme": "mica", "api_key": "AAAKEY", "google_search_key": "GKEY9", "yandex_search_key": "YKEY9", "google_search_cx": "CX9"}
        with mock.patch.object(C, "settings", return_value=s):
            out = self.agent.system_info("settings")
        self.assertNotIn("AAAKEY", out)
        self.assertNotIn("GKEY9", out)
        self.assertNotIn("YKEY9", out)
        self.assertNotIn("CX9", out)

    def test_cli_and_runtime(self):
        def read(name):
            with open(os.path.join(LIB, name), encoding="utf-8") as f:
                return f.read()
        src = read("agent.py")
        self.assertIn("--query", src)
        self.assertIn("--model", src)
        self.assertIn("--send", src)
        self.assertIn("class ModelsDialog", src)
        self.assertIn("ai-runtime", read("root.sh"))
        kr = read("krunner_layout.py")
        self.assertIn("--query", kr)
        self.assertIn("with_ai_search", kr)

    def test_do_web_search_calls_module(self):
        with mock.patch("agent_websearch.search", return_value="Яндекс:\n1. Т\n   https://t.example/") as fn:
            r = self.agent.do("web_search", {"query": "тест"})
        fn.assert_called_once()
        self.assertIn("https://t.example/", r)

    def test_verified_default_backend_still_api(self):
        self.assertEqual(self.agent.backend_of({}), "api")
        self.assertEqual(self.agent.backend_of({"ai": "api", "agent_backend": "local"}), "api")
        d = self.agent.reply_of("Просто текст без JSON.")
        self.assertEqual(d["say"], "Просто текст без JSON.")


if __name__ == "__main__":
    unittest.main()
