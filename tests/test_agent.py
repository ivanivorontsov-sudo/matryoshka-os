import io, json, os, sys, types, unittest
from unittest import mock
import urllib.error

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
LIB = os.path.join(ROOT, "config", "includes.chroot_after_packages", "usr", "lib", "matryoshka")
sys.path.insert(0, LIB)

import common as C


class HttpJson(unittest.TestCase):
    def test_sends_bearer_only_when_key(self):
        payload = {"model": "default", "messages": []}
        body = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()

        def open_ok(req, timeout=120):
            self.assertFalse(req.has_header("Authorization"))
            return FakeResp(body)

        with mock.patch.object(C.urllib.request, "urlopen", open_ok):
            C.http_json("https://api.llm7.io/v1/chat/completions", payload, key=None)

        seen = {}

        def open_key(req, timeout=120):
            seen["auth"] = req.get_header("Authorization")
            return FakeResp(body)

        with mock.patch.object(C.urllib.request, "urlopen", open_key):
            C.http_json("https://api.llm7.io/v1/chat/completions", payload, key="secret-test")
        self.assertEqual(seen["auth"], "Bearer secret-test")

    def test_http_error_uses_api_message(self):
        err_body = json.dumps({"error": {"message": "Your free token allowance has been reached.", "code": "quota_exceeded"}}).encode()

        def boom(req, timeout=120):
            raise urllib.error.HTTPError(req.full_url, 429, "Too Many Requests", {}, io.BytesIO(err_body))

        with mock.patch.object(C.urllib.request, "urlopen", boom):
            with self.assertRaises(RuntimeError) as ar:
                C.http_json("https://api.llm7.io/v1/chat/completions", {})
        self.assertIn("allowance", str(ar.exception))
        self.assertNotIn("Bearer", str(ar.exception))

    def test_connection_refused_is_clear(self):
        def boom(req, timeout=120):
            raise urllib.error.URLError(ConnectionRefusedError(111, "Connection refused"))

        with mock.patch.object(C.urllib.request, "urlopen", boom):
            with self.assertRaises(RuntimeError) as ar:
                C.http_json("http://127.0.0.1:11434/v1/chat/completions", {})
        self.assertIn("нет связи с моделью", str(ar.exception))


class FakeResp:
    def __init__(self, data):
        self._data = data
    def read(self):
        return self._data
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def load_agent():
    if "PyQt6" not in sys.modules:
        try:
            import PyQt6
        except ImportError:
            stub_qt()
    import agent
    return agent


def stub_qt():
    def pkg(name):
        m = types.ModuleType(name)
        sys.modules[name] = m
        return m
    qt = pkg("PyQt6")
    core = pkg("PyQt6.QtCore")
    widgets = pkg("PyQt6.QtWidgets")
    class QThread:
        def __init__(self, parent=None):
            pass
        def start(self):
            pass
    class Sig:
        def connect(self, fn):
            self.fn = fn
        def emit(self, *a):
            pass
        def disconnect(self, *a):
            pass
    def pyqtSignal(*a, **k):
        return Sig()
    class Qt:
        class ItemDataRole:
            UserRole = 256
    class QTimer:
        @staticmethod
        def singleShot(*a, **k):
            pass
    class QUrl:
        def __init__(self, u=""):
            self.u = u
    for k, v in {"QThread": QThread, "pyqtSignal": pyqtSignal, "Qt": Qt, "QTimer": QTimer, "QUrl": QUrl}.items():
        setattr(core, k, v)
    class W:
        def __init__(self, *a, **k):
            pass
        def setWindowTitle(self, *a):
            pass
        def resize(self, *a):
            pass
        def show(self):
            pass
    class Combo:
        def __init__(self, *a, **k):
            self.items = []
            self.i = 0
        def addItem(self, n, k=None):
            self.items.append((n, k))
        def findData(self, k):
            for i, it in enumerate(self.items):
                if it[1] == k:
                    return i
            return -1
        def setCurrentIndex(self, i):
            self.i = i
        def currentData(self):
            return self.items[self.i][1] if self.items else None
        def currentIndexChanged(self):
            return Sig()
        def currentText(self):
            return self.items[self.i][0] if self.items else ""
        def setEditable(self, *a):
            pass
        def blockSignals(self, *a):
            pass
    class Dummy:
        def __init__(self, *a, **k):
            pass
        def clicked(self):
            return Sig()
        def returnPressed(self):
            return Sig()
        def addWidget(self, *a, **k):
            pass
        def addLayout(self, *a, **k):
            pass
        def append(self, *a, **k):
            pass
        def setEnabled(self, *a):
            pass
        def text(self):
            return ""
        def clear(self):
            pass
        def connect(self, *a):
            return Sig()
        def setText(self, *a):
            pass
        def setVisible(self, *a):
            pass
        def hide(self, *a):
            pass
        def show(self, *a):
            pass
        def setRange(self, *a):
            pass
        def setWordWrap(self, *a):
            pass
        def setPlaceholderText(self, *a):
            pass
        def currentItemChanged(self):
            return Sig()
        def currentItem(self):
            return None
        def addItem(self, *a, **k):
            pass
        def exec(self, *a):
            return 0
        def accept(self, *a):
            pass
        def setData(self, *a):
            pass
        def data(self, *a):
            return None
        def blockSignals(self, *a):
            pass
    for name, cls in {
        "QApplication": Dummy, "QWidget": W, "QVBoxLayout": Dummy, "QHBoxLayout": Dummy,
        "QTextEdit": Dummy, "QLineEdit": Dummy, "QPushButton": Dummy, "QComboBox": Combo,
        "QLabel": Dummy, "QMessageBox": Dummy, "QDialog": W, "QListWidget": Dummy,
        "QListWidgetItem": Dummy, "QProgressBar": Dummy,
    }.items():
        setattr(widgets, name, cls)
    qt.QtCore = core
    qt.QtWidgets = widgets


class Backend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = load_agent()

    def test_default_is_api_like_center(self):
        self.assertEqual(self.agent.backend_of({}), "api")
        self.assertEqual(self.agent.backend_of({"ai": "api"}), "api")
        self.assertEqual(self.agent.backend_of(C.settings()), "api")

    def test_uses_center_ai_not_old_local_default(self):
        self.assertEqual(self.agent.backend_of({"ai": "api", "agent_backend": "local"}), "api")
        self.assertEqual(self.agent.backend_of({"ai": "local"}), "local")
        self.assertEqual(self.agent.backend_of({"ai": "chat"}), "chat")
        self.assertEqual(self.agent.backend_of({"agent_backend": "web"}), "chat")
        self.assertEqual(self.agent.backend_of({"agent_backend": "local"}), "local")

    def test_parse_json_and_fences(self):
        d = self.agent.parse('{"say": "привет", "actions": []}')
        self.assertEqual(d["say"], "привет")
        self.assertEqual(d["actions"], [])
        d = self.agent.parse("конечно:\n```json\n{\"say\": \"готово\", \"actions\": [{\"tool\": \"system_info\", \"args\": {\"topic\": \"hardware\"}}]}\n```")
        self.assertEqual(d["say"], "готово")
        self.assertEqual(d["actions"][0]["tool"], "system_info")

    def test_reply_falls_back_to_plain_text(self):
        d = self.agent.reply_of("Просто текст без JSON.")
        self.assertEqual(d["say"], "Просто текст без JSON.")
        self.assertEqual(d["actions"], [])

    def test_local_error_explains_missing_ollama(self):
        msg = self.agent.err_text("local", RuntimeError("нет связи с моделью: [Errno 111] Connection refused"))
        self.assertIn("не запущена", msg)
        self.assertIn("Центре", msg)

    def test_http_chat_empty_key_not_none(self):
        seen = {}
        body = {"choices": [{"message": {"content": "{\"say\": \"ok\", \"actions\": []}"}}]}

        def fake(url, payload, key=None, timeout=120, headers=None):
            seen["key"] = key
            seen["url"] = url
            return body

        with mock.patch.object(C, "http_json", fake):
            t = self.agent.http_chat("https://api.llm7.io/v1", "default", "", [{"role": "user", "content": "x"}])
        self.assertIsNone(seen["key"])
        self.assertTrue(seen["url"].endswith("/chat/completions"))
        self.assertIn("ok", t)


if __name__ == "__main__":
    unittest.main()
