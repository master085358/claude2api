#!/usr/bin/env python3
"""
Idempotent add/update account from fetch() clipboard content.
Usage: python3 add_account.py <clipboard_file> <session_key> <proxies_file> <config_file> [name]

If orgID is new -> name is REQUIRED (prompted by shell wrapper).
If orgID exists -> existing name is kept, name arg is ignored.
Country is detected from proxy URL and preserved on reassignment.
"""
import sys
import re
import json


def detect_country(proxy_url):
    """Detect country code from proxy URL like ...@hollander-3-nl.nexorcdn.com:56628"""
    m = re.search(r'-(\w{2})\.nexorcdn\.com', proxy_url)
    if m:
        return m.group(1).lower()
    return "unknown"


def parse_fetch(text):
    """Extract orgID and other info from fetch() clipboard content."""
    url_pattern = r'fetch\("([^"]+)"'
    urls = re.findall(url_pattern, text)

    target_url = None
    for u in urls:
        if "/completion" in u and "chat_conversations" in u:
            target_url = u
            break

    if not target_url:
        return None

    org_match = re.search(r"/organizations/([a-f0-9-]+)/", target_url)
    if not org_match:
        return None

    org_id = org_match.group(1)

    fetch_start = text.find('fetch("' + target_url + '"')
    if fetch_start == -1:
        return {"orgID": org_id}

    chunk = text[fetch_start:]
    model_match = re.search(r'"model":"([^"]+)"', chunk)
    model = model_match.group(1) if model_match else ""

    return {"orgID": org_id, "model": model}


def get_proxies_by_country(proxies_file):
    """Read proxies and group by country."""
    with open(proxies_file, "r") as f:
        proxies = [line.strip() for line in f if line.strip()]

    by_country = {}
    for p in proxies:
        country = detect_country(p)
        by_country.setdefault(country, []).append(p)

    return by_country


def get_next_proxy(proxies_file, existing_proxies, preferred_country=None):
    """Get next proxy not yet used. If preferred_country set, pick from that country first."""
    by_country = get_proxies_by_country(proxies_file)

    if preferred_country and preferred_country in by_country:
        for p in by_country[preferred_country]:
            if p not in existing_proxies:
                return p, preferred_country

    # Fallback: any unused proxy
    all_proxies = []
    for country_proxies in by_country.values():
        all_proxies.extend(country_proxies)

    for p in all_proxies:
        if p not in existing_proxies:
            return p, detect_country(p)

    # All used, round-robin within preferred country
    if preferred_country and preferred_country in by_country:
        pool = by_country[preferred_country]
    else:
        pool = all_proxies

    if pool:
        idx = len(existing_proxies) % len(pool)
        return pool[idx], detect_country(pool[idx])

    return "", "unknown"


def find_session_by_orgid(content, org_id):
    """Find if orgID exists in config. Returns (found, existing_name, existing_country)."""
    blocks = re.split(r'(?=\s*- sessionKey:)', content)
    for block in blocks:
        if f'orgID: "{org_id}"' in block:
            name_match = re.search(r'name:\s*"([^"]*)"', block)
            existing_name = name_match.group(1) if name_match else ""
            country_match = re.search(r'proxyCountry:\s*"([^"]*)"', block)
            existing_country = country_match.group(1) if country_match else ""
            return True, existing_name, existing_country
    return False, "", ""


def update_session(content, org_id, session_key, proxy, country):
    """Update existing session's sessionKey, proxy, and proxyCountry. Keep name intact."""
    lines = content.split("\n")
    result = []
    in_target = False

    for line in lines:
        if f'orgID: "{org_id}"' in line:
            in_target = True
            result.append(line)
            continue

        if in_target:
            if re.match(r'\s*sessionKey:', line):
                result.append(f'  - sessionKey: "{session_key}"')
            elif re.match(r'\s*proxyCountry:', line):
                result.append(f'    proxyCountry: "{country}"')
            elif re.match(r'\s*proxy:', line):
                result.append(f'    proxy: "{proxy}"')
                in_target = False
            elif re.match(r'\s*- sessionKey:', line) or (line.strip() and not line.startswith(' ') and not line.startswith('\t')):
                in_target = False
                result.append(line)
            else:
                result.append(line)
        else:
            result.append(line)

    return "\n".join(result)


def add_session(content, org_id, session_key, proxy, name, country):
    """Add a new session block."""
    new_block = f"""  - sessionKey: "{session_key}"
    orgID: "{org_id}"
    cookie: ""
    name: "{name}"
    proxyCountry: "{country}"
    proxy: "{proxy}"
"""
    lines = content.split("\n")
    insert_idx = None
    in_sessions = False

    for i, line in enumerate(lines):
        if line.startswith("sessions:"):
            in_sessions = True
            continue
        if in_sessions:
            if line.strip() and not line.startswith(" ") and not line.startswith("\t") and not line.startswith("-"):
                insert_idx = i
                break

    if insert_idx is None:
        insert_idx = len(lines)

    lines.insert(insert_idx, new_block.rstrip())
    return "\n".join(lines)


def main():
    if len(sys.argv) < 5:
        print("Usage: add_account.py <clipboard_file> <session_key> <proxies_file> <config_file> [name]")
        sys.exit(1)

    clipboard_file = sys.argv[1]
    session_key = sys.argv[2]
    proxies_file = sys.argv[3]
    config_file = sys.argv[4]
    account_name = sys.argv[5] if len(sys.argv) > 5 else None

    try:
        with open(clipboard_file, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except Exception as e:
        print(f"ERROR: Cannot read clipboard file: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  Clipboard: {len(text)} chars")

    info = parse_fetch(text)
    if not info:
        print("ERROR: No /completion fetch found in clipboard.")
        sys.exit(1)

    org_id = info["orgID"]
    model = info.get("model", "")
    print(f"  OrgID: {org_id}")
    if model:
        print(f"  Model in request: {model}")

    with open(config_file, "r") as f:
        content = f.read()

    existing_proxies = re.findall(r'proxy:\s*"([^"]+)"', content)
    found, existing_name, existing_country = find_session_by_orgid(content, org_id)

    if found:
        print(f"\n  Account \"{existing_name}\" (orgID {org_id}) EXISTS -> UPDATING")
        print(f"  Country locked: {existing_country}")
        proxy, country = get_next_proxy(proxies_file, [p for p in existing_proxies if p], existing_country)
        content = update_session(content, org_id, session_key, proxy, country)
        display_name = existing_name
    else:
        if not account_name:
            print("ERROR: account name is required for new accounts")
            sys.exit(1)
        print(f"\n  New account \"{account_name}\" (orgID {org_id}) -> ADDING")
        proxy, country = get_next_proxy(proxies_file, existing_proxies)
        content = add_session(content, org_id, session_key, proxy, account_name, country)
        display_name = account_name

    with open(config_file, "w") as f:
        f.write(content)

    print(f"\n  Config updated: {config_file}")
    print(f"  Name:    {display_name}")
    print(f"  OrgID:   {org_id}")
    print(f"  Country: {country}")
    print(f"  Key:     {session_key[:40]}...")
    print(f"  Proxy:   ...{proxy[-40:]}")


if __name__ == "__main__":
    main()