import sys, os, glob, subprocess, tempfile
from PyQt6.QtCore import QObject, pyqtSlot, QCoreApplication
from PyQt6.QtQml import QJSEngine
import common as C

DIR = os.path.join(C.CONF, "scripts")

class Api(QObject):
    @pyqtSlot(str)
    def log(self, s): print(s)
    @pyqtSlot(str, str)
    def notify(self, t, s): C.notify(t, s)
    @pyqtSlot(str)
    def setTheme(self, k):
        if k in C.THEMES: C.apply_theme(k)
    @pyqtSlot(str)
    def setMode(self, m):
        if m in ("standard", "simple"): C.apply_mode(m)
    @pyqtSlot(str)
    def setLayout(self, k):
        if k in C.LAYOUTS: C.apply_layout(k)
    @pyqtSlot(str)
    def openApp(self, q):
        apps = sorted(C.desktop_apps(), key=lambda x: -C.score(x["name"], x["kw"], q))
        if apps and C.score(apps[0]["name"], apps[0]["kw"], q) > 0: C.launch(apps[0])
    @pyqtSlot(result=bool)
    def netOn(self): return C.net_on()
    @pyqtSlot(result=str)
    def time(self):
        import datetime; return datetime.datetime.now().strftime("%H:%M")

PRELUDE = """
var console={log:function(){matryoshka.log(Array.prototype.join.call(arguments,' '))},error:function(){matryoshka.log(Array.prototype.join.call(arguments,' '))}};
var __deny=function(){throw new Error('доступ к файлам и программам в сценариях запрещён')};
var __proxy=new Proxy({},{get:function(){return __deny}});
var require=function(m){return __proxy};
var __api=new Map();
[["log","лог"],["notify","уведомить"],["setTheme","тема"],["setMode","режим"],["setLayout","раскладка"],["openApp","открыть"],["netOn","сеть"],["time","время"]].forEach(function(p){var f=function(){var a=Array.prototype.map.call(arguments,String);return matryoshka[p[0]].apply(matryoshka,a)};__api.set(p[0],f);__api.set(p[1],f)});
var process={argv:[],env:{},platform:'linux',exitCode:0,exit:function(){},stdout:{write:function(s){matryoshka.log(String(s).replace(/\\n$/,''))}},stderr:{write:function(s){matryoshka.log(String(s).replace(/\\n$/,''))}}};
"""

def source(path):
    if path.endswith(".pon"):
        out = tempfile.mkdtemp(); src = os.path.join(out, "s.pon")
        open(src, "w", encoding="utf-8").write("пусть матрёшка = 0\n" + open(path, encoding="utf-8").read())
        r = subprocess.run(["ponyatny", "компилировать", src], cwd=out, capture_output=True, text=True)
        js = os.path.join(out, "s.js")
        if not os.path.exists(js): raise RuntimeError(r.stdout + r.stderr)
        return open(js, encoding="utf-8").read().replace("let $матрёшка = 0;", "let $матрёшка = __api;", 1)
    return open(path, encoding="utf-8").read()

def run(path):
    e = QJSEngine(); api = Api(); e.globalObject().setProperty("матрёшка", e.newQObject(api)); e.globalObject().setProperty("matryoshka", e.newQObject(api))
    e.evaluate(PRELUDE)
    r = e.evaluate(source(path), path)
    if r.isError(): print("Ошибка:", r.toString()); return 1
    return 0

if __name__ == "__main__":
    app = QCoreApplication(sys.argv)
    os.makedirs(DIR, exist_ok=True)
    if sys.argv[1:] == ["--autostart"]:
        for p in sorted(glob.glob(DIR + "/*.js") + glob.glob(DIR + "/*.pon")): run(p)
    elif sys.argv[1:]:
        sys.exit(run(sys.argv[1]))
