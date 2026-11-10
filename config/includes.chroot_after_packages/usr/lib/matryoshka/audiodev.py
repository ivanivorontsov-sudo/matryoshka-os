import json, os, time

def pick_source(names, default):
    names = [x for x in (names or []) if x]
    if default and not str(default).endswith(".monitor"):
        return default
    real = [x for x in names if x.startswith("alsa_input.") and not x.endswith(".monitor")]
    ok = [x for x in names if not x.endswith(".monitor")]
    return real[0] if real else (ok[0] if ok else None)

def vol_key(sink, port):
    return "%s|%s" % (sink or "", port or "")

def load_audio(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("sink", "")
            d.setdefault("volumes", {})
            return d
    except Exception:
        pass
    return {"sink": "", "volumes": {}}

def save_audio(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)

def parse_sinks(text):
    sinks = []
    cur = None
    for line in text.splitlines():
        if line.startswith("Sink #") or line.startswith("Source #"):
            if cur:
                sinks.append(cur)
            cur = {"name": "", "port": "", "volume": ""}
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("Name:"):
            cur["name"] = s.split(":", 1)[1].strip()
        elif s.startswith("Active Port:"):
            cur["port"] = s.split(":", 1)[1].strip()
        elif s.startswith("Volume:") and not cur["volume"]:
            if "/" in s and "%" in s:
                cur["volume"] = s.split("%")[0].split()[-1] + "%"
    if cur:
        sinks.append(cur)
    return [s for s in sinks if s["name"]]

def remember(data, sinks, default_sink):
    if default_sink:
        data["sink"] = default_sink
    for s in sinks:
        if s["volume"]:
            data["volumes"][vol_key(s["name"], s["port"])] = s["volume"]
    return data

def restore_plan(data, sinks):
    sink = data.get("sink") or ""
    port = ""
    for s in sinks:
        if s["name"] == sink:
            port = s["port"]
            break
    vol = data.get("volumes", {}).get(vol_key(sink, port), "") if sink else ""
    return sink, vol

PHONES = ("headphone", "headset", "наушник", "гарнитур", "bluez", "bluetooth", "a2dp", "usb")

def output_kind(sink, port):
    t = ("%s %s" % (sink or "", port or "")).lower()
    return "phones" if any(k in t for k in PHONES) else "speakers"

def preset_for(settings, sink, port):
    if not settings.get("sound_enhance", True):
        return ""
    if output_kind(sink, port) == "phones":
        return settings.get("sound_phones", settings.get("sound_preset", "Пространство-наушники"))
    return settings.get("sound_speakers", "@ee")
