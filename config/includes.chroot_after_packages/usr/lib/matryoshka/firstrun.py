import sys
from PyQt6.QtWidgets import QApplication, QWizard, QWizardPage, QVBoxLayout, QLabel, QLineEdit, QComboBox, QCheckBox
import common as C

class Wiz(QWizard):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Матрёшка — первый запуск"); self.setButtonText(QWizard.WizardButton.NextButton, "Далее >"); self.setButtonText(QWizard.WizardButton.BackButton, "< Назад"); self.setButtonText(QWizard.WizardButton.FinishButton, "Готово"); self.setButtonText(QWizard.WizardButton.CancelButton, "Отмена"); self.resize(640, 460)
        p1 = QWizardPage(); p1.setTitle("Добро пожаловать в Матрёшку"); v = QVBoxLayout(p1)
        v.addWidget(QLabel("Сейчас создадим администратора и выберем вид системы.\nПароль можно оставить пустым — тогда вход без пароля. Позже его можно включить в Центре.", wordWrap=True))
        self.name = QLineEdit("Иван"); self.pw = QLineEdit(); self.pw.setEchoMode(QLineEdit.EchoMode.Password); self.pw2 = QLineEdit(); self.pw2.setEchoMode(QLineEdit.EchoMode.Password)
        for l, w in (("Имя администратора", self.name), ("Пароль (можно пусто)", self.pw), ("Повтор пароля", self.pw2)): v.addWidget(QLabel(l)); v.addWidget(w)
        p2 = QWizardPage(); p2.setTitle("Вид"); v = QVBoxLayout(p2)
        self.theme = QComboBox(); [self.theme.addItem(t["name"], k) for k, t in C.THEMES.items()]; self.theme.setCurrentIndex(list(C.THEMES).index("matryoshka"))
        self.layout_ = QComboBox(); [self.layout_.addItem(n, k) for k, n in C.LAYOUTS.items()]
        self.mode = QComboBox(); self.mode.addItem("Стандартный (красивые анимации)", "standard"); self.mode.addItem("Простой (без анимаций, всё летает)", "simple")
        for l, w in (("Тема", self.theme), ("Расположение", self.layout_), ("Режим", self.mode)): v.addWidget(QLabel(l)); v.addWidget(w)
        p3 = QWizardPage(); p3.setTitle("Сеть и защита"); v = QVBoxLayout(p3)
        self.net = QCheckBox("Включить сеть сейчас (по умолчанию выключена, ничего не отправляется)"); v.addWidget(self.net)
        self.country = QComboBox(); [self.country.addItem(n, k) for k, (n, _) in C.COUNTRIES.items()]
        v.addWidget(QLabel("Страна (для предупреждений антивируса о законах)")); v.addWidget(self.country)
        self.ai = QComboBox(); self.ai.addItem("Бесплатный API (LLM7)", "api"); self.ai.addItem("Чат на сайте нейросети", "chat"); self.ai.addItem("Локальная модель (Ollama)", "local")
        v.addWidget(QLabel("Чем антивирус объясняет находки")); v.addWidget(self.ai)
        self.inf = QCheckBox("Настроить «Бесконечную память» (облака + диск в одной зашифрованной папке)"); v.addWidget(self.inf)
        self.dev = QCheckBox("Вы программист? Показать каталог языков, SDK и инструментов"); v.addWidget(self.dev)
        for p in (p1, p2, p3): self.addPage(p)
    def validateCurrentPage(self):
        if self.currentId() == 0 and self.pw.text() != self.pw2.text():
            self.pw2.setText(""); self.pw2.setPlaceholderText("Пароли не совпадают"); return False
        return True
    def accept(self):
        s = C.settings(); s.update(theme=self.theme.currentData(), layout=self.layout_.currentData(), country=self.country.currentData(), ai=self.ai.currentData(), admin=self.name.text()); C.save("settings", s)
        C.root("set-password", inp=self.pw.text() + "\n")
        C.root("autologin", "off" if self.pw.text() else "on")
        C.run(["chfn", "-f", self.name.text()])
        C.apply_theme(s["theme"]); C.apply_layout(s["layout"]); C.apply_mode(self.mode.currentData()); C.net_set(self.net.isChecked())
        open(C.os.path.join(C.CONF, "firstrun.done"), "w").close()
        if self.inf.isChecked(): C.subprocess.Popen(["matryoshka-cloud"])
        if self.dev.isChecked(): C.subprocess.Popen(["matryoshka-dev"])
        super().accept()

if __name__ == "__main__":
    app = QApplication(sys.argv); C.qt_ru(app); w = Wiz(); w.show(); sys.exit(app.exec())
