# Copyright (c) 2026 Иван Воронцов. SPDX-License-Identifier: GPL-3.0-only
"""Нейросеть как в ИванКоде: те же бесплатные провайдеры, ключи и OpenAI-совместимый чат.

Запрос уходит только по явному действию пользователя и только на выбранный адрес.
Своей телеметрии у офиса нет.
"""

import json
import os
import ssl
import time
import urllib.request

PROVIDERS = [
    {"id": "ollama", "name": "Ollama (локально, без ключа)", "type": "openai", "base": "http://127.0.0.1:11434/v1", "model": "qwen2.5-coder:7b", "key": ""},
    {"id": "deepseek", "name": "DeepSeek API", "type": "openai", "base": "https://api.deepseek.com/v1", "model": "deepseek-chat", "key": ""},
    {"id": "qwen", "name": "Qwen (DashScope)", "type": "openai", "base": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus", "key": ""},
    {"id": "openai", "name": "OpenAI", "type": "openai", "base": "https://api.openai.com/v1", "model": "gpt-4o-mini", "key": ""},
    {"id": "openrouter", "name": "OpenRouter", "type": "openai", "base": "https://openrouter.ai/api/v1", "model": "qwen/qwen-2.5-coder-32b-instruct", "key": ""},
    {"id": "llm7", "name": "LLM7 (бесплатно, без регистрации)", "type": "openai", "base": "https://api.llm7.io/v1", "model": "default", "key": "unused", "keyless": True, "max_tokens": 4000},
    {"id": "pollinations", "name": "Pollinations (бесплатно, без ключа)", "type": "openai", "base": "https://text.pollinations.ai/openai", "model": "openai", "key": ""},
    {"id": "gigachat", "name": "GigaChat API (ключ авторизации)", "type": "gigachat", "base": "", "model": "GigaChat", "key": "", "scope": "GIGACHAT_API_PERS"},
]

SITES = [
    {"id": "deepseek", "name": "DeepSeek", "url": "https://chat.deepseek.com/"},
    {"id": "qwen", "name": "Qwen", "url": "https://chat.qwen.ai/"},
    {"id": "gigachat", "name": "GigaChat", "url": "https://giga.chat/"},
    {"id": "chatgpt", "name": "ChatGPT", "url": "https://chatgpt.com/"},
    {"id": "alice", "name": "Алиса (Яндекс)", "url": "https://alice.yandex.ru/"},
    {"id": "grok", "name": "Grok", "url": "https://grok.com/"},
    {"id": "claude", "name": "Claude", "url": "https://claude.ai/new"},
    {"id": "mistral", "name": "Mistral Le Chat", "url": "https://chat.mistral.ai/chat"},
]

CONF = os.path.join(os.path.expanduser("~"), ".config", "matryoshka", "office-ai.json")
_GIGA = {}
_POL_LAST = 0


def load_settings():
    base = {"prov": "llm7", "providers": json.loads(json.dumps(PROVIDERS)), "site": "deepseek"}
    os_settings = os.path.join(os.path.expanduser("~"), ".config", "matryoshka", "settings.json")
    if os.path.exists(os_settings):
        try:
            shared = json.load(open(os_settings, encoding="utf-8"))
        except Exception:
            shared = {}
        if shared.get("api_key"):
            for p in base["providers"]:
                if p["id"] in ("deepseek", "openai", "openrouter", "qwen") and not p.get("key"):
                    p["key"] = shared["api_key"]
        if shared.get("local_model"):
            for p in base["providers"]:
                if p["id"] == "ollama":
                    p["model"] = shared["local_model"]
                    if shared.get("local_url"):
                        p["base"] = shared["local_url"].rstrip("/") + "/v1"
    if os.path.exists(CONF):
        try:
            saved = json.load(open(CONF, encoding="utf-8"))
            if saved.get("providers"):
                known = {p["id"]: p for p in base["providers"]}
                for item in saved["providers"]:
                    if item.get("id") in known:
                        known[item["id"]].update(item)
            if saved.get("prov"):
                base["prov"] = saved["prov"]
            if saved.get("site"):
                base["site"] = saved["site"]
        except Exception:
            pass
    return base


def save_settings(settings):
    os.makedirs(os.path.dirname(CONF), exist_ok=True)
    fd = os.open(CONF, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=1)


def provider(settings=None, prov_id=None):
    settings = settings or load_settings()
    want = prov_id or settings.get("prov") or "llm7"
    for item in settings["providers"]:
        if item["id"] == want:
            return item
    return settings["providers"][0]


def chat(messages, prov, timeout=120):
    """Один ответ целиком. Повторяет Pollinations при бесплатном пределе, как ИванКод."""
    global _POL_LAST
    if prov.get("type") == "gigachat":
        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": "Bearer " + _giga_token(prov)}
        context = ssl._create_unverified_context()
    else:
        url = prov["base"].rstrip("/") + "/chat/completions"
        headers = {"Content-Type": "application/json"}
        if prov.get("key"):
            headers["Authorization"] = "Bearer " + prov["key"]
        context = None
    body = {"model": prov.get("model") or "default", "messages": messages, "temperature": 0.2}
    if prov.get("max_tokens"):
        body["max_tokens"] = prov["max_tokens"]
    if "pollinations" in (prov.get("base") or ""):
        gap = 31 - (time.time() - _POL_LAST)
        if gap > 0:
            time.sleep(gap)
        body["reasoning_effort"] = "low"
    data = json.dumps(body).encode("utf-8")
    last = None
    for attempt in range(2):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
                payload = json.load(resp)
            if "pollinations" in (prov.get("base") or ""):
                _POL_LAST = time.time()
            return payload["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            last = RuntimeError("HTTP %s: %s" % (exc.code, detail))
            if attempt == 0 and (exc.code == 402 or exc.code == 429) and "pollinations" in (prov.get("base") or ""):
                time.sleep(31)
                continue
            raise last
    raise last


def _giga_token(prov):
    slot = _GIGA.setdefault(prov.get("id") or "gigachat", {})
    if slot.get("token") and slot.get("exp", 0) > time.time() + 60:
        return slot["token"]
    body = ("scope=" + (prov.get("scope") or "GIGACHAT_API_PERS")).encode()
    req = urllib.request.Request(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        data=body,
        headers={
            "Authorization": "Basic " + (prov.get("key") or ""),
            "RqUID": _uuid(),
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30, context=ssl._create_unverified_context()) as resp:
        payload = json.load(resp)
    slot["token"] = payload["access_token"]
    slot["exp"] = time.time() + 1500
    return slot["token"]


def _uuid():
    import uuid
    return str(uuid.uuid4())


def parse_reply(text):
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("в ответе нет JSON")
    data = json.loads(text[start:end + 1])
    if not isinstance(data.get("say", ""), str) or not isinstance(data.get("actions", []), list):
        raise ValueError("нужны поля say и actions")
    for action in data.get("actions", []):
        if action.get("tool") not in TOOLS_ALLOWED():
            raise ValueError("неизвестный инструмент " + str(action.get("tool")))
        if not isinstance(action.get("args", {}), dict):
            raise ValueError("args должен быть объектом")
    return data


def TOOLS_ALLOWED():
    from .tools import TOOLS
    return TOOLS
