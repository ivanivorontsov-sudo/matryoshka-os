import sys, os, glob, subprocess
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QCheckBox, QComboBox, QPushButton, QSpinBox, QHBoxLayout, QFileDialog
import common as C

def kvm():
    flags = open("/proc/cpuinfo").read()
    hw = " vmx" in flags or " svm" in flags
    dev = os.access("/dev/kvm", os.R_OK | os.W_OK)
    if hw and dev: return True, "Аппаратная виртуализация включена — Песочница будет работать быстро."
    if hw: return False, "Процессор умеет виртуализацию, но модуль KVM недоступен. Песочница запустится медленно (программная эмуляция)."
    return False, "Аппаратная виртуализация (Intel VT-x / AMD-V) выключена или не поддерживается. Включите её в настройках UEFI/BIOS (обычно раздел «Advanced» → «CPU Configuration» → «Intel Virtualization Technology» или «SVM Mode»). Без неё Песочница работает, но в 10–50 раз медленнее."

def live_disk():
    try:
        src = subprocess.run(["findmnt", "-no", "SOURCE", "/run/live/medium"], capture_output=True, text=True).stdout.strip()
        if src:
            pk = subprocess.run(["lsblk", "-no", "PKNAME", src], capture_output=True, text=True).stdout.strip()
            return "/dev/" + pk if pk else src
    except Exception:
        pass
    return ""

class Sandbox(QWidget):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Песочница — одноразовая Матрёшка"); self.resize(560, 420)
        v = QVBoxLayout(self); ok, msg = kvm(); self.kvm = ok
        l = QLabel(msg); l.setWordWrap(True); v.addWidget(l)
        v.addWidget(QLabel("Всё, что вы сделаете внутри, исчезнет после закрытия окна."))
        self.img = QComboBox(); d = live_disk()
        if d: self.img.addItem("Эта Матрёшка (с флешки)", d)
        for p in glob.glob(os.path.join(C.HOME, "Загрузки", "*.iso")) + glob.glob(os.path.join(C.HOME, "Downloads", "*.iso")): self.img.addItem(os.path.basename(p), p)
        h = QHBoxLayout(); h.addWidget(self.img, 1); b = QPushButton("Другой ISO…"); b.clicked.connect(self.pick); h.addWidget(b); v.addLayout(h)
        self.net = QCheckBox("Интернет внутри (по умолчанию выключен)"); v.addWidget(self.net)
        self.share = QCheckBox("Папка «Общее» внутри (только чтение)"); v.addWidget(self.share)
        self.clip = QCheckBox("Общий буфер обмена"); v.addWidget(self.clip)
        self.keep = QCheckBox("Сохранять изменения между запусками (отдельный диск)"); v.addWidget(self.keep)
        h2 = QHBoxLayout(); h2.addWidget(QLabel("Память, ГБ:")); self.mem = QSpinBox(); self.mem.setRange(1, 16); self.mem.setValue(2); h2.addWidget(self.mem); v.addLayout(h2)
        go = QPushButton("Запустить Песочницу"); go.clicked.connect(self.start); v.addWidget(go)
    def pick(self):
        p, _ = QFileDialog.getOpenFileName(self, "Образ", C.HOME, "Образы (*.iso *.img *.qcow2)")
        if p: self.img.addItem(os.path.basename(p), p); self.img.setCurrentIndex(self.img.count() - 1)
    def cmd(self):
        src = self.img.currentData()
        if not src: return None
        if src.startswith("/dev/"): C.root("sandbox-grant", src)
        a = ["qemu-system-x86_64", "-sandbox", "on,obsolete=deny,elevateprivileges=deny,spawn=deny,resourcecontrol=deny", "-nodefaults", "-m", str(self.mem.value() * 1024), "-smp", "2", "-name", "Песочница", "-display", "gtk", "-vga", "virtio", "-usb", "-device", "usb-tablet"]
        a += ["-accel", "kvm", "-cpu", "host"] if self.kvm else ["-accel", "tcg,thread=multi", "-cpu", "max"]
        if src.startswith("/dev/"):
            k = sorted(glob.glob("/run/live/medium/live/vmlinuz*")); i = sorted(glob.glob("/run/live/medium/live/initrd*"))
            if k and i:
                a += ["-kernel", k[-1], "-initrd", i[-1], "-append", "boot=live components quiet splash locales=ru_RU.UTF-8 keyboard-layouts=us,ru keyboard-options=grp:alt_shift_toggle timezone=Asia/Vladivostok hostname=sandbox username=ivan user-fullname=Иван matryoshka.sandbox"]
        if src.endswith(".iso"): a += ["-cdrom", src]
        else: a += ["-drive", "file=%s,format=raw,if=virtio,readonly=on,snapshot=on" % src if src.startswith("/dev/") else "file=%s,if=virtio,snapshot=on" % src]
        a += ["-nic", "user,model=virtio-net-pci,ipv6=off"] if self.net.isChecked() else ["-nic", "none"]
        if self.share.isChecked(): a += ["-virtfs", "local,path=%s,mount_tag=shared,security_model=none,readonly=on" % C.shared_dir()]
        if self.clip.isChecked(): a += ["-chardev", "qemu-vdagent,id=vda,clipboard=on", "-device", "virtio-serial-pci", "-device", "virtserialport,chardev=vda,name=com.redhat.spice.0"]
        if self.keep.isChecked():
            k = os.path.join(C.CONF, "sandbox-keep.qcow2")
            if not os.path.exists(k): subprocess.run(["qemu-img", "create", "-f", "qcow2", k, "20G"])
            a += ["-drive", "file=%s,if=virtio" % k]
        return a
    def start(self):
        a = self.cmd()
        if a: subprocess.Popen(a)

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Sandbox(); w.show(); sys.exit(app.exec())
