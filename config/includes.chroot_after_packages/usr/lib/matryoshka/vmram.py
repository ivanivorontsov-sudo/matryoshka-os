import re


def parse_ram(text):
    s = str(text or "").strip().upper()
    if s.endswith("G"):
        return int(float(s[:-1]) * 1024)
    if s.endswith("M"):
        return int(float(s[:-1]))
    return int(s) if s.isdigit() else 2048


def fit_ram(requested, host_mb, avail_mb=None):
    req = parse_ram(requested)
    host = int(host_mb or 0)
    reserve = 3072 if host <= 9216 else 4096
    cap = max(1280, host - reserve) if host else req
    if avail_mb is not None:
        cap = min(cap, max(1280, int(avail_mb) - 768))
    got = min(req, cap)
    if got >= 1536:
        got = got - (got % 256)
    return max(1280, got)


def ram_token(mb):
    if mb % 1024 == 0:
        return 'ram="%dG"' % (mb // 1024)
    return 'ram="%dM"' % mb


def rewrite_ram(text, host_mb, avail_mb=None):
    m = re.search(r'^ram="([^"]+)"', text or "", re.M)
    req = m.group(1) if m else "2G"
    mb = fit_ram(req, host_mb, avail_mb)
    line = ram_token(mb)
    if m:
        return re.sub(r'^ram="[^"]+"', line, text, count=1, flags=re.M), mb
    if "guest_os=" in (text or ""):
        return re.sub(r'^(guest_os="[^"]*"\n)', r"\1" + line + "\n", text, count=1, flags=re.M), mb
    return (line + "\n" + (text or "")), mb


def should_pause_clam(host_mb, avail_mb):
    return int(host_mb or 0) <= 9216 and int(avail_mb or 0) < 4096
