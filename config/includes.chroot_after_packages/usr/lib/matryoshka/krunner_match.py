def find_matches(query, apps, score, kcms, limit=12, app_limit=8):
    q = (query or "").strip()
    if len(q) < 2:
        return []
    out = []
    ranked = sorted(((score(a["name"], a["kw"], q), a) for a in apps), key=lambda x: -x[0])
    remove = q.lower().startswith("удалить") or q.lower().startswith("uninstall")
    qq = q.split(" ", 1)[1] if remove and " " in q else q
    if remove:
        ranked = sorted(((score(a["name"], a["kw"], qq), a) for a in apps), key=lambda x: -x[0])
    for s, a in ranked:
        if s <= 0:
            continue
        mid = "app:" + a["file"]
        props = {"actions": ["info", "uninstall"]}
        out.append((mid, a["name"], a.get("icon") or "application-x-executable", 100, float(s) / 100.0, props))
        if len([x for x in out if x[0].startswith("app:")]) >= app_limit:
            break
    needle = q if not remove else qq
    for kcm, ru, extra in kcms:
        blob = ru + " " + extra
        if score(ru, blob, needle) > 0:
            out.append(("kcm:" + kcm, "Настройки: " + ru, "preferences-system", 50, 0.7, {}))
    return out[:limit]

def with_ai_search(query, matches):
    q = (query or "").strip()
    if len(q) < 2:
        return list(matches)
    if any(not m[0].startswith("ai:") for m in matches):
        return list(matches)
    return list(matches) + [("ai:" + q, "Найти «%s»" % q, "system-search", 70, 0.95, {})]
