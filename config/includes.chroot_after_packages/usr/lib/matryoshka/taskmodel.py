MINERS = ("xmrig", "ethminer", "nbminer", "lolminer", "minerd", "cpuminer", "xmr-stak", "stratum", "cryptonight", "nicehash")
QUIET = {"kwin_wayland", "kwin_x11", "plasmashell", "Xorg", "Xwayland", "systemd", "kworker", "pipewire", "wireplumber"}


def cpu_jiffies(stat):
    rest = stat.rpartition(") ")[2].split()
    return int(rest[11]) + int(rest[12])


def cpu_percent(prev, cur, elapsed):
    if not prev or not cur or not elapsed or elapsed <= 0:
        return 0
    ticks = os_ticks()
    return max(0, int((cur - prev) * 100 / (elapsed * ticks)))


def os_ticks():
    try:
        return os_sysconf()
    except (OSError, ValueError, AttributeError):
        return 100


def os_sysconf():
    import os
    return os.sysconf("SC_CLK_TCK") or 100


def row_why(name, cpu, exe):
    n = (name or "").lower()
    if any(m in n for m in MINERS):
        return "майнер"
    if exe and "(deleted)" in exe:
        return "файл процесса удалён"
    if cpu >= 90 and n not in QUIET and not n.startswith("kworker"):
        return "высокая загрузка процессора"
    return ""


def brief(rows, limit=12, chars=1600):
    lines = []
    for r in rows[:limit]:
        why = r.get("why") or ""
        lines.append("%s pid=%s cpu=%s%% mem=%sМБ %s" % (r.get("name"), r.get("pid"), r.get("cpu", 0), int(r.get("rss_kb", 0) // 1024), why))
    return "\n".join(lines)[:chars]


def low_mem(avail_kb, floor_kb=400000):
    return avail_kb is not None and avail_kb < floor_kb


def ask_text(rows):
    hot = [r for r in rows if r.get("why")]
    body = brief(hot or rows)
    return ("Ты антивирусный аналитик. Ничего не удаляй и не останавливай. По-русски, коротко: есть ли среди процессов майнер, троян или другое подозрительное, и что проверить руками.\n" + body)
