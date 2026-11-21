import json, re, urllib.error, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
import common as C

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
MAX_ITEMS = 8

def _redact(text, s):
    t = str(text)
    for k in (s.get("google_search_key"), s.get("google_search_cx"), s.get("yandex_search_key"), s.get("yandex_search_user"), s.get("api_key")):
        if k and len(str(k)) >= 4:
            t = t.replace(str(k), "…")
    return t

def _open(url, s, timeout=25, headers=None):
    h = {"User-Agent": UA, "Accept": "text/html,application/json,application/xml;q=0.9,*/*;q=0.8"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read(), r.headers.get("content-type", "")
    except Exception as e:
        raise RuntimeError(_redact(e, s))

def _item(title, url, snippet=""):
    title = re.sub(r"\s+", " ", (title or "").strip())
    url = (url or "").strip()
    snippet = re.sub(r"\s+", " ", (snippet or "").strip())
    if not url or not url.startswith("http"):
        return None
    if len(title) < 2:
        title = url
    return {"title": title[:300], "url": url[:1000], "snippet": snippet[:500]}

def format_items(engine, items):
    label = "Яндекс" if engine == "yandex" else "Google"
    if not items:
        return "%s: ничего не найдено" % label
    lines = [label + ":"]
    for i, it in enumerate(items[:MAX_ITEMS], 1):
        lines.append("%d. %s\n   %s%s" % (i, it["title"], it["url"], ("\n   " + it["snippet"]) if it.get("snippet") else ""))
    return "\n".join(lines)

def google_api(query, s):
    key, cx = (s.get("google_search_key") or "").strip(), (s.get("google_search_cx") or "").strip()
    if not key or not cx:
        return None
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode({"key": key, "cx": cx, "q": query, "num": MAX_ITEMS, "hl": "ru"})
    raw, _ = _open(url, s, headers={"Accept": "application/json"})
    data = json.loads(raw.decode("utf-8", "replace"))
    out = []
    for it in data.get("items") or []:
        x = _item(it.get("title"), it.get("link"), it.get("snippet"))
        if x:
            out.append(x)
    return out

def yandex_api(query, s):
    key, user = (s.get("yandex_search_key") or "").strip(), (s.get("yandex_search_user") or "").strip()
    if not key or not user:
        return None
    url = "https://yandex.com/search/xml?" + urllib.parse.urlencode({"l10n": "ru", "user": user, "key": key, "query": query, "maxpassages": 2})
    raw, _ = _open(url, s, headers={"Accept": "application/xml,text/xml"})
    root = ET.fromstring(raw)
    out = []
    for doc in root.iter("doc"):
        link = (doc.findtext("url") or doc.findtext("url") or "").strip()
        title = "".join(doc.find("title").itertext()) if doc.find("title") is not None else ""
        passages = []
        for p in doc.iter("passage"):
            passages.append("".join(p.itertext()))
        x = _item(title, link, " ".join(passages))
        if x:
            out.append(x)
        if len(out) >= MAX_ITEMS:
            break
    return out

def google_page(query, s):
    url = "https://www.google.com/search?" + urllib.parse.urlencode({"q": query, "hl": "ru", "num": MAX_ITEMS, "ie": "UTF-8"})
    raw, _ = _open(url, s)
    html = raw.decode("utf-8", "replace")
    out, seen = [], set()
    for m in re.finditer(r'<a href="(/url\?q=)(https?://[^"&]+)[^"]*"[^>]*>[\s\S]*?<h3[^>]*>([\s\S]*?)</h3>', html):
        link = urllib.parse.unquote(m.group(2))
        title = re.sub("<[^>]+>", "", m.group(3))
        x = _item(title, link)
        if x and x["url"] not in seen and "google.com" not in urllib.parse.urlparse(x["url"]).netloc:
            seen.add(x["url"]); out.append(x)
        if len(out) >= MAX_ITEMS:
            break
    if not out:
        for m in re.finditer(r'<a href="(https?://[^"]+)"[^>]*>\s*<h3[^>]*>([\s\S]*?)</h3>', html):
            link, title = m.group(1), re.sub("<[^>]+>", "", m.group(2))
            host = urllib.parse.urlparse(link).netloc
            if "google." in host or "gstatic." in host:
                continue
            x = _item(title, link)
            if x and x["url"] not in seen:
                seen.add(x["url"]); out.append(x)
            if len(out) >= MAX_ITEMS:
                break
    return out

def yandex_page(query, s):
    url = "https://yandex.ru/search/?" + urllib.parse.urlencode({"text": query, "lr": "213"})
    raw, _ = _open(url, s)
    html = raw.decode("utf-8", "replace")
    out, seen = [], set()
    for m in re.finditer(r'<a[^>]+href="(https?://[^"]+)"[^>]*tabindex="0"[^>]*>\s*<h2[^>]*>([\s\S]*?)</h2>', html):
        link, title = m.group(1), re.sub("<[^>]+>", "", m.group(2))
        host = urllib.parse.urlparse(link).netloc
        if "yandex." in host or "ya.ru" in host:
            continue
        x = _item(title, link)
        if x and x["url"] not in seen:
            seen.add(x["url"]); out.append(x)
        if len(out) >= MAX_ITEMS:
            break
    if not out:
        for m in re.finditer(r'data-log-node="[^"]*organic[^"]*"[\s\S]{0,400}?href="(https?://[^"]+)"[\s\S]{0,200}?>([\s\S]*?)</a>', html):
            link, title = m.group(1), re.sub("<[^>]+>", "", m.group(2))
            host = urllib.parse.urlparse(link).netloc
            if "yandex." in host or "ya.ru" in host:
                continue
            x = _item(title, link)
            if x and x["url"] not in seen:
                seen.add(x["url"]); out.append(x)
            if len(out) >= MAX_ITEMS:
                break
    return out

def google_search(query, s):
    items = google_api(query, s)
    if items is None:
        items = google_page(query, s)
    return items or []

def yandex_search(query, s):
    items = yandex_api(query, s)
    if items is None:
        items = yandex_page(query, s)
    return items or []

def engines_of(s):
    raw = str(s.get("search_engines") or "yandex,google").lower()
    out = [x.strip() for x in raw.split(",") if x.strip() in ("yandex", "google")]
    return out or ["yandex", "google"]

def search(query, settings=None):
    q = (query or "").strip()
    if not q:
        return "пустой запрос"
    s = settings or C.settings()
    if not C.net_on():
        return "Сеть выключена. Включите сеть, чтобы искать в интернете."
    parts = []
    for eng in engines_of(s):
        try:
            items = yandex_search(q, s) if eng == "yandex" else google_search(q, s)
            parts.append(format_items(eng, items))
        except Exception as e:
            parts.append("%s: не удалось получить результаты (%s)" % ("Яндекс" if eng == "yandex" else "Google", _redact(e, s)[:300]))
    return "\n\n".join(parts) or "ничего не найдено"
