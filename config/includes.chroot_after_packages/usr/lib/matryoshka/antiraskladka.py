import sys, re, subprocess
import common as C

EN = C.EN + 'QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>~' + '@#$^&/?|'
RU = C.RU + 'ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮЁ' + '"№;:?.,/'
EMAIL = re.compile(r'^[\w.+-]+"[\w-]+(\.[\w-]+)+$')
URL = re.compile(r'^(https?:)?//|^www\.', re.I)

def conv(s):
    t = s.strip()
    if EMAIL.match(t): return s.replace('"', "@")
    if URL.match(t): return s
    lat = sum(ch.isascii() and ch.isalpha() for ch in s); cyr = sum("а" <= ch.lower() <= "я" or ch in "ёЁ" for ch in s)
    if lat == 0 and cyr == 0:
        lat = sum(ch in "[];',.`{}:\"<>~" for ch in s)
    src, dst = (EN, RU) if lat >= cyr else (RU, EN)
    m = dict(zip(src, dst))
    if src is RU:
        r = "".join(m.get(ch, ch) for ch in s)
        return r
    out = []
    conv_ok = lambda c: c.isalpha() or c in "[]'`{}\"<>~"
    for i, ch in enumerate(s):
        if ch in ",.;:<>":
            j = i + 1
            while j < len(s) and s[j] in ",.;:<>": j += 1
            k = i - 1
            while k >= 0 and s[k] in ",.;:<>": k -= 1
            if not (j < len(s) and conv_ok(s[j]) and k >= 0 and conv_ok(s[k])): out.append(ch); continue
        if ch in "@#$^&/?|": out.append(ch); continue
        out.append(m.get(ch, ch))
    return "".join(out)

if __name__ == "__main__":
    s = " ".join(sys.argv[1:]) or subprocess.run(["wl-paste", "--primary", "--no-newline"], capture_output=True, text=True).stdout
    if s:
        r = conv(s); subprocess.run(["wl-copy"], input=r, text=True); C.notify("Антираскладка", r[:120]); print(r)
