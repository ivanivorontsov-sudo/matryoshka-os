#!/usr/bin/env python3
"""Меню «Пуск» помнит поиск и открытую вкладку минуту после случайного закрытия."""
import os
import sys

KEEP_MS = 60000


def kept(closed_at, now, limit=KEEP_MS):
    return (now - closed_at) <= limit


def once(text, marker, old, new):
    if marker in text:
        return text
    if old not in text or text.count(old) != 1:
        return None
    return text.replace(old, new, 1)


def patch_kickoff_main(text):
    old = "    property Item footer: null\n"
    new = (
        "    property Item footer: null\n"
        "\n"
        "    // Матрёшка: поиск и вкладка меню «Пуск» живут минуту после случайного закрытия.\n"
        "    property double matryoshkaMenuClosedAt: 0\n"
        "    property string matryoshkaSearch: \"\"\n"
        "    property int matryoshkaTab: 0\n"
    )
    return once(text, "property double matryoshkaMenuClosedAt", old, new)


def patch_kickoff_header(text):
    old = """                    Connections {
                        target: kickoff
                        function onExpandedChanged() {
                            if (kickoff.expanded) {
                                searchField.clear()
                            }
                        }
                    }
"""
    new = """                    Connections {
                        target: kickoff
                        function onExpandedChanged() {
                            if (!kickoff.expanded) {
                                kickoff.matryoshkaMenuClosedAt = Date.now()
                                kickoff.matryoshkaSearch = searchField.text
                                return
                            }
                            if (Date.now() - kickoff.matryoshkaMenuClosedAt > 60000) {
                                searchField.clear()
                                kickoff.matryoshkaSearch = ""
                                return
                            }
                            if (searchField.text.length === 0 && kickoff.matryoshkaSearch.length > 0) {
                                searchField.text = kickoff.matryoshkaSearch
                            }
                        }
                    }
"""
    return once(text, "kickoff.matryoshkaSearch = searchField.text", old, new)


def patch_kickoff_footer(text):
    old = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (kickoff.expanded) {
                    tabBar.currentIndex = 0
                }
            }
        }
"""
    new = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (!kickoff.expanded) {
                    kickoff.matryoshkaTab = tabBar.currentIndex
                    return
                }
                if (Date.now() - kickoff.matryoshkaMenuClosedAt > 60000) {
                    tabBar.currentIndex = 0
                    kickoff.matryoshkaTab = 0
                    return
                }
                if (tabBar.currentIndex !== kickoff.matryoshkaTab) {
                    tabBar.currentIndex = kickoff.matryoshkaTab
                }
            }
        }
"""
    return once(text, "kickoff.matryoshkaTab = tabBar.currentIndex", old, new)


def patch_kickoff_view(text):
    old = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (kickoff.expanded) {
                    view.currentIndex = 0
                    view.positionViewAtBeginning()
                }
            }
        }
"""
    new = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (kickoff.expanded && Date.now() - kickoff.matryoshkaMenuClosedAt > 60000) {
                    view.currentIndex = 0
                    view.positionViewAtBeginning()
                }
            }
        }
"""
    return once(text, "kickoff.matryoshkaMenuClosedAt > 60000", old, new)


def patch_kicker_main(text):
    old = """    Connections {
        target: kicker

        function onExpandedChanged(expanded) {
            if (expanded) {
                windowSystem.monitorWindowVisibility(Plasmoid.fullRepresentationItem);
                justOpenedTimer.start();
            } else {
                kicker.reset();
            }
        }
    }
"""
    new = """    // Матрёшка: поиск компактного меню сбрасывается через минуту, не в момент закрытия.
    property double matryoshkaMenuClosedAt: 0
    property string matryoshkaSearch: ""

    Connections {
        target: kicker

        function onExpandedChanged(expanded) {
            if (expanded) {
                windowSystem.monitorWindowVisibility(Plasmoid.fullRepresentationItem);
                justOpenedTimer.start();
                matryoshkaForget.stop();
            } else {
                kicker.matryoshkaMenuClosedAt = Date.now();
                kicker.hideOnWindowDeactivate = true;
                matryoshkaForget.restart();
            }
        }
    }

    Timer {
        id: matryoshkaForget
        interval: 60000
        repeat: false
        onTriggered: kicker.reset()
    }
"""
    return once(text, "id: matryoshkaForget", old, new)


def patch_kicker_menu(text):
    old_text = """        onTextChanged: {
            runnerModel.query = text;
        }
"""
    new_text = """        onTextChanged: {
            runnerModel.query = text;
            kicker.matryoshkaSearch = text;
        }
"""
    old_done = """    Component.onCompleted: {
        kicker.reset.connect(reset);
        windowSystem.hidden.connect(reset);

        rootModel.refresh();
"""
    new_done = """    Component.onCompleted: {
        kicker.reset.connect(reset);
        if (Date.now() - kicker.matryoshkaMenuClosedAt <= 60000 && kicker.matryoshkaSearch.length > 0) {
            searchField.text = kicker.matryoshkaSearch
        } else if (Date.now() - kicker.matryoshkaMenuClosedAt > 60000) {
            kicker.matryoshkaSearch = ""
        }

        rootModel.refresh();
"""
    if "kicker.matryoshkaSearch = text" in text and "windowSystem.hidden.connect(reset)" not in text:
        return text
    if text.count(old_text) != 1 or text.count(old_done) != 1:
        return None
    return text.replace(old_text, new_text, 1).replace(old_done, new_done, 1)


def patch_kicker_dash(text):
    old_prop = "    property bool searching: searchField.text !== \"\"\n"
    new_prop = (
        "    property bool searching: searchField.text !== \"\"\n"
        "    property double matryoshkaClosedAt: 0\n"
    )
    old = """    onVisibleChanged: {
        reset();

        if (visible) {
            preloadAllAppsTimer.restart();
        }
    }
"""
    new = """    onVisibleChanged: {
        if (visible) {
            if (Date.now() - matryoshkaClosedAt > 60000) {
                reset();
            }
            preloadAllAppsTimer.restart();
        } else {
            matryoshkaClosedAt = Date.now()
        }
    }
"""
    if "property double matryoshkaClosedAt" in text and "matryoshkaClosedAt > 60000" in text:
        return text
    if text.count(old_prop) != 1 or text.count(old) != 1:
        return None
    return text.replace(old_prop, new_prop, 1).replace(old, new, 1)


FILES = (
    ("org.kde.plasma.kickoff/contents/ui/main.qml", patch_kickoff_main),
    ("org.kde.plasma.kickoff/contents/ui/Header.qml", patch_kickoff_header),
    ("org.kde.plasma.kickoff/contents/ui/Footer.qml", patch_kickoff_footer),
    ("org.kde.plasma.kickoff/contents/ui/KickoffListView.qml", patch_kickoff_view),
    ("org.kde.plasma.kickoff/contents/ui/KickoffGridView.qml", patch_kickoff_view),
    ("org.kde.plasma.kicker/contents/ui/main.qml", patch_kicker_main),
    ("org.kde.plasma.kicker/contents/ui/MenuRepresentation.qml", patch_kicker_menu),
    ("org.kde.plasma.kicker/contents/ui/DashboardRepresentation.qml", patch_kicker_dash),
)


def patch_tree(root):
    changed = []
    missed = []
    for rel, fn in FILES:
        path = os.path.join(root, rel)
        if not os.path.isfile(path):
            continue
        old = open(path, encoding="utf-8").read()
        new = fn(old)
        if new is None:
            missed.append(rel)
            continue
        if new != old:
            tmp = path + ".matryoshka-new"
            try:
                with open(tmp, "w", encoding="utf-8") as out:
                    out.write(new)
                os.replace(tmp, path)
            except OSError as exc:
                missed.append("%s (%s)" % (rel, exc.errno))
                try:
                    os.remove(tmp)
                except OSError:
                    pass
                continue
            changed.append(rel)
    return changed, missed


def main(argv):
    root = argv[1] if len(argv) > 1 else "/usr/share/plasma/plasmoids"
    if not os.path.isdir(root):
        return 0
    changed, missed = patch_tree(root)
    if changed:
        print("меню Пуск: поиск живёт минуту — " + ", ".join(changed))
    if missed:
        print("меню Пуск: файл Plasma не совпал с ожидаемым, правка пропущена — " + ", ".join(missed))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
