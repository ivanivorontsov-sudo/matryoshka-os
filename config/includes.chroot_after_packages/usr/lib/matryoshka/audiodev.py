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
            cur = {"name": "", "port": "", "volume": "", "off": []}
            continue
        if cur is None:
            continue
        s = line.strip()
        if s.startswith("Name:"):
            cur["name"] = s.split(":", 1)[1].strip()
        elif line.startswith("\t\t") and ": " in s and "(" in s and ("not available" in s or "недоступ" in s) and "type:" in s:
            cur["off"].append(s.split(":", 1)[0].strip())
        elif s.startswith(("Active Port:", "Активный порт:")):
            cur["port"] = s.split(":", 1)[1].strip()
        elif s.startswith("Volume:") and not cur["volume"]:
            if "/" in s and "%" in s:
                cur["volume"] = s.split("%")[0].split()[-1] + "%"
    if cur:
        sinks.append(cur)
    for x in sinks:
        x["dead"] = bool(x["port"]) and x["port"] in x.pop("off", [])
    return [s for s in sinks if s["name"]]

def real_sink(name):
    return bool(name) and name.startswith(("alsa_output.", "bluez_output."))

def sink_rank(x):
    n, p = x["name"], (x.get("port") or "").lower()
    return (x.get("dead", False), "hdmi" in n.lower() or "hdmi" in p or "displayport" in p, not n.startswith("alsa_output.pci"))

def sink_fix(data, sinks, default, user_pick):
    by = {x["name"]: x for x in sinks or []}
    live = [x for x in sinks or [] if real_sink(x["name"]) and not x.get("dead")]
    if real_sink(default) and default in by and not by[default].get("dead"):
        data["sink_virtual_ok"] = False
        return None
    if default and default in by and not real_sink(default):
        if user_pick:
            data["sink_virtual_ok"] = True
            return None
        if data.get("sink_virtual_ok") and data.get("sink") == default:
            return None
    if not live:
        return None
    saved = data.get("sink") or ""
    if real_sink(saved) and saved in by and not by[saved].get("dead") and saved != default:
        return saved
    best = sorted(live, key=sink_rank)[0]["name"]
    return best if best != default else None

def dev_key(sink):
    n = sink or ""
    if n.startswith("bluez_output."):
        mac = n[len("bluez_output."):].split(".")[0]
        return "bt:" + mac.upper() if mac else None
    if n.startswith("alsa_output.usb-"):
        card = n[len("alsa_output.usb-"):].rsplit(".", 1)[0]
        return "usb:" + card if card else None
    return None

def saved_volume(data, sink, port):
    k = dev_key(sink)
    if k:
        v = data.get("devices", {}).get(k, {}).get(port or "", "")
        if v:
            return v
    return data.get("volumes", {}).get(vol_key(sink, port), "")

def choose_sink(data, sinks):
    by = {x["name"]: x for x in sinks or []}
    saved = data.get("sink") or ""
    if saved in by and not by[saved].get("dead"):
        return saved
    key = data.get("device") or ""
    if not key:
        return ""
    for item in sinks or []:
        if item.get("dead"):
            continue
        if dev_key(item["name"]) == key:
            return item["name"]
    return ""


def remember(data, sinks, default_sink, hold=(), keep_choice=False):
    saved = data.get("sink") or ""
    if default_sink and not (keep_choice and saved and saved != default_sink):
        if real_sink(default_sink) or data.get("sink_virtual_ok"):
            data["sink"] = default_sink
            for item in sinks:
                if item["name"] != default_sink:
                    continue
                data["port"] = item.get("port") or ""
                data["device"] = dev_key(default_sink) or ""
                break
    for s in sinks:
        if s["volume"] and s["name"] not in hold:
            data["volumes"][vol_key(s["name"], s["port"])] = s["volume"]
            k = dev_key(s["name"])
            if k:
                data.setdefault("devices", {}).setdefault(k, {})[s["port"] or ""] = s["volume"]
    return data

def restore_plan(data, sinks):
    sink = data.get("sink") or ""
    port = ""
    for s in sinks:
        if s["name"] == sink:
            port = s["port"]
            break
    vol = saved_volume(data, sink, port) if sink else ""
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

def real_source(name):
    return bool(name) and not name.endswith(".monitor") and name.startswith(("alsa_input.", "bluez_input."))

def source_fix(data, sources, default, user_pick, dead=()):
    names = [x for x in (sources or []) if x and not x.endswith(".monitor")]
    if default in dead and real_source(default):
        alive = [x for x in names if real_source(x) and x not in dead]
        internal = [x for x in alive if x.startswith("alsa_input.pci")]
        return (internal or alive or [None])[0]
    if real_source(default):
        data["source"] = default
        data["source_virtual_ok"] = False
        return None
    if not default or default not in names:
        return None
    if user_pick:
        data["source"] = default
        data["source_virtual_ok"] = True
        return None
    if data.get("source_virtual_ok") and data.get("source") == default:
        return None
    saved = data.get("source") or ""
    if real_source(saved) and saved in names and saved not in dead:
        return saved
    real = [x for x in names if real_source(x) and x not in dead]
    internal = [x for x in real if x.startswith("alsa_input.pci")]
    return (internal or real or [None])[0]

def hw_routes(sinks):
    return {x["name"]: x["port"] for x in sinks if x["name"].startswith(("alsa_output.", "bluez_output."))}

def phones_on(routes):
    return any(output_kind(n, p) == "phones" for n, p in (routes or {}).items())

def new_sinks(prev, cur):
    return [n for n in cur if prev is not None and n not in prev]

def needs_reapply(now_vol, saved, first_vol):
    return bool(saved) and bool(now_vol) and now_vol != saved and (now_vol == first_vol or now_vol == "100%")

def route_events(prev, cur):
    changed = [n for n, p in cur.items() if prev is not None and prev.get(n) != p]
    unplugged = prev is not None and phones_on(prev) and not phones_on(cur)
    return changed, unplugged

def has_hw_sink(names):
    return any(n.startswith(("alsa_output.", "bluez_output.")) for n in names or [])
