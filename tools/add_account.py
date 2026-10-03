#!/usr/bin/env python3
"""
Add/update account from a cURL dump (DevTools > Network > Copy as cURL).

Usage:
  add_account.py <curl_file> <proxies_file> <config_file> <name> [session_key]

If session_key is passed it wins over anything found in the dump.
Extracts: orgID, sessionKey, User-Agent, anthropic-device-id, model.

The config is edited through PyYAML (load -> mutate -> dump -> reload-check),
never by regex-splicing text, so the result is always valid YAML.
"""
import sys
import re

import yaml


# ---------- proxy pool ----------

def detect_country(proxy_url):
    m = re.search(r'-(\w{2})\.nexorcdn\.com', proxy_url or "")
    return m.group(1).lower() if m else "unknown"


def proxies_by_country(proxies_file):
    with open(proxies_file, "r") as f:
        proxies = [line.strip() for line in f if line.strip()]
    by_country = {}
    for p in proxies:
        by_country.setdefault(detect_country(p), []).append(p)
    return by_country


def pick_proxy(proxies_file, used, preferred_country=None):
    """Prefer an unused proxy from preferred_country; fall back to any unused."""
    by_country = proxies_by_country(proxies_file)
    flat = [p for group in by_country.values() for p in group]

    pools = []
    if preferred_country and preferred_country in by_country:
        pools.append(by_country[preferred_country])
    pools.append(flat)

    for pool in pools:
        for p in pool:
            if p not in used:
                return p, detect_country(p)

    # everything taken -> round-robin inside the preferred country
    pool = by_country.get(preferred_country) if preferred_country else None
    if not pool:
        pool = flat
    if pool:
        idx = len(used) % len(pool)
        return pool[idx], detect_country(pool[idx])
    return "", "unknown"


# ---------- cURL parsing ----------

def _unquote(value):
    """Chrome escapes some chars in --data-raw; headers stay plain."""
    return value.replace("\\'", "'").replace('\\"', '"').strip()


def extract_session_key(text):
    """sessionKey lives in the Cookie header of the cURL dump."""
    # -H 'Cookie: a=1; sessionKey=sk-ant-...; b=2'
    for m in re.finditer(r"-H\s+['\"]Cookie:\s*([^'\"]*)['\"]", text, re.IGNORECASE):
        ck = re.search(r"sessionKey=([^;\s]+)", m.group(1))
        if ck:
            return _unquote(ck.group(1))
    # -b '...' / --cookie '...'
    for m in re.finditer(r"(?:-b|--cookie)\s+['\"]([^'\"]*)['\"]", text):
        ck = re.search(r"sessionKey=([^;\s]+)", m.group(1))
        if ck:
            return _unquote(ck.group(1))
    # last resort: raw key anywhere in the dump
    m = re.search(r"(sk-ant-sid[A-Za-z0-9_\-]+)", text)
    return m.group(1) if m else None


def extract_header(text, name):
    m = re.search(r"-H\s+['\"]%s:\s*([^'\"]*)['\"]" % re.escape(name),
                  text, re.IGNORECASE)
    return _unquote(m.group(1)) if m else None


def parse_curl(text):
    org = re.search(r"/organizations/([a-f0-9\-]{36})/", text)
    model = re.search(r'"model"\s*:\s*"([^"]+)"', text)
    return {
        "orgID": org.group(1) if org else None,
        "sessionKey": extract_session_key(text),
        "userAgent": extract_header(text, "User-Agent") or "",
        "deviceID": extract_header(text, "anthropic-device-id"),
        "model": model.group(1) if model else None,
    }


# ---------- config.yaml ----------

SESSION_KEYS_ORDER = ["sessionKey", "orgID", "cookie", "name",
                      "userAgent", "proxyCountry", "proxy"]


def load_config(path):
    with open(path, "r") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg.get("sessions"), list):
        cfg["sessions"] = []
    return cfg


def save_config(cfg, path):
    text = yaml.dump(cfg, default_flow_style=False, sort_keys=False,
                     allow_unicode=True, width=4096)
    # round-trip guard: never leave a broken file behind
    yaml.safe_load(text)
    with open(path, "w") as f:
        f.write(text)


def find_session(cfg, org_id):
    for i, s in enumerate(cfg["sessions"]):
        if isinstance(s, dict) and s.get("orgID") == org_id:
            return i
    return None


def ordered_session(s):
    out = {k: s[k] for k in SESSION_KEYS_ORDER if k in s}
    for k, v in s.items():
        if k not in out:
            out[k] = v
    return out


# ---------- main ----------

HINT = """\
  Chrome dropped the Cookie header. Two ways to fix it:

  A) One-time DevTools toggle (then 'Copy as cURL' always carries cookies):
     DevTools (F12) -> Network tab -> gear icon (Settings)
       -> enable "Allow to generate HAR with sensitive data"
     Then hard-reload the page (Ctrl+Shift+R) so the request is not cached,
     send a message on claude.ai, wait until the /completion request FINISHES
     (not pending), right-click -> Copy -> Copy as cURL.

  B) Fastest: paste just the key manually.
     DevTools -> Application -> Cookies -> https://claude.ai -> sessionKey
     copy its Value and run:
       ./tools/add-account.sh <name> <sessionKey>
"""


def main():
    if len(sys.argv) < 5:
        print("Usage: add_account.py <curl_file> <proxies_file> <config_file> "
              "<name> [session_key]")
        sys.exit(1)

    curl_file, proxies_file, config_file = sys.argv[1], sys.argv[2], sys.argv[3]
    account_name = sys.argv[4]
    key_override = sys.argv[5] if len(sys.argv) > 5 else None

    with open(curl_file, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    print(f"  Input: {len(text)} chars")

    data = parse_curl(text)

    if key_override:
        data["sessionKey"] = key_override
        print("  SessionKey: from argument")

    if not data["sessionKey"]:
        print("ERROR: sessionKey not found in the cURL dump.")
        print(HINT)
        sys.exit(3)

    if not data["orgID"]:
        print("ERROR: no /organizations/<uuid>/ in the URL - is this a /completion request?")
        sys.exit(1)

    print(f"  SessionKey: {data['sessionKey'][:36]}...")
    print(f"  OrgID:      {data['orgID']}")
    print(f"  UserAgent:  {(data['userAgent'] or '(none)')[:60]}")
    if data["deviceID"]:
        print(f"  DeviceID:   {data['deviceID']}")
    if data["model"]:
        print(f"  Model:      {data['model']}")

    cfg = load_config(config_file)

    used = [s.get("proxy") for s in cfg["sessions"]
            if isinstance(s, dict) and s.get("proxy")]
    if cfg.get("proxy"):
        used.append(cfg["proxy"])

    idx = find_session(cfg, data["orgID"])

    if idx is not None:
        session = cfg["sessions"][idx]
        name = session.get("name") or account_name
        preferred = session.get("proxyCountry") or None
        proxy, country = pick_proxy(proxies_file, used, preferred)
        print(f'\n  "{name}" EXISTS -> UPDATE (country: {preferred or "?"} -> {country})')
        session["sessionKey"] = data["sessionKey"]
        session["orgID"] = data["orgID"]
        session.setdefault("cookie", "")
        session["name"] = name
        session["userAgent"] = data["userAgent"]
        session["proxyCountry"] = country
        session["proxy"] = proxy
        cfg["sessions"][idx] = ordered_session(session)
    else:
        if not account_name:
            print("ERROR: new account requires a name.")
            sys.exit(2)
        proxy, country = pick_proxy(proxies_file, used)
        name = account_name
        print(f'\n  New account "{name}" -> ADD (country: {country})')
        cfg["sessions"].append(ordered_session({
            "sessionKey": data["sessionKey"],
            "orgID": data["orgID"],
            "cookie": "",
            "name": name,
            "userAgent": data["userAgent"],
            "proxyCountry": country,
            "proxy": proxy,
        }))

    try:
        save_config(cfg, config_file)
    except Exception as e:
        print(f"ERROR: failed to write config: {e}")
        sys.exit(4)

    print(f"\n  OK {name} | {country} | key={data['sessionKey'][:24]}... "
          f"| proxy=...{proxy[-32:]}")
    print(f"  sessions total: {len(cfg['sessions'])}")


if __name__ == "__main__":
    main()