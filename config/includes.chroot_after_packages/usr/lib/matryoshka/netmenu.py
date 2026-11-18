#!/usr/bin/env python3
"""Переключатель «Отключить бумажник» в меню сетей Plasma. Правка до входа в систему."""
import os
import subprocess
import sys

MARKER = "matryoshkaWalletSwitch"
POPUP = "org.kde.plasma.networkmanagement/contents/ui/PopupDialog.qml"

IMPORT_OLD = "import org.kde.plasma.plasmoid 2.0\n"
IMPORT_NEW = IMPORT_OLD + "import org.kde.plasma.plasma5support as Plasma5Support\n"

SOURCE_OLD = "    header: PlasmaExtras.PlasmoidHeading {\n"
SOURCE_NEW = """    Plasma5Support.DataSource {
        id: matryoshkaWallet
        engine: "executable"
        connectedSources: []
        onNewData: function(sourceName, data) {
            var line = String((data && data["stdout"]) || "").trim()
            disconnectSource(sourceName)
            if (line === "on" || line === "off") {
                matryoshkaWalletSwitch.matryoshkaHold = true
                matryoshkaWalletSwitch.checked = line === "off"
                matryoshkaWalletSwitch.matryoshkaHold = false
            } else {
                matryoshkaWalletSwitch.matryoshkaHold = false
            }
        }
    }

    header: PlasmaExtras.PlasmoidHeading {
"""

ROW_OLD = """        contentItem: RowLayout {
            Layout.fillWidth: true

            Toolbar {
"""
ROW_NEW = """        contentItem: ColumnLayout {
            Layout.fillWidth: true

            RowLayout {
            Layout.fillWidth: true

            Toolbar {
"""

TAIL_OLD = """            Loader {
                sourceComponent: stack.currentItem?.headerItems
                visible: !!item
            }
        }
    }
"""
TAIL_NEW = """            Loader {
                sourceComponent: stack.currentItem?.headerItems
                visible: !!item
            }
            }

            PlasmaComponents3.Switch {
                id: matryoshkaWalletSwitch
                property bool matryoshkaHold: true
                Layout.fillWidth: true
                text: "Отключить бумажник"
                visible: stack.depth === 1
                onToggled: {
                    if (matryoshkaHold)
                        return
                    matryoshkaWallet.connectSource("python3 /usr/lib/matryoshka/wallet_menu.py " + (checked ? "off" : "on"))
                }
                Component.onCompleted: matryoshkaWallet.connectSource("python3 /usr/lib/matryoshka/wallet_menu.py status")
            }
        }
    }
"""

SCAN_OLD = """            if (expanded) {
                handler.requestScan();
"""
SCAN_NEW = """            if (expanded) {
                matryoshkaWallet.connectSource("python3 /usr/lib/matryoshka/wallet_menu.py status")
                handler.requestScan();
"""
SCAN_MARK = "matryoshkaWallet.connectSource(\"python3 /usr/lib/matryoshka/wallet_menu.py status\")\n                handler.requestScan();"


def patch_popup(text):
    if not text:
        return None
    steps = (
        ("import org.kde.plasma.plasma5support as Plasma5Support", IMPORT_OLD, IMPORT_NEW),
        ("id: matryoshkaWallet", SOURCE_OLD, SOURCE_NEW),
        ("contentItem: ColumnLayout", ROW_OLD, ROW_NEW),
        ('text: "Отключить бумажник"', TAIL_OLD, TAIL_NEW),
        (SCAN_MARK, SCAN_OLD, SCAN_NEW),
    )
    for marker, old, new in steps:
        if marker in text:
            continue
        if old not in text or text.count(old) != 1:
            return None
        text = text.replace(old, new, 1)
    if MARKER not in text or "Отключить бумажник" not in text:
        return None
    return text


def patch_tree(root):
    path = os.path.join(root, POPUP)
    if not os.path.isfile(path):
        return [], [POPUP]
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as exc:
        return [], ["%s (%s)" % (POPUP, exc.errno)]
    new = patch_popup(text)
    if new is None:
        return [], [POPUP]
    if new == text:
        return [], []
    tmp = path + ".matryoshka-new"
    try:
        with open(tmp, "w", encoding="utf-8") as out:
            out.write(new)
        os.replace(tmp, path)
    except OSError as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return [], ["%s (%s)" % (POPUP, exc.errno)]
    return [POPUP], []


def main(argv):
    root = argv[1] if len(argv) > 1 else "/usr/share/plasma/plasmoids"
    if not os.path.isdir(root):
        return 0
    changed, missed = patch_tree(root)
    if changed:
        print("меню сетей: переключатель бумажника — " + ", ".join(changed))
    if missed:
        print("меню сетей: файл Plasma не совпал с ожидаемым, правка пропущена — " + ", ".join(missed))
    # Старые архивы обновления (18.6.9–18.6.16) после копирования файлов
    # вызывают этот скрипт от администратора и не знают про drop-vpn.sh.
    # Поэтому снятие VPN и прокси запускается здесь, уже с новыми файлами.
    if os.geteuid() == 0 and root == "/usr/share/plasma/plasmoids":
        script = "/usr/lib/matryoshka/drop-vpn.sh"
        if os.path.isfile(script) and os.access(script, os.X_OK):
            subprocess.run([script], timeout=900)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
