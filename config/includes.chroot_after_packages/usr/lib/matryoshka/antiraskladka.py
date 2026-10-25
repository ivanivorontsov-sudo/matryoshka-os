import sys, subprocess
import common as C

def conv(s):
    en = C.EN + C.EN.upper().replace("[", "{").replace("]", "}").replace(";", ":").replace("'", '"').replace(",", "<").replace(".", ">").replace("`", "~")
    ru = C.RU + C.RU.upper()
    lat = sum(ch in en for ch in s); cyr = sum(ch in ru for ch in s)
    a, b = (en, ru) if lat >= cyr else (ru, en)
    return "".join(b[a.index(ch)] if ch in a else ch for ch in s)

if __name__ == "__main__":
    s = " ".join(sys.argv[1:]) or subprocess.run(["wl-paste", "--primary", "--no-newline"], capture_output=True, text=True).stdout
    if s:
        r = conv(s); subprocess.run(["wl-copy"], input=r, text=True); C.notify("Антираскладка", r[:120]); print(r)
