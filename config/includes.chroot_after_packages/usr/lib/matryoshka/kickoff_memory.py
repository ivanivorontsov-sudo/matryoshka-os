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


MAIN_KEEP = (
    "    property Item footer: null\n"
    "\n"
    "    // Матрёшка: поиск и вкладка живут минуту после закрытия, затем сбрасываются сами.\n"
    "    property double matryoshkaMenuClosedAt: 0\n"
    "    property string matryoshkaSearch: \"\"\n"
    "    property int matryoshkaTab: 0\n"
    "    Timer {\n"
    "        id: matryoshkaForget\n"
    "        interval: 60000\n"
    "        repeat: false\n"
    "        onTriggered: {\n"
    "            matryoshkaSearch = \"\"\n"
    "            matryoshkaTab = 0\n"
    "            matryoshkaMenuClosedAt = 0\n"
    "            if (searchField) {\n"
    "                searchField.clear()\n"
    "            }\n"
    "        }\n"
    "    }\n"
    "    onExpandedChanged: {\n"
    "        if (expanded) {\n"
    "            matryoshkaForget.stop()\n"
    "        } else if (!matryoshkaForget.running) {\n"
    "            matryoshkaMenuClosedAt = Date.now()\n"
    "            if (searchField) {\n"
    "                matryoshkaSearch = searchField.text\n"
    "            }\n"
    "            matryoshkaForget.start()\n"
    "        }\n"
    "    }\n"
)

MAIN_OLD_KEEP = (
    "    property Item footer: null\n"
    "\n"
    "    // Матрёшка: поиск и вкладка меню «Пуск» живут минуту после случайного закрытия.\n"
    "    property double matryoshkaMenuClosedAt: 0\n"
    "    property string matryoshkaSearch: \"\"\n"
    "    property int matryoshkaTab: 0\n"
)


def patch_kickoff_main(text):
    if "id: matryoshkaForget" in text:
        return text
    if MAIN_OLD_KEEP in text:
        return text.replace(MAIN_OLD_KEEP, MAIN_KEEP, 1)
    old = "    property Item footer: null\n"
    return once(text, "id: matryoshkaForget", old, MAIN_KEEP)


HEADER_OLD = """                    Connections {
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
HEADER_NEW = """                    Connections {
                        target: kickoff
                        function onExpandedChanged() {
                            if (!kickoff.expanded) {
                                if (searchField.text.length > 0) {
                                    kickoff.matryoshkaSearch = searchField.text
                                }
                                return
                            }
                            if (kickoff.matryoshkaMenuClosedAt === 0 || Date.now() - kickoff.matryoshkaMenuClosedAt > 60000) {
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
HEADER_UPSTREAM = """                    Connections {
                        target: kickoff
                        function onExpandedChanged() {
                            if (kickoff.expanded) {
                                searchField.clear()
                            }
                        }
                    }
"""


def patch_kickoff_header(text):
    if "matryoshkaMenuClosedAt === 0" in text:
        return text
    if HEADER_OLD in text:
        return text.replace(HEADER_OLD, HEADER_NEW, 1)
    return once(text, "matryoshkaMenuClosedAt === 0", HEADER_UPSTREAM, HEADER_NEW)


FOOTER_OLD = """        Connections {
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
FOOTER_NEW = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (!kickoff.expanded) {
                    kickoff.matryoshkaTab = tabBar.currentIndex
                    return
                }
                if (kickoff.matryoshkaMenuClosedAt === 0 || Date.now() - kickoff.matryoshkaMenuClosedAt > 60000) {
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
FOOTER_UPSTREAM = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (kickoff.expanded) {
                    tabBar.currentIndex = 0
                }
            }
        }
"""


def patch_kickoff_footer(text):
    if "matryoshkaMenuClosedAt === 0" in text:
        return text
    if FOOTER_OLD in text:
        return text.replace(FOOTER_OLD, FOOTER_NEW, 1)
    return once(text, "matryoshkaMenuClosedAt === 0", FOOTER_UPSTREAM, FOOTER_NEW)


VIEW_OLD = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (kickoff.expanded && Date.now() - kickoff.matryoshkaMenuClosedAt > 60000) {
                    view.currentIndex = 0
                    view.positionViewAtBeginning()
                }
            }
        }
"""
VIEW_NEW = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (kickoff.expanded && (kickoff.matryoshkaMenuClosedAt === 0 || Date.now() - kickoff.matryoshkaMenuClosedAt > 60000)) {
                    view.currentIndex = 0
                    view.positionViewAtBeginning()
                }
            }
        }
"""
VIEW_UPSTREAM = """        Connections {
            target: kickoff
            function onExpandedChanged() {
                if (kickoff.expanded) {
                    view.currentIndex = 0
                    view.positionViewAtBeginning()
                }
            }
        }
"""


def patch_kickoff_view(text):
    if "matryoshkaMenuClosedAt === 0" in text:
        return text
    if VIEW_OLD in text:
        return text.replace(VIEW_OLD, VIEW_NEW, 1)
    return once(text, "matryoshkaMenuClosedAt === 0", VIEW_UPSTREAM, VIEW_NEW)


def patch_kicker_main(text):
    old_fire = "        onTriggered: kicker.reset()\n"
    new_fire = (
        "        onTriggered: {\n"
        "            kicker.matryoshkaSearch = \"\"\n"
        "            kicker.matryoshkaMenuClosedAt = 0\n"
        "            kicker.reset()\n"
        "        }\n"
    )
    if "kicker.matryoshkaMenuClosedAt = 0" in text:
        return text
    if "id: matryoshkaForget" in text and text.count(old_fire) == 1:
        return text.replace(old_fire, new_fire, 1)
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
        onTriggered: {
            kicker.matryoshkaSearch = ""
            kicker.matryoshkaMenuClosedAt = 0
            kicker.reset()
        }
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
