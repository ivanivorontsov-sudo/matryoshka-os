#!/usr/bin/env python3
"""Состояние бумажника для переключателя в меню сетей. Печатает только on или off."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main(argv):
    import common
    cmd = argv[1].strip() if len(argv) > 1 else "status"
    saved = common.settings()
    if cmd == "status":
        print("off" if saved.get("kwallet", True) is False else "on")
        return 0
    if cmd not in ("on", "off"):
        return 2
    on = cmd == "on"
    saved["kwallet"] = on
    common.save("settings", saved)
    import session
    session.kwallet(on)
    print("on" if on else "off")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
