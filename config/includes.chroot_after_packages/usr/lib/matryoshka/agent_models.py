import json, os, re, shlex, subprocess, urllib.error, urllib.parse, urllib.request
import common as C

UA = "Matryoshka/18.6.20 (Ollama library and Hugging Face official APIs)"
APPDIR_NAME = "applications"
DESKTOP_PREFIX = "matryoshka-ai-"

def name_ok(name):
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/:@+-]{0,200}", name or ""))

def desktop_id(model):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", model or "").strip("-") or "model"
    return DESKTOP_PREFIX + safe + ".desktop"

def appdir():
    return os.path.join(os.path.expanduser("~"), ".local", "share", APPDIR_NAME)

def desktop_path(model):
    return os.path.join(appdir(), desktop_id(model))

def local_base(s=None):
    return ((s or C.settings()).get("local_url") or "http://127.0.0.1:11434").rstrip("/")

def _req(url, data=None, method=None, timeout=30, headers=None, stream=False):
    h = {"User-Agent": UA, "Accept": "application/json"}
    if headers:
        h.update(headers)
    if data is not None and not isinstance(data, (bytes, bytearray)):
        data = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    return urllib.request.urlopen(req, timeout=timeout)

def search_ollama(query, limit=20):
    q = (query or "").strip()
    out, seen = [], set()
    if not q:
        raw = _req("https://ollama.com/api/tags", timeout=25).read()
        data = json.loads(raw.decode("utf-8", "replace"))
        for m in data.get("models") or []:
            name = (m.get("name") or m.get("model") or "").strip()
            if not name_ok(name) or name in seen:
                continue
            seen.add(name)
            out.append({"name": name, "title": name, "source": "ollama", "detail": " ".join(m.get("capabilities") or [])})
            if len(out) >= limit:
                break
        return out
    url = "https://ollama.com/search?" + urllib.parse.urlencode({"q": q})
    raw = _req(url, timeout=25, headers={"Accept": "text/html"}).read()
    html = raw.decode("utf-8", "replace")
    for href in re.findall(r'href="(/library/([^"?#]+))"', html):
        name = urllib.parse.unquote(href[1]).strip().strip("/")
        if "/" in name or not name_ok(name) or name in seen:
            continue
        seen.add(name)
        out.append({"name": name, "title": name, "source": "ollama", "detail": "библиотека Ollama"})
        if len(out) >= limit:
            break
    return out

def ollama_tags(name):
    if not name_ok(name) or "/" in name:
        return []
    url = "https://ollama.com/library/%s/tags" % urllib.parse.quote(name)
    raw = _req(url, timeout=25).read()
    data = json.loads(raw.decode("utf-8", "replace"))
    tags = data.get("tags") if isinstance(data, dict) else None
    out = []
    for t in tags or []:
        tag = t if isinstance(t, str) else (t.get("name") or t.get("tag") or "")
        tag = str(tag).strip()
        if not tag:
            continue
        full = name if tag == "latest" else (name if ":" in name else name + ":" + tag)
        if tag == "latest":
            full = name
        else:
            full = name.split(":")[0] + ":" + tag
        if name_ok(full):
            out.append(full)
    return out[:80]

def search_hf(query, limit=20):
    q = (query or "").strip() or "gguf"
    url = "https://huggingface.co/api/models?" + urllib.parse.urlencode({"search": q, "filter": "gguf", "sort": "downloads", "direction": "-1", "limit": str(limit)})
    raw = _req(url, timeout=25).read()
    data = json.loads(raw.decode("utf-8", "replace"))
    out = []
    for m in data if isinstance(data, list) else []:
        mid = (m.get("id") or "").strip()
        if not mid or not name_ok(mid):
            continue
        name = "hf.co/" + mid
        if not name_ok(name):
            continue
        downloads = m.get("downloads")
        detail = "Hugging Face, GGUF"
        if downloads:
            detail += ", скачиваний: %s" % downloads
        out.append({"name": name, "title": mid, "source": "huggingface", "detail": detail})
        if len(out) >= limit:
            break
    return out

def installed(s=None):
    raw = _req(local_base(s) + "/api/tags", timeout=5).read()
    data = json.loads(raw.decode("utf-8", "replace"))
    out = []
    for m in data.get("models") or []:
        name = (m.get("name") or m.get("model") or "").strip()
        if name:
            out.append({"name": name, "size": m.get("size") or 0, "modified": m.get("modified_at") or ""})
    return out

def running(s=None):
    try:
        installed(s)
        return True
    except Exception:
        return False

def pull(name, s=None, progress=None, timeout=7200):
    if not name_ok(name):
        raise ValueError("недопустимое имя модели")
    req = urllib.request.Request(local_base(s) + "/api/pull", json.dumps({"name": name, "stream": True}).encode(), {"Content-Type": "application/json", "User-Agent": UA})
    last = ""
    with urllib.request.urlopen(req, timeout=timeout) as r:
        buf = b""
        while True:
            chunk = r.read(4096)
            if not chunk:
                break
            buf += chunk
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line.decode("utf-8", "replace"))
                except Exception:
                    continue
                if ev.get("error"):
                    raise RuntimeError(str(ev["error"])[:400])
                st = ev.get("status") or ""
                if ev.get("total") and ev.get("completed"):
                    st = "%s %d%%" % (st, int(100 * ev["completed"] / ev["total"]))
                last = st
                if progress:
                    progress(st)
    if progress and last:
        progress(last)
    return last or "готово"

def delete_model(name, s=None):
    if not name_ok(name):
        raise ValueError("недопустимое имя модели")
    _req(local_base(s) + "/api/delete", {"name": name}, method="DELETE", timeout=30).read()

def write_desktop(model, title=None):
    if not name_ok(model):
        raise ValueError("недопустимое имя модели")
    d = appdir()
    os.makedirs(d, exist_ok=True)
    path = desktop_path(model)
    name = title or ("Чат: %s" % model)
    exec_ = "matryoshka-agent --model %s" % shlex.quote(model)
    text = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=%s" % name,
        "Exec=%s" % exec_,
        "Icon=im-user",
        "Categories=Utility;",
        "Comment=Локальная модель Матрёшки",
        "StartupNotify=true",
        "",
    ])
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path

def remove_desktop(model):
    path = desktop_path(model)
    if os.path.isfile(path):
        os.remove(path)
        return True
    return False

def owned_desktops():
    d = appdir()
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, n) for n in os.listdir(d) if n.startswith(DESKTOP_PREFIX) and n.endswith(".desktop")]

def sync_desktops(s=None):
    models = installed(s)
    keep = set()
    paths = []
    for m in models:
        path = write_desktop(m["name"])
        keep.add(os.path.basename(path))
        paths.append(path)
    for p in owned_desktops():
        if os.path.basename(p) not in keep:
            os.remove(p)
    return paths

def refresh_menu():
    d = appdir()
    os.makedirs(d, exist_ok=True)
    subprocess.run(["update-desktop-database", d], capture_output=True, text=True, timeout=30)
    subprocess.run(["kbuildsycoca6"], capture_output=True, text=True, timeout=30)
