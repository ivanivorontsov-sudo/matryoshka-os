import sys, os, subprocess
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QLabel, QMessageBox
from PyQt6.QtCore import Qt
import common as C

TOOLS = [("python", "Python", "mise"), ("node", "Node.js", "mise"), ("go", "Go", "mise"), ("rust", "Rust", "mise"), ("java", "Java (Temurin)", "mise"), ("kotlin", "Kotlin", "mise"),
         ("dotnet", ".NET", "mise"), ("ruby", "Ruby", "mise"), ("php", "PHP", "mise"), ("zig", "Zig", "mise"), ("deno", "Deno", "mise"), ("bun", "Bun", "mise"), ("flutter", "Flutter", "mise"),
         ("gcc", "C/C++ (gcc, gdb, cmake)", "apt:build-essential gdb cmake ninja-build"), ("git", "Git", "apt:git git-lfs"), ("docker", "Podman (контейнеры без root)", "apt:podman podman-compose"),
         ("com.visualstudio.code", "VS Code", "flatpak"), ("com.vscodium.codium", "VSCodium (без телеметрии)", "flatpak"), ("com.jetbrains.IntelliJ-IDEA-Community", "IntelliJ IDEA CE", "flatpak"),
         ("com.jetbrains.PyCharm-Community", "PyCharm CE", "flatpak"), ("com.google.AndroidStudio", "Android Studio", "flatpak"), ("org.kde.kdevelop", "KDevelop", "flatpak")]
PROFILE = os.path.join(C.HOME, ".config/matryoshka/dev.sh")

MISE_SH = 'M="$HOME/.local/bin/mise"; mkdir -p "$HOME/.local/bin"; [ -x "$M" ] || { echo "Загрузка mise..."; curl -fsSL --connect-timeout 15 --max-time 120 https://mise.run | sh; [ -x \"$M\" ] || { T=$(curl -fsSL --max-time 30 https://api.github.com/repos/jdx/mise/releases/latest | sed -n "s/.*\\"tag_name\\": *\\"\\([^\\"]*\\)\\".*/\\1/p"); curl -fL --connect-timeout 15 -o "$M" "https://github.com/jdx/mise/releases/download/$T/mise-$T-linux-x64" && chmod +x "$M"; }; }'

def mise():
    m = os.path.join(C.HOME, ".local/bin/mise")
    os.makedirs(os.path.dirname(PROFILE), exist_ok=True)
    open(PROFILE, "w").write('export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"\n')
    for rc in (".bashrc", ".profile"):
        p = os.path.join(C.HOME, rc); s = open(p).read() if os.path.exists(p) else ""
        if PROFILE not in s: open(p, "a").write('\n[ -f "%s" ] && . "%s"\n' % (PROFILE, PROFILE))
    return m

def register_ides():
    shims = os.path.join(C.HOME, ".local/share/mise/shims")
    subprocess.run(["flatpak", "override", "--user", "--filesystem=~/.local/share/mise:ro", "--filesystem=~/.local/bin:ro", "--env=PATH=/app/bin:/usr/bin:" + shims])

class Dev(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Вы программист?"); self.resize(560, 620)
        v = QVBoxLayout(self); l = QLabel("Отметьте нужное — Матрёшка скачает только это. Языки ставятся через mise и сразу видны в терминале, VS Code и JetBrains."); l.setWordWrap(True); v.addWidget(l)
        self.list = QListWidget(); v.addWidget(self.list, 1)
        for k, n, how in TOOLS:
            it = QListWidgetItem(n); it.setData(256, (k, how)); it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable); it.setCheckState(Qt.CheckState.Unchecked); self.list.addItem(it)
        b = QPushButton("Установить отмеченное"); b.clicked.connect(self.go); v.addWidget(b)
    def go(self):
        from PyQt6.QtCore import Qt
        if not C.net_on(): QMessageBox.information(self, "Сеть", "Включите сеть."); return
        sel = [self.list.item(i).data(256) for i in range(self.list.count()) if self.list.item(i).checkState() == Qt.CheckState.Checked]
        cmds = []; ms = [k for k, h in sel if h == "mise"]; ap = " ".join(h[4:] for k, h in sel if h.startswith("apt:")); fp = [k for k, h in sel if h == "flatpak"]
        if ms: m = mise(); cmds.append(MISE_SH); cmds.append("\"%s\" use -g %s" % (m, " ".join(x + "@latest" for x in ms)))
        if ap: cmds.append("pkexec /usr/lib/matryoshka/root.sh apt-install " + ap)
        if fp: cmds.append("flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo; flatpak install --user -y flathub " + " ".join(fp))
        if not cmds: return
        register_ides()
        subprocess.Popen(["konsole", "--hold", "-e", "sh", "-c", "; ".join(cmds) + "; echo; echo ГОТОВО. Откройте новый терминал."], start_new_session=True)
        QMessageBox.information(self, "Установка", "Установка идёт в окне терминала, там виден ход загрузки."); self.close()

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Dev(); w.show(); sys.exit(app.exec())
