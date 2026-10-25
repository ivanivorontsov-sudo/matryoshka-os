import sys, os, json, zipfile, io, subprocess, urllib.request
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QMessageBox
import common as C

EMU = [("org.libretro.RetroArch", "RetroArch — много приставок в одном"), ("org.DolphinEmu.dolphin-emu", "Dolphin — GameCube и Wii"), ("net.pcsx2.PCSX2", "PCSX2 — PlayStation 2"),
       ("org.duckstation.DuckStation", "DuckStation — PlayStation"), ("org.ppsspp.PPSSPP", "PPSSPP — PSP"), ("net.rpcs3.RPCS3", "RPCS3 — PlayStation 3"), ("app.xemu.xemu", "xemu — первый Xbox"),
       ("net.kuribo64.melonDS", "melonDS — Nintendo DS"), ("org.azahar_emu.Azahar", "Azahar — Nintendo 3DS"), ("info.cemu.Cemu", "Cemu — Wii U"), ("org.mamedev.MAME", "MAME — игровые автоматы"),
       ("io.mgba.mGBA", "mGBA — Game Boy Advance"), ("com.snes9x.Snes9x", "Snes9x — SNES"), ("org.flycast.Flycast", "Flycast — Dreamcast"), ("io.github.simple64.simple64", "simple64 — Nintendo 64"),
       ("io.github.stella_emu.Stella", "Stella — Atari 2600"), ("com.github.AmatCoder.mednaffe", "Mednafen/Mednaffe — PC Engine, PC-FX и другие")]
CORES = [("mednafen_pce", "PC Engine / TurboGrafx-16"), ("mednafen_pce_fast", "PC Engine (быстрый)"), ("mednafen_supergrafx", "SuperGrafx"), ("mednafen_pcfx", "PC-FX"), ("np2kai", "NEC PC-98"), ("stella", "Atari 2600")]
SYSTEMS = ["nes", "snes", "n64", "gc", "wii", "wiiu", "nds", "3ds", "gba", "gb", "psx", "ps2", "ps3", "psp", "xbox", "dreamcast", "pce", "pcfx", "pc98", "atari2600", "arcade"]
GAMES = os.path.join(C.HOME, "Игры")

def prep():
    for s in SYSTEMS: os.makedirs(os.path.join(GAMES, "ROMs", s), exist_ok=True)
    os.makedirs(os.path.join(GAMES, "BIOS"), exist_ok=True)
    open(os.path.join(GAMES, "ПРОЧТИ.txt"), "w", encoding="utf-8").write("Положите сюда СВОИ копии игр (ROMs/<приставка>) и СВОИ файлы BIOS (BIOS).\nМатрёшка никогда не скачивает игры, BIOS и ключи — их можно получить только со своих дисков и приставок.\n")

def installed():
    try: return subprocess.run(["flatpak", "list", "--user", "--app", "--columns=application"], capture_output=True, text=True).stdout.split()
    except Exception: return []

class Emu(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Эмуляторы консолей"); self.resize(620, 620); prep()
        v = QVBoxLayout(self); l = QLabel("Установка в один щелчок из Flathub. Игры и BIOS — только свои, в папке ~/Игры."); l.setWordWrap(True); v.addWidget(l)
        self.list = QListWidget(); v.addWidget(self.list, 1); self.fill()
        h = QHBoxLayout(); v.addLayout(h)
        for t, f in (("Установить", self.inst), ("Удалить", self.rem), ("Запустить", self.run), ("Ядра RetroArch (NEC, Atari)", self.cores), ("ES-DE (общее меню)", self.esde)):
            b = QPushButton(t); b.clicked.connect(f); h.addWidget(b)
    def fill(self):
        self.list.clear(); ins = installed()
        for i, n in EMU:
            it = QListWidgetItem(("✔ " if i in ins else "   ") + n); it.setData(256, i); self.list.addItem(it)
    def cur(self):
        it = self.list.currentItem(); return it.data(256) if it else None
    def need_net(self):
        if not C.net_on(): QMessageBox.information(self, "Сеть", "Включите сеть для загрузки."); return False
        return True
    def inst(self):
        i = self.cur()
        if not i or not self.need_net(): return
        subprocess.run(["flatpak", "remote-add", "--user", "--if-not-exists", "flathub", "https://dl.flathub.org/repo/flathub.flatpakrepo"])
        subprocess.run(["konsole", "-e", "flatpak", "install", "--user", "-y", "flathub", i])
        subprocess.run(["flatpak", "override", "--user", "--filesystem=%s:ro" % GAMES, i]); self.fill()
    def rem(self):
        i = self.cur()
        if i: subprocess.run(["konsole", "-e", "flatpak", "uninstall", "--user", "-y", i]); self.fill()
    def run(self):
        i = self.cur()
        if i: subprocess.Popen(["flatpak", "run", i])
    def cores(self):
        if not self.need_net(): return
        d = os.path.join(C.HOME, ".var/app/org.libretro.RetroArch/config/retroarch/cores"); os.makedirs(d, exist_ok=True); ok = []
        for c, n in CORES:
            try:
                z = urllib.request.urlopen("https://buildbot.libretro.com/nightly/linux/x86_64/latest/%s_libretro.so.zip" % c, timeout=60).read()
                zipfile.ZipFile(io.BytesIO(z)).extractall(d); ok.append(n)
            except Exception as e:
                ok.append(n + " — ошибка: %s" % e)
        QMessageBox.information(self, "Ядра", "\n".join(ok))
    def esde(self):
        dst = os.path.join(C.HOME, ".local/bin/ES-DE.AppImage")
        if not os.path.exists(dst):
            if not self.need_net(): return
            rel = json.load(urllib.request.urlopen("https://gitlab.com/api/v4/projects/18817634/releases", timeout=30))[0]
            url = next(l["url"] for l in rel["assets"]["links"] if l["name"] == "ES-DE_x64.AppImage")
            os.makedirs(os.path.dirname(dst), exist_ok=True); urllib.request.urlretrieve(url, dst); os.chmod(dst, 0o755)
        subprocess.Popen([dst])

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Emu(); w.show(); sys.exit(app.exec())
