import os, re, shutil, sys, tempfile
from urllib.parse import unquote

STAMP = os.path.expanduser("~/.local/state/matryoshka/icons-v3")
CFG = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
DIRS = [os.path.expanduser("~/.local/share/applications"), "/usr/share/applications", "/usr/local/share/applications", "/var/lib/flatpak/exports/share/applications", os.path.expanduser("~/.local/share/flatpak/exports/share/applications")]
URL = re.compile(r"file://(/[^,\n]*?\.desktop)(?=,|$)")


def known(name):
    return any(os.path.isfile(os.path.join(d, name)) for d in DIRS)


def convert(line):
    k, sep, v = line.partition("=")
    if not sep or k.strip() != "launchers":
        return line, 0
    n = [0]

    def sub(m):
        name = os.path.basename(unquote(m.group(1)))
        if known(name):
            n[0] += 1
            return "applications:" + name
        return m.group(0)
    return k + sep + URL.sub(sub, v.rstrip("\n")) + ("\n" if line.endswith("\n") else ""), n[0]


def fix():
    if os.path.exists(STAMP) or not os.path.isfile(CFG):
        return 0
    text = open(CFG, encoding="utf-8", errors="surrogateescape").read()
    out, total = [], 0
    for line in text.splitlines(True):
        new, n = convert(line)
        out.append(new)
        total += n
    if total:
        shutil.copy2(CFG, CFG + ".matryoshka-icons.bak")
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(CFG), prefix=".appletsrc.")
        with os.fdopen(fd, "w", encoding="utf-8", errors="surrogateescape") as f:
            f.write("".join(out))
        shutil.copymode(CFG, tmp)
        os.replace(tmp, CFG)
    os.makedirs(os.path.dirname(STAMP), exist_ok=True)
    open(STAMP, "w", encoding="utf-8").write("%d\n" % total)
    return total


if __name__ == "__main__":
    try:
        print(fix())
    except Exception as e:
        print("launchers: %s" % e, file=sys.stderr)
